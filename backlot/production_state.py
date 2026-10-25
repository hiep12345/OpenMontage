"""Bounded observation of production stores, without importing their writer APIs.

Only quiescent rollback-journal SQLite is supported. Recorded dispositions are
not revalidated acceptance, and recorded review checks are not media inspection.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time

MAX_DATABASE_BYTES = 32 * 1024 * 1024
MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_ROWS = 128
SIDECARS = ("-wal", "-shm", "-journal")
REQUEST_STATES = {"PREPARED", "RESERVED", "SUBMITTED", "UNKNOWN", "GENERATED", "REJECTED", "ACCEPTED", "FAILED"}
CHECK_STATES = {"PASS", "FAIL", "NOT_TESTED"}
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
HEX = re.compile(r"[a-f0-9]{64}\Z")


class ObservationError(ValueError):
    """A fixed reason code, never untrusted source text or an OS error."""


def _require(condition, reason="MALFORMED"):
    if not condition:
        raise ObservationError(reason)


def _unlinked(path):
    path = Path(os.path.abspath(path))
    # Inspect parents before children. A leaf probe through a junction can
    # already reach a remote target before a later parent check rejects it.
    for part in (*reversed(path.parents), path):
        try:
            metadata = part.lstat()  # Never follow the entry being inspected.
        except FileNotFoundError:
            continue
        _require(not stat.S_ISLNK(metadata.st_mode), "LINKED_SOURCE")
        _require(not (getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT), "LINKED_SOURCE")
    return path


def _signature(path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _bytes(path, maximum):
    _unlinked(path)
    _require(path.is_file(), "ABSENT")
    before = _signature(path)
    _require(before[2] <= maximum, "SIZE_LIMIT")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    _require(len(raw) <= maximum, "SIZE_LIMIT")
    _require(_signature(path) == before, "CONCURRENT_CHANGE")
    return raw, before


def _json(raw):
    def finite_float(text):
        value = float(text)
        _require(math.isfinite(value))
        return value

    def pairs(items):
        value = {}
        for key, item in items:
            _require(key not in value)
            value[key] = item
        return value
    value = json.loads(raw, object_pairs_hook=pairs, parse_float=finite_float,
                       parse_constant=lambda _: (_ for _ in ()).throw(ObservationError("MALFORMED")))
    return value


def _token(value):
    _require(isinstance(value, str) and TOKEN.fullmatch(value))
    return value


def _checks(value):
    _require(isinstance(value, list) and len(value) <= MAX_ROWS)
    counts = {state: 0 for state in sorted(CHECK_STATES)}
    for check in value:
        _require(isinstance(check, dict) and check.get("status") in CHECK_STATES)
        counts[check["status"]] += 1
    return counts


def _cost(value):
    if value is None:
        return None
    _require(isinstance(value, dict))
    unit, amount = value.get("unit"), value.get("amount")
    _require(unit in {"credits", "usd"}, "UNSUPPORTED_COST_UNIT")
    _require(not isinstance(amount, bool) and isinstance(amount, (int, float))
             and math.isfinite(amount) and amount >= 0)
    return {"unit": unit, "amount": amount}


def _source(project, value):
    if value is None:
        return None
    _require(isinstance(value, dict) and isinstance(value.get("path"), str))
    _require(isinstance(value.get("sha256"), str) and HEX.fullmatch(value["sha256"]))
    path = Path(value["path"])
    # Normalize lexically first: even a metadata probe of an external UNC path
    # can contact its server. Containment must precede _unlinked/stat calls.
    path = Path(os.path.abspath(path if path.is_absolute() else project / path))
    try:
        relative = path.relative_to(project)
    except ValueError:
        raise ObservationError("UNSAFE_SOURCE") from None
    _require(relative.parts and not any(part.startswith(".") for part in relative.parts), "UNSAFE_SOURCE")
    _unlinked(path)
    return {"path": relative.as_posix(), "sha256": value["sha256"], "freshness": "NOT_REVALIDATED"}


def _request(project, key, record):
    _require(isinstance(record, dict) and record.get("request_id") == key)
    _require({"request_id", "scene_id", "status", "artifact", "observed_cost", "reviews", "history"} <= record.keys())
    status = record.get("status")
    _require(status in REQUEST_STATES, "UNSUPPORTED_STATUS")
    reviews = record.get("reviews", [])
    _require(isinstance(reviews, list) and len(reviews) <= MAX_ROWS)
    checks = _checks(reviews[-1].get("checks", [])) if reviews and isinstance(reviews[-1], dict) else None
    _require(not reviews or checks is not None)
    history = record.get("history", [])
    _require(isinstance(history, list) and len(history) <= MAX_ROWS)
    _require(all(isinstance(event, dict) and event.get("status") in REQUEST_STATES for event in history))
    derived = bool(record.get("adopted_from") or record.get("selected_from"))
    return {"request_id": _token(key), "scene_id": _token(record.get("scene_id")),
            "status": status, "source": _source(project, record.get("artifact")),
            "review_checks": checks, "observed_cost": _cost(record.get("observed_cost")),
            "submitted": any(event["status"] == "SUBMITTED" for event in history),
            "derived": derived, "freshness": "NOT_REVALIDATED"}


def _receipt(key, kind, record):
    _require(isinstance(record, dict) and record.get("id") == key)
    _token(key)
    _require(kind in {"application", "review", "feedback", "configuration"}, "UNSUPPORTED_RECORD")
    if kind not in {"application", "review"}:
        return None  # No feedback text, profiles, prompts or account metadata.
    _require(record.get("version") == "1.0", "UNSUPPORTED_VERSION")
    for field in ("context_hash", "artifact_hash"):
        _require(isinstance(record.get(field), str) and HEX.fullmatch(record[field]))
    result = {"kind": kind, "stage": _token(record.get("stage")),
              "freshness": "NOT_REVALIDATED"}
    if kind == "review":
        result["checks"] = _checks(record.get("checks"))
    return result


def _sidecars_absent(database):
    _require(not any(os.path.lexists(str(database) + suffix) for suffix in SIDECARS), "SQLITE_SIDECAR")


def _read_store(project, filename, kind, version):
    database = _unlinked(project / filename)
    _sidecars_absent(database)
    raw, before = _bytes(database, MAX_DATABASE_BYTES)
    _require(raw.startswith(b"SQLite format 3\x00") and len(raw) >= 100)
    _require(raw[18:20] == b"\x01\x01", "WAL_MODE")
    table = "requests" if kind == "generation" else "events"
    expected = {"id", "payload", "digest"} if kind == "generation" else {"seq", "id", "kind", "payload", "digest"}
    deadline = time.monotonic() + 2
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True, timeout=0.1)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        if hasattr(db, "setlimit"):  # Python 3.10 remains supported.
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_RECORD_BYTES + 4096)
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        for name, columns in (("metadata", {"key", "value"}), (table, expected)):
            entry = db.execute("SELECT type FROM sqlite_master WHERE name=?", (name,)).fetchone()
            _require(entry == ("table",), "UNSUPPORTED_SCHEMA")
            actual = {row[1] for row in db.execute(f"PRAGMA table_info({name})")}
            _require(actual == columns, "UNSUPPORTED_SCHEMA")
        owner = db.execute("SELECT value FROM metadata WHERE key='project'").fetchone()
        _require(owner and isinstance(owner[0], str)
                 and os.path.normcase(os.path.abspath(owner[0])) == os.path.normcase(str(project)), "OWNER_MISMATCH")
        if kind == "stage_context":
            policy = db.execute("SELECT value FROM metadata WHERE key='policy'").fetchone()
            _require(policy == (version,), "UNSUPPORTED_VERSION")
        select = "id,payload,digest" if kind == "generation" else "id,kind,payload,digest"
        rows = db.execute(f"SELECT {select} FROM {table} ORDER BY rowid DESC LIMIT ?", (MAX_ROWS + 1,)).fetchall()
    projected = []
    for row in rows[:MAX_ROWS]:
        payload, digest = row[-2:]
        _require(isinstance(payload, str) and len(payload.encode("utf-8")) <= MAX_RECORD_BYTES, "SIZE_LIMIT")
        _require(hashlib.sha256(payload.encode("utf-8")).hexdigest() == digest, "DIGEST_MISMATCH")
        record = _json(payload)
        item = _request(project, row[0], record) if kind == "generation" else _receipt(row[0], row[1], record)
        if item is not None:
            projected.append(item)
    final, after = _bytes(database, MAX_DATABASE_BYTES)
    _require(before == after and raw == final, "CONCURRENT_CHANGE")
    _sidecars_absent(database)
    return {"status": "RECORDED", "reason": None, "records": projected,
            "truncated": len(rows) > MAX_ROWS, "row_limit": MAX_ROWS,
            "source": {"file": filename, "sha256": hashlib.sha256(raw).hexdigest(),
                       "bytes": len(raw), "modified_at": datetime.fromtimestamp(before[3] / 1e9, timezone.utc).isoformat()},
            "freshness": "STABLE_READ_ONLY_SNAPSHOT"}


def _unknown(reason):
    return {"status": "UNKNOWN", "reason": reason, "records": [], "truncated": False,
            "source": None, "freshness": "UNKNOWN"}


def load_production_observation(project_dir):
    """Return allowlisted observations; never create a file, migrate or accept media."""
    result = {"observed_at": datetime.now(timezone.utc).isoformat(),
              "evidence_scope": "Recorded store data only. Media, review truth and current evidence freshness are NOT REVALIDATED.",
              "snapshot_scope": "Independent file reads, not an atomic production snapshot. WAL or concurrent changes remain UNKNOWN."}
    try:
        project = _unlinked(project_dir)
        marker_raw, marker_stat = _bytes(project / "project.json", MAX_RECORD_BYTES)
        marker = _json(marker_raw)
        _require(isinstance(marker, dict) and marker.get("project_id") == project.name, "OWNER_MISMATCH")
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        reason = str(exc) if isinstance(exc, ObservationError) else "MALFORMED"
        return {**result, "status": "UNKNOWN", "generation": _unknown(reason), "stage_context": _unknown(reason)}
    for kind, filename, policy_name, versions in (
        ("generation", "generation_quality.sqlite3", "generation_quality_policy", {"1.0"}),
        ("stage_context", "stage_context.sqlite3", "stage_context_policy", {"1.0", "1.1"}),
    ):
        try:
            policy = marker.get(policy_name)
            _require(isinstance(policy, dict), "POLICY_MISSING")
            _require(policy.get("version") in versions and policy.get("required") is True, "UNSUPPORTED_VERSION")
            if kind == "generation":
                budgets = policy.get("budgets")
                _require(isinstance(budgets, dict) and budgets)
                for unit, amount in budgets.items():
                    _token(unit)
                    _require(not isinstance(amount, bool) and isinstance(amount, (int, float))
                             and math.isfinite(amount) and amount >= 0)
            else:
                _require(isinstance(policy.get("profile"), dict))
            store = _read_store(project, filename, kind, policy["version"])
            _require(_bytes(project / "project.json", MAX_RECORD_BYTES) == (marker_raw, marker_stat), "CONCURRENT_CHANGE")
            result[kind] = store
        except (OSError, ValueError, TypeError, OverflowError, RecursionError, sqlite3.Error) as exc:
            result[kind] = _unknown(str(exc) if isinstance(exc, ObservationError) else "MALFORMED")
    generation = result["generation"]
    if generation["status"] == "RECORDED":
        try:
            totals = {}
            missing = 0
            for request in generation["records"]:
                cost = request["observed_cost"]
                if cost is not None and not request["derived"]:
                    totals[cost["unit"]] = totals.get(cost["unit"], 0) + cost["amount"]
                elif request["submitted"] and not request["derived"]:
                    missing += 1
            _require(all(math.isfinite(amount) for amount in totals.values()))
            generation["observed_costs"] = totals
            generation["submitted_cost_unknown"] = missing
            generation["cost_scope"] = "shown requests only" if generation["truncated"] else "all recorded requests"
        except (ValueError, TypeError, OverflowError):
            result["generation"] = _unknown("MALFORMED")
    result["status"] = "RECORDED" if all(result[key]["status"] == "RECORDED" for key in ("generation", "stage_context")) else "PARTIAL" if any(result[key]["status"] == "RECORDED" for key in ("generation", "stage_context")) else "UNKNOWN"
    return result
