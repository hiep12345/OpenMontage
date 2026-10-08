import concurrent.futures
import copy
import json
from pathlib import Path

import pytest

from lib.content_novelty import NoveltyRegistry, digest, normalize_recipe, source_formula_key, validate_identity
from lib.distribution_hub import HubClient, HubError, HubHttpError


def identity(**extra):
    return {"schemaVersion": 1, "familyId": "violet-family", "variantId": "v1", "productionId": "p1", "purpose": "TEST",
            "question": "What does white do?", "takeaway": "White creates a lighter violet tint", "storyBeats": ["Pour violet", "Add white", "Compare tint"],
            "recipeKeys": ["sha256:" + "a" * 64], "templateFamily": "bucket", "applicationContext": "painting",
            "scriptHash": None, "primaryFileSha256": None, "nativeClipSha256": [], "experimentRef": "experiment-1", "parentVariantId": None, "differenceReason": None, **extra}


def snapshot(items):
    coverage = {"completeHubInventory": True, "providerHistory": "PARTIAL", "creativeHistory": "PARTIAL"}
    body = {"channelCode": "MT", "active": 1, "coverage": coverage, "items": sorted(items, key=lambda i: i["id"])}
    return {**body, "schemaVersion": 1, "revision": digest(body), "total": len(items), "nextCursor": None}


class Transport:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []
    def request(self, method, url, **kwargs):
        if url.endswith("/api/ingest/content-index/revision"):
            class LegacyResponse:
                status_code = 404
                def json(self):
                    return {}
            return LegacyResponse()
        self.calls.append((method, url, kwargs))
        assert method == "GET" and kwargs["allow_redirects"] is False
        page = self.pages.pop(0)
        class Response:
            status_code = 200
            def json(self):
                return copy.deepcopy(page)
        return Response()


def client(pages):
    return HubClient("https://hub.example", "id", "secret", transport=Transport(pages))


class CreativeTransport:
    def __init__(self):
        self.epoch = 1
        self.calls = []
        self.status = 200
        self.channel = "MT"
        self.items = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        assert method == "GET"
        stamp = digest({"epoch": self.epoch, "channel": self.channel})
        if url.endswith("/revision"):
            body = {"schemaVersion": 1, "scope": "creative", "channelCode": self.channel, "active": 1,
                    "inventoryRevision": stamp, "readCost": {"queries": 1, "rowsRead": 2}}
        else:
            assert kwargs["params"]["scope"] == "creative"
            body = snapshot(self.items)
            body["channelCode"] = self.channel
            body["coverage"]["operationalJobState"] = "NOT_INCLUDED"
            body["revision"] = digest({k: body[k] for k in ("channelCode", "active", "coverage", "items")})
            body.update(scope="creative", inventoryRevision=stamp, readCost={"queries": 6, "rowsRead": 150})
        if self.status != 200:
            body = {"code": "D1_READ_QUOTA_EXCEEDED"}
        class Response:
            status_code = self.status
            def json(inner):
                return copy.deepcopy(body)
        return Response()


def test_creative_cache_checks_live_stamp_and_reuses_complete_inventory_across_calls(tmp_path):
    transport = CreativeTransport()
    c = HubClient("https://hub.example", "id", "secret", transport=transport)
    path = tmp_path / "cache.sqlite"
    first = c.creative_index("MT", registry_path=path)
    assert len(transport.calls) == 2
    assert c.creative_index("MT", registry_path=path) == first
    assert len(transport.calls) == 3  # Warm call is only the indexed validator.
    assert c.diagnostics[-1]["d1ReadCost"] == {"queries": 1, "rowsRead": 2}
    transport.epoch += 1
    changed = c.creative_index("MT", registry_path=path)
    assert changed["inventoryRevision"] != first["inventoryRevision"] and len(transport.calls) == 5
    transport.status = 503
    with pytest.raises(HubHttpError) as error:
        c.creative_index("MT", registry_path=path)
    assert error.value.code == "D1_READ_QUOTA_EXCEEDED" and len(transport.calls) == 6


@pytest.mark.parametrize("mutation", [{"revision": "sha256:" + "f" * 64}, {"total": True}, {"scope": "operational"}, {"nextCursor": "more"}, {"items": [{"id": "x", "kind": "hub", "title": "corrupt"}]}])
def test_corrupt_creative_cache_is_rebuilt_only_after_fresh_validator(tmp_path, mutation):
    transport = CreativeTransport()
    c = HubClient("https://hub.example", "id", "secret", transport=transport)
    path = tmp_path / "cache.sqlite"
    first = c.creative_index("MT", registry_path=path)
    registry = NoveltyRegistry(path)
    try:
        registry.cache_inventory(c.origin, {**first, **mutation})
    finally:
        registry.close()
    assert c.creative_index("MT", registry_path=path) == first
    assert len(transport.calls) == 4


