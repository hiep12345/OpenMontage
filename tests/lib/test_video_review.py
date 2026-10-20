"""Acceptance regressions, not assertions that software understands aesthetics."""
import copy
import json
from pathlib import Path
import pytest

from lib.video_review import (CHECKS, VideoReviewError, context_refs, enable_policy,
                             enforce_checkpoint_review, evaluate_review, file_ref,
                             policy_enabled, require_video_review, save_json)


@pytest.fixture
def reviewed(tmp_path):
    project = tmp_path / "run"
    save_json(project / "project.json", {"id": "run"})
    enable_policy(project)
    video = project / "test.mp4"
    video.write_bytes(b"unit fixture: no claim of codec validation")
    save_json(project / "artifacts/script.json", {"version":"1.0", "total_duration_seconds":22})
    source = project / "source.jpg"; source.write_bytes(b"original product fixture")
    save_json(project / "artifacts/product-source.json", {"originalPath":str(source)})
    folder = project / "qa/video-review" / file_ref(video)["sha256"]
    folder.mkdir(parents=True)
    visual = folder / "contact.jpg"; visual.write_bytes(b"visual evidence fixture")
    audio = folder / "audio.wav"; audio.write_bytes(b"listening evidence fixture")
    technical = folder / "technical.json"; save_json(technical, {"video": file_ref(video), "probe": {"format": {"duration": "22"}, "streams": [{"codec_type": "video", "width": 160, "height": 284}, {"codec_type": "audio"}]}, "full_decode_exit_code": 0, "full_decode_stderr": "", "issues": []})
    packet = {"video": file_ref(video), "duration_seconds":22, "context":context_refs(project), "contact":file_ref(visual),
              "frames":[], "audio":file_ref(audio)}
    save_json(folder / "packet.json", packet)
    review = {"version":"1.0", "reviewed_at":"2026-10-10T00:00:00Z", "reviewer":"Unit fixture, not a real perceptual reviewer",
              "video":file_ref(video), "context":context_refs(project), "findings":[], "checks":[]}
    for check_id in CHECKS:
        method = "technical_analysis" if check_id == "technical" else "audio_listening" if check_id == "audio_quality" else "video_playback" if check_id in {"action_physics","edit_continuity"} else "rendered_frames"
        evidence = technical if check_id == "technical" else audio if check_id == "audio_quality" else visual
        refs = [file_ref(evidence)]
        if check_id == "product_fidelity": refs.append(file_ref(source))
        if check_id in {"action_physics","edit_continuity"}: refs.append(file_ref(video))
        review["checks"].append({"id":check_id,"status":"PASS","method":method,
                                 "observation":"Concrete unit-test inspection observation; not video quality validation.",
                                 "time_ranges":[[0,22]],"evidence":refs})
    save_json(project / "artifacts/video_review.json", review)
    return project, video, review


def _check(review, check_id):
    return next(check for check in review["checks"] if check["id"] == check_id)


def test_complete_evidence_allows_declared_output(reviewed):
    project, video, review = reviewed
    assert evaluate_review(project, video)["ready"]
    enforce_checkpoint_review(project, "compose", "completed", {"render_report":{"outputs":[{"path":str(video)}]}})


@pytest.mark.parametrize("status", ["FAIL", "NOT_TESTED"])
def test_required_nonpass_blocks_even_when_old_review_says_pass(reviewed, status):
    project, video, review = reviewed
    _check(review, "audio_quality")["status"] = status
    save_json(project / "artifacts/video_review.json", review)
    with pytest.raises(VideoReviewError, match=status):
        enforce_checkpoint_review(project, "compose", "completed", {
            "render_report":{"outputs":[{"path":str(video)}]}, "final_review":{"status":"pass"}})


def test_asr_is_not_listening(reviewed):
    project, video, review = reviewed
    _check(review,"audio_quality")["method"] = "ASR"
    assert any("actual listening" in reason for reason in evaluate_review(project,video,review)["blockers"])


def test_unchanged_video_cannot_use_missing_or_changed_evidence(reviewed):
    project, video, review = reviewed
    evidence = Path(_check(review,"brief_fit")["evidence"][0]["path"])
    evidence.write_bytes(b"changed evidence")
    assert not evaluate_review(project,video,review)["ready"]
    evidence.unlink()
    assert not evaluate_review(project,video,review)["ready"]


def test_changed_video_invalidates_review(reviewed):
    project, video, review = reviewed
    video.write_bytes(b"different render")
    assert not evaluate_review(project,video,review)["ready"]


def test_changed_context_invalidates_review(reviewed):
    project, video, review = reviewed
    save_json(project / "artifacts/script.json", {"version":"1.0", "new_claim":"Camera is already on"})
    assert any("context changed" in reason for reason in evaluate_review(project,video,review)["blockers"])


def test_open_blocker_overrides_passing_checkboxes(reviewed):
    project, video, review = reviewed
    review["findings"] = [{"check_id":"spatial_continuity","severity":"blocker","status":"open",
        "start_seconds":2,"end_seconds":4,"observation":"One shelf duplicated across opposite walls",
        "proposed_fix":"Keep exactly one shelf behind the chair in both camera views."}]
    assert any("Unresolved blocker" in reason for reason in evaluate_review(project,video,review)["blockers"])


