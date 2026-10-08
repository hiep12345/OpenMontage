"""Offline episode/variant contract. It selects no creative work or destinations."""
from __future__ import annotations

import copy
import re

from lib.content_novelty import validate_identity
from lib.distribution_hub import HubError, TARGETS, _require, digest, require_disjoint_meta_targets, validate_manifest

PLAN_FIELDS = {"schemaVersion", "channelCode", "contentType", "identity", "strategy", "variants"}
# Final renders may change these fields, but must preserve the planned lesson.
RENDER_FIELDS = {"variantId", "parentVariantId", "differenceReason", "scriptHash",
                 "primaryFileSha256", "nativeClipSha256"}


def _identity(value):
    try:
        return validate_identity(value)
    except (KeyError, TypeError, ValueError):
        raise HubError("Invalid delivery creative identity") from None


def _targets(values, *, canonical=True):
    _require(isinstance(values, list) and values and all(isinstance(v, str) for v in values) and
             len(values) == len(set(values)) and (not canonical or values == sorted(values)) and
             set(values) <= TARGETS, "Invalid planned destinations")
    require_disjoint_meta_targets(values)
    return set(values)


def _plan_body(plan):
    _require(isinstance(plan, dict) and set(plan) == PLAN_FIELDS and type(plan["schemaVersion"]) is int and
             plan["schemaVersion"] == 1, "Invalid delivery plan")
    _require(isinstance(plan["channelCode"], str) and re.fullmatch(r"[A-Z][A-Z0-9_-]{1,15}", plan["channelCode"]) and
             isinstance(plan["contentType"], str) and plan["contentType"] in {"photo", "video"}, "Invalid planned source")
    base = _identity(plan["identity"])
    _require(re.fullmatch(r"[a-z0-9][a-z0-9._:-]{2,179}", base["productionId"]), "Invalid planned manifest production ID")
    _require(base["primaryFileSha256"] is None, "Delivery plan must precede final rendering")
    rows = plan["variants"]
    _require(isinstance(rows, list) and 0 < len(rows) <= len(TARGETS), "Invalid planned variants")
    ids, targets = set(), set()
    for row in rows:
        _require(isinstance(row, dict) and set(row) == {"variantId", "targets", "differenceReason"} and
                 isinstance(row["variantId"], str) and re.fullmatch(r"[a-z0-9][a-z0-9._:-]{2,179}", row["variantId"]),
                 "Invalid planned variant")
        selected = _targets(row["targets"])
        _require(row["variantId"] not in ids and not targets.intersection(selected), "Repeated variant or episode destination")
        ids.add(row["variantId"])
        targets.update(selected)
    require_disjoint_meta_targets(targets)
    if plan["strategy"] == "SHARED_ASSET":
        _require(len(rows) == 1 and rows[0]["variantId"] == base["variantId"] and
                 rows[0]["differenceReason"] == base["differenceReason"], "Shared asset must retain one content identity")
    elif plan["strategy"] == "PLATFORM_VARIANTS":
        _require(len(rows) > 1 and base["variantId"] not in ids and all(
            isinstance(r["differenceReason"], str) and r["differenceReason"].strip() for r in rows),
            "Platform renders require distinct variants and planned reasons")
    else:
        raise HubError("Invalid delivery strategy")
    for row in rows:
        parent = base["variantId"] if plan["strategy"] == "PLATFORM_VARIANTS" else base["parentVariantId"]
        _identity({**base, "variantId": row["variantId"], "parentVariantId": parent, "differenceReason": row["differenceReason"]})
    return plan


def seal_plan(plan):
    """Seal an unsigned proposal plan without modifying the caller's artifact."""
    body = copy.deepcopy(_plan_body(plan))
    return {**body, "planHash": digest(body)}


def validate_plan(plan, *, channel=None, identity=None):
    _require(isinstance(plan, dict) and set(plan) == PLAN_FIELDS | {"planHash"}, "Missing sealed delivery plan")
    body = _plan_body({k: v for k, v in plan.items() if k != "planHash"})
    _require(plan["planHash"] == digest(body), "Delivery plan hash mismatch")
    if channel is not None:
        _require(channel == plan["channelCode"], "Delivery plan channel mismatch")
    if identity is not None:
        _require(_identity(identity) == plan["identity"], "Pre-generation identity differs from delivery plan")
    return plan


def validate_batch(payload, delivery_plan=None):
    """Check the whole sealed batch before any Hub reads or writes."""
    _require(isinstance(payload, dict) and isinstance(payload.get("items"), list) and
             0 < len(payload["items"]) <= 100 and all(isinstance(i, dict) for i in payload["items"]), "Invalid delivery batch")
    items = payload["items"]
    _require(all(isinstance(i.get("id"), str) for i in items) and len({i["id"] for i in items}) == len(items),
             "Duplicate ingest identity")
    for item in items:
        try:
            manifest = validate_manifest(item.get("deliveryManifest"), {**item, "contentId": item["id"]})
            selected = _targets(item.get("targets"), canonical=False)
            _require(selected == {d["target"] for d in manifest["destinations"]}, "Manifest destinations differ from selected jobs")
            if "contentIdentity" in item:
                identity = _identity(item["contentIdentity"])
                _require(identity["variantId"] == item["id"] and identity["productionId"] == manifest["productionId"] and
                         identity["primaryFileSha256"] == item["assetHash"], "Creative identity differs from exact packaged source")
        except (KeyError, TypeError):
            raise HubError("Invalid packaged source") from None
    plans = [] if delivery_plan is None else delivery_plan if isinstance(delivery_plan, list) else [delivery_plan]
    _require(isinstance(plans, list) and len(plans) <= 100, "Invalid delivery plans")
    covered, productions = set(), set()
    for plan in plans:
        validate_plan(plan)
        base = plan["identity"]
        key = (plan["channelCode"], base["productionId"])
        _require(key not in productions, "Repeated episode plan")
        productions.add(key)
        wanted = {r["variantId"]: r for r in plan["variants"]}
        actual = {i["id"]: i for i in items if i.get("channelCode") == key[0] and
                  i.get("contentIdentity", {}).get("productionId") == key[1]}
        _require(set(actual) == set(wanted), "Delivery batch differs from complete planned episode")
        hashes, native_clips = set(), None
        for content_id, row in wanted.items():
            item = actual[content_id]
            identity = item["contentIdentity"]
            _require(item["contentType"] == plan["contentType"] and set(item["targets"]) == set(row["targets"]) and
                     all(identity[k] == base[k] for k in base.keys() - RENDER_FIELDS), "Packaged variant differs from planned lesson or destinations")
            parent = base["variantId"] if plan["strategy"] == "PLATFORM_VARIANTS" else base["parentVariantId"]
            _require(identity["parentVariantId"] == parent and identity["differenceReason"] == row["differenceReason"],
                     "Packaged variant lost planned episode lineage")
            clips = identity["nativeClipSha256"]
            _require(native_clips is None or native_clips == clips, "Episode variants must retain the same native clips")
            native_clips = clips
            hashes.add(item["assetHash"])
        _require(plan["strategy"] != "PLATFORM_VARIANTS" or len(hashes) == len(wanted),
                 "Identical renders must use one shared content identity")
        covered.update(actual)
    _require(all(i["id"] in covered for i in items if i.get("channelCode") == "MT" and "contentIdentity" in i),
             "MT identity ingest requires its reserved delivery plan")
    return {"planHashes": [p["planHash"] for p in plans], "episodeCount": len(plans),
            "variantCount": len(covered), "targetCount": sum(len(i["targets"]) for i in items)}
