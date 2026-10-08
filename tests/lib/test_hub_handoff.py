"""Exercise interruption boundaries through the real client and local byte transport."""
import base64
import copy
import json

import pytest

from lib.distribution_hub import HubError, HubClient
from lib.hub_handoff import CONTRACT, _locked, handoff
from test_distribution_hub import Response, Transport, setup


class HandoffTransport(Transport):
    def request(self, method, url, **kwargs):
        if method == "GET" and url.endswith("/api/ingest"):
            self.calls.append((method, url, kwargs))
            return Response({"ready": True, "contract": CONTRACT})
        return super().request(method, url, **kwargs)


def prepared(tmp_path, kind="photo"):
    data, item, original, _ = setup(kind)
    transport = HandoffTransport(original.snapshot)
    client = HubClient("https://hub.example", "private-id", "private-secret", transport=transport)
    root = tmp_path / "files"
    for file in data["files"]:
        path = root / file["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(file["base64"]))
    return data, item, transport, client, root, tmp_path / "checkpoint.json"


def posts(transport):
    return [kw for method, url, kw in transport.calls if method == "POST" and url.endswith("/api/ingest")]


@pytest.mark.parametrize("kind", ["photo", "video"])
def test_full_handoff_and_completed_resume_never_reingest_or_resend_bytes(tmp_path, kind):
    data, item, transport, client, root, checkpoint = prepared(tmp_path, kind)
    result = handoff(client, data["payload"], root, checkpoint)
    assert result["ready"] and result["publicPublication"] == "NOT_ASSERTED"
    assert {r["target"] for r in result["readiness"]} == set(item["targets"])
    writes = [(m, u, kw) for m, u, kw in transport.calls if m in {"PUT", "POST"}]
    resumed = handoff(client, data["payload"], root, checkpoint)
    assert resumed["ready"] and all(r["uploadedChunks"] == 0 for r in resumed["deliveries"])
    assert [(m, u, kw) for m, u, kw in transport.calls if m in {"PUT", "POST"}] == writes
    assert len(posts(transport)) == 1
    text = checkpoint.read_text()
    assert all(private not in text for private in ["private-id", "private-secret", item["title"], item["driveUrl"], data["payload"]["idempotencyKey"]])


def test_whole_batch_local_failure_stops_before_network(tmp_path):
    data, _, transport, client, root, checkpoint = prepared(tmp_path)
    (root / data["files"][-1]["path"]).write_bytes(b"wrong")
    with pytest.raises(HubError, match="hash or size"):
        handoff(client, data["payload"], root, checkpoint)
    assert not transport.calls and not checkpoint.exists()


def test_unsupported_contract_stops_before_metadata(tmp_path):
    data, _, transport, client, root, checkpoint = prepared(tmp_path)
    original = transport.request
    def request(method, url, **kwargs):
        if method == "GET" and url.endswith("/api/ingest"):
            return Response({"ready": True, "contract": {**CONTRACT, "ingestSchemaVersion": 3}})
        return original(method, url, **kwargs)
    transport.request = request
    with pytest.raises(HubError) as caught:
        handoff(client, data["payload"], root, checkpoint)
    assert caught.value.code == "HANDOFF_PROTOCOL_UNSUPPORTED" and not posts(transport)


def test_unknown_metadata_cannot_resume_without_explicit_exact_request_reconciliation(tmp_path):
    data, _, transport, client, root, checkpoint = prepared(tmp_path)
    transport.lose.add("POST_INGEST")
    with pytest.raises(HubError):
        handoff(client, data["payload"], root, checkpoint)
    assert json.loads(checkpoint.read_text())["state"] == "METADATA_UNKNOWN"
    calls = len(transport.calls)
    with pytest.raises(HubError) as caught:
        handoff(client, data["payload"], root, checkpoint)
    assert caught.value.code == "HANDOFF_METADATA_UNCERTAIN" and len(transport.calls) == calls
    result = handoff(client, data["payload"], root, checkpoint, reconcile_metadata=True)
    assert result["ready"] and len(posts(transport)) == 2
    assert posts(transport)[0]["data"] == posts(transport)[1]["data"]
    assert posts(transport)[0]["headers"]["Idempotency-Key"] == posts(transport)[1]["headers"]["Idempotency-Key"]


def test_positive_metadata_checkpoint_survives_readback_failure(tmp_path, monkeypatch):
    data, _, transport, client, root, checkpoint = prepared(tmp_path)
    original = client.inspect
    monkeypatch.setattr(client, "inspect", lambda *a: (_ for _ in ()).throw(HubError("Readback unavailable")))
    with pytest.raises(HubError, match="Readback"):
        handoff(client, data["payload"], root, checkpoint)
    assert json.loads(checkpoint.read_text())["state"] == "METADATA_ACCEPTED"
    monkeypatch.setattr(client, "inspect", original)
    assert handoff(client, data["payload"], root, checkpoint)["ready"]
    assert len(posts(transport)) == 1


def test_process_exit_during_send_leaves_durable_unknown_checkpoint(tmp_path, monkeypatch):
    data, _, transport, client, root, checkpoint = prepared(tmp_path)
    original = transport.request
    def exit_on_send(method, url, **kwargs):
        if method == "POST" and url.endswith("/api/ingest"):
            assert json.loads(checkpoint.read_text())["state"] == "METADATA_UNKNOWN"
            raise SystemExit()
        return original(method, url, **kwargs)
    monkeypatch.setattr(transport, "request", exit_on_send)
    with pytest.raises(SystemExit):
        handoff(client, data["payload"], root, checkpoint)
    with pytest.raises(HubError) as caught:
        handoff(client, data["payload"], root, checkpoint)
    assert caught.value.code == "HANDOFF_METADATA_UNCERTAIN"


def test_failed_pre_send_persistence_and_concurrent_execution_never_send(tmp_path, monkeypatch):
    import lib.hub_handoff as module
    data, _, transport, client, root, checkpoint = prepared(tmp_path)
    original = module._write
    monkeypatch.setattr(module, "_write", lambda *a: (_ for _ in ()).throw(OSError("Unavailable disk")))
    with pytest.raises(OSError):
        handoff(client, data["payload"], root, checkpoint)
    assert not posts(transport)
    monkeypatch.setattr(module, "_write", original)
    with _locked(checkpoint):
        with pytest.raises(HubError) as caught:
            handoff(client, data["payload"], root, checkpoint)
        assert caught.value.code == "HANDOFF_CHECKPOINT_BUSY"
    assert handoff(client, data["payload"], root, checkpoint)["ready"]


@pytest.mark.parametrize("change", ["body", "actor", "origin", "corrupt"])
def test_resume_binding_conflicts_stop_before_network(tmp_path, change):
    data, _, transport, client, root, checkpoint = prepared(tmp_path)
    handoff(client, data["payload"], root, checkpoint)
    if change == "body":
        data["payload"]["items"][0]["title"] = "changed"
    elif change == "actor":
        client._headers["CF-Access-Client-Id"] = "different-id"
    elif change == "origin":
        client.origin = "https://other.example"
    else:
        checkpoint.write_text('{}')
    count = len(transport.calls)
    with pytest.raises(HubError) as caught:
        handoff(client, data["payload"], root, checkpoint)
    assert caught.value.code == "HANDOFF_CHECKPOINT_CONFLICT" and len(transport.calls) == count


def test_selected_job_changed_since_checkpoint_blocks_media_mutation(tmp_path):
    from test_distribution_hub import seal
    data, _, transport, client, root, checkpoint = prepared(tmp_path)
    handoff(client, data["payload"], root, checkpoint)
    transport.snapshot["jobs"][0]["version"] += 1
    row = transport.snapshot["jobDeliveryEvidence"]["jobs"][0]
    row["version"] += 1
    row["delivery"]["version"] += 1
    seal(transport.snapshot["jobDeliveryEvidence"])
    count = len(transport.calls)
    with pytest.raises(HubError) as caught:
        handoff(client, data["payload"], root, checkpoint)
    assert caught.value.code == "HANDOFF_JOB_STALE"
    assert all(m == "GET" for m, _, _ in transport.calls[count:])


def test_known_metadata_rejection_can_retry_after_auth_fix_without_unknown_label(tmp_path, monkeypatch):
    data, _, transport, client, root, checkpoint = prepared(tmp_path)
    original = transport.request
    def denied(method, url, **kwargs):
        if method == "POST" and url.endswith("/api/ingest"):
            return Response({"code": "FORBIDDEN"}, status=403)
        return original(method, url, **kwargs)
    monkeypatch.setattr(transport, "request", denied)
    with pytest.raises(HubError):
        handoff(client, data["payload"], root, checkpoint)
    assert json.loads(checkpoint.read_text())["state"] == "PREPARED"
    monkeypatch.setattr(transport, "request", original)
    assert handoff(client, data["payload"], root, checkpoint)["ready"]


@pytest.mark.parametrize("status", [403, 409])
def test_failed_explicit_reconciliation_preserves_original_uncertainty(tmp_path, monkeypatch, status):
    data, _, transport, client, root, checkpoint = prepared(tmp_path)
    transport.lose.add("POST_INGEST")
    with pytest.raises(HubError):
        handoff(client, data["payload"], root, checkpoint)
    original = transport.request
    def rejected(method, url, **kwargs):
        if method == "POST" and url.endswith("/api/ingest"):
            return Response({"code": "FORBIDDEN"}, status=status)
        return original(method, url, **kwargs)
    monkeypatch.setattr(transport, "request", rejected)
    with pytest.raises(HubError):
        handoff(client, data["payload"], root, checkpoint, reconcile_metadata=True)
    assert json.loads(checkpoint.read_text())["state"] == "METADATA_UNKNOWN"
    monkeypatch.setattr(transport, "request", original)
    count = len(transport.calls)
    with pytest.raises(HubError) as caught:
        handoff(client, data["payload"], root, checkpoint)
    assert caught.value.code == "HANDOFF_METADATA_UNCERTAIN" and len(transport.calls) == count


def test_failed_positive_receipt_persistence_cannot_disguise_uncertainty(tmp_path, monkeypatch):
    import lib.hub_handoff as module
    data, _, transport, client, root, checkpoint = prepared(tmp_path)
    original = module._write
    def failed(path, record):
        if record["state"] == "METADATA_ACCEPTED":
            raise OSError("Disk unavailable")
        original(path, record)
    monkeypatch.setattr(module, "_write", failed)
    with pytest.raises(HubError) as caught:
        handoff(client, data["payload"], root, checkpoint)
    assert caught.value.code == "HANDOFF_METADATA_UNCERTAIN"
    assert json.loads(checkpoint.read_text())["state"] == "METADATA_UNKNOWN"
    monkeypatch.setattr(module, "_write", original)
    with pytest.raises(HubError) as caught:
        handoff(client, data["payload"], root, checkpoint)
    assert caught.value.code == "HANDOFF_METADATA_UNCERTAIN" and len(posts(transport)) == 1


def test_partial_media_server_failure_resumes_only_missing_chunks(tmp_path, monkeypatch):
    data, _, transport, client, root, checkpoint = prepared(tmp_path)
    original = transport.request
    failed = False
    def request(method, url, **kwargs):
        nonlocal failed
        result = original(method, url, **kwargs)
        if method == "PUT" and not failed:
            failed = True
            return Response({}, status=503)  # Bytes committed, response outcome unclear.
        return result
    monkeypatch.setattr(transport, "request", request)
    with pytest.raises(HubError):
        handoff(client, data["payload"], root, checkpoint)
    assert json.loads(checkpoint.read_text())["state"] == "BOUND"
    assert handoff(client, data["payload"], root, checkpoint)["ready"]
    puts = [(kw["params"]["path"], kw["params"]["chunkIndex"]) for m, _, kw in transport.calls if m == "PUT"]
    assert len(puts) == len(set(puts)) == len(data["files"]) and len(posts(transport)) == 1


def test_unrelated_job_update_during_selected_delivery_is_not_a_false_failure(tmp_path):
    from test_distribution_hub import seal
    data, item, transport, client, root, _ = prepared(tmp_path)
    changed = False
    def update_other_job(path, index):
        nonlocal changed
        if changed:
            return
        changed = True
        job = next(j for j in transport.snapshot["jobs"] if j["platformCode"] == "pinterest")
        job.update(version=2, state="CLAIMED")
        row = next(r for r in transport.snapshot["jobDeliveryEvidence"]["jobs"] if r["platformCode"] == "pinterest")
        row["version"] = row["delivery"]["version"] = 2
        seal(transport.snapshot["jobDeliveryEvidence"])
    transport.after_write = update_other_job
    assert client.deliver("MT", item["id"], "fb-ig", root, item)["ready"] and changed


def test_batch_separate_roots_and_second_item_failure_are_checked_before_first_post(tmp_path):
    photo, pitem, ptransport, _, proot, checkpoint = prepared(tmp_path / "photo", "photo")
    video, vitem, vtransport, _, vroot, _ = prepared(tmp_path / "video", "video")
    payload = {**photo["payload"], "items": [pitem, vitem]}
    calls = []
    ptransport.calls = vtransport.calls = calls
    class BatchTransport:
        def request(self, method, url, **kwargs):
            if url.endswith("/api/ingest"):
                calls.append((method, url, kwargs))
                return Response({"ready": True, "contract": CONTRACT} if method == "GET" else {"created": 2})
            query = kwargs["params"]
            transport = ptransport if query["contentId"] == pitem["id"] else vtransport
            return transport.request(method, url, **kwargs)
    client = HubClient("https://hub.example", "private-id", "private-secret", transport=BatchTransport())
    roots = {pitem["id"]: proot, vitem["id"]: vroot}
    member = vroot / video["files"][-1]["path"]
    original = member.read_bytes()
    member.write_bytes(b"broken")
    with pytest.raises(HubError):
        handoff(client, payload, None, checkpoint, roots=roots)
    assert not calls
    member.write_bytes(original)
    result = handoff(client, payload, None, checkpoint, roots=roots)
    assert result["ready"] and len(result["readiness"]) == 4
    assert {r["contentId"] for r in result["readiness"]} == {pitem["id"], vitem["id"]}
    assert len([m for m, u, _ in calls if m == "POST" and u.endswith("/api/ingest")]) == 1
