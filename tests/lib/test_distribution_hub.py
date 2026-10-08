"""No sockets: adversarial exact-evidence and resumed byte transport tests."""
import copy
import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.distribution_hub import (CHUNK_BYTES, HubClient, HubError, bytes_digest,
                                 canonical_json, describe_file, digest, safe_path, verify_handoff)
from scripts.hub_contract_fixture import fixture


def seal(row, key="evidenceHash"):
    row[key] = digest({k: v for k, v in row.items() if k != key})
    return row


def handoff(item):
    source = {key: item[key] for key in ("channelCode", "contentType", "driveFileId", "sourceRevision",
              "sourceUpdatedAt", "assetHash", "qaReceiptHash", "distributionRevision")}
    source.update(contentId=item["id"], payloadHash="a" * 64, xPackageHash=None,
                  tiktokPackageHash=None, facebookInstagramPackageHash=None)
    source_hash = digest(source)
    profile = seal({"schemaVersion": 1, "channel": {"code": "MT", "active": True, "version": 1},
                    "assignments": []}, "profileRevision")
    jobs = [{"platformCode": t, "jobId": item["id"] + ":" + t, "version": 1,
             "state": "READY", "manualOnly": t in item.get("manualTargets", [])} for t in item["targets"]]
    manifest = item["deliveryManifest"]
    rows = [{"jobId": j["jobId"], "platformCode": j["platformCode"], "version": 1,
             "verification": "VERIFIED", "errorCode": None, "delivery": {"version": 1,
                 "binding": digest({"id": j["jobId"]}), "manifestHash": manifest["manifestHash"],
                 "assetHash": item["assetHash"], "qaReceiptHash": item["qaReceiptHash"],
                 "distributionRevision": item["distributionRevision"], "packageHash": None,
                 "files": copy.deepcopy(manifest["files"])}} for j in jobs]
    return {"schemaVersion": 1, "profile": profile, "source": source, "sourceRecordHash": source_hash,
            "deliveryManifest": copy.deepcopy(manifest), "jobs": jobs,
            "packageEvidence": seal({"schemaVersion": 2, "contentId": item["id"], "assetHash": item["assetHash"],
                                     "sourceRecordHash": source_hash, "packages": {}}),
            "jobDeliveryEvidence": seal({"schemaVersion": 1, "contentId": item["id"], "sourceRecordHash": source_hash, "jobs": rows}),
            "publicationEvidence": seal({"schemaVersion": 1, "contentId": item["id"], "sourceRecordHash": source_hash,
                                         "publicPublication": "NOT_ASSERTED", "events": []})}


class Response:
    status_code = 200

    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return copy.deepcopy(self.body)


class Transport:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.descriptors, self.chunks, self.calls = {}, set(), []
        self.lose = set()
        self.after_write = None

    def request(self, method, url, **kwargs):
        if url.endswith("/api/ingest/content-index/revision"):
            return Response({}, status=404)  # Explicitly exercise compatibility with the legacy Hub.
        self.calls.append((method, url, kwargs))
        assert kwargs["allow_redirects"] is False
        if url.endswith("/api/ingest/handoff"):
            return Response(self.snapshot)
        if url.endswith("/api/ingest"):
            if method == "POST" and "POST_INGEST" in self.lose:
                self.lose.remove("POST_INGEST")
                raise requests.Timeout("secret detail never emitted")
            return Response({"created": 1})
        query = kwargs["params"]
        delivery = next(r["delivery"] for r in self.snapshot["jobDeliveryEvidence"]["jobs"] if r["platformCode"] == query["target"])
        if "path" not in query:
            return Response({"contentId": self.snapshot["source"]["contentId"], "target": query["target"],
                             "binding": delivery["binding"], "manifestHash": delivery["manifestHash"], "files": delivery["files"]})
        path = query["path"]
        if method == "POST":
            self.descriptors[path] = json.loads(kwargs["data"])
        elif method == "PUT":
            index = query["chunkIndex"]
            assert bytes_digest(kwargs["data"]) == self.descriptors[path]["chunks"][index]
            self.chunks.add((path, index))
            if self.after_write:
                self.after_write(path, index)
        if method in self.lose:
            self.lose.remove(method)
            raise requests.Timeout("secret detail never emitted")
        d = self.descriptors.get(path)
        missing = [i for i in range(len(d["chunks"])) if (path, i) not in self.chunks] if d else None
        return Response({"binding": delivery["binding"], "descriptor": d, "missingChunks": missing,
                         "ready": missing == []})


