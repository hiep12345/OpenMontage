"""Offline provenance/semantic-attestation tests; no creative quality claims."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess

import pytest

from lib import stage_context as sc


def make_project(root, name="current", profile=None):
    project = root / name
    project.mkdir()
    (project / "project.json").write_text(json.dumps({"project_id": name, "pipeline_type": "cinematic", "title": "A functional reading corner", "brief": "Resolve glare while retaining daylight"}), encoding="utf-8")
    sc.enable_policy(project, profile or {"content_kind": "functional_household", "channel": "home", "tags": ["reading"]})
    return project


def script():
    return {"version": "1.0", "title": "Glare resolved", "total_duration_seconds": 12,
            "sections": [{"id": "context", "text": "A reader squints at sun glare. A diffusing blind softens the light; the reader continues comfortably.", "start_seconds": 0, "end_seconds": 12}]}


def decisions(context):
    return [{"id": item["id"], "decision": "applied" if item["applicability"] == "applicable" else "inapplicable",
             "reason": "Fixture decision refers to the exact source content", "output_evidence": "Fixture: section context addresses glare and visible resolution"}
            for item in context["items"]]


def receipt(project, stage="script", artifact=None, review_status="PASS"):
    artifact = artifact or script()
    context = sc.build_stage_context(project, stage)
    application = sc.record_application(project, stage, artifact, decisions(context), "fixture reviewer", context_hash=context["context_hash"])
    packet = {sc.CANONICAL[stage]: artifact, "stage_context": context, "knowledge_application": application}
    if stage == "script":
        review = sc.review_template(project, stage, artifact)
        if review_status != "NOT_TESTED":
            review["reviewer"] = "fixture reviewer"
            review["method"] = "manual_semantic_review"
            for check in review["checks"]:
                check.update(status=review_status, observation="Fixture: glare motivates a diffusing blind", evidence="sections[0].text")
        packet["stage_logic_review"] = sc.record_logic_review(project, stage, artifact, review)
    return packet


def checkpoint(project, stage, artifacts):
    marker = json.loads((project / "project.json").read_text(encoding="utf-8"))
    (project / f"checkpoint_{stage}.json").write_text(json.dumps({"project_id": marker["project_id"], "pipeline_type": marker["pipeline_type"], "stage": stage, "status": "completed", "human_approved": True, "artifacts": artifacts}), encoding="utf-8")


def feedback(**changes):
    return {"text": "Decoration alone did not solve reading glare; show the intervention and its result",
            "scope": {"content_kind": ["functional_household"], "channel": ["home"], "tags": ["reading"]},
            "authority": "owner", "author": "owner", "polarity": "negative", **changes}


def test_context_is_deterministic_actual_director_and_checkpoint_artifacts(tmp_path):
    project = make_project(tmp_path)
    checkpoint(project, "proposal", {"proposal_packet": {"selected": "diffused daylight"}})
    first = sc.build_stage_context(project, "script")
    assert first == sc.build_stage_context(project, "script")
    selected = next(item for item in first["items"] if item["id"] == "director")
    assert selected["authority"] == "trusted_director"
    assert selected["reference"].endswith("script-director.md")
    assert selected["sha256"] == sc.hashlib.sha256(Path(selected["reference"]).read_bytes()).hexdigest()
    assert "diffused daylight" in next(item["content"] for item in first["items"] if item["id"] == "artifact:proposal_packet")
    checkpoint(project, "script", {"script": script()})
    assert first == sc.build_stage_context(project, "script")  # no circular output digest
    sc._validate("stage_context", first)


def test_complete_receipt_and_changed_output_blocked(tmp_path):
    project = make_project(tmp_path)
    packet = receipt(project)
    sc.enforce_stage_context(project, "script", "completed", packet)
    packet["script"]["title"] = "A changed intent"
    with pytest.raises(sc.StageContextError, match="stale"):
        sc.enforce_stage_context(project, "script", "completed", packet)


@pytest.mark.parametrize("status", ["FAIL", "NOT_TESTED"])
def test_logic_failure_and_not_tested_block_readiness(tmp_path, status):
    project = make_project(tmp_path)
    packet = receipt(project, review_status=status)
    with pytest.raises(sc.StageContextError, match="FAIL or NOT_TESTED"):
        sc.enforce_stage_context(project, "script", "awaiting_human", packet)
    sc.enforce_stage_context(project, "script", "in_progress", {})


def test_missing_review_and_forged_application_blocked(tmp_path):
    project = make_project(tmp_path)
    packet = receipt(project)
    review = packet.pop("stage_logic_review")
    with pytest.raises(sc.StageContextError, match="Invalid stage_logic_review"):
        sc.enforce_stage_context(project, "script", "completed", packet)
    packet["stage_logic_review"] = review
    packet["knowledge_application"]["reviewer"] = "forged reviewer"
    with pytest.raises(sc.StageContextError, match="forged"):
        sc.enforce_stage_context(project, "script", "completed", packet)


def test_forged_context_and_changed_brief_stale(tmp_path):
    project = make_project(tmp_path)
    packet = receipt(project)
    packet["stage_context"]["items"][0]["content"] = "forged director"
    with pytest.raises(sc.StageContextError, match="forged or stale"):
        sc.enforce_stage_context(project, "script", "completed", packet)
    context = sc.build_stage_context(project, "script")
    marker = json.loads((project / "project.json").read_text())
    marker["brief"] = "A different goal"
    (project / "project.json").write_text(json.dumps(marker))
    with pytest.raises(sc.StageContextError, match="stale context"):
        sc.record_application(project, "script", script(), decisions(context), "reviewer", context_hash=context["context_hash"])


@pytest.mark.parametrize("key,value", [("provider", "other-provider"), ("model", "other-model"), ("mode", "other-mode"), ("tags", "other-tag")])
def test_scoped_knowledge_rejects_incompatible_values(tmp_path, key, value):
    scope = {"provider": ["flow"], "model": ["omni"], "mode": ["text"], "tags": ["reading"]}
    profile = {"provider": "flow", "model": "omni", "mode": "text", "tags": ["reading"],
               "knowledge": [{"id": "framing", "version": "1", "text": "Keep the functional intervention legible", "scope": scope}]}
    profile[key] = [value] if key == "tags" else value
    project = make_project(tmp_path, profile=profile)
    context = sc.build_stage_context(project, "script")
    item = next(item for item in context["items"] if item["id"] == "knowledge:framing")
    assert item["applicability"] == "inapplicable"
    assert key in item["reason"]
    choices = decisions(context)
    choices[-1]["decision"] = "applied"
    with pytest.raises(sc.StageContextError, match="cannot be applied"):
        sc.record_application(project, "script", script(), choices, "reviewer", context_hash=context["context_hash"])


def test_expiry_supersession_and_visible_truncation(tmp_path):
    scope = {"stages": ["script"]}
    profile = {"knowledge": [
        {"id": "old", "version": "1", "text": "old evidence", "scope": scope},
        {"id": "new", "version": "2", "text": "new evidence", "scope": scope, "supersedes": "old"},
        {"id": "expired", "version": "1", "text": "past evidence", "scope": scope, "expires_at": "2000-01-01T00:00:00Z"},
        {"id": "long", "version": "1", "text": "x" * (sc.TEXT_LIMIT + 100), "scope": scope}]}
    project = make_project(tmp_path, profile=profile)
    items = {item["id"]: item for item in sc.build_stage_context(project, "script")["items"]}
    assert items["knowledge:old"]["reason"] == "superseded"
    assert items["knowledge:expired"]["reason"] == "expired"
    assert items["knowledge:long"]["truncated"]
    assert items["knowledge:long"]["full_length"] == sc.TEXT_LIMIT + 100


def test_local_reference_content_change_invalidates_receipt(tmp_path):
    project = make_project(tmp_path, profile={"knowledge": [{"id": "local", "version": "1", "path": "lesson.md", "scope": {"stages": ["script"]}}]})
    (project / "knowledge").mkdir()
    path = project / "knowledge" / "lesson.md"
    path.write_text("The accepted root cause is glare", encoding="utf-8")
    packet = receipt(project)
    path.write_text("The accepted root cause is dampness", encoding="utf-8")
    with pytest.raises(sc.StageContextError, match="stale stage context"):
        sc.enforce_stage_context(project, "script", "completed", packet)


@pytest.mark.parametrize("path", ["../project.json", "C:/private.json", ".env", "secret.json", "credentials.md", "nested/../../x.txt", "token.txt", "id_rsa.txt", "api-key.json"])
def test_unsafe_knowledge_reference_rejected(tmp_path, path):
    project = make_project(tmp_path, profile={"knowledge": [{"id": "unsafe", "version": "1", "path": path, "scope": {"stages": ["script"]}}]})
    with pytest.raises(sc.StageContextError):
        sc.build_stage_context(project, "script")


def test_feedback_append_only_supersession_and_matching_future_project(tmp_path):
    previous = make_project(tmp_path, "previous")
    first = sc.append_feedback(previous, feedback())
    second = sc.append_feedback(previous, feedback(text="The revised diffusing blind solves glare", polarity="positive", supersedes=first["id"]))
    assert len(sc.read_feedback(previous)) == 2
    with sqlite3.connect(previous / sc.DB_NAME) as db:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute("DELETE FROM events")
    with pytest.raises(sc.StageContextError, match="already superseded"):
        sc.append_feedback(previous, feedback(supersedes=first["id"]))
    current = make_project(tmp_path)
    context = sc.build_stage_context(current, "script")
    items = {item["id"]: item for item in context["items"]}
    assert "feedback:" + first["id"] not in items  # retained in history, inactive for automatic reuse
    assert items["feedback:" + second["id"]]["applicability"] == "applicable"
    assert items["feedback:" + second["id"]]["authority"] == "untrusted_source_data"
    assert context["discovery"]["feedback_projects"] == [str(previous)]
    assert sc.read_feedback(previous)[0] == first


def test_incompatible_and_broad_feedback_cannot_become_universal(tmp_path):
    prior = make_project(tmp_path, "prior")
    incompatible = sc.append_feedback(prior, feedback(scope={"content_kind": ["abstract"]}))
    broad = sc.append_feedback(prior, feedback(scope={"stages": ["script"]}))
    current = make_project(tmp_path)
    items = {item["id"]: item for item in sc.build_stage_context(current, "script")["items"]}
    assert "feedback:" + incompatible["id"] not in items
    assert "feedback:" + broad["id"] not in items
    with pytest.raises(sc.StageContextError, match="nonempty"):
        sc.append_feedback(prior, feedback(scope={}))


def test_concurrent_feedback_appends_survive_restart(tmp_path):
    project = make_project(tmp_path)
    with ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(lambda number: sc.append_feedback(project, feedback(text=f"Observation {number}")), range(20)))
    persisted = sc.read_feedback(project)
    assert len(persisted) == len({row["id"] for row in persisted}) == 20
    assert {row["id"] for row in persisted} == {row["id"] for row in records}


def test_feedback_stales_existing_context(tmp_path):
    project = make_project(tmp_path)
    packet = receipt(project)
    sc.append_feedback(project, feedback())
    with pytest.raises(sc.StageContextError, match="stale"):
        sc.enforce_stage_context(project, "script", "completed", packet)


def test_generic_semantic_review_does_not_inherit_household_restrictions(tmp_path):
    project = make_project(tmp_path, profile={"content_kind": "abstract_montage"})
    review = sc.review_template(project, "script", script())
    assert {item["id"] for item in review["checks"]} == {"declared_intent", "coherence", "payoff"}
    assert all(item["status"] == "NOT_TESTED" for item in review["checks"])


def test_generation_revalidates_current_script_and_scene_checkpoints(tmp_path):
    project = make_project(tmp_path)
    with pytest.raises(sc.StageContextError, match="script checkpoint"):
        sc.require_generation_context(project)
    checkpoint(project, "script", receipt(project))
    plan = {"version": "1.0", "scenes": []}
    checkpoint(project, "scene_plan", receipt(project, "scene_plan", plan))
    sc.require_generation_context(project)
    path = project / "checkpoint_script.json"
    altered = json.loads(path.read_text())
    altered["artifacts"]["script"]["title"] = "Silently changed"
    path.write_text(json.dumps(altered))
    with pytest.raises(sc.StageContextError, match="stale"):
        sc.require_generation_context(project)


def test_policy_legacy_noop_and_removal_fails_closed(tmp_path):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    assert not sc.policy_enabled(legacy)
    sc.enforce_stage_context(legacy, "script", "completed", {})
    sc.require_generation_context(legacy)
    assert list(legacy.iterdir()) == []
    sc.enforce_stage_context(tmp_path / "not-created", "script", "completed", {})
    project = make_project(tmp_path)
    marker = json.loads((project / "project.json").read_text())
    del marker["stage_context_policy"]
    (project / "project.json").write_text(json.dumps(marker))
    with pytest.raises(sc.StageContextError, match="removed"):
        sc.policy_enabled(project)
    sc.enforce_stage_context(project, "script", "in_progress", {})
    sc.enforce_stage_context(project, "script", "failed", {})


def test_configuration_change_journaled_and_stales_context(tmp_path):
    project = make_project(tmp_path)
    packet = receipt(project)
    sc.configure_profile(project, {"content_kind": "abstract_montage"})
    assert sc._events(project, "configuration")[0]["before"]["content_kind"] == "functional_household"
    with pytest.raises(sc.StageContextError, match="stale"):
        sc.enforce_stage_context(project, "script", "completed", packet)


def test_source_projects_cannot_escape_canonical_root(tmp_path):
    nested = tmp_path / "canonical"
    nested.mkdir()
    outside = make_project(tmp_path, "outside")
    current = make_project(nested, profile={"source_projects": [str(outside)]})
    with pytest.raises(sc.StageContextError, match="siblings"):
        sc.build_stage_context(current, "script")


def test_current_artifact_file_conflict_blocked(tmp_path):
    project = make_project(tmp_path)
    checkpoint(project, "script", receipt(project))
    (project / "script.json").write_text(json.dumps({**script(), "title": "Not checkpoint content"}))
    with pytest.raises(sc.StageContextError, match="differs from checkpoint"):
        sc.build_stage_context(project, "scene_plan")


def test_explicit_generation_lesson_selection_reuses_existing_reader(tmp_path, monkeypatch):
    previous = make_project(tmp_path, "previous")
    current = make_project(tmp_path, profile={"source_projects": [str(previous)], "provider": "flow", "model": "omni", "mode": "text", "video_format": "home"})
    calls = []
    def find(projects, **kwargs):
        calls.append((projects, kwargs))
        return [{"source_project": str(previous), "request_id": "corrected", "provider": "flow", "model": "omni", "mode": "text", "video_format": "home", "evidence_current": True, "failures": [{"status": "FAIL", "observation": "glare remains"}], "correction": {"change": "diffuse glare"}}]
    monkeypatch.setattr("lib.generation_lessons.find_lessons", find)
    result = sc.build_stage_context(current, "script")
    assert calls[0][0] == [str(previous)]
    lesson = next(item for item in result["items"] if item["kind"] == "outcome_lesson")
    assert lesson["applicability"] == "applicable"
    assert "manual transfer decision" in lesson["reason"]
    assert "glare remains" in lesson["content"]


def test_no_decision_autopass_missing_explanations_or_director_rejection(tmp_path):
    project = make_project(tmp_path)
    context = sc.build_stage_context(project, "script")
    choices = decisions(context)
    choices[0]["decision"] = "rejected"
    with pytest.raises(sc.StageContextError, match="director"):
        sc.record_application(project, "script", script(), choices, "reviewer", context_hash=context["context_hash"])
    with pytest.raises(sc.StageContextError, match="Every context item"):
        sc.record_application(project, "script", script(), choices[1:], "reviewer", context_hash=context["context_hash"])


def test_review_requires_named_manual_assessment_and_exact_criteria(tmp_path):
    project = make_project(tmp_path)
    review = sc.review_template(project, "script", script())
    for check in review["checks"]:
        check.update(status="PASS", observation="text inspected", evidence="sections[0]")
    with pytest.raises(sc.StageContextError, match="named manual reviewer"):
        sc.record_logic_review(project, "script", script(), review)
    review.update(reviewer="tester", method="manual_semantic_review")
    review["checks"].pop()
    with pytest.raises(sc.StageContextError, match="criteria"):
        sc.record_logic_review(project, "script", script(), review)


@pytest.mark.parametrize("stage", ["scene_plan", "assets"])
def test_stage_entry_blocks_unreviewed_script_before_asset_work(tmp_path, stage):
    project = make_project(tmp_path)
    with pytest.raises(sc.StageContextError, match="script checkpoint"):
        sc.build_stage_context(project, stage)
    checkpoint(project, "script", receipt(project, review_status="NOT_TESTED"))
    with pytest.raises(sc.StageContextError, match="NOT_TESTED"):
        sc.build_stage_context(project, stage)


def test_framework_manifest_without_director_is_explicit(tmp_path):
    project = make_project(tmp_path)
    marker = json.loads((project / "project.json").read_text())
    marker["pipeline_type"] = "framework-smoke"
    (project / "project.json").write_text(json.dumps(marker))
    context = sc.build_stage_context(project, "script")
    assert context["items"][0]["authority"] == "trusted_manifest"
    assert "No director skill is declared" in context["items"][0]["content"]
    packet = receipt(project)
    sc.enforce_stage_context(project, "script", "completed", packet)


def test_linked_knowledge_directory_is_rejected(tmp_path):
    project = make_project(tmp_path, profile={"knowledge": [{"id": "local", "version": "1", "path": "lesson.md", "scope": {"stages": ["script"]}}]})
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "lesson.md").write_text("external content")
    try:
        (project / "knowledge").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt" or not hasattr(Path(), "is_junction"):
            pytest.skip(f"Host cannot create a symlink: {exc}")
        link = str(project / "knowledge").replace("'", "''")
        target = str(outside).replace("'", "''")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                                 f"New-Item -ItemType Junction -Path '{link}' -Target '{target}' -ErrorAction Stop | Out-Null"],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    with pytest.raises(sc.StageContextError, match="escapes|Linked"):
        sc.build_stage_context(project, "script")


def test_director_content_change_invalidates_context(tmp_path, monkeypatch):
    project = make_project(tmp_path)
    selected = tmp_path / "repository" / "skills" / "pipelines" / "cinematic" / "script-director.md"
    selected.parent.mkdir(parents=True)
    selected.write_text("Director version one")
    monkeypatch.setattr(sc, "ROOT", tmp_path / "repository")
    first = sc.build_stage_context(project, "script")
    selected.write_text("Director version two")
    second = sc.build_stage_context(project, "script")
    assert first["context_hash"] != second["context_hash"]
    assert first["items"][0]["sha256"] != second["items"][0]["sha256"]


def test_empty_or_unrelated_sibling_does_not_stale_context(tmp_path):
    project = make_project(tmp_path)
    first = sc.build_stage_context(project, "script")
    sibling = make_project(tmp_path, "unrelated")
    assert sc.build_stage_context(project, "script") == first
    sc.append_feedback(sibling, feedback(scope={"content_kind": ["abstract"]}))
    assert sc.build_stage_context(project, "script") == first


def test_actual_retained_failure_ledger_is_selected_without_paid_io(tmp_path):
    # Exercise the real read-only lesson consumer with its retained ledger
    # contract, without importing unrelated generation submission adapters.
    previous = make_project(tmp_path, "previous")
    output = previous / "correction.mp4"
    output.write_bytes(b"synthetic evidence; no actual video review")
    ref = {"path": str(output), "sha256": sc.hashlib.sha256(output.read_bytes()).hexdigest()}
    prior = {"request_id": "initial", "contract": {"intent": "Visible intervention",
        "video_format": "home", "aesthetic": "editorial",
        "requirements": [{"id": "framing", "kind": "visual"}]},
        "reviews": [{"checks": [{"id": "framing", "status": "FAIL",
            "observation": "Intervention obscured", "evidence": [ref]}]}]}
    corrected = {"request_id": "corrected", "retry": {"prior_request_id": "initial", "change": "Reframe"},
        "provider": "Google Flow", "model": "selected-model", "mode": "selected-mode",
        "status": "accepted", "reviews": [{"checks": [{"id": "framing", "status": "PASS", "evidence": [ref]}]}]}
    with sqlite3.connect(previous / "generation_quality.sqlite3") as db:
        db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO metadata VALUES ('project', ?)", (str(previous),))
        db.execute("CREATE TABLE requests (payload TEXT, digest TEXT)")
        for row in (prior, corrected):
            payload = sc._json(row)
            db.execute("INSERT INTO requests VALUES (?,?)", (payload, sc.hashlib.sha256(payload.encode()).hexdigest()))
    current = make_project(tmp_path, profile={"source_projects": [str(previous)], "provider": "Google Flow",
        "model": "selected-model", "mode": "selected-mode", "video_format": "home"})
    stage = sc.build_stage_context(current, "script")
    candidate = next(item for item in stage["items"] if item["kind"] == "outcome_lesson")
    assert candidate["applicability"] == "applicable"
    assert "Intervention obscured" in candidate["content"]
    output.write_bytes(b"changed evidence")
    changed = sc.build_stage_context(current, "script")
    assert changed["context_hash"] != stage["context_hash"]
    assert next(item for item in changed["items"] if item["kind"] == "outcome_lesson")["applicability"] == "inapplicable"


def test_character_animation_primary_output_and_secondary_prior_artifact(tmp_path):
    project = make_project(tmp_path)
    marker = json.loads((project / "project.json").read_text())
    marker["pipeline_type"] = "character-animation"
    (project / "project.json").write_text(json.dumps(marker))
    checkpoint(project, "script", receipt(project))
    context = sc.build_stage_context(project, "rig_plan")
    primary = {"version": "1.0", "rig": "fixture"}
    application = sc.record_application(project, "rig_plan", primary, decisions(context), "fixture reviewer", context_hash=context["context_hash"])
    packet = {"stage_context": context, "knowledge_application": application, "rig_plan": primary, "pose_library": {"pose": "fixture"}}
    sc.enforce_stage_context(project, "rig_plan", "completed", packet)
    checkpoint(project, "rig_plan", packet)
    scene = sc.build_stage_context(project, "scene_plan")
    assert any(item["id"] == "artifact:pose_library" for item in scene["items"])