def test_cache_is_partitioned_by_origin_channel_and_legacy_reads_are_never_cached(tmp_path):
    path = tmp_path / "cache.sqlite"
    transport = CreativeTransport()
    c = HubClient("https://hub.example", "id", "secret", transport=transport)
    c.creative_index("MT", registry_path=path)
    other = HubClient("https://other.example", "id", "secret", transport=transport)
    other.creative_index("MT", registry_path=path)
    assert len(transport.calls) == 4
    transport.channel = "OTHER"
    other.creative_index("OTHER", registry_path=path)
    assert len(transport.calls) == 6
    legacy = client([snapshot([]), snapshot([])])
    legacy.creative_index("MT", registry_path=path)
    legacy.creative_index("MT", registry_path=path)
    assert len(legacy.transport.calls) == 2


def test_creative_pages_with_changed_or_missing_stamp_restart_once_before_any_cache_write(tmp_path):
    data = snapshot([{"id": "a", "kind": "hub", "title": "A", "identity": None},
                     {"id": "b", "kind": "external", "title": "B", "identity": None}])
    data["coverage"]["operationalJobState"] = "NOT_INCLUDED"
    data["revision"] = digest({k: data[k] for k in ("channelCode", "active", "coverage", "items")})
    data.update(scope="creative", inventoryRevision=digest("stamp-1"))
    first = {**data, "items": data["items"][:1], "nextCursor": "page2"}
    changed = {**data, "items": data["items"][1:], "inventoryRevision": digest("stamp-2")}
    c = client([first, changed, data])
    assert c.content_index("MT", scope="creative")["items"] == data["items"]
    assert len(c.transport.calls) == 3
    missing = {k: v for k, v in changed.items() if k != "inventoryRevision"}
    with pytest.raises(HubError, match="changed during pagination"):
        client([first, missing, first, missing]).content_index("MT", scope="creative")


def test_complete_pagination_scope_and_revision():
    data = snapshot([{"id": "a", "kind": "hub", "title": "A", "identity": None}, {"id": "b", "kind": "external", "title": "B", "identity": None}])
    page1, page2 = copy.deepcopy(data), copy.deepcopy(data)
    page1.update(items=data["items"][:1], nextCursor="cursor1")
    page2.update(items=data["items"][1:], nextCursor=None)
    assert client([page1, page2]).content_index("MT")["items"] == data["items"]
    for mutation in ({"channelCode": "OTHER"}, {"total": 3}, {"revision": "sha256:" + "f" * 64}, {"coverage": {"completeHubInventory": False}}):
        bad = {**data, **mutation}
        with pytest.raises(HubError):
            client([bad]).content_index("MT")
    duplicate = {**page2, "items": data["items"][:1]}
    with pytest.raises(HubError, match="Duplicate"):
        client([page1, duplicate]).content_index("MT")


def test_ratio_equivalence_ingredient_order_and_source_identity():
    a = [{"item": "Blue1005", "pigment": "PB60", "parts": "2"}, {"item": "Magenta1305", "pigment": "PR122", "parts": "5"}]
    b = [{"item": "Magenta1305", "pigment": "PR122", "parts": "2.5"}, {"item": "Blue1005", "pigment": "PB60", "parts": "1"}]
    assert normalize_recipe("GOLDEN", "Heavy Body", a) == normalize_recipe("golden", "Heavy Body", b)
    assert normalize_recipe("Other Brand", "Heavy Body", a) != normalize_recipe("GOLDEN", "Heavy Body", a)
    with pytest.raises(ValueError):
        normalize_recipe("GOLDEN", "Heavy Body", [{**a[0], "parts": "0"}])


def test_recipe_history_and_reedit_have_different_reasons_and_never_false_clear(tmp_path):
    r = NoveltyRegistry(tmp_path / "registry.sqlite")
    try:
        source = identity(productionId="old", variantId="old-v", nativeClipSha256=["sha256:" + "b" * 64])
        r.sync(snapshot([{"id": "published", "kind": "hub", "title": "Different lesson", "identity": source,
                          "distribution": [{"platform": "FACEBOOK", "publication": "VERIFIED_PUBLIC"}]}]))
        test = identity(productionId="new", variantId="new-v", parentVariantId="old-v", nativeClipSha256=source["nativeClipSha256"])
        first = r.evaluate("MT", test, "PRE_GENERATION")
        assert first["testAllowed"] and first["status"] == "REVIEW_REQUIRED"
        assert {"SOURCE_CLIP_REUSED", "DECLARED_DERIVATIVE", "RECIPE_REUSED"} <= set(first["matches"][0]["reasons"])
        assert r.evaluate("MT", test, "PRE_GENERATION")["cacheHit"]
        changed = identity(**{**test, "takeaway": "Use violet in mountain shadows"})
        assert not r.evaluate("MT", changed, "PRE_GENERATION")["cacheHit"]
        r.sync(snapshot([]))
        assert not r.evaluate("MT", test, "PRE_GENERATION")["cacheHit"]
        assert r.evaluate("MT", test, "PRE_GENERATION")["status"] != "CLEAR"
    finally:
        r.close()


