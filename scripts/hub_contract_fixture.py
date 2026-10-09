"""Deterministic synthetic producer fixture, not a production/QA artifact."""
from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.distribution_hub import HubClient, bytes_digest, digest, verify_handoff


def fixture(content_type="photo", meta_target="fb-ig"):
    if meta_target not in {"fb-ig", "facebook", "instagram"}:
        raise ValueError("Invalid synthetic Meta target")
    suffix = content_type if meta_target == "fb-ig" else meta_target + "-" + content_type
    content_id = "openmontage-contract-" + suffix
    channel = "CRL" if meta_target == "facebook" else "MT"
    caption_path = "metadata/caption.txt" if meta_target == "fb-ig" else meta_target + "/caption.txt"
    targets = ["fb-ig", "pinterest"] if meta_target == "fb-ig" else [meta_target]
    # These tiny format-like bytes test transport/contracts only, never visual QA.
    primary = (b"\x00\x00\x00\x18ftypmp42synthetic-contract-video" if content_type == "video" else
               base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII="))
    path = "media/source.mp4" if content_type == "video" else "media/source.png"
    receipt = b'{"scope":"synthetic-contract-only","visualQa":"NOT_ASSERTED"}'
    members = {path: primary, caption_path: b"Synthetic contract fixture; never publish.\n", "metadata/qa.json": receipt}
    files = [{"path": name, "sha256": bytes_digest(data), "sizeBytes": len(data),
              "mimeType": ("video/mp4" if name.endswith(".mp4") else "image/png" if name.endswith(".png") else
                           "application/json" if name.endswith(".json") else "text/plain")}
             for name, data in sorted(members.items())]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(members.items()):
            entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    asset = next(f for f in files if f["path"] == path)
    item = {"id": content_id, "channelCode": channel, "channelName": "CosyRoom Lab" if channel == "CRL" else "Mix Therapy",
            "title": "Synthetic OpenMontage " + content_type + " contract fixture",
            "contentType": content_type, "driveUrl": "https://drive.google.com/file/d/synthetic-contract-archive/view",
            "driveFileId": "synthetic-contract-archive", "producedAt": "2026-01-01T00:00:00.000Z",
            "sourceUpdatedAt": "2026-01-01T00:00:00.000Z", "sourceRevision": digest({"fixture": suffix}),
            "qaScore": 9, "assetHash": asset["sha256"], "qaReceiptHash": bytes_digest(receipt),
            "distributionRevision": digest({"producer": "openmontage", "fixture": suffix}),
            "targets": targets, "manualTargets": ["pinterest"] if meta_target == "fb-ig" else []}
    if meta_target != "fb-ig":
        del item["manualTargets"]
    manifest = {"schemaVersion": 1, "contentId": content_id, "productionId": content_id, "channelCode": channel,
                "asset": asset, "qaReceiptHash": item["qaReceiptHash"], "distributionRevision": item["distributionRevision"],
                "archiveHash": bytes_digest(buffer.getvalue()), "files": files,
                "destinations": [{"target": target, "packageHash": None, "requiredFiles": [f["path"] for f in files]}
                                 for target in item["targets"]]}
    manifest["manifestHash"] = digest(manifest)
    item["deliveryManifest"] = manifest

    from lib.caption_links import is_caption_file, seal_fields
    fields = seal_fields([{"id": "file:" + file["path"], "text": members[file["path"]].decode("utf-8")}
                          for file in files if is_caption_file(file)])
    qa = {"schemaVersion": 1, "contentId": content_id, "assetHash": item["assetHash"],
          "distributionRevision": item["distributionRevision"], "fields": fields,
          "reviewer": {"name": "synthetic-contract-only", "checkedAt": "2026-01-01T00:00:00Z",
                       "semantic": "NOT_APPLICABLE", "browser": "NOT_APPLICABLE", "evidence": []},
          "checkedAt": "2026-01-01T00:00:00Z", "websiteRelease": None, "checks": []}
    if channel == "MT":
        item["captionLinkQa"] = {**qa, "receiptHash": digest(qa)}

    return {"schemaVersion": 1, "payload": {"schemaVersion": 2, "sourceSystem": "production-pipeline",
            "idempotencyKey": "openmontage-contract-fixture-" + suffix, "items": [item]},
            "files": [{**f, "base64": base64.b64encode(members[f["path"]]).decode("ascii")} for f in files],
            "archive": {"sha256": bytes_digest(buffer.getvalue()), "base64": base64.b64encode(buffer.getvalue()).decode("ascii")},
            "expected": {"channelCode": channel, "contentId": content_id, "targets": item["targets"], "manualTargets": item.get("manualTargets", [])}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-type", choices=["photo", "video"], default="photo")
    parser.add_argument("--meta-target", choices=["fb-ig", "facebook", "instagram"], default="fb-ig")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--exercise-origin", help="Explicit local synthetic Hub fixture only")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--handoff", action="store_true", help="Exercise the deterministic handoff facade")
    parser.add_argument("--reconcile-metadata", action="store_true", help="Explicit exact-request reconciliation in the synthetic test")
    args = parser.parse_args()
    data = fixture(args.content_type, args.meta_target)
    expected = data["payload"]["items"][0]
    if args.snapshot:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        snapshot = snapshot.get("snapshot", snapshot)
        verify_handoff(snapshot, expected["channelCode"], expected["id"], expected)
        print(json.dumps({"verified": True, "contentId": expected["id"], "sourceRecordHash": snapshot["sourceRecordHash"]}))
    elif args.exercise_origin:
        from urllib.parse import urlsplit
        origin = urlsplit(args.exercise_origin)
        if origin.hostname not in {"127.0.0.1", "::1", "localhost"}:
            parser.error("exercise-origin must be an explicit localhost fixture")
        if not args.root:
            parser.error("--root is required for the synthetic fixture")
        for file in data["files"]:
            path = args.root / file["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(file["base64"]))
        client = HubClient(args.exercise_origin, "synthetic-service-id", "synthetic-service-secret", allow_insecure_loopback=True)
        if args.handoff:
            from lib.hub_handoff import handoff
            result = handoff(client, data["payload"], args.root, args.root / "checkpoint.json",
                             reconcile_metadata=args.reconcile_metadata)
        else:
            result = client.ingest(data["payload"])
            result["deliveries"] = [client.deliver(expected["channelCode"], expected["id"], target, args.root, expected) for target in expected["targets"]]
        print(json.dumps(result))
    else:
        print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