def test_empty_observation_or_evidence_cannot_pass(reviewed):
    project, video, review = reviewed
    _check(review,"brief_fit").update(observation=" ",evidence=[])
    assert not evaluate_review(project,video,review)["ready"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "pending_reviewer"])
def test_incomplete_receipts_cannot_pass(reviewed, change):
    project, video, review = reviewed
    if change == "missing": review["checks"].pop()
    elif change == "duplicate": review["checks"][-1] = copy.deepcopy(review["checks"][0])
    else: review["reviewer"] = "PENDING"
    assert not evaluate_review(project,video,review)["ready"]


@pytest.mark.parametrize("method", ["rendered_frames", "source_comparison"])
def test_stills_do_not_pass_temporal_acceptance(reviewed, method):
    project, video, review = reviewed
    _check(review,"edit_continuity")["method"] = method
    assert not evaluate_review(project,video,review)["ready"]


def test_partial_listening_does_not_pass_full_mix(reviewed):
    project, video, review = reviewed
    _check(review,"audio_quality")["time_ranges"] = [[0,4],[14,22]]
    assert not evaluate_review(project,video,review)["ready"]


def test_reference_only_does_not_prove_rendered_product(reviewed):
    project, video, review = reviewed
    source = project / "reference.jpg"; source.write_bytes(b"source only")
    _check(review,"product_fidelity").update(method="source_comparison",evidence=[file_ref(source)])
    assert not evaluate_review(project,video,review)["ready"]


def test_render_only_does_not_prove_exact_product(reviewed):
    project, video, review = reviewed
    check = _check(review,"product_fidelity")
    check["evidence"] = check["evidence"][:1]
    assert any("original product reference" in reason for reason in evaluate_review(project,video,review)["blockers"])


def test_source_image_change_invalidates_receipt(reviewed):
    project, video, review = reviewed
    (project / "source.jpg").write_bytes(b"different product image")
    assert not evaluate_review(project,video,review)["ready"]


def test_all_render_outputs_require_acceptance(reviewed):
    project, video, review = reviewed
    unreviewed = project / "variant.mp4"; unreviewed.write_bytes(b"new variant")
    with pytest.raises(VideoReviewError, match="Missing review"):
        enforce_checkpoint_review(project,"compose","completed",{"render_report":{"outputs":[{"path":str(video)},{"path":str(unreviewed)}]}})


def test_publish_rechecks_current_bytes(reviewed):
    project, video, review = reviewed
    save_json(project / "artifacts/render_report.json", {"outputs":[{"path":str(video)}]})
    _check(review,"product_fidelity")["status"] = "FAIL"
    save_json(project / "artifacts/video_review.json",review)
    with pytest.raises(VideoReviewError, match="product_fidelity"):
        enforce_checkpoint_review(project,"publish","completed",{})


def test_invalid_policy_fails_closed(reviewed):
    project, video, review = reviewed
    marker = json.loads((project / "project.json").read_text())
    marker["video_review_policy"]["required"] = False
    save_json(project / "project.json", marker)
    with pytest.raises(VideoReviewError, match="Invalid video_review_policy"):
        enforce_checkpoint_review(project,"compose","completed",{})


def test_historical_projects_and_failure_heartbeats_remain_writable(tmp_path):
    project = tmp_path / "legacy"
    save_json(project / "project.json", {"id": "legacy"})
    assert not policy_enabled(project)
    enforce_checkpoint_review(project,"compose","completed",{})
    enable_policy(project)
    enforce_checkpoint_review(project,"compose","in_progress",{})
    enforce_checkpoint_review(project,"compose","failed",{})


@pytest.mark.parametrize("stage", ["compose", "publish"])
@pytest.mark.parametrize("status", ["completed", "awaiting_human"])
@pytest.mark.parametrize("verdict", ["FAIL", "NOT_TESTED"])
def test_incoming_nonpass_cannot_be_hidden_by_saved_pass(reviewed, stage, status, verdict):
    project, video, review = reviewed
    incoming = copy.deepcopy(review)
    _check(incoming, "audio_quality")["status"] = verdict
    report = {"outputs": [{"path": str(video)}]}
    save_json(project / "artifacts/render_report.json", report)
    with pytest.raises(VideoReviewError, match=verdict):
        enforce_checkpoint_review(project, stage, status, {"render_report": report, "video_review": incoming})
    assert json.loads((project / "artifacts/video_review.json").read_text()) == review


def test_incoming_pass_can_be_evaluated_before_persistence(reviewed):
    project, video, review = reviewed
    saved = copy.deepcopy(review)
    _check(saved, "audio_quality")["status"] = "NOT_TESTED"
    save_json(project / "artifacts/video_review.json", saved)
    enforce_checkpoint_review(project, "compose", "completed", {
        "render_report": {"outputs": [{"path": str(video)}]}, "video_review": review})
    assert not evaluate_review(project, video)["ready"]  # The gate does not save the incoming receipt.


