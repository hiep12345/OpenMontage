"""Local production scope must not manufacture or acquire Hub delivery authority."""
import concurrent.futures
import json
import sqlite3
import sys

import pytest

from lib.content_novelty import NoveltyRegistry
from lib.distribution_hub import HubClient, HubError
from test_content_delivery import episode
from test_content_novelty import client, identity, snapshot


def test_local_only_cli_retains_live_novelty_and_shared_intent(monkeypatch, tmp_path, capsys):
    import scripts.content_novelty as command
    candidate = identity(purpose="PRODUCTION", experimentRef=None)
    identity_file = tmp_path / "identity.json"
    identity_file.write_text(json.dumps(candidate), encoding="utf-8")
    path = tmp_path / "registry.sqlite"
    hub = client([snapshot([])])
    monkeypatch.setattr(command, "configured_client", lambda: hub)
    monkeypatch.setattr(sys, "argv", ["content_novelty", "check", "--identity", str(identity_file),
                                    "--registry", str(path), "--reserve", "--local-only"])
    command.main()
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "REVIEW_REQUIRED" and report["coverage"]["completeHubInventory"]
    assert report["intent"]["deliveryScope"] == "LOCAL_ONLY"
    assert "deliveryPlanHash" not in report["intent"] and hub.transport.calls
    registry = NoveltyRegistry(path)
    try:
        assert registry.db.execute("SELECT count(*) FROM delivery_plans").fetchone()[0] == 0
        assert registry.reserve("MT", candidate, local_only=True) == report["intent"]
        assert registry.transition(candidate["productionId"], 1, "GENERATING") == 2
        with pytest.raises(ValueError, match="reentry"):
            registry.transition(candidate["productionId"], 2, "GENERATING")
    finally:
        registry.close()


@pytest.mark.parametrize("change", [{"local_only": "true"}, {"reserve": False}, {"channel": "OTHER"},
                                  {"stage": "PRE_DELIVERY"}, {"delivery_plan": {}}])
def test_invalid_local_scope_fails_before_hub_reads(change):
    arguments = {"channel": "MT", "identity": identity(), "reserve": True, "local_only": True, **change}
    with pytest.raises(HubError):
        client([]).novelty(**arguments)


def test_invalid_cli_scope_never_loads_credentials(monkeypatch, tmp_path):
    import scripts.content_novelty as command
    p = tmp_path / "identity.json"
    p.write_text(json.dumps(identity()), encoding="utf-8")
    monkeypatch.setattr(command, "configured_client", lambda: pytest.fail("Invalid scope loaded credentials"))
    monkeypatch.setattr(sys, "argv", ["content_novelty", "check", "--identity", str(p), "--local-only"])
    with pytest.raises(HubError, match="Local-only"):
        command.main()


def test_local_scope_cannot_be_promoted_or_historical_scope_relabelled(tmp_path):
    plan, _ = episode()
    r = NoveltyRegistry(tmp_path / "scope.sqlite")
    try:
        original = r.reserve("MT", plan["identity"], local_only=True)
        with pytest.raises(ValueError, match="scope cannot be changed"):
            r.reserve("MT", plan["identity"], plan)
        with pytest.raises(ValueError, match="Invalid local-only"):
            r.reserve("MT", plan["identity"], plan, local_only=True)
        assert r.db.execute("SELECT count(*) FROM delivery_plans").fetchone()[0] == 0
        r.transition(original["productionId"], 1, "GENERATING")
        r.transition(original["productionId"], 2, "FINISHED")
        with pytest.raises(ValueError, match="Local-only production"):
            r.verify_delivery_plan(plan)
        historical = identity(productionId="historical")
        r.reserve("MT", historical)
        before = r.db.execute("SELECT * FROM intents WHERE production_id='historical'").fetchone()
        with pytest.raises(ValueError, match="scope cannot be changed"):
            r.reserve("MT", historical, local_only=True)
        assert r.db.execute("SELECT * FROM intents WHERE production_id='historical'").fetchone() == before
        assert r.db.execute("SELECT count(*) FROM local_only_intents").fetchone()[0] == 1
    finally:
        r.close()


def test_local_and_hub_bound_runners_share_story_fencing(tmp_path):
    path = tmp_path / "shared.sqlite"
    NoveltyRegistry(path).close()
    def reserve(local_only):
        r = NoveltyRegistry(path)
        try:
            candidate = identity(productionId="runner-1" if local_only else "runner-2", variantId="variant-1", purpose="PRODUCTION", experimentRef=None)
            if local_only:
                r.reserve("MT", candidate, local_only=True)
            else:
                from lib.content_delivery import seal_plan
                plan = seal_plan({"schemaVersion": 1, "channelCode": "MT", "contentType": "video",
                                  "identity": candidate, "strategy": "SHARED_ASSET",
                                  "variants": [{"variantId": candidate["variantId"], "targets": ["youtube"], "differenceReason": None}]})
                r.reserve("MT", candidate, plan)
            return True
        except ValueError as error:
            assert "ACTIVE_INTENT_CONFLICT" in str(error)
            return False
        finally:
            r.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(reserve, [True, False])) == 1


def test_persistent_guard_blocks_older_clients_plan_insert(tmp_path):
    plan, _ = episode()
    path = tmp_path / "mixed-version.sqlite"
    r = NoveltyRegistry(path)
    r.reserve("MT", plan["identity"], local_only=True)
    r.close()
    with sqlite3.connect(path) as older_client:
        with pytest.raises(sqlite3.IntegrityError, match="LOCAL_ONLY_DELIVERY_FORBIDDEN"):
            older_client.execute("INSERT INTO delivery_plans VALUES(?,?,?,?)",
                                 (plan["identity"]["productionId"], "MT", plan["planHash"], json.dumps(plan)))
        assert older_client.execute("SELECT count(*) FROM delivery_plans").fetchone()[0] == 0


def test_local_only_cannot_enter_legacy_ingest_without_identity_or_plan(tmp_path):
    plan, payload = episode()
    path = tmp_path / "scope.sqlite"
    r = NoveltyRegistry(path)
    r.reserve("MT", plan["identity"], local_only=True)
    r.close()
    for item in payload["items"]:
        item.pop("contentIdentity")
    class NoTransport:
        def request(self, *args, **kwargs):
            pytest.fail("Local-only legacy ingest reached Hub")
    hub = HubClient("https://hub.example", "id", "secret", transport=NoTransport())
    with pytest.raises(HubError, match="local-only"):
        hub.ingest(payload, novelty_registry=path)


def test_unmarked_historical_legacy_ingest_does_not_create_a_registry(tmp_path):
    _, payload = episode()
    for item in payload["items"]:
        item.pop("contentIdentity")
    path = tmp_path / "absent.sqlite"
    assert client([])._validate_ingest(payload, novelty_registry=path)["planHashes"] == []
    assert not path.exists()
