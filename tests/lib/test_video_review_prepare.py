"""Real FFmpeg packet checks; synthetic tones/pixels establish no perceptual quality."""
import copy
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import lib.video_review as gate


@pytest.fixture(scope="module")
def synthetic_video(tmp_path_factory):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("Real FFmpeg and ffprobe are required for packet integration checks")
    path = tmp_path_factory.mktemp("synthetic") / "clip.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x284:rate=24:duration=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    ], check=True, capture_output=True)
    return path


@pytest.fixture
def prepared(tmp_path, synthetic_video):
    project = tmp_path / "run"
    gate.save_json(project / "project.json", {"id": "run"})
    gate.save_json(project / "artifacts/script.json", {"total_duration_seconds": 1})
    source = project / "source.jpg"
    source.write_bytes(b"Synthetic product reference; no perceptual quality claim")
    gate.save_json(project / "artifacts/product-source.json", {"originalPath": str(source)})
    video = project / "clip.mp4"
    shutil.copyfile(synthetic_video, video)
    packet = gate.prepare_review(project, video)
    path = project / "artifacts/video_review.json"
    return project, video, packet, path


def check(review, name):
    return next(item for item in review["checks"] if item["id"] == name)


def canonical_bytes(project):
    roots = [project / "artifacts/video_review.json", project / "qa/video-review"]
    return {str(path.relative_to(project)): path.read_bytes()
            for root in roots for path in ([root] if root.is_file() else root.rglob("*"))
            if path.is_file() and path.name != ".prepare.lock"}


def test_actual_preparation_only_passes_measured_technical_check_and_is_idempotent(prepared):
    project, video, packet, path = prepared
    review = gate.read_json(path)
    assert gate.policy_enabled(project)
    assert review["reviewer"] == "PENDING"
    technical = check(review, "technical")
    assert technical["status"] == "PASS"
    measurement = gate.read_json(Path(technical["evidence"][0]["path"]))
    assert measurement["video"] == gate.file_ref(video)
    assert measurement["full_decode_exit_code"] == 0
    assert measurement["issues"] == []
    assert all(item["status"] == "NOT_TESTED" for item in review["checks"] if item["id"] != "technical")
    assert not gate.evaluate_review(project, video)["ready"]
    before = canonical_bytes(project)
    assert gate.prepare_review(project, video) == packet
    assert canonical_bytes(project) == before
    assert not list((project / "history/video_reviews").glob("*.json"))


@pytest.mark.parametrize("technical_status", ["PASS", "FAIL", "NOT_TESTED"])
def test_legacy_reprepare_archives_before_evidence_change_and_preserves_judgments(prepared, monkeypatch, technical_status):
    project, video, _, path = prepared
    old = gate.read_json(path)
    technical = check(old, "technical")
    measurement_path = Path(technical["evidence"][0]["path"])
    legacy = gate.read_json(measurement_path)
    legacy.pop("video")
    gate.save_json(measurement_path, legacy)
    legacy_bytes = measurement_path.read_bytes()
    technical.update(status=technical_status, observation="Human technical judgment must survive")
    technical["evidence"] = [gate.file_ref(measurement_path)]
    check(old, "audio_quality").update(status="FAIL", observation="Reviewer heard an abrupt cut")
    original_bytes = (json.dumps(old, indent=1, ensure_ascii=True).replace("\n", "\r\n") + "\r\n\r\n").encode("utf-8")
    path.write_bytes(original_bytes)
    original_hash = gate.sha256(path)
    archived = []
    original_archive = gate._archive_review

    def inspect_before_archive(project, receipt, receipt_bytes):
        assert measurement_path.read_bytes() == legacy_bytes
        assert gate.read_json(path) == old
        assert receipt_bytes == original_bytes
        original_archive(project, receipt, receipt_bytes)
        archived.append(True)

    monkeypatch.setattr(gate, "_archive_review", inspect_before_archive)
    gate.prepare_review(project, video)
    updated = gate.read_json(path)
    assert archived == [True]
    assert check(updated, "technical")["status"] == technical_status
    assert check(updated, "technical")["observation"] == technical["observation"]
    assert check(updated, "technical")["evidence"] == [gate.file_ref(measurement_path)]
    assert updated["checks"][1:] == old["checks"][1:]
    assert updated["reviewer"] == old["reviewer"]
    histories = list((project / "history/video_reviews").glob("*.json"))
    assert len(histories) == 1 and gate.read_json(histories[0]) == old
    assert histories[0].read_bytes() == original_bytes
    assert gate.sha256(histories[0]) == original_hash
    archived_folder = histories[0].with_suffix("")
    assert (archived_folder / "technical.json").read_bytes() == legacy_bytes
    evidence_map = gate.read_json(archived_folder / "evidence-map.json")
    assert evidence_map["receipt"]["original"]["sha256"] == original_hash
    assert evidence_map["receipt"]["snapshot"]["sha256"] == original_hash
    for refs in evidence_map["files"]:
        assert refs["original"]["sha256"] == gate.file_ref(Path(refs["snapshot"]["path"]))["sha256"]
    before = canonical_bytes(project)
    gate.prepare_review(project, video)
    assert canonical_bytes(project) == before
    assert len(list((project / "history/video_reviews").glob("*.json"))) == 1
    assert not gate.evaluate_review(project, video)["ready"]


