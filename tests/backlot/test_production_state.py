"""Read-only store projection, with independently constructed offline fixtures."""
import hashlib
import json
from pathlib import Path
import sqlite3
import stat
from types import SimpleNamespace

import pytest

from backlot import production_state as observation
from backlot.state import load_board_state


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "film"
    path.mkdir()
    (path / "project.json").write_text(json.dumps({
        "project_id": "film", "pipeline_type": "cinematic",
        "generation_quality_policy": {"version": "1.0", "required": True, "budgets": {"credits": 500, "usd": 10}},
        "stage_context_policy": {"version": "1.1", "required": True, "profile": {}},
    }), encoding="utf-8")
    return path


def request(key="r1", status="GENERATED", cost=None):
    return {"request_id": key, "scene_id": "sc1", "status": status,
            "artifact": None, "observed_cost": cost, "reviews": [],
            "history": [{"status": "SUBMITTED", "at": "2026-10-25T00:00:00Z"}],
            "inputs": {"prompt": "DO_NOT_EXPOSE_PROMPT", "account": "DO_NOT_EXPOSE_ACCOUNT"},
            "result": {"token": "DO_NOT_EXPOSE_TOKEN"}}


def store(project, kind="generation", records=None):
    filename = "generation_quality.sqlite3" if kind == "generation" else "stage_context.sqlite3"
    path = project / filename
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO metadata VALUES ('project', ?)", (str(project),))
        if kind == "generation":
            db.execute("CREATE TABLE requests (id TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL)")
            for value in records or []:
                payload = canonical(value)
                db.execute("INSERT INTO requests VALUES (?,?,?)", (value["request_id"], payload, hashlib.sha256(payload.encode()).hexdigest()))
        else:
            db.execute("INSERT INTO metadata VALUES ('policy', '1.1')")
            db.execute("CREATE TABLE events (seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL)")
            for kind, value in records or []:
                payload = canonical(value)
                db.execute("INSERT INTO events(id,kind,payload,digest) VALUES (?,?,?,?)", (value["id"], kind, payload, hashlib.sha256(payload.encode()).hexdigest()))
    return path


