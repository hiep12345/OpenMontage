"""One explicit reviewed handoff, with local durable evidence and no publisher."""
from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

from lib.distribution_hub import CHUNK_BYTES, HubError, _local_file, canonical_json, describe_file, digest

CONTRACT = {"schemaVersion": 1, "ingestSchemaVersion": 2, "deliveryManifestVersion": 1,
            "mediaDescriptorVersion": 1, "chunkSizeBytes": CHUNK_BYTES}


def _fail(message, code):
    error = HubError(message)
    error.code = code
    error.outcome_unknown = code == "HANDOFF_METADATA_UNCERTAIN"
    raise error


@contextmanager
def _locked(path):
    """OS lock releases on process death; an old lock file is harmless."""
    lock = path.with_suffix(path.suffix + ".lock")
    if lock.is_symlink():
        _fail("Unsafe handoff checkpoint lock", "HANDOFF_CHECKPOINT_CONFLICT")
    with lock.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            _fail("Another execution owns this handoff", "HANDOFF_CHECKPOINT_BUSY")
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _write(path, value):
    # No request body, caption, credential or upload URL enters this record.
    sealed = {**value, "checkpointHash": digest(value)}
    temporary = path.with_name(path.name + "." + str(uuid.uuid4()) + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(sealed, stream, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load(path, fingerprint):
    if not path.exists():
        return {"schemaVersion": 1, "fingerprint": fingerprint, "state": "PREPARED", "bindings": []}
    try:
        if path.is_symlink() or path.stat().st_size > 1024 * 1024:
            raise ValueError()
        record = json.loads(path.read_text(encoding="utf-8"))
        seal = record.pop("checkpointHash")
        if (record.get("schemaVersion") != 1 or record.get("fingerprint") != fingerprint or
                digest(record) != seal or record.get("state") not in
                {"PREPARED", "METADATA_UNKNOWN", "METADATA_ACCEPTED", "BOUND", "COMPLETE"} or
                not isinstance(record.get("bindings"), list)):
            raise ValueError()
        return record
    except (OSError, ValueError, KeyError, TypeError):
        _fail("Handoff checkpoint differs from the exact reviewed request", "HANDOFF_CHECKPOINT_CONFLICT")


def _bindings(snapshot, item):
    rows = []
    for target in sorted(item["targets"]):
        job = next(j for j in snapshot["jobs"] if j["platformCode"] == target)
        delivery = next(r for r in snapshot["jobDeliveryEvidence"]["jobs"] if r["platformCode"] == target)["delivery"]
        rows.append({"channel": item["channelCode"], "contentId": item["id"], "target": target,
                     "sourceRecordHash": snapshot["sourceRecordHash"], "binding": delivery["binding"],
                     "job": {k: job[k] for k in ("jobId", "platformCode", "version", "state", "manualOnly")}})
    return rows


def handoff(client, payload, root, checkpoint_path, *, roots=None, delivery_plan=None,
            registry_path=None, reconcile_metadata=False):
    """Resume accepted metadata; an unknown send needs explicit exact-key reconciliation."""
    if type(reconcile_metadata) is not bool:
        raise HubError("Invalid metadata reconciliation choice")
    # Freeze the exact canonical body before validation, checkpoints and sending.
    payload = json.loads(canonical_json(payload))
    delivery_plan = json.loads(canonical_json(delivery_plan))
    client._validate_ingest(payload, novelty_registry=registry_path, delivery_plan=delivery_plan, _caption_freshness=False)
    items = payload["items"]
    if roots is not None and (not isinstance(roots, dict) or set(roots) != {i["id"] for i in items}):
        raise HubError("Local roots must cover the exact reviewed batch")
    local_roots = {}
    for item in items:
        selected_root = Path(roots[item["id"]] if roots is not None else root).resolve(strict=True)
        local_roots[item["id"]] = selected_root
        # Validate the whole batch, including caption/receipt members, before network.
        for file in item["deliveryManifest"]["files"]:
            describe_file(_local_file(selected_root, file), file)
        from lib.caption_links import validate_qa
        # Accepted checkpoint resumes are byte verification and readback;
        # HubClient checks freshness before any possibly new metadata POST.
        validate_qa(item, selected_root, freshness=False)
    path = Path(checkpoint_path)
    if path.is_symlink():
        _fail("Unsafe handoff checkpoint", "HANDOFF_CHECKPOINT_CONFLICT")
    path.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = digest({"origin": client.origin, "actorHash": digest(client._headers["CF-Access-Client-Id"]),
                          "payloadHash": digest(payload), "deliveryPlanHash": digest(delivery_plan)})
    with _locked(path):
        record = _load(path, fingerprint)
        if record["state"] == "METADATA_UNKNOWN" and not reconcile_metadata:
            _fail("Metadata outcome is unknown; reconcile the exact reviewed body and permanent key",
                  "HANDOFF_METADATA_UNCERTAIN")
        # Always check the live protocol, including on a completed resume.
        readiness = client._request("GET", "/api/ingest")
        contract = readiness.get("contract")
        if (readiness.get("ready") is not True or not isinstance(contract, dict) or
                any(type(contract.get(k)) is not int or contract[k] != v for k, v in CONTRACT.items())):
            _fail("Hub handoff contract is unsupported; update the client before delivery", "HANDOFF_PROTOCOL_UNSUPPORTED")
        if record["state"] in {"PREPARED", "METADATA_UNKNOWN"}:
            reconciling_unknown = record["state"] == "METADATA_UNKNOWN"
            def before_send():
                record["state"] = "METADATA_UNKNOWN"
                _write(path, record)  # Failure blocks the POST; crash leaves uncertainty.

            def on_receipt(receipt):
                record.update(state="METADATA_ACCEPTED", receiptHash=digest(receipt))
                try:
                    _write(path, record)  # Before readback, index refresh or media activity.
                except OSError:
                    _fail("Metadata response received but acceptance could not be persisted; reconcile exact request",
                          "HANDOFF_METADATA_UNCERTAIN")

            try:
                client.ingest(payload, novelty_registry=registry_path, delivery_plan=delivery_plan,
                              _before_send=before_send, _on_receipt=on_receipt)
            except HubError as error:
                step = getattr(error, "request_step", {})
                if (not reconciling_unknown and record["state"] == "METADATA_UNKNOWN" and step.get("method") == "POST" and
                        step.get("route") == "/api/ingest" and step.get("outcome") == "HTTP_ERROR" and
                        400 <= getattr(error, "status", 0) < 500):
                    record["state"] = "PREPARED"
                    _write(path, record)
                raise
        snapshots = [client.inspect(i["channelCode"], i["id"], i) for i in items]
        current = [row for snapshot, item in zip(snapshots, items) for row in _bindings(snapshot, item)]
        if record["state"] in {"BOUND", "COMPLETE"} and current != record["bindings"]:
            _fail("Selected job or file binding changed since handoff checkpoint", "HANDOFF_JOB_STALE")
        record.update(state="BOUND", bindings=current)
        _write(path, record)
        delivered = []
        for item in items:
            for target in sorted(item["targets"]):
                pinned = next(r for r in current if r["contentId"] == item["id"] and r["target"] == target)
                delivered.append(client.deliver(item["channelCode"], item["id"], target, local_roots[item["id"]], item,
                                                novelty_registry=registry_path, expected_job=pinned["job"],
                                                expected_binding=pinned["binding"]))
        verified = []
        for pinned in current:
            item = next(i for i in items if i["id"] == pinned["contentId"])
            result = client.readiness(pinned["channel"], item["id"], pinned["target"], item)
            if (result["ready"] is not True or result["binding"] != pinned["binding"] or
                    result["sourceRecordHash"] != pinned["sourceRecordHash"] or
                    any(result["job"].get(k) != v for k, v in pinned["job"].items())):
                _fail("Final selected job or readiness changed", "HANDOFF_JOB_STALE")
            verified.append(result)
        record.update(state="COMPLETE", publicPublication="NOT_ASSERTED")
        _write(path, record)
        return {"ready": True, "deliveries": delivered, "readiness": verified, "handoffs": snapshots,
                "checkpointPath": str(path), "stage": "COMPLETE", "publicPublication": "NOT_ASSERTED"}