def test_atomic_shared_reservation_and_unknown_submission_fencing(tmp_path):
    path = tmp_path / "shared.sqlite"
    r = NoveltyRegistry(path)
    r.close()
    def reserve(production_id):
        local = NoveltyRegistry(path)
        try:
            local.reserve("MT", identity(productionId=production_id, purpose="PRODUCTION", experimentRef=None))
            return production_id
        except ValueError as error:
            assert "ACTIVE_INTENT_CONFLICT" in str(error)
            return None
        finally:
            local.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        winners = [v for v in pool.map(reserve, ["runner-1", "runner-2"]) if v]
    assert len(winners) == 1
    r = NoveltyRegistry(path)
    try:
        r.transition(winners[0], 1, "SUBMITTED_UNKNOWN")
        with pytest.raises(ValueError, match="reconciliation"):
            r.transition(winners[0], 2, "CANCELLED")
        assert r.transition(winners[0], 2, "FINISHED", reconciled=True) == 3
        with pytest.raises(ValueError, match="Stale"):
            r.transition(winners[0], 2, "CANCELLED", reconciled=True)
        r.reserve("MT", identity(productionId="another-test", variantId="test-v2"))
        r.reserve("MT", identity(productionId="another-test-2", variantId="test-v3"))
        assert r.db.execute("SELECT count(*) FROM intents").fetchone()[0] == 3
        assert r.transition("another-test", 1, "GENERATING") == 2
        with pytest.raises(ValueError, match="reentry"):
            r.transition("another-test", 2, "GENERATING")
        with pytest.raises(ValueError, match="reconciliation"):
            r.transition("another-test", 2, "CANCELLED")
    finally:
        r.close()


def test_context_truncation_is_explicit_and_missing_snapshot_never_clear(tmp_path):
    r = NoveltyRegistry(tmp_path / "budget.sqlite")
    try:
        c = identity()
        report = r.evaluate("MT", c, "PRE_GENERATION")
        assert report["indexRevision"] == "UNAVAILABLE" and report["status"] == "REVIEW_REQUIRED"
        r.sync(snapshot([{"id": f"item-{i:02}", "kind": "hub", "title": "white violet painting " * 8, "identity": identity(productionId=f"old-{i}")} for i in range(30)]))
        report = r.evaluate("MT", c, "PRE_GENERATION", 2000)
        assert report["omittedMatches"] > 0
        assert report["contextBytes"] <= 2000
        assert len(json.dumps({"candidate": report["candidate"], "matches": report["matches"]}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()) == report["contextBytes"]
    finally:
        r.close()


def test_identity_contract_and_boolean_flags_are_strict():
    for bad in (identity(schemaVersion=True), identity(purpose="TEST", experimentRef=None), identity(recipeKeys=["random"]), identity(parentVariantId="v1")):
        with pytest.raises(ValueError):
            validate_identity(bad)
    with pytest.raises(HubError, match="reservation flag"):
        client([]).novelty("MT", identity(), reserve="false")


def test_retained_bridge_usage_only_and_authoritative_hub_fields(tmp_path):
    packet = tmp_path / "packet"
    (packet / "History").mkdir(parents=True)
    (packet / "Formulas").mkdir()
    formula = {"status": "SOURCE_VERIFIED", "formula_fingerprint": "a" * 64,
               "medium": {"brand": "GOLDEN Artist Colors", "product_line": "Heavy Body Acrylics"},
               "inputs": [{"item_number": "1005", "pigment_codes": ["PB60"], "parts": 2}]}
    (packet / "Formulas/source-verified-85.json").write_text(json.dumps({"formulas": [formula]}))
    (packet / "History/content-identities.json").write_text(json.dumps({"records": [{"content_id": "published", "title": "Old title", "legacy_status": "WITHDRAWN"}]}))
    (packet / "History/formula-usage.json").write_text(json.dumps([{"content_id": c, "formula_fingerprint": "a" * 64} for c in ["published", "usage-only"]]))
    r = NoveltyRegistry(tmp_path / "retained.sqlite")
    try:
        assert r.import_retained(packet)["retainedFacts"] == 2
        r.sync(snapshot([{"id": "published", "kind": "hub", "title": "Current Hub title", "identity": None,
                          "distribution": [{"publication": "VERIFIED_PUBLIC"}]}]))
        report = r.evaluate("MT", identity(recipeKeys=[source_formula_key(formula)]), "PRE_GENERATION")
        assert {m["id"] for m in report["matches"]} == {"published", "usage-only"}
        row = next(m for m in report["matches"] if m["id"] == "published")
        assert row["title"] == "Current Hub title" and row["legacyStatus"] == "WITHDRAWN"
        assert row["distribution"][0]["publication"] == "VERIFIED_PUBLIC"
    finally:
        r.close()


def test_recipe_list_order_cannot_bypass_reservation(tmp_path):
    r = NoveltyRegistry(tmp_path / "ordered.sqlite")
    try:
        keys = ["sha256:" + "a" * 64, "sha256:" + "b" * 64]
        r.reserve("MT", identity(purpose="PRODUCTION", recipeKeys=keys, experimentRef=None))
        with pytest.raises(ValueError, match="ACTIVE_INTENT_CONFLICT"):
            r.reserve("MT", identity(productionId="p2", purpose="PRODUCTION", recipeKeys=keys[::-1], experimentRef=None))
    finally:
        r.close()