def snapshot(project):
    return {str(path.relative_to(project)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in project.rglob("*") if path.is_file()}


def test_projection_cost_units_sources_partial_review_and_nonmutation(project):
    generated = request("native", "ACCEPTED", {"unit": "credits", "amount": 12})
    generated["artifact"] = {"path": str(project / "assets" / "sc1.mp4"), "sha256": "a" * 64}
    generated["reviews"] = [{"checks": [{"status": "PASS"}, {"status": "NOT_TESTED"}]}]
    rejected = request("rejected", "REJECTED", {"unit": "usd", "amount": 0.25})
    pending = request("uncertain", "UNKNOWN")
    derived = request("copy", "ACCEPTED", {"unit": "credits", "amount": 99})
    derived["adopted_from"] = {"request_id": "native"}
    store(project, records=[generated, rejected, pending, derived])
    store(project, "stage_context", [
        ("application", {"id": "app1", "version": "1.0", "stage": "script", "context_hash": "a" * 64, "artifact_hash": "b" * 64}),
        ("review", {"id": "review1", "version": "1.0", "stage": "script", "context_hash": "a" * 64,
                    "artifact_hash": "b" * 64, "checks": [{"status": "FAIL"}, {"status": "NOT_TESTED"}]}),
        ("feedback", {"id": "feedback1", "text": "DO_NOT_EXPOSE_FEEDBACK"}),
    ])
    before = snapshot(project)
    result = load_board_state(project)["production_observation"]
    assert snapshot(project) == before
    assert result["status"] == "RECORDED"
    generation = result["generation"]
    assert generation["observed_costs"] == {"credits": 12, "usd": 0.25}
    assert generation["submitted_cost_unknown"] == 1
    assert generation["cost_scope"] == "all recorded requests"
    records = {row["request_id"]: row for row in generation["records"]}
    assert records["native"]["source"] == {"path": "assets/sc1.mp4", "sha256": "a" * 64, "freshness": "NOT_REVALIDATED"}
    assert records["native"]["review_checks"] == {"PASS": 1, "FAIL": 0, "NOT_TESTED": 1}
    assert records["uncertain"]["status"] == "UNKNOWN"
    assert generation["source"]["sha256"] == hashlib.sha256((project / "generation_quality.sqlite3").read_bytes()).hexdigest()
    assert generation["freshness"] == "STABLE_READ_ONLY_SNAPSHOT"
    assert len(result["stage_context"]["records"]) == 2
    assert result["stage_context"]["records"][0]["checks"]["NOT_TESTED"] == 1
    assert "DO_NOT_EXPOSE" not in json.dumps(result)


def test_missing_stores_do_not_create_files_or_open_sqlite(project, monkeypatch):
    before = snapshot(project)
    monkeypatch.setattr(observation.sqlite3, "connect", lambda *a, **k: pytest.fail("Absent database must not be opened"))
    result = observation.load_production_observation(project)
    assert result["status"] == "UNKNOWN"
    assert result["generation"]["reason"] == "ABSENT"
    assert snapshot(project) == before


@pytest.mark.parametrize("suffix", observation.SIDECARS)
def test_sidecar_blocks_only_affected_store_without_sqlite_open(project, monkeypatch, suffix):
    path = store(project, records=[request()])
    Path(str(path) + suffix).write_bytes(b"existing writer state")
    before = snapshot(project)
    monkeypatch.setattr(observation.sqlite3, "connect", lambda *a, **k: pytest.fail("Sidecar database must not be opened"))
    result = observation.load_production_observation(project)
    assert result["generation"]["reason"] == "SQLITE_SIDECAR"
    assert snapshot(project) == before


def test_wal_header_without_sidecars_stays_unknown(project, monkeypatch):
    path = store(project)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    assert not Path(str(path) + "-wal").exists()
    before = snapshot(project)
    monkeypatch.setattr(observation.sqlite3, "connect", lambda *a, **k: pytest.fail("WAL header must be rejected before open"))
    assert observation.load_production_observation(project)["generation"]["reason"] == "WAL_MODE"
    assert snapshot(project) == before


@pytest.mark.parametrize("change,reason", [
    ("schema", "UNSUPPORTED_SCHEMA"), ("owner", "OWNER_MISMATCH"),
    ("digest", "DIGEST_MISMATCH"), ("json", "MALFORMED"),
    ("nonfinite", "MALFORMED"), ("duplicates", "MALFORMED"),
])
def test_unsupported_or_malformed_store_is_unknown_and_does_not_block_other_store(project, change, reason):
    path = store(project, records=[request()])
    store(project, "stage_context")
    with sqlite3.connect(path) as db:
        if change == "schema":
            db.execute("ALTER TABLE requests ADD COLUMN future TEXT")
        elif change == "owner":
            db.execute("UPDATE metadata SET value='other-project' WHERE key='project'")
        elif change == "digest":
            db.execute("UPDATE requests SET digest='wrong'")
        else:
            payload = {"json": "{", "nonfinite": '{"bad":1e999}', "duplicates": '{"id":1,"id":2}'}[change]
            db.execute("UPDATE requests SET payload=?,digest=?", (payload, hashlib.sha256(payload.encode()).hexdigest()))
    before = snapshot(project)
    result = observation.load_production_observation(project)
    assert result["status"] == "PARTIAL"
    assert result["generation"]["reason"] == reason
    assert result["stage_context"]["status"] == "RECORDED"
    assert snapshot(project) == before


@pytest.mark.parametrize("kind", ["generation", "stage_context"])
def test_future_policy_version_is_unknown(project, kind):
    marker_path = project / "project.json"
    marker = json.loads(marker_path.read_text())
    marker["generation_quality_policy" if kind == "generation" else "stage_context_policy"]["version"] = "99.0"
    marker_path.write_text(json.dumps(marker))
    assert observation.load_production_observation(project)[kind]["reason"] == "UNSUPPORTED_VERSION"


@pytest.mark.parametrize("field,value,reason", [
    ("status", "FUTURE", "UNSUPPORTED_STATUS"),
    ("observed_cost", {"unit": "tokens", "amount": 4}, "UNSUPPORTED_COST_UNIT"),
    ("observed_cost", {"unit": "credits", "amount": -1}, "MALFORMED"),
    ("observed_cost", {"unit": "credits", "amount": 10 ** 400}, "MALFORMED"),
    ("artifact", {"path": "../escape.mp4", "sha256": "a" * 64}, "UNSAFE_SOURCE"),
])
def test_unsupported_request_fields_remain_unknown(project, field, value, reason):
    row = request()
    row[field] = value
    store(project, records=[row])
    assert observation.load_production_observation(project)["generation"]["reason"] == reason


def test_query_is_explicitly_read_only_and_immutable(project, monkeypatch):
    store(project)
    original = sqlite3.connect
    calls = []
    def connect(database_uri, **kwargs):
        calls.append((database_uri, kwargs))
        assert database_uri.endswith("?mode=ro&immutable=1") and kwargs["uri"] is True
        return original(database_uri, **kwargs)
    monkeypatch.setattr(observation.sqlite3, "connect", connect)
    assert observation.load_production_observation(project)["generation"]["status"] == "RECORDED"
    assert len(calls) == 1


def test_concurrent_byte_change_discards_projection(project, monkeypatch):
    path = store(project, records=[request()])
    original = observation._bytes
    calls = 0
    def read(source, maximum):
        nonlocal calls
        raw, signature = original(source, maximum)
        if source == path:
            calls += 1
            if calls == 2:
                return raw + b"changed", signature
        return raw, signature
    monkeypatch.setattr(observation, "_bytes", read)
    result = observation.load_production_observation(project)["generation"]
    assert result["reason"] == "CONCURRENT_CHANGE" and result["records"] == []


def test_sidecar_appearing_during_read_discards_projection(project, monkeypatch):
    path = store(project, records=[request()])
    original = observation._bytes
    calls = 0
    def read(source, maximum):
        nonlocal calls
        result = original(source, maximum)
        if source == path:
            calls += 1
            if calls == 2:
                Path(str(path) + "-journal").write_bytes(b"concurrent fixture writer")
        return result
    monkeypatch.setattr(observation, "_bytes", read)
    result = observation.load_production_observation(project)["generation"]
    assert result["reason"] == "SQLITE_SIDECAR" and result["records"] == []


def test_malformed_database_and_marker_are_unknown(project):
    (project / "generation_quality.sqlite3").write_bytes(b"not sqlite")
    assert observation.load_production_observation(project)["generation"]["reason"] == "MALFORMED"
    (project / "project.json").write_text("{broken")
    assert observation.load_production_observation(project)["status"] == "UNKNOWN"


def test_cost_total_overflow_is_unknown_instead_of_nonfinite_json(project):
    store(project, records=[request(f"r{i}", cost={"unit": "credits", "amount": 1e308}) for i in range(2)])
    result = observation.load_production_observation(project)
    assert result["generation"]["reason"] == "MALFORMED"
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("location", ["outside", "traversal", "unc"])
def test_external_artifact_is_rejected_before_any_filesystem_probe(monkeypatch, location):
    project = Path.cwd() / "observed-project"
    source = {
        "outside": str(project.parent / "elsewhere" / "source.mp4"),
        "traversal": "../elsewhere/source.mp4",
        "unc": "//outside.invalid/share/source.mp4",
    }[location]
    def forbidden(*args, **kwargs):
        pytest.fail("External artifact must be rejected before filesystem metadata or _unlinked")
    monkeypatch.setattr(observation, "_unlinked", forbidden)
    monkeypatch.setattr(Path, "stat", forbidden)
    with pytest.raises(observation.ObservationError, match="^UNSAFE_SOURCE$"):
        observation._source(project, {"path": source, "sha256": "a" * 64})


@pytest.mark.parametrize("link_kind", ["symlink", "reparse"])
def test_linked_ancestor_stops_probes_before_any_descendant(monkeypatch, link_kind):
    project = Path.cwd() / "observed-project"
    linked = project / "assets"
    leaf = linked / "nested" / "source.mp4"
    probes = []
    def lstat(path, *args, **kwargs):
        if path != linked and path.is_relative_to(linked):
            pytest.fail("Descendant metadata must not be probed through a linked ancestor")
        probes.append(path)
        return SimpleNamespace(
            st_mode=stat.S_IFLNK if path == linked and link_kind == "symlink" else stat.S_IFDIR,
            st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT if path == linked and link_kind == "reparse" else 0,
        )
    def forbidden(*args, **kwargs):
        pytest.fail("Only lstat is safe here; stat/exists may follow the linked ancestor")
    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(Path, "stat", forbidden)
    monkeypatch.setattr(Path, "exists", forbidden)
    monkeypatch.setattr(Path, "is_symlink", forbidden)
    with pytest.raises(observation.ObservationError, match="^LINKED_SOURCE$"):
        observation._source(project, {"path": str(leaf), "sha256": "a" * 64})
    ordered = [*reversed(leaf.parents), leaf]
    assert probes == ordered[:ordered.index(linked) + 1]


def test_integer_cost_aggregation_overflow_is_contained_without_filesystem_writes(monkeypatch):
    project = Path.cwd() / "observed-project"
    marker = json.dumps({
        "project_id": project.name,
        "generation_quality_policy": {"version": "1.0", "required": True, "budgets": {"credits": 1}},
        "stage_context_policy": {"version": "1.1", "required": True, "profile": {}},
    }).encode()
    monkeypatch.setattr(observation, "_unlinked", lambda path: project)
    monkeypatch.setattr(observation, "_bytes", lambda *args: (marker, (1, 2, 3, 4, 5)))
    def read_store(project, filename, kind, version):
        rows = [] if kind == "stage_context" else [
            {"observed_cost": {"unit": "credits", "amount": 10 ** 308}, "derived": False, "submitted": True}
            for _ in range(2)
        ]
        return {"status": "RECORDED", "reason": None, "records": rows, "truncated": False}
    monkeypatch.setattr(observation, "_read_store", read_store)
    result = observation.load_production_observation(project)
    assert result["status"] == "PARTIAL"
    assert result["generation"]["status"] == "UNKNOWN"
    assert result["generation"]["reason"] == "MALFORMED"
    assert result["stage_context"]["status"] == "RECORDED"
    json.dumps(result, allow_nan=False)


def test_row_bound_marks_costs_as_partial(project, monkeypatch):
    store(project, records=[request(f"r{i}", cost={"unit": "credits", "amount": i}) for i in range(4)])
    monkeypatch.setattr(observation, "MAX_ROWS", 2)
    result = observation.load_production_observation(project)["generation"]
    assert result["truncated"] is True and len(result["records"]) == 2
    assert result["observed_costs"] == {"credits": 5}
    assert result["cost_scope"] == "shown requests only"


def test_existing_storyboard_and_checkpoint_fields_are_preserved(project):
    (project / "artifacts").mkdir()
    (project / "artifacts" / "scene_plan.json").write_text(json.dumps({"version": "1.0", "scenes": [
        {"id": "sc1", "type": "generated", "description": "Opening", "start_seconds": 0, "end_seconds": 4}]}))
    (project / "checkpoint_assets.json").write_text(json.dumps({"stage": "assets", "status": "in_progress", "artifacts": {}}))
    state = load_board_state(project)
    assert state["storyboard"]["scenes"][0]["id"] == "sc1"
    assert next(stage for stage in state["stages"] if stage["name"] == "assets")["status"] == "in_progress"
    assert state["cost"] is None
