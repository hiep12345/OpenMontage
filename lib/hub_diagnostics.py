"""Small local handoff reports: no credentials, payloads or response bodies."""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from lib.distribution_hub import HubError, PUBLIC_ERROR_CODES, digest

_LABEL = re.compile(r"[A-Za-z0-9_.:-]{1,180}\Z")
_OPERATIONS = {"inspect", "readiness", "ingest", "deliver", "content_index", "novelty"}


def _label(value):
    return value if isinstance(value, str) and _LABEL.fullmatch(value) else None


def _version(value):
    return value if type(value) is int and value >= 0 else None


def _revision(value):
    if isinstance(value, str) and re.fullmatch(r"sha256:[a-f0-9]{64}", value):
        return value
    return _version(value)


def next_action(code, unknown=False):
    if unknown:
        return "RECONCILE_EXACT_REQUEST"
    if code == "D1_READ_QUOTA_EXCEEDED":
        return "WAIT_FOR_QUOTA_RESET"
    if code in {"AUTH_REQUIRED", "FORBIDDEN", "MANUAL_ONLY"}:
        return "CHECK_AUTHORIZATION"
    if code and ("STALE" in code or code == "CONTENT_INDEX_CHANGED"):
        return "INSPECT_CURRENT_BINDINGS"
    if code and ("PACKAGE" in code or "MANIFEST" in code or "DESCRIPTOR" in code):
        return "CHECK_EXACT_PACKAGE"
    if code == "SOURCE_STORAGE_UNAVAILABLE":
        return "CHECK_MEDIA_STORAGE"
    return "INSPECT_REPORT"


class HandoffReport:
    def __init__(self, inputs):
        project = Path(inputs.get("project_dir") or Path(__file__).resolve().parents[1] / "projects" / "hub-handoffs")
        directory = project / "artifacts" / "hub-handoffs"
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{uuid.uuid4()}.json"
        self.value = {"schemaVersion": 1, "startedAt": datetime.now(timezone.utc).isoformat(),
                      "operation": inputs.get("operation") if inputs.get("operation") in _OPERATIONS else "invalid",
                      "channel": _label(inputs.get("channel")), "contentId": _label(inputs.get("content_id")),
                      "target": _label(inputs.get("target")), "state": "RUNNING",
                      "publicPublication": "NOT_ASSERTED", "requests": []}
        payload = inputs.get("payload")
        reviewed = [inputs["expected"]] if isinstance(inputs.get("expected"), dict) else []
        if isinstance(payload, dict):
            self.value["requestFingerprint"] = digest(payload)
            key = payload.get("idempotencyKey")
            if isinstance(key, str):
                self.value["idempotencyKeyHash"] = digest(key)
            if isinstance(payload.get("items"), list):
                reviewed = [item for item in payload["items"] if isinstance(item, dict)]
        self.value["reviewedVersions"] = [{"contentId": _label(item.get("id")),
                                           "sourceRevision": _revision(item.get("sourceRevision")),
                                           "distributionRevision": _revision(item.get("distributionRevision"))}
                                          for item in reviewed]
        self._write()

    def _write(self):
        temporary = self.path.with_suffix(".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(self.value, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def finish(self, result=None, error=None, requests=()):
        self.value.update(finishedAt=datetime.now(timezone.utc).isoformat(),
                          state="FAILED" if error else "COMPLETE", requests=list(requests),
                          traceTruncated=len(requests) >= 5000)
        if error is not None:
            code = getattr(error, "code", None)
            code = code if code in PUBLIC_ERROR_CODES else None
            unknown = getattr(error, "outcome_unknown", False) is True
            self.value.update(errorCode=code, httpStatus=getattr(error, "status", None),
                              failedStep=getattr(error, "request_step", {"outcome": "LOCAL_VALIDATION"}),
                              outcomeUnknown=unknown, nextAction=next_action(code, unknown))
            # HubError is the client's sanitized boundary. Its local validation
            # reason is needed after the ToolResult/UI has gone away.
            if isinstance(error, HubError):
                self.value["error"] = str(error)
        elif isinstance(result, dict):
            if type(result.get("ready")) is bool:
                self.value["ready"] = result["ready"]
            self.value["nextAction"] = "OPERATOR_INSPECTION" if result.get("ready") is True else "INSPECT_REPORT"
            snapshots = result.get("handoffs", []) or ([result] if "source" in result else [])
            self.value["versions"] = [{"contentId": _label(row.get("source", {}).get("contentId")),
                                       "sourceRevision": _revision(row.get("source", {}).get("sourceRevision")),
                                       "jobs": [{"target": _label(job.get("platformCode")), "version": _version(job.get("version"))}
                                                for job in row.get("jobs", [])]}
                                      for row in snapshots]
        self._write()
        return str(self.path)