def test_incoming_review_must_name_declared_output(reviewed):
    project, video, review = reviewed
    review["video"]["path"] = str(project / "other.mp4")
    with pytest.raises(VideoReviewError, match="undeclared output"):
        enforce_checkpoint_review(project, "compose", "completed", {
            "render_report": {"outputs": [{"path": str(video)}]}, "video_review": review})


@pytest.mark.parametrize("incoming", [None, {}, {"video": None}])
def test_malformed_incoming_review_does_not_fall_back_to_saved_pass(reviewed, incoming):
    project, video, _ = reviewed
    with pytest.raises(VideoReviewError, match="invalid render report or incoming review"):
        enforce_checkpoint_review(project, "compose", "completed", {
            "render_report": {"outputs": [{"path": str(video)}]}, "video_review": incoming})


@pytest.mark.parametrize("outputs", [[], None, {}, [{"path": ""}], [{}]])
def test_invalid_output_declaration_blocks(reviewed, outputs):
    project, _, _ = reviewed
    with pytest.raises(VideoReviewError):
        enforce_checkpoint_review(project, "compose", "completed", {"render_report": {"outputs": outputs}})


def test_unrelated_technical_evidence_is_blocked(reviewed):
    project, video, review = reviewed
    _check(review, "technical")["evidence"] = [file_ref(project / "source.jpg")]
    assert "prepared probe/decode evidence" in ";".join(evaluate_review(project, video, review)["blockers"])


@pytest.mark.parametrize("failure", [
    "fixture", "decode", "decode_missing", "decode_boolean", "decode_stderr", "issues", "issues_missing",
    "streams", "no_video", "malformed_stream", "dimensions", "duration", "duration_nan", "duration_inf",
    "duration_zero", "duration_boolean", "duration_missing", "video", "video_path", "probe_missing",
])
def test_measured_failure_cannot_be_overruled_by_claimed_pass(reviewed, failure):
    project, video, review = reviewed
    technical = Path(_check(review, "technical")["evidence"][0]["path"])
    measured = json.loads(technical.read_text())
    if failure == "fixture": measured = {"unit_fixture": True}
    elif failure == "decode": measured["full_decode_exit_code"] = 1
    elif failure == "decode_missing": measured.pop("full_decode_exit_code")
    elif failure == "decode_boolean": measured["full_decode_exit_code"] = False
    elif failure == "decode_stderr": measured["full_decode_stderr"] = "corrupt frame"
    elif failure == "issues": measured["issues"] = ["measured failure"]
    elif failure == "issues_missing": measured.pop("issues")
    elif failure == "streams": measured["probe"]["streams"].pop()
    elif failure == "no_video": measured["probe"]["streams"].pop(0)
    elif failure == "malformed_stream": measured["probe"]["streams"] = [None]
    elif failure == "dimensions": measured["probe"]["streams"][0]["width"] = 0
    elif failure == "duration": measured["probe"]["format"]["duration"] = "18"
    elif failure == "duration_nan": measured["probe"]["format"]["duration"] = "NaN"
    elif failure == "duration_inf": measured["probe"]["format"]["duration"] = "Infinity"
    elif failure == "duration_zero": measured["probe"]["format"]["duration"] = 0
    elif failure == "duration_boolean": measured["probe"]["format"]["duration"] = True
    elif failure == "duration_missing": measured["probe"]["format"].pop("duration")
    elif failure == "video": measured["video"]["sha256"] = "0" * 64
    elif failure == "video_path": measured["video"]["path"] = str(project / "other.mp4")
    else: measured.pop("probe")
    save_json(technical, measured)
    _check(review, "technical")["evidence"] = [file_ref(technical)]
    result = evaluate_review(project, video, review)
    assert not result["ready"]
    assert result["blockers"]


@pytest.mark.parametrize("value", ["NaN", "Infinity", 0, -1, True, None])
def test_invalid_packet_duration_cannot_bypass_full_duration_checks(reviewed, value):
    project, video, review = reviewed
    packet_path = project / "qa/video-review" / file_ref(video)["sha256"] / "packet.json"
    packet = json.loads(packet_path.read_text())
    packet["duration_seconds"] = value
    save_json(packet_path, packet)
    assert not evaluate_review(project, video, review)["ready"]


def test_declared_script_duration_is_checked_independently_of_context_hash(reviewed):
    project, video, review = reviewed
    save_json(project / "artifacts/script.json", {"total_duration_seconds": 18})
    review["context"] = context_refs(project)
    packet_path = project / "qa/video-review" / file_ref(video)["sha256"] / "packet.json"
    packet = json.loads(packet_path.read_text())
    packet["context"] = context_refs(project)
    save_json(packet_path, packet)
    assert any("approved script" in reason for reason in evaluate_review(project, video, review)["blockers"])


def test_missing_or_malformed_technical_file_fails_closed(reviewed):
    project, video, review = reviewed
    technical = Path(_check(review, "technical")["evidence"][0]["path"])
    technical.write_text("not json", encoding="utf-8")
    assert not evaluate_review(project, video, review)["ready"]
    technical.unlink()
    assert not evaluate_review(project, video, review)["ready"]