def test_changed_script_invalidates_semantic_receipt_and_preserves_original(prepared):
    project, video, _, path = prepared
    old = gate.read_json(path)
    old["reviewer"] = "Synthetic receipt for invalidation test only"
    check(old, "brief_fit").update(status="FAIL", observation="Existing human failure")
    gate.save_json(path, old)
    gate.save_json(project / "artifacts/script.json", {"total_duration_seconds": 2, "claim": "changed"})
    assert not gate.evaluate_review(project, video)["ready"]
    gate.prepare_review(project, video)
    updated = gate.read_json(path)
    assert updated["reviewer"] == "PENDING"
    assert check(updated, "technical")["status"] == "FAIL"
    assert "approved script" in check(updated, "technical")["observation"]
    assert all(item["status"] == "NOT_TESTED" for item in updated["checks"] if item["id"] != "technical")
    assert updated["context"] == gate.context_refs(project)
    histories = list((project / "history/video_reviews").glob("*.json"))
    assert len(histories) == 1 and gate.read_json(histories[0]) == old


def test_new_decode_failure_cannot_leave_old_technical_pass(prepared, monkeypatch):
    project, video, _, path = prepared
    old = gate.read_json(path)
    run = gate.subprocess.run

    def corrupt_decode(command, **kwargs):
        if "0:v?" in command:
            return subprocess.CompletedProcess(command, 1, "", "Corrupt frame in full decode")
        return run(command, **kwargs)

    monkeypatch.setattr(gate.subprocess, "run", corrupt_decode)
    gate.prepare_review(project, video)
    updated = gate.read_json(path)
    assert check(updated, "technical")["status"] == "FAIL"
    assert updated["checks"][1:] == old["checks"][1:]
    assert len(list((project / "history/video_reviews").glob("*.json"))) == 1
    before = canonical_bytes(project)
    gate.prepare_review(project, video)
    assert canonical_bytes(project) == before
    assert len(list((project / "history/video_reviews").glob("*.json"))) == 1


def test_missing_audio_is_recorded_as_technical_failure(tmp_path, synthetic_video):
    project = tmp_path / "silent"
    gate.save_json(project / "project.json", {"id": "silent"})
    video = project / "silent.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(synthetic_video), "-c:v", "copy", "-an", str(video)],
                   check=True, capture_output=True)
    packet = gate.prepare_review(project, video)
    review = gate.read_json(project / "artifacts/video_review.json")
    assert packet["audio"] is None
    assert check(review, "technical")["status"] == "FAIL"
    assert "audio stream" in check(review, "technical")["observation"]
    assert not gate.evaluate_review(project, video)["ready"]