def setup(content_type="photo"):
    data = fixture(content_type)
    item = data["payload"]["items"][0]
    transport = Transport(handoff(item))
    client = HubClient("https://hub.example", "id", "secret", transport=transport)
    return data, item, transport, client


@pytest.mark.parametrize("reviewed,normalized", [
    ("2026-10-07T22:07:02.123456+07:00", "2026-10-07T15:07:02.123Z"),
    ("2026-10-07T15:07:02.123999Z", "2026-10-07T15:07:02.123Z"),
    ("2026-10-07T15:07:02Z", "2026-10-07T15:07:02.000Z"),
])
def test_ingest_accepts_hub_normalized_timestamp_without_rewriting_request(reviewed, normalized):
    data, item, transport, client = setup()
    item["sourceUpdatedAt"] = reviewed
    actual = copy.deepcopy(item)
    actual["sourceUpdatedAt"] = normalized
    transport.snapshot = handoff(actual)
    original = copy.deepcopy(data["payload"])
    result = client.ingest(data["payload"])
    assert result["handoffs"][0]["source"]["sourceUpdatedAt"] == normalized
    posts = [kw for method, url, kw in transport.calls if method == "POST" and url.endswith("/api/ingest")]
    assert len(posts) == 1 and json.loads(posts[0]["data"]) == original and data["payload"] == original


def test_legacy_ingest_replays_unsorted_targets_without_rewriting_payload():
    data, item, transport, client = setup()
    item["targets"].reverse()
    original = copy.deepcopy(data["payload"])
    transport.snapshot = handoff(item)
    client.ingest(data["payload"])
    client.ingest(data["payload"])
    posts = [kw for method, url, kw in transport.calls if method == "POST" and url.endswith("/api/ingest")]
    assert len(posts) == 2 and all(json.loads(p["data"]) == original for p in posts)
    assert data["payload"] == original


def test_timestamp_normalization_preserves_instant_and_full_source_hash_checks():
    data, item, _, _ = setup()
    item["sourceUpdatedAt"] = "2026-10-07T22:07:02.123456+07:00"
    actual = copy.deepcopy(item)
    actual["sourceUpdatedAt"] = "2026-10-07T15:07:02.124Z"
    with pytest.raises(HubError, match="Reviewed source mismatch"):
        verify_handoff(handoff(actual), "MT", item["id"], item)
    snapshot = handoff(item)
    snapshot["source"]["sourceUpdatedAt"] = "2026-10-07T15:07:02.123Z"
    with pytest.raises(HubError):
        verify_handoff(snapshot, "MT", item["id"], item)


@pytest.mark.parametrize("value", ["2026-10-07T22:07:02", "2026-13-07T00:00:00Z", "secret", None])
def test_invalid_reviewed_timestamp_remains_fail_closed(value):
    _, item, _, _ = setup()
    snapshot = handoff(item)
    item["sourceUpdatedAt"] = value
    with pytest.raises(HubError, match="timestamp"):
        verify_handoff(snapshot, "MT", item["id"], item)


