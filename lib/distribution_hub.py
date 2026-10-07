"""Immutable Distribution Hub handoff and byte transport, without publishing."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

import requests

CHUNK_BYTES = 8 * 1024 * 1024
TARGETS = {"fb-ig", "pinterest", "youtube", "x", "tiktok", "amz"}
_HASH = re.compile(r"sha256:[a-f0-9]{64}\Z")


class HubError(ValueError):
    """Safe error text: never includes credentials, response bodies or URLs."""


class HubTransportError(HubError):
    pass


def _require(condition, message):
    if not condition:
        raise HubError(message)


def _json_numbers(value):
    # Reject nonfinite values before serializing requests or evidence.
    if isinstance(value, float):
        _require(math.isfinite(value), "Nonfinite canonical number")
        return value
    if isinstance(value, dict):
        return {key: _json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_numbers(item) for item in value]
    return value


def _lex(value):
    return value.encode("utf-16-be", errors="surrogatepass")


def canonical_json(value):
    value = _json_numbers(value)
    if isinstance(value, dict):
        return "{" + ",".join(canonical_json(key) + ":" + canonical_json(value[key])
                              for key in sorted(value, key=_lex)) + "}"
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, float):
        if value == 0:
            return "0"
        text = repr(value).lower()
        if "e" not in text:
            return text[:-2] if text.endswith(".0") else text
        mantissa, exponent = text.split("e")
        power = int(exponent)
        # ECMAScript uses fixed notation for [1e-6,1e21); Python's shortest
        # round-trip mantissa supplies the digits without precision rounding.
        if -6 <= power < 21:
            sign = "-" if mantissa.startswith("-") else ""
            digits = mantissa.lstrip("-").replace(".", "")
            point = power + 1
            if point <= 0:
                return sign + "0." + "0" * -point + digits
            if point >= len(digits):
                return sign + digits + "0" * (point - len(digits))
            return sign + digits[:point] + "." + digits[point:]
        return mantissa + "e" + ("+" if power >= 0 else "-") + str(abs(power))
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def bytes_digest(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _hash(value):
    return isinstance(value, str) and bool(_HASH.fullmatch(value))


def _sealed(value, key):
    _require(isinstance(value, dict) and _hash(value.get(key)), "Invalid evidence envelope")
    _require(digest({k: v for k, v in value.items() if k != key}) == value[key], "Evidence hash mismatch")


def safe_path(value):
    _require(isinstance(value, str) and 0 < len(value) <= 512 and
             not any(ord(c) < 32 or c in "\\:" for c in value) and
             all(part not in {"", ".", ".."} for part in value.split("/")), "Unsafe media path")
    return value


def _file(value):
    _require(isinstance(value, dict) and set(value) == {"path", "sha256", "sizeBytes", "mimeType"}, "Invalid file evidence")
    safe_path(value["path"])
    _require(_hash(value["sha256"]) and type(value["sizeBytes"]) is int and
             0 <= value["sizeBytes"] <= 2**53 - 1 and isinstance(value["mimeType"], str) and
             re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", value["mimeType"]), "Invalid file evidence")
    return value


def _files(values):
    _require(isinstance(values, list) and 0 < len(values) <= 1024, "Missing exact files")
    result = {_file(value)["path"]: value for value in values}
    _require(len(result) == len(values), "Duplicate file path")
    return result


def validate_manifest(manifest, source):
    fields = {"schemaVersion", "contentId", "productionId", "channelCode", "asset", "qaReceiptHash",
              "distributionRevision", "archiveHash", "files", "destinations", "manifestHash"}
    _require(isinstance(manifest, dict) and set(manifest) == fields and manifest["schemaVersion"] == 1,
             "Invalid delivery manifest")
    _sealed(manifest, "manifestHash")
    for key in ("contentId", "channelCode", "qaReceiptHash", "distributionRevision"):
        _require(manifest[key] == source[key], "Manifest source mismatch")
    _require(_hash(manifest["archiveHash"]) and _hash(manifest["qaReceiptHash"]) and
             _hash(manifest["distributionRevision"]) and isinstance(manifest["productionId"], str) and
             re.fullmatch(r"[a-z0-9][a-z0-9._:-]{2,179}", manifest["productionId"]), "Invalid manifest identity")
    files = _files(manifest["files"])
    _require(list(files) == sorted(files, key=_lex), "Unsorted manifest files")
    asset = _file(manifest["asset"])
    allowed = {"image/png", "image/jpeg", "image/webp", "image/gif"} if source["contentType"] == "photo" else {"video/mp4"}
    _require(source["contentType"] in {"photo", "video"} and asset["sha256"] == source["assetHash"] and
             asset["mimeType"] in allowed and asset["sizeBytes"] > 0 and files.get(asset["path"]) == asset,
             "Manifest primary asset mismatch")
    destinations = manifest["destinations"]
    _require(isinstance(destinations, list) and 0 < len(destinations) <= len(TARGETS), "Missing manifest destinations")
    targets = []
    for row in destinations:
        _require(isinstance(row, dict) and set(row) == {"target", "packageHash", "requiredFiles"} and
                 row["target"] in TARGETS and (row["packageHash"] is None or _hash(row["packageHash"])), "Invalid destination")
        paths = row["requiredFiles"]
        _require(isinstance(paths, list) and all(isinstance(p, str) and p in files for p in paths) and
                 asset["path"] in paths and paths == sorted(set(paths), key=_lex), "Invalid destination files")
        targets.append(row["target"])
    _require(targets == sorted(set(targets), key=_lex), "Duplicate or unsorted destinations")
    return manifest


def verify_handoff(snapshot, channel, content_id, expected=None):
    """Verify current evidence, optionally against a reviewed schema-v2 item.

    No cached receipt, aggregate count, READY state or owner acceptance proves QA
    or public publication. Expected item binding is required for ingest recovery.
    """
    _require(isinstance(snapshot, dict) and snapshot.get("schemaVersion") == 1, "Invalid handoff")
    source = snapshot.get("source")
    _require(isinstance(source, dict) and source.get("channelCode") == channel and
             source.get("contentId") == content_id and source.get("contentType") in {"photo", "video"}, "Wrong handoff identity")
    _require(_hash(snapshot.get("sourceRecordHash")) and digest(source) == snapshot["sourceRecordHash"], "Source record hash mismatch")
    for key in ("assetHash", "qaReceiptHash", "distributionRevision"):
        _require(_hash(source.get(key)), "Missing source evidence")
    profile = snapshot.get("profile")
    _sealed(profile, "profileRevision")
    _require(profile.get("schemaVersion") == 1 and isinstance(profile.get("channel"), dict) and
             profile["channel"].get("code") == channel, "Wrong assignment profile")
    for key in ("packageEvidence", "jobDeliveryEvidence", "publicationEvidence"):
        evidence = snapshot.get(key)
        _sealed(evidence, "evidenceHash")
        _require(evidence.get("contentId") == content_id and evidence.get("sourceRecordHash") == snapshot["sourceRecordHash"], "Evidence source mismatch")
    _require(snapshot["packageEvidence"].get("schemaVersion") == 2 and
             snapshot["packageEvidence"].get("assetHash") == source["assetHash"] and
             snapshot["jobDeliveryEvidence"].get("schemaVersion") == 1 and
             snapshot["publicationEvidence"].get("publicPublication") == "NOT_ASSERTED", "Invalid evidence contract")
    manifest = snapshot.get("deliveryManifest")
    if manifest is not None:
        validate_manifest(manifest, source)
    jobs = snapshot.get("jobs")
    _require(isinstance(jobs, list), "Missing jobs")
    by_target = {}
    ids = set()
    for job in jobs:
        _require(isinstance(job, dict) and job.get("platformCode") in TARGETS and
                 isinstance(job.get("jobId"), str) and job["jobId"] and
                 type(job.get("version")) is int and job["version"] > 0 and
                 type(job.get("manualOnly")) is bool and job.get("state") in
                 {"READY", "CLAIMED", "SCHEDULED", "BLOCKED", "UPLOADED", "SKIPPED"} and
                 job["platformCode"] not in by_target and job["jobId"] not in ids, "Invalid or duplicate job")
        by_target[job["platformCode"]] = job
        ids.add(job["jobId"])
    deliveries = snapshot["jobDeliveryEvidence"].get("jobs")
    _require(isinstance(deliveries, list) and len(deliveries) == len(jobs), "Missing per-job evidence")
    seen = set()
    for row in deliveries:
        _require(isinstance(row, dict), "Invalid per-job evidence")
        target = row.get("platformCode")
        job = by_target.get(target)
        _require(job is not None and target not in seen and row.get("jobId") == job["jobId"] and
                 row.get("version") == job["version"], "Stale per-job evidence")
        seen.add(target)
        if row.get("verification") == "UNAVAILABLE":
            _require(row.get("delivery") is None and isinstance(row.get("errorCode"), str), "Invalid unavailable evidence")
            continue
        delivery = row.get("delivery")
        _require(row.get("verification") == "VERIFIED" and isinstance(delivery, dict) and
                 delivery.get("version") == job["version"] and row.get("errorCode") is None, "Invalid effective delivery")
        for key in ("binding", "assetHash", "qaReceiptHash", "distributionRevision"):
            _require(_hash(delivery.get(key)), "Missing effective delivery binding")
        _require(delivery.get("manifestHash") is None or _hash(delivery["manifestHash"]), "Invalid effective manifest")
        _require(delivery.get("packageHash") is None or _hash(delivery["packageHash"]), "Invalid effective package")
        _files(delivery.get("files"))
    if expected is not None:
        _require(expected.get("id") == content_id and expected.get("channelCode") == channel and
                 expected.get("contentType") == source["contentType"], "Expected identity mismatch")
        for key in ("assetHash", "qaReceiptHash", "distributionRevision", "sourceRevision", "sourceUpdatedAt", "driveFileId"):
            if key in expected:
                _require(source.get(key) == expected[key], "Reviewed source mismatch")
        wanted = expected.get("targets")
        _require(isinstance(wanted, list) and wanted and len(set(wanted)) == len(wanted) and set(wanted) <= TARGETS, "Invalid selected targets")
        expected_manifest = expected.get("deliveryManifest")
        if expected_manifest is not None:
            validate_manifest(expected_manifest, {**expected, "contentId": content_id})
        for target in wanted:
            job = by_target.get(target)
            _require(job is not None and job["manualOnly"] == (target in expected.get("manualTargets", [])), "Missing selected job or changed manual intent")
            row = next(r for r in deliveries if r["platformCode"] == target)
            _require(row["verification"] == "VERIFIED", "Selected delivery unavailable")
            delivery = row["delivery"]
            for key in ("assetHash", "qaReceiptHash", "distributionRevision"):
                _require(delivery[key] == expected[key], "Selected effective source mismatch")
            if expected_manifest is not None:
                dest = next((d for d in expected_manifest["destinations"] if d["target"] == target), None)
                _require(dest is not None and delivery["manifestHash"] == expected_manifest["manifestHash"] and
                         delivery["packageHash"] == dest["packageHash"], "Selected package or manifest mismatch")
                if dest["packageHash"] is not None:
                    package = snapshot["packageEvidence"].get("packages", {}).get(target)
                    _require(isinstance(package, dict) and package.get("packageHash") == dest["packageHash"] and
                             package.get("verification") == "CANONICAL_PREIMAGE_VERIFIED", "Selected package preimage unverified")
                declared = {f["path"]: f for f in expected_manifest["files"] if f["path"] in dest["requiredFiles"]}
                _require(_files(delivery["files"]) == declared, "Selected exact files differ")
    return snapshot


def _local_file(root, evidence):
    path = root / safe_path(evidence["path"])
    _require(path.is_file() and path.resolve().is_relative_to(root), "Local exact file unavailable")
    _require(not any(p.is_symlink() for p in [path, *path.parents] if p != root.parent), "Symlink media is not accepted")
    return path


def describe_file(path, evidence):
    whole = hashlib.sha256()
    chunks = []
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(CHUNK_BYTES):
            whole.update(block)
            size += len(block)
            chunks.append(bytes_digest(block))
    _require(size == evidence["sizeBytes"] and "sha256:" + whole.hexdigest() == evidence["sha256"], "Local file hash or size differs")
    _require(size > 0, "Empty transport file")
    return {"schemaVersion": 1, "sha256": evidence["sha256"], "sizeBytes": size,
            "chunkSizeBytes": CHUNK_BYTES, "chunks": chunks}


class HubClient:
    def __init__(self, origin, client_id, client_secret, *, transport=None,
                 allow_insecure_loopback=False, timeout=30):
        parsed = urlsplit(origin)
        loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
        _require(parsed.scheme == "https" or (allow_insecure_loopback and parsed.scheme == "http" and loopback), "HTTPS Hub origin required")
        _require(parsed.hostname and not parsed.username and not parsed.password and
                 parsed.path in {"", "/"} and not parsed.query and not parsed.fragment and
                 not any(c.isspace() for c in origin), "Invalid Hub origin")
        _require(all(isinstance(v, str) and v and "\r" not in v and "\n" not in v
                     for v in (client_id, client_secret)), "Service authentication required")
        _require(isinstance(timeout, (int, float)) and math.isfinite(timeout) and timeout > 0, "Invalid transport timeout")
        self.origin = origin.rstrip("/")
        self._headers = {"CF-Access-Client-Id": client_id, "CF-Access-Client-Secret": client_secret}
        self.transport = transport if transport is not None else requests.Session()
        self.timeout = timeout

    def _request(self, method, route, *, params=None, body=None, data=None, key=None):
        headers = dict(self._headers)
        if key is not None:
            headers["Idempotency-Key"] = key
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = canonical_json(body).encode("utf-8")
        elif data is not None:
            headers["Content-Type"] = "application/octet-stream"
        try:
            response = self.transport.request(method, self.origin + route, params=params, headers=headers,
                                              data=data, timeout=self.timeout, allow_redirects=False)
        except requests.RequestException:
            raise HubTransportError("Hub transport failed; inspect exact request before resuming") from None
        _require(200 <= response.status_code < 300, f"Hub HTTP {response.status_code}")
        try:
            return response.json()
        except (ValueError, requests.exceptions.JSONDecodeError):
            raise HubError("Hub returned invalid JSON") from None

    def inspect(self, channel, content_id, expected=None):
        snapshot = self._request("GET", "/api/ingest/handoff", params={"channel": channel, "contentId": content_id})
        return verify_handoff(snapshot, channel, content_id, expected)

    def content_index(self, channel):
        """Read all pages; verify the coherent revision, scope and exact cardinality."""
        from lib.content_novelty import validate_identity
        _require(isinstance(channel, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,11}", channel), "Invalid index channel")
        for attempt in range(2):
            items, seen, cursors = [], set(), set()
            cursor = None
            first = None
            try:
                while True:
                    params = {"channel": channel, "limit": 200}
                    if cursor:
                        params["cursor"] = cursor
                    page = self._request("GET", "/api/ingest/content-index", params=params)
                    _require(isinstance(page, dict) and page.get("schemaVersion") == 1 and page.get("channelCode") == channel and
                             type(page.get("active")) is int and page["active"] in (0, 1) and _hash(page.get("revision")) and
                             type(page.get("total")) is int and 0 <= page["total"] <= 10000 and isinstance(page.get("coverage"), dict) and
                             page["coverage"].get("completeHubInventory") is True and isinstance(page.get("items"), list) and len(page["items"]) <= 200,
                             "Invalid or incomplete content index")
                    if first is None:
                        first = {k: page[k] for k in ("schemaVersion", "channelCode", "active", "revision", "total", "coverage")}
                    _require(all(page[k] == first[k] for k in first), "Content index changed during pagination")
                    for item in page["items"]:
                        _require(isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"] not in seen and
                                 item.get("kind") in {"hub", "external"} and isinstance(item.get("title"), str), "Duplicate or invalid index row")
                        if item.get("identity") is not None:
                            try:
                                validate_identity(item["identity"])
                            except (TypeError, ValueError):
                                raise HubError("Invalid creative index identity") from None
                        seen.add(item["id"])
                        items.append(item)
                    _require(len(items) <= first["total"], "Index has excess rows")
                    cursor = page.get("nextCursor")
                    if cursor is None:
                        break
                    _require(isinstance(cursor, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", cursor) and cursor not in cursors and page["items"], "Invalid or repeated index cursor")
                    cursors.add(cursor)
                _require(len(items) == first["total"] and [i["id"] for i in items] == sorted(i["id"] for i in items), "Incomplete or unsorted content index")
                _require(digest({"channelCode": channel, "active": first["active"], "coverage": first["coverage"], "items": items}) == first["revision"], "Content index revision mismatch")
                return {**first, "items": items, "nextCursor": None}
            except HubError as error:
                # Retrying only an idempotent read can recover an explicit page conflict.
                if attempt == 0 and str(error) in {"Hub HTTP 409", "Content index changed during pagination"}:
                    continue
                raise

    def novelty(self, channel, identity, stage="PRE_GENERATION", *, registry_path=None, reserve=False):
        from lib.content_novelty import check_content
        _require(type(reserve) is bool, "Invalid production reservation flag")
        try:
            return check_content(self, channel, identity, stage, registry_path, reserve)
        except (ValueError, OSError, sqlite3.Error) as error:
            if str(error).startswith("ACTIVE_INTENT_CONFLICT"):
                raise HubError("ACTIVE_INTENT_CONFLICT") from None
            raise HubError("Creative preflight inputs or registry unavailable") from None

    def ingest(self, payload, *, novelty_registry=None):
        _require(isinstance(payload, dict) and payload.get("schemaVersion") == 2 and
                 payload.get("sourceSystem") == "production-pipeline" and
                 isinstance(payload.get("idempotencyKey"), str) and 16 <= len(payload["idempotencyKey"]) <= 180 and
                 isinstance(payload.get("items"), list) and 0 < len(payload["items"]) <= 100, "Invalid schema-v2 ingest")
        _require(len({item.get("id") for item in payload["items"]}) == len(payload["items"]), "Duplicate ingest identity")
        for item in payload["items"]:
            archive = urlsplit(item.get("driveUrl", ""))
            _require(archive.scheme == "https" and archive.hostname == "drive.google.com" and
                     not archive.username and not archive.password and item.get("driveFileId"), "Real archive reference required")
            validate_manifest(item.get("deliveryManifest"), {**item, "contentId": item["id"]})
        # A handoff readback proves selected source/job evidence, not the full
        # batch actor/key receipt. Unknown metadata outcomes remain unresolved.
        checks = [self.novelty(item["channelCode"], item["contentIdentity"], "PRE_DELIVERY", registry_path=novelty_registry)
                  for item in payload["items"] if "contentIdentity" in item]
        receipt = self._request("POST", "/api/ingest", body=payload, key=payload["idempotencyKey"])
        snapshots = [self.inspect(item["channelCode"], item["id"], item) for item in payload["items"]]
        result = {"receipt": receipt, "recoveredByReadback": False, "handoffs": snapshots, "publicPublication": "NOT_ASSERTED"}
        if checks:
            result["noveltyChecks"] = checks
        return result

    def _context(self, content_id, target, delivery):
        context = self._request("GET", "/api/ingest/artifacts/media", params={"contentId": content_id, "target": target})
        _require(isinstance(context, dict) and context.get("contentId") == content_id and context.get("target") == target and
                 context.get("binding") == delivery["binding"] and context.get("manifestHash") == delivery.get("manifestHash") and
                 _files(context.get("files")) == _files(delivery["files"]), "Media context differs from effective job")
        return context

    def _status(self, params, file, local_descriptor=None):
        result = self._request("GET", "/api/ingest/artifacts/media", params={**params, "path": file["path"]})
        _require(isinstance(result, dict) and result.get("binding") == params["binding"] and type(result.get("ready")) is bool,
                 "Invalid media readiness")
        descriptor = result.get("descriptor")
        if descriptor is None:
            _require(result["ready"] is False and result.get("missingChunks") is None, "Invalid missing descriptor")
            return result
        _require(isinstance(descriptor, dict) and set(descriptor) == {"schemaVersion", "sha256", "sizeBytes", "chunkSizeBytes", "chunks"} and
                 descriptor["schemaVersion"] == 1 and descriptor["sha256"] == file["sha256"] and descriptor["sizeBytes"] == file["sizeBytes"] and
                 descriptor["chunkSizeBytes"] == CHUNK_BYTES and isinstance(descriptor["chunks"], list) and
                 len(descriptor["chunks"]) == math.ceil(file["sizeBytes"] / CHUNK_BYTES) and
                 all(_hash(h) for h in descriptor["chunks"]) and
                 (len(descriptor["chunks"]) != 1 or descriptor["chunks"][0] == file["sha256"]), "Transport descriptor mismatch")
        if local_descriptor is not None:
            _require(descriptor == local_descriptor, "Transport chunk hashes differ")
        missing = result.get("missingChunks")
        _require(isinstance(missing, list) and all(type(i) is int and 0 <= i < len(descriptor["chunks"]) for i in missing) and
                 len(set(missing)) == len(missing) and result["ready"] == (len(missing) == 0), "Invalid missing chunks")
        return result

    def readiness(self, channel, content_id, target, expected=None):
        snapshot = self.inspect(channel, content_id, expected)
        row = next((r for r in snapshot["jobDeliveryEvidence"]["jobs"] if r["platformCode"] == target), None)
        _require(row is not None and row["verification"] == "VERIFIED", "Selected delivery unavailable")
        context = self._context(content_id, target, row["delivery"])
        params = {"contentId": content_id, "target": target, "binding": context["binding"]}
        statuses = [{"path": file["path"], **self._status(params, file)} for file in context["files"]]
        return {"contentId": content_id, "target": target, "sourceRecordHash": snapshot["sourceRecordHash"],
                "job": next(j for j in snapshot["jobs"] if j["platformCode"] == target),
                "binding": context["binding"], "manifestHash": context.get("manifestHash"),
                "files": statuses, "ready": all(s["ready"] for s in statuses), "publicPublication": "NOT_ASSERTED"}

    def deliver(self, channel, content_id, target, root, expected=None, *, content_identity=None, novelty_registry=None):
        snapshot = self.inspect(channel, content_id, expected)
        identity = content_identity or (expected or {}).get("contentIdentity")
        novelty_check = None
        if identity is not None:
            novelty_check = self.novelty(channel, identity, "PRE_DELIVERY", registry_path=novelty_registry)
            index = self.content_index(channel)
            indexed = next((c for c in index["items"] if c["kind"] == "hub" and c["id"] == content_id), None)
            _require(indexed is not None and indexed.get("sourceRevision") == snapshot["source"]["sourceRevision"] and
                     indexed.get("identityHash") == digest(identity), "Delivery creative identity differs from its accepted source")
        row = next((r for r in snapshot["jobDeliveryEvidence"]["jobs"] if r["platformCode"] == target), None)
        _require(row is not None and row["verification"] == "VERIFIED", "Selected delivery unavailable")
        context = self._context(content_id, target, row["delivery"])
        root = Path(root).resolve(strict=True)
        # Verify every local member before the first write. A missing/changed
        # caption must not cause a partially delivered different package.
        local = [(file, _local_file(root, file)) for file in context["files"]]
        prepared = [(file, path, describe_file(path, file)) for file, path in local]
        params = {"contentId": content_id, "target": target, "binding": context["binding"]}
        uploaded = 0
        for file, path, descriptor in prepared:
            query = {**params, "path": file["path"]}
            status = self._status(params, file, descriptor)
            if status["descriptor"] is None:
                try:
                    self._request("POST", "/api/ingest/artifacts/media", params=query, body=descriptor)
                except HubTransportError:
                    pass
                status = self._status(params, file, descriptor)
                _require(status["descriptor"] is not None, "Descriptor registration not confirmed; resume exact delivery")
            with path.open("rb") as stream:
                for index in status["missingChunks"]:
                    stream.seek(index * CHUNK_BYTES)
                    block = stream.read(CHUNK_BYTES)
                    _require(len(block) == min(CHUNK_BYTES, file["sizeBytes"] - index * CHUNK_BYTES) and
                             bytes_digest(block) == descriptor["chunks"][index], "Local file changed during delivery")
                    try:
                        self._request("PUT", "/api/ingest/artifacts/media", params={**query, "chunkIndex": index}, data=block)
                    except HubTransportError:
                        recovered = self._status(params, file, descriptor)
                        _require(index not in recovered["missingChunks"], "Chunk send not confirmed; resume exact delivery")
                    uploaded += 1
            _require(self._status(params, file, descriptor)["ready"], "Exact file not ready after delivery")
            describe_file(path, file)
        final = self.inspect(channel, content_id, expected)
        final_row = next(r for r in final["jobDeliveryEvidence"]["jobs"] if r["platformCode"] == target)
        _require(final["sourceRecordHash"] == snapshot["sourceRecordHash"] and final_row == row and
                 final["jobs"] == snapshot["jobs"], "Handoff changed during delivery")
        verified = self.readiness(channel, content_id, target, expected)
        _require(verified["sourceRecordHash"] == snapshot["sourceRecordHash"] and verified["binding"] == context["binding"] and
                 verified["job"] == next(j for j in snapshot["jobs"] if j["platformCode"] == target) and verified["ready"],
                 "Final handoff readiness changed")
        result = {**verified, "uploadedChunks": uploaded, "localFilesVerified": [f["path"] for f, _, _ in prepared]}
        if novelty_check is not None:
            result["noveltyCheck"] = novelty_check
        return result
