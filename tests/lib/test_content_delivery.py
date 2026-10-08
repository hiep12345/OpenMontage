"""No provider calls: episode planning, immutable reservations and final batches."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from lib.content_delivery import seal_plan, validate_batch, validate_plan
from lib.content_novelty import NoveltyRegistry
from lib.distribution_hub import HubClient, HubError, digest
from scripts.hub_contract_fixture import fixture
from test_content_novelty import identity


def plan_for_item(item):
    base = copy.deepcopy(item["contentIdentity"])
    base["primaryFileSha256"] = None
    return seal_plan({"schemaVersion": 1, "channelCode": item["channelCode"], "contentType": item["contentType"],
                      "identity": base, "strategy": "SHARED_ASSET", "variants": [{"variantId": item["id"],
                      "targets": item["targets"], "differenceReason": base["differenceReason"]}]})


def reserve_finished(path, plan):
    registry = NoveltyRegistry(path)
    try:
        registry.reserve(plan["channelCode"], plan["identity"], plan)
        registry.transition(plan["identity"]["productionId"], 1, "GENERATING")
        registry.transition(plan["identity"]["productionId"], 2, "FINISHED")
    finally:
        registry.close()


def episode(targets=None):
    base = identity(variantId="lesson-master", productionId="episode-1", familyId="lesson-family", purpose="PRODUCTION", experimentRef=None)
    rows = [{"variantId": "lesson-" + t, "targets": [t], "differenceReason": "Different rendered hook/CTA for " + t}
            for t in (targets or ["fb-ig", "pinterest", "tiktok", "youtube"])]
    plan = seal_plan({"schemaVersion": 1, "channelCode": "MT", "contentType": "video", "identity": base,
                      "strategy": "PLATFORM_VARIANTS", "variants": rows})
    payload = fixture("video")["payload"]
    template = payload["items"][0]
    payload["items"] = []
    for n, row in enumerate(rows):
        item = copy.deepcopy(template)
        item.update(id=row["variantId"], targets=row["targets"], manualTargets=[], assetHash="sha256:" + str(n + 1) * 64)
        manifest = item["deliveryManifest"]
        manifest.update(contentId=item["id"], productionId=base["productionId"])
        manifest["asset"]["sha256"] = item["assetHash"]
        next(f for f in manifest["files"] if f["path"] == manifest["asset"]["path"])["sha256"] = item["assetHash"]
        manifest["destinations"] = [{"target": row["targets"][0], "packageHash": None, "requiredFiles": [f["path"] for f in manifest["files"]]}]
        manifest["manifestHash"] = digest({k: v for k, v in manifest.items() if k != "manifestHash"})
        item["contentIdentity"] = {**base, "variantId": item["id"], "parentVariantId": base["variantId"],
                                   "differenceReason": row["differenceReason"], "primaryFileSha256": item["assetHash"],
                                   "scriptHash": "sha256:" + str(n + 5) * 64, "nativeClipSha256": ["sha256:" + "f" * 64]}
        payload["items"].append(item)
    return plan, payload


def reseal(plan):
    return seal_plan({k: v for k, v in plan.items() if k != "planHash"})


def test_four_actual_renders_are_one_planned_episode_without_changing_payload():
    plan, payload = episode()
    original = copy.deepcopy((plan, payload))
    result = validate_batch(payload, plan)
    assert (result["episodeCount"], result["variantCount"], result["targetCount"]) == (1, 4, 4)
    assert (plan, payload) == original


def test_shared_file_uses_one_id_with_multiple_destinations():
    payload = fixture("photo")["payload"]
    item = payload["items"][0]
    item["contentIdentity"] = identity(variantId=item["id"], productionId=item["deliveryManifest"]["productionId"], primaryFileSha256=item["assetHash"])
    plan = plan_for_item(item)
    assert validate_batch(payload, plan)["variantCount"] == 1
    assert validate_batch(payload, plan)["targetCount"] == 2


def test_unrelated_legacy_and_crl_items_can_share_one_batch():
    payload = fixture()["payload"]
    payload["items"].extend(fixture("video", "facebook")["payload"]["items"])
    assert validate_batch(payload)["targetCount"] == 3


def test_independent_facebook_and_instagram_variants_share_one_planned_episode():
    plan, payload = episode(["facebook", "instagram", "pinterest", "youtube"])
    assert validate_batch(payload, plan)["targetCount"] == 4


@pytest.mark.parametrize("target", ["facebook", "instagram"])
def test_legacy_pair_cannot_overlap_an_independent_variant(target):
    with pytest.raises(HubError, match="fb-ig overlaps"):
        episode(["fb-ig", target])


@pytest.mark.parametrize("targets", [["facebook"], ["instagram"], ["facebook", "instagram"], ["fb-ig"]])
def test_shared_meta_asset_accepts_exact_nonoverlapping_targets(targets):
    payload = fixture()["payload"]
    item = payload["items"][0]
    item.update(targets=targets, manualTargets=[])
    manifest = item["deliveryManifest"]
    manifest["destinations"] = [{**manifest["destinations"][0], "target": target} for target in targets]
    manifest["manifestHash"] = digest({k: v for k, v in manifest.items() if k != "manifestHash"})
    item["contentIdentity"] = identity(variantId=item["id"], productionId=manifest["productionId"], primaryFileSha256=item["assetHash"])
    assert validate_batch(payload, plan_for_item(item))["targetCount"] == len(targets)


@pytest.mark.parametrize("target", ["facebook", "instagram"])
@pytest.mark.parametrize("overlap_in_manifest", [True, False])
def test_alias_overlap_blocks_ingest_before_network(target, overlap_in_manifest):
    payload = fixture()["payload"]
    item = payload["items"][0]
    item.update(targets=sorted(["fb-ig", target]), manualTargets=[])
    manifest = item["deliveryManifest"]
    manifest["destinations"] = [manifest["destinations"][0]]
    if overlap_in_manifest:
        manifest["destinations"] = sorted([manifest["destinations"][0], {**manifest["destinations"][0], "target": target}], key=lambda row: row["target"])
    manifest["manifestHash"] = digest({k: v for k, v in manifest.items() if k != "manifestHash"})
    class NoTransport:
        def request(self, *args, **kwargs):
            pytest.fail("Overlapping Meta targets reached Hub")
    client = HubClient("https://hub.example", "id", "secret", transport=NoTransport())
    with pytest.raises(HubError, match="fb-ig overlaps"):
        client.ingest(payload)


@pytest.mark.parametrize("change", ["missing", "unplanned", "target", "production", "family", "parent", "reason", "lesson", "clips", "asset", "manifest-target"])
def test_packaging_drift_blocks_before_any_hub_call(change):
    plan, payload = episode()
    item = payload["items"][0]
    if change == "missing":
        payload["items"].pop()
    elif change == "unplanned":
        item["id"] = "unplanned-render"
    elif change == "target":
        item["targets"] = ["x"]
    elif change == "manifest-target":
        item["deliveryManifest"]["destinations"][0]["target"] = "x"
        item["deliveryManifest"]["manifestHash"] = digest({k: v for k, v in item["deliveryManifest"].items() if k != "manifestHash"})
    else:
        key = {"production": "productionId", "family": "familyId", "parent": "parentVariantId", "reason": "differenceReason",
               "lesson": "takeaway", "clips": "nativeClipSha256", "asset": "primaryFileSha256"}[change]
        item["contentIdentity"][key] = ["sha256:" + "a" * 64] if change == "clips" else "sha256:" + "a" * 64 if change == "asset" else "other-value"
    class NoTransport:
        def request(self, *args, **kwargs):
            pytest.fail("Invalid batch reached Hub")
    client = HubClient("https://hub.example", "id", "secret", transport=NoTransport())
    with pytest.raises(HubError):
        client.ingest(payload, delivery_plan=plan)


def test_identical_files_cannot_masquerade_as_four_render_variants():
    plan, payload = episode()
    first, second = payload["items"][:2]
    second["assetHash"] = first["assetHash"]
    second["contentIdentity"]["primaryFileSha256"] = first["assetHash"]
    manifest = second["deliveryManifest"]
    manifest["asset"]["sha256"] = first["assetHash"]
    next(f for f in manifest["files"] if f["path"] == manifest["asset"]["path"])["sha256"] = first["assetHash"]
    manifest["manifestHash"] = digest({k: v for k, v in manifest.items() if k != "manifestHash"})
    with pytest.raises(HubError, match="Identical renders"):
        validate_batch(payload, plan)


def test_plan_must_be_sealed_early_and_destinations_cannot_overlap():
    plan, _ = episode()
    changed = copy.deepcopy(plan)
    changed["variants"][0]["differenceReason"] = "changed"
    with pytest.raises(HubError, match="hash mismatch"):
        validate_plan(changed)
    changed = copy.deepcopy(plan)
    changed["variants"][1]["targets"] = changed["variants"][0]["targets"]
    with pytest.raises(HubError, match="Repeated"):
        reseal(changed)
    changed = copy.deepcopy(plan)
    changed["identity"]["primaryFileSha256"] = "sha256:" + "a" * 64
    with pytest.raises(HubError, match="precede"):
        reseal(changed)


@pytest.mark.parametrize("change", ["reason", "unicode-reason", "production", "variant", "content-type"])
def test_preflight_rejects_plans_that_cannot_become_valid_final_packages(change):
    plan, _ = episode()
    if change == "reason":
        plan["variants"][0]["differenceReason"] = "x" * 301
    elif change == "unicode-reason":
        plan["variants"][0]["differenceReason"] = "🎨" * 151
    elif change == "production":
        plan["identity"]["productionId"] = "Invalid Production"
    elif change == "variant":
        plan["variants"][0]["variantId"] = "UPPERCASE"
    else:
        plan["contentType"] = []
    with pytest.raises(HubError):
        reseal(plan)


def test_missing_plan_blocks_mt_generation_before_index_read():
    class NoTransport:
        def request(self, *args, **kwargs):
            pytest.fail("Missing plan reached Hub")
    client = HubClient("https://hub.example", "id", "secret", transport=NoTransport())
    with pytest.raises(HubError, match="sealed delivery plan"):
        client.novelty("MT", identity(), reserve=True)


def test_maintained_reservation_saves_plan_from_pre_generation_report(tmp_path):
    from test_content_novelty import client, snapshot
    plan, _ = episode()
    path = tmp_path / "registry.sqlite"
    result = client([snapshot([])]).novelty("MT", plan["identity"], reserve=True, registry_path=path, delivery_plan=plan)
    assert result["intent"]["deliveryPlanHash"] == plan["planHash"]
    registry = NoveltyRegistry(path)
    try:
        row = registry.db.execute("SELECT plan_hash,body FROM delivery_plans").fetchone()
        assert row[0] == plan["planHash"] and json.loads(row[1]) == plan
    finally:
        registry.close()


def test_valid_batch_without_reserved_finished_plan_never_reaches_hub(tmp_path):
    plan, payload = episode()
    class NoTransport:
        def request(self, *args, **kwargs):
            pytest.fail("Unreserved production reached Hub")
    client = HubClient("https://hub.example", "id", "secret", transport=NoTransport())
    with pytest.raises(HubError, match="reserved plan"):
        client.ingest(payload, delivery_plan=plan, novelty_registry=tmp_path / "absent.sqlite")


def test_cli_validates_plan_before_loading_credentials(monkeypatch, tmp_path):
    import scripts.content_novelty as command
    path = tmp_path / "identity.json"
    path.write_text(json.dumps(identity()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["content_novelty", "check", "--identity", str(path), "--reserve"])
    monkeypatch.setattr(command, "configured_client", lambda: pytest.fail("Missing plan loaded credentials"))
    with pytest.raises(HubError, match="sealed delivery plan"):
        command.main()


def test_reserved_plan_is_immutable_and_requires_finished_intent(tmp_path):
    plan, _ = episode()
    registry = NoveltyRegistry(tmp_path / "registry.sqlite")
    try:
        result = registry.reserve("MT", plan["identity"], plan)
        assert result["deliveryPlanHash"] == plan["planHash"]
        assert registry.reserve("MT", plan["identity"], plan) == result
        changed = copy.deepcopy(plan)
        changed["variants"][0]["differenceReason"] = "new render direction"
        changed = reseal(changed)
        with pytest.raises(ValueError, match="cannot be replaced"):
            registry.reserve("MT", plan["identity"], changed)
        with pytest.raises(ValueError, match="finished"):
            registry.verify_delivery_plan(plan)
        registry.transition("episode-1", 1, "GENERATING")
        registry.transition("episode-1", 2, "FINISHED")
        assert registry.verify_delivery_plan(plan) == plan["planHash"]
        with pytest.raises(ValueError):
            registry.verify_delivery_plan(changed)
    finally:
        registry.close()


def test_historical_intent_cannot_be_retroactively_given_a_plan(tmp_path):
    plan, _ = episode()
    registry = NoveltyRegistry(tmp_path / "old.sqlite")
    try:
        registry.reserve("MT", plan["identity"])
        registry.transition("episode-1", 1, "GENERATING")
        with pytest.raises(ValueError, match="after generation"):
            registry.reserve("MT", plan["identity"], plan)
        assert registry.db.execute("SELECT count(*) FROM delivery_plans").fetchone()[0] == 0
        assert registry.db.execute("SELECT state,version FROM intents").fetchone() == ("GENERATING", 2)
    finally:
        registry.close()


def test_separate_episodes_can_share_one_batch_without_false_grouping():
    a, payload = episode()
    b, other = episode()
    b["identity"].update(productionId="episode-2", variantId="another-master", familyId="another-family")
    for row, item in zip(b["variants"], other["items"]):
        row["variantId"] += "-2"
        item["id"] = row["variantId"]
        item["contentIdentity"].update(productionId="episode-2", variantId=item["id"], parentVariantId="another-master", familyId="another-family")
        item["deliveryManifest"].update(productionId="episode-2", contentId=item["id"])
        item["deliveryManifest"]["manifestHash"] = digest({k: v for k, v in item["deliveryManifest"].items() if k != "manifestHash"})
    payload["items"].extend(other["items"])
    assert validate_batch(payload, [a, reseal(b)])["episodeCount"] == 2


def test_offline_cli_needs_no_hub_credentials(tmp_path):
    plan, payload = episode()
    path, body = tmp_path / "plan.json", tmp_path / "payload.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    body.write_text(json.dumps(payload), encoding="utf-8")
    script = Path(__file__).resolve().parents[2] / "scripts/content_delivery.py"
    result = subprocess.run([sys.executable, str(script), "check", "--plan", str(path), "--payload", str(body)], capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout)["episodeCount"] == 1
