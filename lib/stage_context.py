"""Local, provenance-bound stage work; no provider calls or quality inference.

Receipts attest to recorded decisions, not comprehension or creative quality.
Source text is untrusted data. Only repository manifest-selected directors are
labelled trusted instructions. SQLite serializes append-only feedback/receipts.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from functools import wraps
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import uuid

import jsonschema

from lib.stage_context_selection import (
    CONTEXT_VERSIONS, DEFAULT_CONTEXT_VERSION, has_content_scope,
    production_guidance, stage_inputs, stage_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
DB_NAME = "stage_context.sqlite3"
MAX_BYTES = 2 * 1024 * 1024
TEXT_LIMIT = 16000
MAX_ITEMS = 128
SCOPE_KEYS = {"pipeline_type", "channel", "content_kind", "provider", "model", "mode", "video_format", "tags", "stages"}
PROFILE_KEYS = SCOPE_KEYS - {"stages"} | {"knowledge", "source_projects"}
CANONICAL = {"research": "research_brief", "proposal": "proposal_packet", "idea": "brief",
             "script": "script", "scene_plan": "scene_plan", "assets": "asset_manifest",
             "edit": "edit_decisions", "compose": "render_report", "publish": "publish_log"}


class StageContextError(ValueError):
    """Stage provenance, explicit decisions or semantic review is missing/stale."""


def _stage_writer(function=None, *, wait=0):
    """Serialize a full stage mutation, including its source preconditions."""
    if function is None:
        return lambda selected: _stage_writer(selected, wait=wait)
    @wraps(function)
    def guarded(project, *args, **kwargs):
        from lib.run_lock import RunWriterError, run_write_lock
        project = _project(project)
        try:
            with run_write_lock(project, timeout=wait):
                return function(project, *args, **kwargs)
        except RunWriterError as exc:
            raise StageContextError(str(exc)) from exc
    return guarded


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise StageContextError("Expected finite JSON data") from exc


def digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise StageContextError(f"{label} must be nonempty text")
    return value


def _now():
    return datetime.now(timezone.utc).isoformat()


def _project(project):
    path = Path(project).resolve()
    if not path.is_dir():
        raise StageContextError("Project directory does not exist")
    return path


def _safe(root, relative):
    """Explicit relative text paths only; prevent traversal, links and secrets."""
    relative = _text(relative, "relative path")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or ":" in relative or "\\" in relative:
        raise StageContextError("Unsafe relative path")
    if any(part.startswith(".") or re.search(r"secret|credential|token|password|private[-_.]?key|api[-_]?key|id_rsa|id_ed25519", part, re.I)
           for part in candidate.parts):
        raise StageContextError("Secret or hidden paths are not context sources")
    target = root / candidate
    if not target.resolve().is_relative_to(root.resolve()):
        raise StageContextError("Source path escapes its declared root")
    cursor = target
    while cursor != root:
        if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
            raise StageContextError("Linked sources are not allowed")
        cursor = cursor.parent
    return target


def _bytes(path):
    try:
        with path.open("rb") as stream:
            content = stream.read(MAX_BYTES + 1)
    except OSError as exc:
        raise StageContextError(f"Cannot read context source: {path.name}") from exc
    if len(content) > MAX_BYTES:
        raise StageContextError("Source exceeds 2 MiB bound")
    return content


def _read(root, name):
    try:
        return json.loads(_bytes(_safe(root, name)).decode("utf-8"))
    except (OSError, ValueError) as exc:
        if isinstance(exc, StageContextError):
            raise
        raise StageContextError(f"Invalid JSON source: {name}") from exc


def _marker(project):
    if not _safe(project, "project.json").exists():
        return {}
    marker = _read(project, "project.json")
    if not isinstance(marker, dict):
        raise StageContextError("project.json must be an object")
    return marker


def _scope(scope):
    if not isinstance(scope, dict) or not scope or set(scope) - SCOPE_KEYS:
        raise StageContextError("An explicit nonempty supported scope is required")
    for key, values in scope.items():
        if not isinstance(values, list) or not values or any(not isinstance(value, str) for value in values) or len(values) != len(set(values)):
            raise StageContextError(f"Scope {key} must be a nonempty unique text list")
        for value in values:
            _text(value, key)
    return scope


def _profile(profile):
    if not isinstance(profile, dict) or set(profile) - PROFILE_KEYS:
        raise StageContextError("Unsupported stage context profile")
    for key in SCOPE_KEYS - {"stages", "tags"}:
        if key in profile:
            _text(profile[key], key)
    for key in ("tags", "source_projects", "knowledge"):
        values = profile.get(key, [])
        if not isinstance(values, list) or len(values) > MAX_ITEMS:
            raise StageContextError(f"{key} must be a bounded array")
        if key != "knowledge":
            for value in values:
                _text(value, key)
    for item in profile.get("knowledge", []):
        _knowledge(item)
    return profile


def validate_profile(profile):
    """Validate activation input before init_project writes any marker."""
    return _profile(profile)


def serialize_marker(marker):
    """Use one readable, bounded UTF-8 representation at all marker writes."""
    payload = json.dumps(marker, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if len(payload.encode("utf-8")) > MAX_BYTES:
        raise StageContextError("Stage-context project marker exceeds 2 MiB; narrow the profile")
    return payload


def _knowledge(item):
    allowed = {"id", "text", "path", "private_skill", "scope", "version", "expires_at", "supersedes"}
    if not isinstance(item, dict) or set(item) - allowed:
        raise StageContextError("Invalid knowledge declaration")
    _text(item.get("id"), "knowledge id")
    _text(item.get("version"), "knowledge version")
    _scope(item.get("scope"))
    sources = [key for key in ("text", "path", "private_skill") if key in item]
    if len(sources) != 1:
        raise StageContextError("Declare exactly one text, path or private_skill knowledge source")
    _text(item[sources[0]], "knowledge source")
    if len(_json(item).encode()) > MAX_BYTES:
        raise StageContextError("Knowledge declaration exceeds bound")
    _expiry(item)
    if "supersedes" in item:
        _text(item["supersedes"], "supersedes")


def _private_skill_path(name, *, required=False):
    """Use only an explicitly bound, allowlisted canonical package."""
    from lib.workspace import WorkspaceError, private_skill_dir
    try:
        directory = private_skill_dir(name, repo_root=ROOT)
    except WorkspaceError as exc:
        raise StageContextError(str(exc)) from exc
    if directory is None:
        if required:
            raise StageContextError("Private skill is not selected by the workspace binding")
        return None
    return _safe(directory, "SKILL.md")


def _expiry(item):
    if "expires_at" not in item:
        return False
    try:
        stamp = datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError()
        return stamp <= datetime.now(timezone.utc)
    except (ValueError, TypeError, AttributeError) as exc:
        raise StageContextError("expires_at must be a timezone-aware ISO date") from exc


def _applicability(scope, profile, stage):
    for key, expected in scope.items():
        actual = [stage] if key == "stages" else profile.get(key)
        if key == "tags":
            matches = set(expected).issubset(actual or [])
        elif key == "stages":
            matches = stage in expected
        else:
            matches = actual in expected
        if not matches:
            return "inapplicable", f"scope mismatch: {key}"
    return "applicable", "declared scope matches"


def _db_path(project):
    return _safe(project, DB_NAME)


@contextmanager
def _journal(project):
    db = sqlite3.connect(_db_path(project), timeout=30)
    try:
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL)")
        db.execute("CREATE TRIGGER IF NOT EXISTS immutable_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'append-only events'); END")
        db.execute("CREATE TRIGGER IF NOT EXISTS immutable_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'append-only events'); END")
        owner = db.execute("SELECT value FROM metadata WHERE key='project'").fetchone()
        if owner and owner[0] != str(project):
            raise StageContextError("Stage journal belongs to another project")
        db.execute("INSERT OR IGNORE INTO metadata VALUES ('project', ?)", (str(project),))
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _events(project, kind):
    if not _db_path(project).exists():
        return []
    with closing(sqlite3.connect(_db_path(project).as_uri() + "?mode=ro", uri=True)) as db:
        owner = db.execute("SELECT value FROM metadata WHERE key='project'").fetchone()
        if not owner or owner[0] != str(project):
            raise StageContextError("Stage journal belongs to another project")
        result = []
        rows = db.execute("SELECT payload,digest FROM events WHERE kind=? ORDER BY seq", (kind,))
        for payload, stored_hash in rows:
            if len(payload.encode()) > MAX_BYTES + 4096:
                raise StageContextError("Journal record exceeds context bound")
            value = json.loads(payload)
            if digest(value) != stored_hash:
                raise StageContextError("Stage journal integrity mismatch")
            result.append(value)
    return result


def policy_enabled(project):
    if not Path(project).exists():
        return False
    project = _project(project)
    marker = _marker(project)
    policy = marker.get("stage_context_policy")
    if policy is None:
        if _db_path(project).exists():
            with closing(sqlite3.connect(_db_path(project).as_uri() + "?mode=ro", uri=True)) as db:
                if db.execute("SELECT value FROM metadata WHERE key='policy'").fetchone():
                    raise StageContextError("Stage context policy was removed")
        return False
    if not isinstance(policy, dict) or set(policy) != {"version", "required", "profile"} or not isinstance(policy.get("version"), str) or policy.get("version") not in CONTEXT_VERSIONS or policy.get("required") is not True:
        raise StageContextError("Invalid stage_context_policy; refusing to disable gate")
    _profile(policy["profile"])
    return True


@_stage_writer
def enable_policy(project, profile=None, *, version=DEFAULT_CONTEXT_VERSION):
    if not isinstance(version, str) or version not in CONTEXT_VERSIONS:
        raise StageContextError("Unsupported stage context policy version")
    project = _project(project)
    with _journal(project) as db:
        marker = _marker(project)
        existing = marker.get("stage_context_policy")
        if existing is not None:
            policy_enabled(project)
            if profile is not None and profile != existing["profile"]:
                raise StageContextError("Existing policy profile differs; preserve its provenance")
            policy = existing
        else:
            policy = {"version": version, "required": True, "profile": _profile(profile or {})}
            marker["stage_context_policy"] = policy
            payload = serialize_marker(marker)
            fd, temporary = tempfile.mkstemp(prefix="stage-policy-", suffix=".json", dir=project)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(payload)
                os.replace(temporary, _safe(project, "project.json"))
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        db.execute("INSERT OR IGNORE INTO metadata VALUES ('policy',?)", (policy["version"],))
    return policy


@_stage_writer
def configure_profile(project, profile):
    """Record an explicit configuration change and invalidate prior contexts."""
    project = _project(project)
    _profile(profile)
    if not policy_enabled(project):
        raise StageContextError("Enable policy before configuring its profile")
    with _journal(project) as db:
        marker = _marker(project)
        old = marker["stage_context_policy"]["profile"]
        if old == profile:
            return marker["stage_context_policy"]
        _put(db, "configuration", {"id": str(uuid.uuid4()), "created_at": _now(), "before": old, "after": profile})
        marker["stage_context_policy"]["profile"] = profile
        payload = serialize_marker(marker)
        fd, temporary = tempfile.mkstemp(prefix="stage-policy-", suffix=".json", dir=project)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
            os.replace(temporary, _safe(project, "project.json"))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return marker["stage_context_policy"]


def _put(db, kind, record):
    payload = _json(record)
    if len(payload.encode("utf-8")) > MAX_BYTES:
        raise StageContextError("Stage journal record exceeds 2 MiB")
    db.execute("INSERT INTO events(id,kind,payload,digest) VALUES (?,?,?,?)",
               (record["id"], kind, payload, digest(record)))


@_stage_writer(wait=10)
def append_feedback(project, feedback):
    """Append an owner correction or observation; never promote it to a rule."""
    project = _project(project)
    # Bounded waiting preserves concurrent appends while excluding migration
    # and owner reassignment across the complete SQLite transaction.
    allowed = {"text", "scope", "authority", "author", "polarity", "supersedes", "expires_at", "artifact_hash", "stage"}
    if not isinstance(feedback, dict) or set(feedback) - allowed:
        raise StageContextError("Invalid feedback fields")
    for key in ("text", "author"):
        _text(feedback.get(key), key)
    _scope(feedback.get("scope"))
    if feedback.get("authority") not in {"owner", "observation"} or feedback.get("polarity") not in {"positive", "negative", "neutral"}:
        raise StageContextError("Feedback requires explicit authority and polarity")
    if "artifact_hash" in feedback and (not isinstance(feedback["artifact_hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", feedback["artifact_hash"])):
        raise StageContextError("Feedback artifact_hash must be a canonical SHA-256")
    if "stage" in feedback:
        _text(feedback["stage"], "feedback stage")
    if len(_json(feedback).encode()) > MAX_BYTES:
        raise StageContextError("Feedback exceeds bound")
    _expiry(feedback)
    record = {**feedback, "id": str(uuid.uuid4()), "created_at": _now(), "source_project": str(project)}
    with _journal(project) as db:
        if feedback.get("supersedes"):
            prior = db.execute("SELECT payload FROM events WHERE id=? AND kind='feedback'", (feedback["supersedes"],)).fetchone()
            if not prior or json.loads(prior[0])["authority"] != feedback["authority"]:
                raise StageContextError("Feedback may supersede an existing record of the same authority only")
            if any(json.loads(row[0]).get("supersedes") == feedback["supersedes"] for row in db.execute("SELECT payload FROM events WHERE kind='feedback'")):
                raise StageContextError("Feedback was already superseded; append against its current successor")
        _put(db, "feedback", record)
    return record


def read_feedback(project):
    return _events(_project(project), "feedback")


def _item(identifier, kind, payload, *, authority="untrusted_source_data", reference=None, version="1.0", applicability="applicable", reason="stage input"):
    text = payload if isinstance(payload, str) else _json(payload)
    return {"id": identifier, "kind": kind, "authority": authority,
            "reference": reference or "inline", "version": version,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "content": text[:TEXT_LIMIT], "truncated": len(text) > TEXT_LIMIT,
            "full_length": len(text), "applicability": applicability, "reason": reason}


def _manifest(project):
    from lib.pipeline_loader import load_pipeline
    marker = _marker(project)
    pipeline = _text(marker.get("pipeline_type"), "pipeline_type")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", pipeline):
        raise StageContextError("Unsafe pipeline name")
    try:
        manifest = load_pipeline(pipeline)  # deliberately uncached: edits stale receipts
    except Exception as exc:
        raise StageContextError(f"Unable to load pipeline {pipeline}") from exc
    return marker, manifest


def _artifact(project, name, stage=None):
    """Canonical checkpoint owns its output; parallel file must agree if present."""
    checkpoint = None
    if stage and _safe(project, f"checkpoint_{stage}.json").exists():
        checkpoint = _read(project, f"checkpoint_{stage}.json")
        if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("artifacts"), dict):
            raise StageContextError("Invalid canonical checkpoint structure")
        if checkpoint.get("stage") != stage:
            raise StageContextError("Checkpoint stage identity mismatch")
    embedded = (checkpoint or {}).get("artifacts", {}).get(name)
    if name == "decision_log" and embedded is not None:
        # The root log is cumulative; the predecessor's record is a frozen
        # stage-owned snapshot and is expected to differ after later decisions.
        return embedded, checkpoint
    external = None
    for filename in (f"artifacts/{name}.json", f"{name}.json"):
        if _safe(project, filename).exists():
            value = _read(project, filename)
            if external is not None and value != external:
                raise StageContextError(f"Conflicting canonical {name} files")
            external = value
    if embedded is not None and external is not None and embedded != external:
        raise StageContextError(f"Canonical {name} differs from checkpoint")
    return embedded if embedded is not None else external, checkpoint


def _reusable_feedback(rows, profile, stage, *, cross_project=True):
    superseded = {row.get("supersedes") for row in rows}
    return [row for row in rows if row["id"] not in superseded and not _expiry(row)
            and (not cross_project or set(row["scope"]) & {"channel", "content_kind", "video_format", "tags"})
            and _applicability(row["scope"], profile, stage)[0] == "applicable"]


def _sources(project, profile, stage, *, lean=False):
    """Discover only direct siblings with project markers and feedback journals."""
    sources = [project]
    discovered = []
    feedback_cache = {}
    explicit = {(Path(value) if Path(value).is_absolute() else project.parent / value).resolve()
                for value in profile.get("source_projects", [])} if lean else set()
    candidates = [] if lean and not has_content_scope(profile) else list(islice(project.parent.iterdir(), 513))
    if len(candidates) > 512:
        raise StageContextError("Project root discovery exceeds 512 entries")
    for candidate in sorted(candidates, key=lambda path: path.name):
        if candidate == project or not candidate.is_dir() or candidate.is_symlink() or (hasattr(candidate, "is_junction") and candidate.is_junction()):
            continue
        if not (candidate / "project.json").is_file() or not (candidate / DB_NAME).is_file():
            continue
        marker = _marker(candidate)
        if marker.get("project_id") != candidate.name:
            continue
        rows = read_feedback(candidate)
        applicable = _reusable_feedback(rows, profile, stage)
        if lean and (applicable or candidate.resolve() in explicit):
            feedback_cache[candidate.resolve()] = rows
        if not applicable:
            continue
        sources.append(candidate.resolve())
        discovered.append(str(candidate.resolve()))
    for value in profile.get("source_projects", []):
        source = Path(value)
        if not source.is_absolute():
            source = project.parent / source
        if source.is_symlink() or (hasattr(source, "is_junction") and source.is_junction()):
            raise StageContextError("Linked source project is not allowed")
        source = _project(source)
        if source.parent != project.parent:
            raise StageContextError("Explicit source projects must be siblings in the canonical project root")
        if _marker(source).get("project_id") != source.name:
            raise StageContextError("Source project marker identity mismatch")
        if source not in sources:
            sources.append(source)
        if str(source) in discovered:
            discovered.remove(str(source))  # explicitly selected projects include exclusions
    return sources, discovered, feedback_cache


def _safe_lesson_sources(sources):
    """Validate paths before existing lesson reader follows ledger evidence refs."""
    for source in sources:
        path = _safe(source, "generation_quality.sqlite3")
        if not path.exists():
            continue
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            rows = db.execute("SELECT payload FROM requests ORDER BY rowid LIMIT 4097").fetchall()
        if len(rows) > 4096:
            raise StageContextError("Outcome ledger exceeds bounded context lookup")
        def walk(value):
            if isinstance(value, dict):
                if "path" in value and "sha256" in value:
                    ref = Path(value["path"])
                    if not ref.is_absolute() or not ref.resolve().is_relative_to(source):
                        raise StageContextError("Lesson evidence escapes source project")
                    _safe(source, ref.relative_to(source).as_posix())
                for nested in value.values():
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)
        for (payload,) in rows:
            if len(payload.encode()) > MAX_BYTES:
                raise StageContextError("Outcome record exceeds context bound")
            walk(json.loads(payload))


def build_stage_context(project, stage, *, _full_content=None):
    # Capture only the selected sources for bounded retrieval. This does not
    # change the persisted preview, its hash, or any historical reconstruction.
    def selected_item(identifier, kind, payload, **kwargs):
        if _full_content is not None:
            _full_content[identifier] = payload if isinstance(payload, str) else _json(payload)
        return _item(identifier, kind, payload, **kwargs)

    project = _project(project)
    if not policy_enabled(project):
        raise StageContextError("Enable stage context policy before stage entry")
    marker, manifest = _manifest(project)
    stages = [entry["name"] for entry in manifest["stages"]]
    if stage not in stages:
        raise StageContextError("Stage is not in project pipeline")
    for predecessor in ("script", "scene_plan"):
        if predecessor in stages and stages.index(stage) > stages.index(predecessor):
            _require_checkpoint(project, predecessor)
    entry = manifest["stages"][stages.index(stage)]
    profile = {**marker["stage_context_policy"]["profile"], "pipeline_type": marker["pipeline_type"]}
    context_version = marker["stage_context_policy"]["version"]
    lean = context_version == "1.1"
    if entry.get("skill"):
        director_path = _private_skill_path(entry["skill"])
        if director_path is None:
            director_path = _safe(ROOT, "skills/" + entry["skill"] + ".md")
        try:
            director = _bytes(director_path).decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise StageContextError("Manifest-selected director cannot be read") from exc
        director_item = selected_item("director", "director", director, authority="trusted_director",
                              reference=str(director_path), version=manifest["version"])
    else:
        director_item = selected_item("director", "manifest", "No director skill is declared for this stage by its manifest.",
                              authority="trusted_manifest", reference=f"pipeline_defs/{marker['pipeline_type']}.yaml", version=manifest["version"])
    manifest_content = {"selected": stage_manifest(manifest, stage), "full_source_sha256": digest(manifest)} if lean else manifest
    items = [director_item, selected_item("manifest", "manifest", manifest_content, authority="trusted_manifest",
                   reference=f"pipeline_defs/{marker['pipeline_type']}.yaml", version=manifest["version"]),
             selected_item("project_brief", "brief", {key: marker[key] for key in ("project_id", "title", "brief", "description", "request", "style_playbook") if key in marker})]
    guidance = _safe(ROOT, "AGENTS.md")
    if guidance.exists():
        guidance_text = _bytes(guidance).decode("utf-8")
        guidance_content = {"production_boundaries": production_guidance(guidance_text),
                            "full_source_sha256": hashlib.sha256(guidance_text.encode("utf-8")).hexdigest(),
                            "scope": "Selected production boundaries; complete native AGENTS precedence still applies. Read other sections when the task needs them."} if lean else guidance_text
        items.append(selected_item("project_guidance", "project_guidance", guidance_content,
                           authority="trusted_project_guidance", reference=str(guidance)))
    output_names = set(entry.get("produces", [])) | {CANONICAL.get(stage)}
    names = {}
    for prior in manifest["stages"][:stages.index(stage)]:
        for name in prior.get("produces", [CANONICAL.get(prior["name"])]):
            if not name:
                continue
            names[name] = prior["name"]
    for name in entry.get("required_artifacts_in", []) + entry.get("optional_artifacts_in", []) + ["brief", "video_analysis_brief", "source_media_review"]:
        names.setdefault(name, None)
    selected_names = stage_inputs(manifest, stage, CANONICAL) if lean else names
    names.update(selected_names)
    predecessor_fingerprints = {}
    for name, owner_stage in sorted(names.items()):
        if name in output_names:
            continue  # no circular inclusion of this stage's own output
        value, checkpoint = _artifact(project, name, owner_stage)
        if value is not None:
            content = {"artifact": value}
            if checkpoint:
                content["checkpoint"] = {key: checkpoint.get(key) for key in ("status", "human_approved")}
            if lean:
                # Keep existing transitive freshness gates without sending every
                # predecessor's full content or requiring an application item.
                predecessor_fingerprints[name] = digest(content)
                if name not in selected_names:
                    continue
            items.append(selected_item("artifact:" + name, "prior_artifact", content, reference=f"project:{name}"))
    knowledge = profile.get("knowledge", [])
    identifiers = [item["id"] for item in knowledge]
    if len(identifiers) != len(set(identifiers)):
        raise StageContextError("Duplicate knowledge ids")
    superseded = {item["supersedes"] for item in knowledge if "supersedes" in item}
    if superseded - set(identifiers):
        raise StageContextError("Unknown superseded knowledge")
    edges = {item["id"]: item.get("supersedes") for item in knowledge}
    for identifier in edges:
        seen = set()
        while identifier is not None:
            if identifier in seen:
                raise StageContextError("Knowledge supersession must be acyclic")
            seen.add(identifier)
            identifier = edges[identifier]
    for declaration in knowledge:
        status, reason = _applicability(declaration["scope"], profile, stage)
        if _expiry(declaration):
            status, reason = "inapplicable", "expired"
        if declaration["id"] in superseded:
            status, reason = "inapplicable", "superseded"
        content = declaration.get("text")
        reference = declaration.get("path", "inline")
        if "private_skill" in declaration:
            if status == "applicable":
                path = _private_skill_path(declaration["private_skill"], required=True)
                try:
                    content = _bytes(path).decode("utf-8")
                except UnicodeError as exc:
                    raise StageContextError("Private skill source must be UTF-8 text") from exc
                reference = str(path)
            else:
                content = "Private skill not read: " + reason
                reference = "unread private skill declaration"
        if "path" in declaration:
            _safe(project, declaration["path"])  # reject absolute/traversal before prefixing
            path = _safe(project, "knowledge/" + declaration["path"])
            if path.suffix.lower() not in {".md", ".txt", ".json"}:
                raise StageContextError("Knowledge references must be text, Markdown or JSON")
            try:
                content = _bytes(path).decode("utf-8")
            except UnicodeError as exc:
                raise StageContextError("Knowledge sources must be UTF-8 text") from exc
        items.append(selected_item("knowledge:" + declaration["id"], "knowledge", content,
                           reference=reference, version=declaration["version"],
                           applicability=status, reason=reason))
    sources, discovered, feedback_cache = _sources(project, profile, stage, lean=lean)
    for source in sources:
        feedback = feedback_cache[source] if source in feedback_cache else read_feedback(source)
        if source == project or str(source) in discovered:
            feedback = _reusable_feedback(feedback, profile, stage, cross_project=source != project)
        superseded_feedback = {row.get("supersedes") for row in feedback}
        for row in feedback:
            status, reason = _applicability(row["scope"], profile, stage)
            if source != project and not set(row["scope"]) & {"channel", "content_kind", "video_format", "tags"}:
                status, reason = "inapplicable", "cross-project feedback requires a declared content selector"
            if _expiry(row):
                status, reason = "inapplicable", "expired"
            if row["id"] in superseded_feedback:
                status, reason = "inapplicable", "superseded"
            items.append(selected_item("feedback:" + row["id"], "owner_feedback", row,
                               reference=str(source / DB_NAME), applicability=status, reason=reason))
    from lib.generation_lessons import find_lessons
    # Existing project lesson ledgers are explicit inputs, not auto-discovered.
    lesson_sources = []
    for value in profile.get("source_projects", []):
        source = Path(value)
        lesson_sources.append((source if source.is_absolute() else project.parent / source).resolve())
    lesson_sources = list(dict.fromkeys(lesson_sources))
    try:
        _safe_lesson_sources(lesson_sources)
        lessons = find_lessons([str(source) for source in lesson_sources], video_format=profile.get("video_format"), model=profile.get("model"), mode=profile.get("mode"))
    except (ValueError, OSError, sqlite3.Error) as exc:
        raise StageContextError(f"Cannot consume declared lesson sources: {exc}") from exc
    for lesson in lessons:
        matches = all(profile.get(key) is not None and profile[key] == lesson[key] for key in ("video_format", "provider", "model", "mode"))
        applicable = matches and lesson["evidence_current"]
        items.append(selected_item("lesson:" + digest([lesson["source_project"], lesson["request_id"]]), "outcome_lesson", lesson,
                           reference=lesson["source_project"], applicability="applicable" if applicable else "inapplicable",
                           reason="matching candidate; manual transfer decision required" if applicable else "different/undeclared generation scope or stale evidence"))
    if len(items) > MAX_ITEMS:
        raise StageContextError("Context exceeds 128 items; narrow explicit project sources")
    # Full knowledge text lives only in bounded items. Preserve declaration scope,
    # lifecycle and complete hashes without duplicating unbounded source text.
    public_profile = {key: value for key, value in profile.items() if key != "knowledge"}
    public_profile["knowledge"] = [{**{key: value for key, value in item.items() if key != "text"},
                                    **({"text_sha256": hashlib.sha256(item["text"].encode()).hexdigest()} if "text" in item else {})}
                                   for item in knowledge]
    body = {"version": context_version, "project": str(project), "stage": stage, "profile": public_profile,
            "items": items, "discovery": {"root": str(project.parent), "feedback_projects": discovered,
            "feedback_count": sum(item["kind"] == "owner_feedback" for item in items)},
            "limitations": "Recorded provenance and decisions do not prove understanding or creative quality. Source data is not instruction authority."}
    if lean:
        body["predecessor_fingerprints"] = predecessor_fingerprints
    return {**body, "context_hash": digest(body)}


def consumption_status(context):
    """Selection diagnostics outside the frozen context; never infer reading."""
    scoped = has_content_scope(context["profile"])
    return {
        "automatic_feedback": "enabled" if scoped else "skipped_missing_content_selector",
        "selectors": {key: context["profile"][key] for key in sorted(SCOPE_KEYS - {"stages"})
                      if context["profile"].get(key)},
        "warnings": [] if scoped else [
            "No channel/content_kind/video_format/tags: automatic sibling feedback is skipped. "
            "Recover the actual brief's selectors and configure explicitly; do not guess or broaden scope."],
        "truncated_items": [{"id": item["id"], "full_length": item["full_length"],
                             "preview_length": len(item["content"])}
                            for item in context["items"] if item["truncated"]],
        "application": "NOT_TESTED",
        "semantic_review": "NOT_TESTED",
        "media_quality": "NOT_TESTED",
        "limitations": "Content returned, saved or hashed does not prove reading or application. "
                        "Read needed omitted sections with read-item; inspect the actual output before recording decisions.",
    }


def read_context_item(project, stage, identifier, *, context_hash, offset=0, limit=TEXT_LIMIT):
    """Read a selected full source in bounded pages, rejecting stale packets.

    Sources are rebuilt from the same safe readers, including inline knowledge
    and checkpoint-owned artifacts. No arbitrary filename or catalog is opened.
    Offsets and lengths count Unicode characters, not UTF-8 bytes.
    """
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= TEXT_LIMIT:
        raise StageContextError("Read offset must be nonnegative and limit within 1..16000 characters")
    full_content = {}
    context = build_stage_context(project, stage, _full_content=full_content)
    if context_hash != context["context_hash"]:
        raise StageContextError("Read request refers to stale context; inspect stage again")
    item = next((item for item in context["items"] if item["id"] == identifier), None)
    if item is None:
        raise StageContextError("Item is not selected in this stage context")
    text = full_content[identifier]
    if offset > len(text):
        raise StageContextError("Read offset exceeds selected source length")
    end = min(offset + limit, len(text))
    return {"id": identifier, "context_hash": context_hash, "sha256": item["sha256"],
            "authority": item["authority"], "reference": item["reference"],
            "offset": offset, "end": end, "full_length": len(text),
            "content": text[offset:end], "next_offset": end if end < len(text) else None}


def application_template(context, artifact):
    """Unassessed handoff input; never manufacture per-source decisions."""
    return {"context_hash": context["context_hash"], "artifact_hash": digest(artifact),
            "reviewer": "NOT_TESTED", "decisions": [
                {"id": item["id"], "decision": "NOT_TESTED", "reason": "", "output_evidence": ""}
                for item in context["items"]]}


def _validate(name, value):
    try:
        schema = json.loads((ROOT / "schemas" / "artifacts" / f"{name}.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(value, schema)
    except (jsonschema.ValidationError, TypeError) as exc:
        raise StageContextError(f"Invalid {name}: {exc}") from exc


def _decisions(context, decisions):
    if not isinstance(decisions, list):
        raise StageContextError("decisions must be an array")
    expected = {item["id"]: item for item in context["items"]}
    if len(decisions) != len(expected) or {item.get("id") for item in decisions} != set(expected):
        raise StageContextError("Every context item requires exactly one explicit decision")
    for decision in decisions:
        if set(decision) != {"id", "decision", "reason", "output_evidence"}:
            raise StageContextError("Decision requires id, decision, reason, output_evidence")
        if decision["decision"] not in {"applied", "rejected", "inapplicable"}:
            raise StageContextError("Invalid application decision")
        _text(decision["reason"], "decision reason")
        _text(decision["output_evidence"], "output evidence or exclusion explanation")
        item = expected[decision["id"]]
        if item["applicability"] == "inapplicable" and decision["decision"] != "inapplicable":
            raise StageContextError("Expired, superseded or scope-mismatched knowledge cannot be applied")
        if item["authority"] in {"trusted_director", "trusted_manifest", "trusted_project_guidance"} and decision["decision"] != "applied":
            raise StageContextError("Manifest and selected director must be explicitly applied")


@_stage_writer
def record_application(project, stage, artifact, decisions, reviewer, *, context_hash):
    project = _project(project)
    context = build_stage_context(project, stage)
    if context_hash != context["context_hash"]:
        raise StageContextError("Application decisions refer to stale context")
    _decisions(context, decisions)
    if not isinstance(artifact, dict):
        raise StageContextError("Canonical artifact must be an object")
    if reviewer == "NOT_TESTED":
        raise StageContextError("Application needs a named reviewer")
    record = {"version": "1.0", "id": str(uuid.uuid4()), "stage": stage,
              "context_hash": context["context_hash"], "artifact_hash": digest(artifact),
              "reviewer": _text(reviewer, "reviewer"), "decisions": decisions, "created_at": _now()}
    _validate("knowledge_application", record)
    with _journal(project) as db:
        _put(db, "application", record)
    return record


def _criteria(context):
    if context["profile"].get("content_kind") == "functional_household":
        return ["context", "goal", "root_cause", "intervention", "payoff"]
    return ["declared_intent", "coherence", "payoff"]


def review_template(project, stage, artifact):
    context = build_stage_context(project, stage)
    return {"version": "1.0", "stage": stage, "context_hash": context["context_hash"],
            "artifact_hash": digest(artifact), "reviewer": "NOT_TESTED", "method": "not_performed",
            "checks": [{"id": criterion, "status": "NOT_TESTED", "observation": "", "evidence": ""}
                       for criterion in _criteria(context)]}


@_stage_writer
def record_logic_review(project, stage, artifact, review):
    project = _project(project)
    context = build_stage_context(project, stage)
    record = {**review, "id": str(uuid.uuid4()), "created_at": _now()}
    _validate("stage_logic_review", record)
    _review_matches(context, artifact, record, require_pass=False)
    with _journal(project) as db:
        _put(db, "review", record)
    return record


def _review_matches(context, artifact, record, *, require_pass=True):
    if record["context_hash"] != context["context_hash"] or record["artifact_hash"] != digest(artifact) or record["stage"] != context["stage"]:
        raise StageContextError("Logic review has stale context or canonical artifact")
    checks = record["checks"]
    if len(checks) != len(_criteria(context)) or {item["id"] for item in checks} != set(_criteria(context)):
        raise StageContextError("Logic review criteria do not match declared content kind")
    for check in checks:
        if check["status"] != "NOT_TESTED":
            _text(check["observation"], "semantic observation")
            _text(check["evidence"], "semantic evidence in canonical output")
            if record["method"] != "manual_semantic_review" or record["reviewer"] == "NOT_TESTED":
                raise StageContextError("Semantic assessment requires a named manual reviewer")
    if require_pass and any(check["status"] != "PASS" for check in checks):
        raise StageContextError("Required semantic logic review is FAIL or NOT_TESTED")


def _recorded(project, kind, record):
    if not _db_path(project).exists():
        raise StageContextError(f"Unrecorded or forged {kind} receipt")
    with closing(sqlite3.connect(_db_path(project).as_uri() + "?mode=ro", uri=True)) as db:
        owner = db.execute("SELECT value FROM metadata WHERE key='project'").fetchone()
        row = db.execute("SELECT payload,digest FROM events WHERE id=? AND kind=?", (record.get("id"), kind)).fetchone()
    if not owner or owner[0] != str(project) or not row or digest(record) != row[1] or _json(record) != row[0]:
        raise StageContextError(f"Unrecorded or forged {kind} receipt")


def enforce_stage_context(project, stage, status, artifacts):
    if status not in {"completed", "awaiting_human"} or not policy_enabled(project):
        return
    project = _project(project)
    context = build_stage_context(project, stage)
    if artifacts.get("stage_context") != context:
        raise StageContextError("Missing, forged or stale stage context; enter stage again")
    name = CANONICAL.get(stage)
    if name is None:
        _, manifest = _manifest(project)
        entry = next(entry for entry in manifest["stages"] if entry["name"] == stage)
        produced = entry.get("produces", [])
        if not produced:
            raise StageContextError("Stage requires a declared primary output for context binding")
        name = produced[0]
    if not isinstance(artifacts.get(name), dict):
        raise StageContextError("Missing canonical stage artifact")
    application = artifacts.get("knowledge_application")
    _validate("knowledge_application", application)
    if application["context_hash"] != context["context_hash"] or application["artifact_hash"] != digest(artifacts[name]) or application["stage"] != stage:
        raise StageContextError("Knowledge application has stale context or canonical artifact")
    _decisions(context, application["decisions"])
    _recorded(project, "application", application)
    if stage == "script":
        review = artifacts.get("stage_logic_review")
        _validate("stage_logic_review", review)
        _review_matches(context, artifacts[name], review)
        _recorded(project, "review", review)


def _require_checkpoint(project, stage, *, optional=False):
    _, manifest = _manifest(project)
    entry = next((entry for entry in manifest["stages"] if entry["name"] == stage), None)
    if entry is None and optional:
        return
    path = _safe(project, f"checkpoint_{stage}.json")
    if entry is None or not path.exists():
        raise StageContextError(f"Current {stage} checkpoint is required")
    checkpoint = _read(project, path.name)
    marker = _marker(project)
    if checkpoint.get("project_id") != marker.get("project_id") or checkpoint.get("pipeline_type") != marker.get("pipeline_type"):
        raise StageContextError(f"Current {stage} checkpoint project/pipeline identity mismatch")
    if checkpoint.get("stage") != stage or checkpoint.get("status") != "completed":
        raise StageContextError(f"Current {stage} checkpoint must be completed")
    if entry.get("human_approval_default") and checkpoint.get("human_approved") is not True:
        raise StageContextError(f"Current {stage} checkpoint needs human approval")
    value, _ = _artifact(project, CANONICAL[stage], stage)
    if value is None:
        raise StageContextError(f"Current {stage} artifact is missing")
    enforce_stage_context(project, stage, "completed", checkpoint.get("artifacts", {}))
    return {"context_hash": checkpoint["artifacts"]["stage_context"]["context_hash"],
            "artifact_hash": digest(value)}


def require_generation_context(project):
    if not policy_enabled(project):
        return
    project = _project(project)
    return {"version": "1.0", "script": _require_checkpoint(project, "script", optional=True),
            "scene_plan": _require_checkpoint(project, "scene_plan")}
