"""No sockets: adversarial exact-evidence and resumed byte transport tests."""
import copy
import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.distribution_hub import (CHUNK_BYTES, HubClient, HubError, bytes_digest,
                                 describe_file, digest, safe_path, verify_handoff)
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


def test_ingest_timeout_readback_and_bound_header():
    data, item, transport, client = setup()
    transport.lose.add("POST_INGEST")
    result = client.ingest(data["payload"])
    assert result["recoveredByReadback"] and result["receipt"] is None
    call = transport.calls[0][2]
    assert call["headers"]["Idempotency-Key"] == data["payload"]["idempotencyKey"]
    assert result["handoffs"][0]["source"]["contentId"] == item["id"]


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