def test_ffmpeg_failure_preserves_published_packet_and_verdict(prepared, monkeypatch):
    project, video, _, _ = prepared
    before = canonical_bytes(project)
    run = gate.subprocess.run

    def fail_contact(command, **kwargs):
        if str(command[-1]).endswith("contact.jpg"):
            raise subprocess.CalledProcessError(1, command, stderr="Synthetic extraction failure")
        return run(command, **kwargs)

    monkeypatch.setattr(gate.subprocess, "run", fail_contact)
    with pytest.raises(subprocess.CalledProcessError):
        gate.prepare_review(project, video)
    assert canonical_bytes(project) == before
    assert not list((project / "history/video_reviews").glob("*.json"))
    assert not (project / "qa/video-review/.prepare.lock").exists()


@pytest.mark.parametrize("changed", ["verdict", "video", "context"])
def test_concurrent_change_during_preparation_is_detected(prepared, monkeypatch, changed):
    project, video, _, path = prepared
    old = gate.read_json(path)
    packet_before = (project / "qa/video-review" / gate.sha256(video) / "packet.json").read_bytes()
    build = gate._build_packet
    newest = copy.deepcopy(old)
    check(newest, "audio_quality")["observation"] = "A newer human observation"

    def change_after_build(*args, **kwargs):
        result = build(*args, **kwargs)
        if changed == "verdict": gate.save_json(path, newest)
        elif changed == "video": video.write_bytes(b"Concurrent render replacement")
        else: gate.save_json(project / "artifacts/script.json", {"total_duration_seconds": 3})
        return result

    monkeypatch.setattr(gate, "_build_packet", change_after_build)
    with pytest.raises(gate.VideoReviewError, match="changed during preparation"):
        gate.prepare_review(project, video)
    assert gate.read_json(path) == (newest if changed == "verdict" else old)
    assert (project / "qa/video-review" / old["video"]["sha256"] / "packet.json").read_bytes() == packet_before
    assert not list((project / "history/video_reviews").glob("*.json"))


def test_overlapping_preparations_are_rejected(prepared):
    project, video, _, _ = prepared
    before = canonical_bytes(project)
    with gate._preparation_lock(project, video):
        lock = gate.read_json(project / "qa/video-review/.prepare.lock")
        assert lock["pid"] == os.getpid()
        assert lock["started_at"]
        assert lock["project"] == str(project.resolve())
        assert lock["video"] == str(video.resolve())
        with pytest.raises(gate.VideoReviewError, match="already active"):
            gate.prepare_review(project, video)
    assert canonical_bytes(project) == before


def test_relative_receipt_paths_preserve_existing_human_failure(prepared):
    project, video, _, path = prepared
    review = gate.read_json(path)
    review["video"]["path"] = video.name
    for ref in review["context"]:
        ref["path"] = str(Path(ref["path"]).relative_to(project))
    check(review, "audio_quality").update(status="FAIL", observation="Preserve relative-path human verdict")
    gate.save_json(path, review)
    gate.prepare_review(project, video)
    assert gate.read_json(path) == review
    assert not list((project / "history/video_reviews").glob("*.json"))


def _record_synthetic_pass(project, video, packet, path):
    """A gate fixture, never a claim that someone reviewed these generated pixels."""
    review = gate.read_json(path)
    review["reviewer"] = "Synthetic gate fixture only"
    for item in review["checks"]:
        if item["id"] == "technical":
            continue
        item.update(status="PASS", observation="Synthetic gate assertion, not perceptual validation",
                    time_ranges=[[0, packet["duration_seconds"]]], method="rendered_frames",
                    evidence=[packet["contact"]])
        if item["id"] in {"action_physics", "edit_continuity"}:
            item.update(method="video_playback", evidence=[gate.file_ref(video)])
        elif item["id"] == "audio_quality":
            item.update(method="audio_listening", evidence=[packet["audio"]])
        elif item["id"] == "product_fidelity":
            item["evidence"].append(gate.file_ref(project / "source.jpg"))
    original_bytes = (json.dumps(review, separators=(",", ":"), ensure_ascii=True) + "\r\n\r\n").encode("utf-8")
    path.write_bytes(original_bytes)
    assert gate.evaluate_review(project, video)["ready"]
    return original_bytes