class IdentityTransport(Transport):
    def __init__(self, item):
        super().__init__(handoff(item))
        self.item = item
        self.index_available = True
        self.accept_identity = True
        self.accepted = False
    def request(self, method, url, **kwargs):
        if url.endswith("/api/ingest/content-index"):
            self.calls.append((method, url, kwargs))
            if not self.index_available:
                return Response({}, status=503)
            card = {"id": self.item["id"], "kind": "hub", "title": self.item["title"],
                    "sourceRevision": self.item["sourceRevision"],
                    "identity": self.item["contentIdentity"] if self.accepted and self.accept_identity else None,
                    "identityHash": digest(self.item["contentIdentity"]) if self.accepted and self.accept_identity else None}
            body = {"channelCode": "MT", "active": 1, "coverage": {"completeHubInventory": True}, "items": [card]}
            return Response({**body, "schemaVersion": 1, "revision": digest(body), "total": 1, "nextCursor": None})
        if method == "POST" and url.endswith("/api/ingest"):
            self.accepted = True
        return super().request(method, url, **kwargs)


def identity_setup():
    from test_content_novelty import identity
    data = fixture("photo")
    item = data["payload"]["items"][0]
    item["contentIdentity"] = identity(variantId=item["id"], productionId=item["deliveryManifest"]["productionId"],
                                       primaryFileSha256=item["deliveryManifest"]["asset"]["sha256"])
    transport = IdentityTransport(item)
    return data, item, transport, HubClient("https://hub.example", "id", "secret", transport=transport)


def test_identity_ingest_and_byte_delivery_refresh_and_verify_source(tmp_path):
    from test_content_delivery import plan_for_item, reserve_finished
    data, item, transport, client = identity_setup()
    registry = tmp_path / "shared.sqlite"
    plan = plan_for_item(item)
    reserve_finished(registry, plan)
    result = client.ingest(data["payload"], novelty_registry=registry, delivery_plan=plan)
    assert result["noveltyChecks"][0]["stage"] == "PRE_DELIVERY"
    assert transport.calls[0][0] == "GET" and transport.calls[1][0] == "POST"
    write_files(tmp_path, data)
    delivered = client.deliver("MT", item["id"], "fb-ig", tmp_path, item, novelty_registry=registry)
    assert delivered["ready"] and delivered["noveltyCheck"]["status"] == "REVIEW_REQUIRED"


def test_four_variant_batch_shares_one_preflight_and_one_post_ingest_snapshot(tmp_path):
    from test_content_delivery import episode, reserve_finished
    from test_content_novelty import CreativeTransport, snapshot
    plan, payload = episode()
    class BatchTransport(CreativeTransport):
        def request(self, method, url, **kwargs):
            if url.endswith("/api/ingest") and method == "POST":
                self.calls.append((method, url, kwargs))
                assert json.loads(kwargs["data"]) == payload
                self.epoch += 1
                self.items = [{"id": i["id"], "kind": "hub", "title": i["title"], "identity": i["contentIdentity"],
                               "identityHash": digest(i["contentIdentity"]), "sourceRevision": i["sourceRevision"]}
                              for i in payload["items"]]
                return Response({"created": 4})
            if url.endswith("/api/ingest/handoff"):
                self.calls.append((method, url, kwargs))
                item = next(i for i in payload["items"] if i["id"] == kwargs["params"]["contentId"])
                return Response(handoff(item))
            return super().request(method, url, **kwargs)
    registry = tmp_path / "batch.sqlite"
    reserve_finished(registry, plan)
    transport = BatchTransport()
    c = HubClient("https://hub.example", "id", "secret", transport=transport)
    result = c.ingest(payload, novelty_registry=registry, delivery_plan=plan)
    assert len(result["handoffs"]) == len(result["noveltyChecks"]) == 4
    assert len([u for _, u, _ in transport.calls if u.endswith("/content-index")]) == 2
    assert len([u for _, u, _ in transport.calls if u.endswith("/revision")]) == 2
    assert len([u for m, u, _ in transport.calls if m == "POST"]) == 1
    assert result["publicPublication"] == "NOT_ASSERTED"


