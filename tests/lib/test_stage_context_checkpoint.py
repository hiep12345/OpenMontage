"""Offline checkpoint integration; fixture attestations do not establish quality."""
from copy import deepcopy
import json
import socket

import pytest

from lib import stage_context as sc
from lib.checkpoint import CheckpointValidationError, init_project, write_checkpoint
from tests.contracts.test_phase0_contracts import sample_artifact


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Checkpoint integration must not make network/provider calls")
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def project(root, *, pipeline="framework-smoke", **kwargs):
    return init_project("run", title="Reading glare", pipeline_type=pipeline, pipeline_dir=root, **kwargs)


def packet(path, stage, *, review_status="PASS"):
    artifact = sample_artifact(sc.CANONICAL[stage])
    context = sc.build_stage_context(path, stage)
    decisions = [
        {"id": item["id"], "decision": "applied" if item["applicability"] == "applicable" else "inapplicable",
         "reason": "Fixture decision bound to this source", "output_evidence": "Fixture canonical output reviewed"}
        for item in context["items"]
    ]
    application = sc.record_application(path, stage, artifact, decisions, "fixture reviewer", context_hash=context["context_hash"])
    result = {sc.CANONICAL[stage]: artifact, "stage_context": context, "knowledge_application": application}
    if stage == "script":
        review = sc.review_template(path, stage, artifact)
        if review_status != "NOT_TESTED":
            review.update(reviewer="fixture reviewer", method="manual_semantic_review")
            for check in review["checks"]:
                check.update(status=review_status, observation="Fixture intent is coherent", evidence="sections[0].text")
        result["stage_logic_review"] = sc.record_logic_review(path, stage, artifact, review)
    return result


def advance(path, stage, artifacts, status="completed", **kwargs):
    return write_checkpoint(path.parent, path.name, stage, status, artifacts, human_approved=True, **kwargs)


def test_new_project_defaults_to_context_and_reinit_preserves_policy(tmp_path):
    path = project(tmp_path, stage_context_profile={"channel": "home"})
    before = json.loads((path / "project.json").read_text(encoding="utf-8"))
    assert before["stage_context_policy"] == {"version": "1.1", "required": True, "profile": {"channel": "home"}}
    assert (path / sc.DB_NAME).is_file()
    project(tmp_path, stage_context_required=False)
    after = json.loads((path / "project.json").read_text(encoding="utf-8"))
    assert after["stage_context_policy"] == before["stage_context_policy"]
    assert after["created_at"] == before["created_at"]
    with pytest.raises(CheckpointValidationError, match="stage context"):
        advance(path, "research", {"research_brief": sample_artifact("research_brief")})


def test_existing_legacy_project_remains_legacy_until_explicit_activation(tmp_path):
    path = tmp_path / "run"
    path.mkdir()
    marker = {"version": "1.0", "project_id": "run", "pipeline_type": "framework-smoke", "created_at": "original"}
    (path / "project.json").write_text(json.dumps(marker), encoding="utf-8")
    project(tmp_path)
    assert not sc.policy_enabled(path)
    assert not (path / sc.DB_NAME).exists()
    advance(path, "research", {"research_brief": sample_artifact("research_brief")})
    project(tmp_path, stage_context_required=True)
    assert sc.policy_enabled(path)
    assert json.loads((path / "project.json").read_text())["created_at"] == "original"


def test_existing_version_10_policy_is_preserved(tmp_path):
    path = project(tmp_path, stage_context_required=False)
    sc.enable_policy(path, {"channel": "home"}, version="1.0")
    project(tmp_path)
    assert json.loads((path / "project.json").read_text())["stage_context_policy"]["version"] == "1.0"


@pytest.mark.parametrize("options", [
    {"stage_context_profile": {"unsupported": "x"}},
    {"stage_context_required": False, "stage_context_profile": {}},
])
def test_invalid_activation_never_creates_project(tmp_path, options):
    with pytest.raises(ValueError):
        project(tmp_path, **options)
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("active", [False, True])
def test_profile_conflict_does_not_rewrite_existing_marker(tmp_path, active):
    path = project(tmp_path, stage_context_required=active)
    marker = path / "project.json"
    original = marker.read_bytes()
    with pytest.raises(CheckpointValidationError):
        project(tmp_path, stage_context_profile={"channel": "changed"})
    assert marker.read_bytes() == original