@pytest.mark.parametrize("failure", ["second_replace", "receipt_save", "packet_publish", "external_receipt"])
def test_interrupted_publication_blocks_until_reprepare_and_preserves_history(prepared, monkeypatch, failure):
    project, video, packet, path = prepared
    original_bytes = _record_synthetic_pass(project, video, packet, path)
    folder = project / "qa/video-review" / gate.sha256(video)
    original_packet_bytes = (folder / "packet.json").read_bytes()
    build, replace, save = gate._build_packet, Path.replace, gate.save_json
    external = gate.read_json(path)
    check(external, "audio_quality").update(status="FAIL", observation="Newer external human failure")
    external_bytes = (json.dumps(external, indent=3) + "\n").encode("utf-8")
    replaced = []

    def changed_candidate(*args, **kwargs):
        candidate, issues = build(*args, **kwargs)
        staging = args[2]
        measured = gate.read_json(staging / "technical.json")
        measured["test_attempt"] = "new measurements"
        save(staging / "technical.json", measured)
        contact = staging / "contact.jpg"
        contact.write_bytes(contact.read_bytes() + b"synthetic changed evidence")
        candidate["contact"]["sha256"] = gate.sha256(contact)
        save(staging / "packet.json", candidate)
        return candidate, issues

    def replace_with_failure(source, target):
        target = Path(target)
        if target.parent == folder and target.name != "packet.json":
            replaced.append(target.name)
            if failure == "second_replace" and len(replaced) == 2:
                raise OSError("Injected second canonical replacement failure")
            if failure == "external_receipt" and len(replaced) == 1:
                path.write_bytes(external_bytes)
        if failure == "packet_publish" and target == folder / "packet.json" and source.name == "packet.json":
            raise OSError("Injected final packet publication failure")
        return replace(source, target)

    def save_with_failure(target, value):
        if failure == "receipt_save" and target == path:
            raise OSError("Injected final receipt save failure")
        return save(target, value)

    with monkeypatch.context() as patch:
        patch.setattr(gate, "_build_packet", changed_candidate)
        patch.setattr(Path, "replace", replace_with_failure)
        patch.setattr(gate, "save_json", save_with_failure)
        error = gate.VideoReviewError if failure == "external_receipt" else OSError
        with pytest.raises(error):
            gate.prepare_review(project, video)
    assert replaced  # Failure occurred after entering canonical publication.
    if failure == "external_receipt":
        assert path.read_bytes() == external_bytes
    result = gate.evaluate_review(project, video)
    assert not result["ready"]
    assert any("publication is incomplete" in blocker for blocker in result["blockers"])
    histories = list((project / "history/video_reviews").glob("*.json"))
    assert len(histories) == 1
    assert histories[0].read_bytes() == original_bytes
    assert (histories[0].with_suffix("") / "packet.json").read_bytes() == original_packet_bytes
    assert not (project / "qa/video-review/.prepare.lock").exists()
    gate.prepare_review(project, video)
    assert "preparation_status" not in gate.read_json(folder / "packet.json")
    assert histories[0].read_bytes() == original_bytes
    if failure == "external_receipt":
        assert check(gate.read_json(path), "audio_quality")["status"] == "FAIL"
        assert not gate.evaluate_review(project, video)["ready"]
    else:
        # Original evidence regenerated exactly; retained synthetic verdict still binds.
        assert gate.evaluate_review(project, video)["ready"]