def test_delivery_uses_selected_registry_and_one_verified_inventory(tmp_path, monkeypatch):
    from test_content_delivery import plan_for_item, reserve_finished
    import lib.content_novelty as novelty
    data, item, _, _ = identity_setup()
    class CachedIdentityTransport(IdentityTransport):
        def request(self, method, url, **kwargs):
            stamp = digest("accepted-inventory")
            if url.endswith("/revision"):
                self.calls.append((method, url, kwargs))
                return Response({"schemaVersion": 1, "scope": "creative", "channelCode": "MT", "active": 1, "inventoryRevision": stamp})
            response = super().request(method, url, **kwargs)
            if url.endswith("/content-index") and kwargs["params"].get("scope") == "creative":
                body = response.json()
                body["coverage"]["operationalJobState"] = "NOT_INCLUDED"
                body["revision"] = digest({k: body[k] for k in ("channelCode", "active", "coverage", "items")})
                body.update(scope="creative", inventoryRevision=stamp)
                return Response(body)
            return response
    transport = CachedIdentityTransport(item)
    transport.accepted = True
    c = HubClient("https://hub.example", "id", "secret", transport=transport)
    registry = tmp_path / "selected.sqlite"
    reserve_finished(registry, plan_for_item(item))
    def forbidden_default():
        raise AssertionError("Selected registry must never open the default registry")
    monkeypatch.setattr(novelty, "default_registry", forbidden_default)
    write_files(tmp_path, data)
    assert c.deliver("MT", item["id"], "fb-ig", tmp_path, item, novelty_registry=registry)["ready"]
    assert len([u for _, u, _ in transport.calls if u.endswith("/content-index")]) == 1
    transport.calls.clear()
    assert c.deliver("MT", item["id"], "fb-ig", tmp_path, item, novelty_registry=registry)["ready"]
    assert len([u for _, u, _ in transport.calls if u.endswith("/content-index")]) == 0
    assert len([u for _, u, _ in transport.calls if u.endswith("/revision")]) == 1


def test_missing_index_blocks_identity_ingest_before_any_write(tmp_path):
    from test_content_delivery import plan_for_item, reserve_finished
    data, item, transport, client = identity_setup()
    transport.index_available = False
    plan = plan_for_item(item)
    reserve_finished(tmp_path / "missing.sqlite", plan)
    with pytest.raises(HubError):
        client.ingest(data["payload"], novelty_registry=tmp_path / "missing.sqlite", delivery_plan=plan)
    assert all(m == "GET" for m, _, _ in transport.calls)


def test_identity_readback_mismatch_is_not_success_and_blocks_media_write(tmp_path):
    from test_content_delivery import plan_for_item, reserve_finished
    data, item, transport, client = identity_setup()
    transport.accept_identity = False
    registry = tmp_path / "wrong.sqlite"
    plan = plan_for_item(item)
    reserve_finished(registry, plan)
    with pytest.raises(HubError, match="accepted source"):
        client.ingest(data["payload"], novelty_registry=registry, delivery_plan=plan)
    assert len([m for m, u, _ in transport.calls if m == "POST" and u.endswith('/api/ingest')]) == 1
    transport.calls.clear()
    with pytest.raises(HubError, match="accepted source"):
        client.deliver("MT", item["id"], "fb-ig", tmp_path, item, novelty_registry=registry)
    assert all(m == "GET" for m, _, _ in transport.calls)


