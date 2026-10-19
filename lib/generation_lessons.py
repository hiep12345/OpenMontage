"""Read existing outcome ledgers for contextual learning, without a prompt catalog."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sqlite3


def find_lessons(projects, *, kind=None, video_format=None, model=None, mode=None):
    """Return candidate failure/correction evidence, never automatic new rules.

    Only explicitly supplied project ledgers are opened, in read-only mode. A
    different aesthetic/format is reported so a reviewer can judge transfer.
    Historical pre-policy receipts are not migrated or relabelled here.
    """
    if not isinstance(projects, list) or any(not isinstance(value, str) or not value.strip() for value in projects):
        raise ValueError("projects must be an array of explicit paths")
    lessons = []
    for value in projects:
        project = Path(value).resolve()
        path = project / "generation_quality.sqlite3"
        if not path.is_file():
            continue
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            identity = db.execute("SELECT value FROM metadata WHERE key='project'").fetchone()
            if not identity or identity[0] != str(project):
                raise ValueError("Outcome ledger belongs to another project")
            rows = db.execute("SELECT payload,digest FROM requests ORDER BY rowid").fetchall()
        records = []
        for payload, digest in rows:
            if hashlib.sha256(payload.encode()).hexdigest() != digest:
                raise ValueError("Outcome ledger integrity mismatch")
            records.append(json.loads(payload))
        by_id = {record["request_id"]: record for record in records}
        for record in records:
            retry = record.get("retry")
            if not retry:
                continue
            prior = by_id.get(retry["prior_request_id"])
            if prior is None:
                continue
            criteria = {item["id"]: item for item in prior["contract"]["requirements"]}
            failures = [check for witness in prior.get("reviews", []) for check in witness["checks"]
                        if check["status"] == "FAIL" and (kind is None or criteria[check["id"]]["kind"] == kind)]
            if kind is not None and not failures:
                continue
            checks = record.get("reviews", [])[-1:]
            refs = [ref for witness in checks for check in witness["checks"] for ref in check.get("evidence", [])]
            refs += [ref for failure in failures for ref in failure.get("evidence",[])]
            current = bool(checks and refs) and all(
                Path(ref["path"]).is_file() and hashlib.sha256(Path(ref["path"]).read_bytes()).hexdigest() == ref["sha256"]
                for ref in refs
            )
            lessons.append({
                "source_project":str(project), "prior_request_id":prior["request_id"],
                "request_id":record["request_id"], "intent":prior["contract"]["intent"],
                "video_format":prior["contract"]["video_format"], "aesthetic":prior["contract"]["aesthetic"],
                "provider":record["provider"], "model":record["model"], "mode":record["mode"],
                "failures":failures, "correction":retry, "recorded_outcome":record["status"],
                "evidence_current":current,
                "same_context":{"video_format":video_format is None or prior["contract"]["video_format"] == video_format,
                                "model":model is None or record["model"] == model,
                                "mode":mode is None or record["mode"] == mode},
                "transfer_scope":"Candidate lesson; compare intent and allowed changes before applying it.",
            })
    return lessons