@pytest.mark.parametrize("status", ["completed", "awaiting_human"])
@pytest.mark.parametrize("invalid", ["missing", "forged_application", "forged_context", "changed_output", "changed_brief", "missing_review", "NOT_TESTED", "FAIL"])
def test_invalid_stage_evidence_blocks_advancement_without_writes(tmp_path, status, invalid):
    path = project(tmp_path)
    advance(path, "research", packet(path, "research"))
    artifacts = packet(path, "script", review_status=invalid if invalid in {"NOT_TESTED", "FAIL"} else "PASS")
    if invalid == "missing":
        artifacts.pop("stage_context")
    elif invalid == "forged_application":
        artifacts["knowledge_application"]["reviewer"] = "forged reviewer"
    elif invalid == "forged_context":
        artifacts["stage_context"]["items"][0]["content"] = "forged manifest"
    elif invalid == "changed_output":
        artifacts["script"]["title"] = "Changed authored output"
    elif invalid == "changed_brief":
        marker = json.loads((path / "project.json").read_text())
        marker["title"] = "Changed intent"
        (path / "project.json").write_text(json.dumps(marker), encoding="utf-8")
    elif invalid == "missing_review":
        artifacts.pop("stage_logic_review")
    artifacts["decision_log"] = {"version": "1.0", "project_id": "run", "decisions": []}
    original = deepcopy(artifacts)
    with pytest.raises(CheckpointValidationError):
        advance(path, "script", artifacts, status)
    assert artifacts == original
    assert not (path / "checkpoint_script.json").exists()
    assert not (path / "decision_log.json").exists()
    assert not (path / "history").exists()


def test_heartbeat_can_record_incomplete_context(tmp_path):
    path = project(tmp_path)
    assert advance(path, "script", {}, "in_progress").is_file()


def test_bound_script_can_advance_through_human_gate(tmp_path):
    path = project(tmp_path)
    advance(path, "research", packet(path, "research"))
    artifacts = packet(path, "script")
    original = deepcopy(artifacts)
    advance(path, "script", artifacts, "awaiting_human")
    checkpoint = advance(path, "script", artifacts)
    stored = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert stored["status"] == "completed"
    assert stored["artifacts"] == artifacts == original
    assert len(list((path / "history").glob("checkpoint_script_*.json"))) == 1


def test_decision_reference_preserves_exact_authored_proposal_and_render(tmp_path):
    path = project(tmp_path, pipeline="cinematic")
    advance(path, "research", packet(path, "research"))
    artifacts = packet(path, "proposal")
    artifacts["render_report"] = sample_artifact("render_report")
    artifacts["decision_log"] = {"version": "1.0", "project_id": "run", "decisions": []}
    original = deepcopy(artifacts)
    metadata = {"owner_note": "Keep authored bytes"}
    checkpoint = advance(path, "proposal", artifacts, metadata=metadata)
    stored = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert stored["artifacts"] == artifacts == original
    assert stored["metadata"] == {**metadata, "decision_log_ref": str(path / "decision_log.json")}
    assert metadata == {"owner_note": "Keep authored bytes"}
    assert (path / "decision_log.json").is_file()
    sc.enforce_stage_context(path, "proposal", "completed", stored["artifacts"])


def test_unicode_marker_and_checkpoint_are_readable_and_bounded(tmp_path):
    path = init_project("run", title="Ánh sáng", pipeline_type="framework-smoke", pipeline_dir=tmp_path)
    assert "Ánh sáng" in (path / "project.json").read_text(encoding="utf-8")
    metadata = {"note": "漢" * 360000}
    checkpoint = advance(path, "research", packet(path, "research"), metadata=metadata)
    payload = checkpoint.read_bytes()
    assert len(payload) < sc.MAX_BYTES
    assert b"\\u6f22" not in payload
    assert json.loads(payload)["metadata"] == metadata
    assert len(json.dumps(json.loads(payload)).encode()) > sc.MAX_BYTES


def test_oversized_marker_does_not_mutate_existing_identity(tmp_path):
    path = project(tmp_path)
    original = (path / "project.json").read_bytes()
    with pytest.raises(sc.StageContextError, match="exceeds 2 MiB"):
        init_project("run", title="x" * sc.MAX_BYTES, pipeline_type="framework-smoke", pipeline_dir=tmp_path)
    assert (path / "project.json").read_bytes() == original


def test_oversized_checkpoint_rejected_before_decision_log_or_history(tmp_path):
    path = project(tmp_path)
    artifacts = packet(path, "research")
    advance(path, "research", artifacts)
    original = (path / "checkpoint_research.json").read_bytes()
    artifacts["decision_log"] = {"version": "1.0", "project_id": "run", "decisions": []}
    with pytest.raises(CheckpointValidationError, match="exceeds 2 MiB"):
        advance(path, "research", artifacts, metadata={"padding": "x" * sc.MAX_BYTES})
    assert (path / "checkpoint_research.json").read_bytes() == original
    assert not (path / "decision_log.json").exists()
    assert not (path / "history").exists()


def test_invalid_checkpoint_rejected_before_decision_log(tmp_path):
    path = project(tmp_path)
    artifacts = packet(path, "research")
    artifacts["decision_log"] = {"version": "1.0", "project_id": "run", "decisions": []}
    with pytest.raises(CheckpointValidationError):
        advance(path, "research", artifacts, checkpoint_policy="invalid")
    assert not (path / "decision_log.json").exists()
    assert not (path / "checkpoint_research.json").exists()