@pytest.mark.parametrize("operation", ["novelty", "ingest"])
def test_quota_during_real_creative_preflight_survives_to_report(tmp_path, monkeypatch, operation):
    from test_content_delivery import plan_for_item, reserve_finished
    from tools.publishers.distribution_hub import DistributionHub
    data, item, transport, client = identity_setup()
    plan = plan_for_item(item)
    registry = tmp_path / "shared.sqlite"
    reserve_finished(registry, plan)
    calls = []
    def quota(method, url, **kwargs):
        calls.append((method, url))
        return Response({"code": "D1_READ_QUOTA_EXCEEDED", "error": "private quota body"}, 503)
    transport.request = quota
    monkeypatch.setattr(DistributionHub, "_client", staticmethod(lambda: client))
    result = DistributionHub().execute({"operation": operation, "channel": "MT", "identity": item["contentIdentity"],
                                       "stage": "PRE_DELIVERY", "payload": data["payload"],
                                       **({"delivery_plan": plan} if operation == "ingest" else {}),
                                       "registry_path": str(registry), "project_dir": str(tmp_path)})
    report = json.loads(Path(result.data["reportPath"]).read_text(encoding="utf-8"))
    assert not result.success and report["errorCode"] == "D1_READ_QUOTA_EXCEEDED"
    assert report["httpStatus"] == 503 and report["nextAction"] == "WAIT_FOR_QUOTA_RESET"
    assert report["requests"][0]["errorCode"] == report["errorCode"]
    assert report["failedStep"]["route"] == "/api/ingest/content-index/revision"
    assert len(calls) == 1 and calls[0][0] == "GET"


def test_coded_index_page_conflict_restarts_once_and_never_retries_other_conflicts():
    from test_content_novelty import snapshot
    body = snapshot([])
    _, _, transport, client = setup()
    responses = [Response({"code": "CONTENT_INDEX_CHANGED"}, 409), Response(body)]
    transport.request = lambda *a, **kw: responses.pop(0)
    assert client.content_index("MT")["items"] == [] and not responses
    responses = [Response({"code": "CONTENT_INDEX_CHANGED"}, 409)] * 2
    with pytest.raises(HubError, match="CONTENT_INDEX_CHANGED"):
        client.content_index("MT")
    assert not responses
    responses = [Response({"code": "CONTENT_INDEX_TOO_LARGE"}, 409), Response(body)]
    with pytest.raises(HubError, match="CONTENT_INDEX_TOO_LARGE"):
        client.content_index("MT")
    assert len(responses) == 1


def write_files(root, data):
    import base64
    for file in data["files"]:
        path = root / file["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(file["base64"]))


@pytest.mark.parametrize("kind", ["photo", "video"])
def test_complete_exact_delivery_and_resume(tmp_path, kind):
    data, item, transport, client = setup(kind)
    write_files(tmp_path, data)
    assert not client.readiness("MT", item["id"], "fb-ig", item)["ready"]
    first = client.deliver("MT", item["id"], "fb-ig", tmp_path, item)
    assert first["ready"] and first["uploadedChunks"] == 3
    assert first["publicPublication"] == "NOT_ASSERTED"
    before = copy.deepcopy(transport.snapshot)
    transport.calls.clear()
    second = client.deliver("MT", item["id"], "pinterest", tmp_path, item)
    assert second["ready"] and second["uploadedChunks"] == 0
    assert second["job"]["manualOnly"]
    assert all(m == "GET" for m, _, _ in transport.calls)
    assert before == transport.snapshot


@pytest.mark.parametrize("lost", ["POST", "PUT"])
def test_lost_response_inspects_without_retransmitting(tmp_path, lost):
    data, item, transport, client = setup()
    write_files(tmp_path, data)
    transport.lose.add(lost)
    assert client.deliver("MT", item["id"], "fb-ig", tmp_path, item)["ready"]
    assert len([m for m, _, _ in transport.calls if m == "PUT"]) == 3


@pytest.mark.parametrize("metadata", [{}, {"title": "New reviewed title"}, {"qaScore": 8.5}, {"producedAt": "2026-02-01T00:00:00.000Z"}])
def test_unknown_ingest_stops_even_if_preexisting_handoff_matches_selected_fields(metadata):
    data, item, transport, client = setup()
    transport.lose.add("POST_INGEST")
    item.update(metadata)
    with pytest.raises(HubError, match="Hub transport failed"):
        client.ingest(data["payload"])
    call = transport.calls[0][2]
    assert call["headers"]["Idempotency-Key"] == data["payload"]["idempotencyKey"]
    assert len(transport.calls) == 1


def test_fractional_qa_request_and_ecmascript_number_evidence():
    data, item, transport, client = setup()
    item["qaScore"] = 8.5
    client.ingest(data["payload"])
    assert json.loads(transport.calls[0][2]["data"])["items"][0]["qaScore"] == 8.5
    for value, expected in [(8.5, "8.5"), (9.0, "9"), (-0.0, "0"), (1e-6, "0.000001"),
                            (1.234e-5, "0.00001234"), (1e-7, "1e-7"), (1e21, "1e+21")]:
        assert canonical_json(value) == expected
    for invalid in [float("nan"), float("inf"), -float("inf")]:
        with pytest.raises(HubError, match="Nonfinite"):
            canonical_json({"qaScore": invalid})


@pytest.mark.parametrize("bad", ["source", "job_version", "files", "manual", "manifest", "evidence", "duplicate"])
def test_tampering_rejected_even_with_resealed_evidence(bad):
    _, item, transport, _ = setup()
    snapshot = transport.snapshot
    row = snapshot["jobDeliveryEvidence"]["jobs"][0]
    if bad == "source": snapshot["source"]["driveFileId"] = "changed"
    if bad == "job_version": row["version"] += 1
    if bad == "files": row["delivery"]["files"][0]["sizeBytes"] += 1
    if bad == "manual": snapshot["jobs"][1]["manualOnly"] = False
    if bad == "manifest": snapshot["deliveryManifest"]["archiveHash"] = "sha256:" + "0" * 64
    if bad == "evidence": snapshot["packageEvidence"]["evidenceHash"] = "sha256:" + "0" * 64
    if bad == "duplicate": snapshot["jobDeliveryEvidence"]["jobs"][1] = copy.deepcopy(row)
    if bad in {"job_version", "files", "duplicate"}: seal(snapshot["jobDeliveryEvidence"])
    with pytest.raises(HubError): verify_handoff(snapshot, "MT", item["id"], item)


@pytest.mark.parametrize("path", ["/absolute", "../escape", "a/../b", "a\\b", "C:/b", "a//b", "a/\x00b"])
def test_safe_paths(path):
    with pytest.raises(HubError): safe_path(path)


def test_bad_local_caption_prevents_any_write(tmp_path):
    data, item, transport, client = setup()
    write_files(tmp_path, data)
    (tmp_path / "metadata/caption.txt").write_bytes(b"altered")
    with pytest.raises(HubError, match="Local file hash"):
        client.deliver("MT", item["id"], "fb-ig", tmp_path, item)
    assert all(m == "GET" for m, _, _ in transport.calls)


def test_change_after_hash_prevents_chunk_send(tmp_path):
    data, item, transport, client = setup()
    write_files(tmp_path, data)
    original = transport.request
    def change_on_register(method, url, **kwargs):
        result = original(method, url, **kwargs)
        if method == "POST": (tmp_path / kwargs["params"]["path"]).write_bytes(b"changed after hashing")
        return result
    transport.request = change_on_register
    with pytest.raises(HubError, match="changed during delivery"):
        client.deliver("MT", item["id"], "fb-ig", tmp_path, item)
    assert not transport.chunks


def test_chunk_boundary_partial_resume(tmp_path):
    data, item, transport, client = setup("video")
    write_files(tmp_path, data)
    video = tmp_path / "media/source.mp4"
    video.write_bytes(b"a" * CHUNK_BYTES + b"last")
    file = item["deliveryManifest"]["asset"]
    file.update(sha256=bytes_digest(video.read_bytes()), sizeBytes=video.stat().st_size)
    item["assetHash"] = file["sha256"]
    seal(item["deliveryManifest"], "manifestHash")
    transport.snapshot = handoff(item)
    transport.descriptors[file["path"]] = describe_file(video, file)
    transport.chunks.add((file["path"], 0))
    result = client.deliver("MT", item["id"], "fb-ig", tmp_path, item)
    video_puts = [c for c in transport.calls if c[0] == "PUT" and c[2]["params"]["path"] == file["path"]]
    assert result["ready"] and len(video_puts) == 1
    assert video_puts[0][2]["params"]["chunkIndex"] == 1 and video_puts[0][2]["data"] == b"last"


def test_final_job_change_rejects_completion(tmp_path):
    data, item, transport, client = setup()
    write_files(tmp_path, data)
    def change(*_):
        transport.snapshot["jobs"][0]["state"] = "CLAIMED"
    transport.after_write = change
    with pytest.raises(HubError, match="changed during delivery"):
        client.deliver("MT", item["id"], "fb-ig", tmp_path, item)


@pytest.mark.parametrize("origin", ["http://hub.example", "https://user:secret@hub.example", "https://hub.example/path", "https://hub.example?x=1"])
def test_unsafe_origin(origin):
    with pytest.raises(HubError): HubClient(origin, "id", "secret")


def test_loopback_requires_explicit_opt_in():
    with pytest.raises(HubError): HubClient("http://127.0.0.1:1234", "id", "secret")
    HubClient("http://127.0.0.1:1234", "id", "secret", allow_insecure_loopback=True)


def test_redirect_and_manual_denial_never_mutate():
    _, item, transport, client = setup()
    transport.request = lambda *a, **kw: Response({"error": "secret content"}, 403)
    with pytest.raises(HubError, match="^Hub HTTP 403$"): client.readiness("MT", item["id"], "pinterest", item)
    transport.request = lambda *a, **kw: Response({"error": "secret content"}, 302)
    with pytest.raises(HubError, match="^Hub HTTP 302$"): client.inspect("MT", item["id"])


@pytest.mark.parametrize("status,code", [(409, "HANDOFF_JOB_STALE"), (409, "HANDOFF_PACKAGE_REQUIRED"),
                                        (503, "D1_READ_QUOTA_EXCEEDED")])
def test_public_error_codes_survive_without_response_text(status, code):
    _, item, transport, client = setup()
    transport.request = lambda *a, **kw: Response({"code": code, "error": "private body"}, status)
    with pytest.raises(HubError) as raised:
        client.inspect("MT", item["id"])
    assert raised.value.code == code and raised.value.status == status
    assert str(raised.value) == f"Hub HTTP {status} [{code}]"
    assert "private body" not in str(client.diagnostics)


@pytest.mark.parametrize("body", [{"code": "SECRET_TOKEN", "error": "private"}, [], None, {"code": []}])
def test_unknown_error_body_is_not_a_diagnostic(body):
    _, item, transport, client = setup()
    transport.request = lambda *a, **kw: Response(body, 403)
    with pytest.raises(HubError, match="^Hub HTTP 403$") as raised:
        client.inspect("MT", item["id"])
    assert raised.value.code is None


def test_server_error_and_invalid_success_leave_mutation_outcome_unknown():
    _, _, transport, client = setup()
    transport.request = lambda *a, **kw: Response({"code": "UNEXPECTED_ERROR"}, 500)
    with pytest.raises(HubError) as raised:
        client._request("POST", "/api/ingest", body={"schemaVersion": 2})
    assert raised.value.outcome_unknown
    class InvalidResponse:
        status_code = 200
        def json(self):
            raise ValueError("private response")
    transport.request = lambda *a, **kw: InvalidResponse()
    with pytest.raises(HubError) as raised:
        client._request("POST", "/api/ingest", body={"schemaVersion": 2})
    assert raised.value.outcome_unknown and "private" not in str(raised.value)
    for body in (None, [], "private body"):
        transport.request = lambda *a, **kw: Response(body)
        with pytest.raises(HubError) as raised:
            client._request("POST", "/api/ingest", body={"schemaVersion": 2})
        assert raised.value.outcome_unknown and "private" not in str(raised.value)


@pytest.mark.parametrize("bad", ["duplicate", "negative", "out_of_range", "ready_lie", "chunk_hash"])
def test_invalid_descriptor_or_missing_indices_block_writes(tmp_path, bad):
    data, item, transport, client = setup()
    write_files(tmp_path, data)
    file = item["deliveryManifest"]["files"][0]
    transport.descriptors[file["path"]] = describe_file(tmp_path / file["path"], file)
    original = transport.request
    def corrupt(method, url, **kwargs):
        result = original(method, url, **kwargs)
        if method == "GET" and kwargs.get("params", {}).get("path") == file["path"]:
            if bad == "duplicate": result.body["missingChunks"] = [0, 0]
            if bad == "negative": result.body["missingChunks"] = [-1]
            if bad == "out_of_range": result.body["missingChunks"] = [1]
            if bad == "ready_lie": result.body["ready"] = True
            if bad == "chunk_hash": result.body["descriptor"]["chunks"] = ["sha256:" + "0" * 64]
        return result
    transport.request = corrupt
    with pytest.raises(HubError): client.deliver("MT", item["id"], "fb-ig", tmp_path, item)
    assert all(m == "GET" for m, _, _ in transport.calls)


def test_source_complete_hash_includes_unknown_additive_fields():
    _, item, transport, _ = setup()
    transport.snapshot["source"]["futurePackageHash"] = "sha256:" + "b" * 64
    with pytest.raises(HubError, match="Source record hash mismatch"):
        verify_handoff(transport.snapshot, "MT", item["id"], item)


def test_unconfirmed_timeout_stops_before_next_chunk(tmp_path):
    data, item, transport, client = setup()
    write_files(tmp_path, data)
    original = transport.request
    puts = []
    def lose_without_store(method, url, **kwargs):
        if method == "PUT":
            puts.append(kwargs["params"])
            raise requests.Timeout("private transport exception")
        return original(method, url, **kwargs)
    transport.request = lose_without_store
    with pytest.raises(HubError, match="Chunk send not confirmed"):
        client.deliver("MT", item["id"], "fb-ig", tmp_path, item)
    assert len(puts) == 1 and not transport.chunks


def test_symlink_rejection_without_os_privilege(tmp_path, monkeypatch):
    data, item, transport, client = setup()
    write_files(tmp_path, data)
    actual = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda p: p.name == "caption.txt" or actual(p))
    with pytest.raises(HubError, match="Symlink media"):
        client.deliver("MT", item["id"], "fb-ig", tmp_path, item)
    assert all(m == "GET" for m, _, _ in transport.calls)


def test_synthetic_archive_hash_binds_actual_zip_members():
    import base64
    import io
    import zipfile
    data = fixture("video")
    archive_bytes = base64.b64decode(data["archive"]["base64"])
    assert bytes_digest(archive_bytes) == data["payload"]["items"][0]["deliveryManifest"]["archiveHash"]
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        assert archive.namelist() == [f["path"] for f in data["files"]]
        for file in data["files"]:
            assert archive.read(file["path"]) == base64.b64decode(file["base64"])


def test_symlink_escape_rejected(tmp_path):
    data, item, transport, client = setup()
    write_files(tmp_path, data)
    path = tmp_path / "metadata/caption.txt"
    original = path.read_bytes()
    outside = tmp_path.parent / (tmp_path.name + "-caption")
    outside.write_bytes(original)
    path.unlink()
    try: path.symlink_to(outside)
    except OSError: pytest.skip("OS symlink privilege unavailable")
    with pytest.raises(HubError): client.deliver("MT", item["id"], "fb-ig", tmp_path, item)
    assert all(m == "GET" for m, _, _ in transport.calls)
