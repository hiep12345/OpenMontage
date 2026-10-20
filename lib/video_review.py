"""Evidence-bound video acceptance; semantic inspection is never inferred from a probe."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from schemas.artifacts import validate_artifact

CHECKS = {
    "technical": "Container, full decode, duration, resolution and required audio",
    "brief_fit": "Ordinary buyer situation, plain language, no invented expertise",
    "story_clarity": "Understandable problem, action and visible payoff",
    "spatial_continuity": "Room geometry, object count and positions across angles",
    "action_physics": "Hands, supported objects, movement and contact",
    "product_fidelity": "Original artwork AND frame, proportions, preview and claims",
    "edit_continuity": "Cuts, repeated actions, before/after framing and pacing",
    "speech_sync": "Narration claims agree with the action at that time",
    "subtitle_readability": "Rendered legibility, timing and safe placement",
    "audio_quality": "Actual listening: voice cadence, intelligibility, music balance",
}
VISUAL_METHODS = {"rendered_frames", "video_playback", "multimodal_video"}


class VideoReviewError(ValueError):
    pass


def _parse_json(text: str, label: str) -> dict:
    def reject_constant(value: str):
        raise VideoReviewError(f"Nonfinite JSON value in {label}: {value}")
    return json.loads(text, parse_constant=reject_constant)


def read_json(path: Path) -> dict:
    return _parse_json(path.read_text(encoding="utf-8"), path.name)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_ref(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": sha256(path)}


def save_json(path: Path, value: dict) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    _save_bytes(path, payload.encode("utf-8"))


def _save_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                     prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
        temp = Path(stream.name)
        stream.write(payload)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def context_refs(project: Path) -> list[dict]:
    paths = [project / "artifacts" / (name + ".json") for name in
             ("proposal_packet", "script", "scene_plan", "edit_decisions", "asset_manifest", "product-source")]
    paths = [path for path in paths if path.is_file()]
    source = project / "artifacts/product-source.json"
    if source.is_file():
        original = read_json(source).get("originalPath")
        if original:
            original_path = Path(original)
            paths.append(original_path if original_path.is_absolute() else project / original_path)
    return [file_ref(path) for path in paths]


def policy_enabled(project: Path) -> bool:
    marker_path = project / "project.json"
    if not marker_path.exists():
        return False
    marker = read_json(marker_path)
    policy = marker.get("video_review_policy")
    if policy is None:
        return False  # Historical projects are not silently migrated.
    if policy != {"version": "1.0", "required": True}:
        raise VideoReviewError("Invalid video_review_policy; refusing to disable an active review gate")
    return True


def enable_policy(project: Path) -> None:
    marker_path = project / "project.json"
    marker = read_json(marker_path)
    if marker.get("video_review_policy") == {"version": "1.0", "required": True}:
        return
    marker["video_review_policy"] = {"version": "1.0", "required": True}
    save_json(marker_path, marker)


def _resolve(project: Path, value: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise VideoReviewError("Missing or invalid file path")
    path = Path(value)
    return path.resolve() if path.is_absolute() else (project / path).resolve()


def _duration(value, label: str) -> float:
    if isinstance(value, bool):
        raise VideoReviewError(f"Invalid {label}")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise VideoReviewError(f"Invalid {label}") from exc
    if not math.isfinite(result) or result <= 0:
        raise VideoReviewError(f"Invalid {label}")
    return result


def _technical_issues(measured: dict, video_ref: dict, duration: float, script: dict) -> list[str]:
    """Check persisted measurements independently of a reviewer's claimed PASS."""
    issues = []
    if measured.get("video") != video_ref:
        issues.append("Measurements do not bind the exact video")
    if type(measured.get("full_decode_exit_code")) is not int or measured["full_decode_exit_code"] != 0:
        issues.append("Full decode failed or its exit code is missing")
    # Old bound packets did not persist stderr; new packets must not conceal decode errors.
    stderr = measured.get("full_decode_stderr", "")
    if not isinstance(stderr, str) or stderr.strip():
        issues.append("Full decode reported errors")
    if measured.get("issues") != []:
        issues.append("Measured checks failed or their results are missing")
    try:
        probe = measured["probe"]
        streams = probe["streams"]
        if not isinstance(streams, list) or not all(isinstance(stream, dict) for stream in streams):
            raise VideoReviewError("Invalid probe streams")
        videos = [stream for stream in streams if stream.get("codec_type") == "video"]
        if not videos:
            issues.append("Missing video stream")
        elif any(type(stream.get(key)) is not int or stream[key] <= 0
                 for stream in videos for key in ("width", "height")):
            issues.append("Invalid video stream dimensions")
        if not any(stream.get("codec_type") == "audio" for stream in streams):
            issues.append("Missing expected speech/music audio stream")
        measured_duration = _duration(probe["format"]["duration"], "measured duration")
        if abs(measured_duration - duration) > .1:
            issues.append("Measured duration does not match the packet")
        expected = script.get("total_duration_seconds")
        if expected is not None and abs(measured_duration - _duration(expected, "approved script duration")) > .1:
            issues.append("Output duration differs from the approved script")
    except (KeyError, TypeError, ValueError) as exc:
        issues.append(f"Invalid technical measurements: {exc}")
    return issues


def load_video_review(project: Path, video: Path) -> dict:
    primary = project / "artifacts/video_review.json"
    current = read_json(primary) if primary.exists() else None
    digest = sha256(video)
    if current and current.get("video", {}).get("sha256") == digest:
        return current
    archived = project / "artifacts/video_reviews" / (digest + ".json")
    if archived.exists():
        return read_json(archived)
    raise VideoReviewError("Missing review for the exact rendered video")


def evaluate_review(project: Path, video: Path, review: dict | None = None) -> dict:
    """Derive readiness from required findings and actual byte identities, not claimed PASS."""
    project, video = project.resolve(), video.resolve()
    blockers: list[str] = []
    try:
        review = review if review is not None else load_video_review(project, video)
        validate_artifact("video_review", review)
        if review["reviewer"].strip().upper() in {"PENDING", "NOT_TESTED", ""}:
            blockers.append("Reviewer inspection has not been recorded")
        if _resolve(project, review["video"]["path"]) != video:
            blockers.append("Review names a different video path")
        if review["video"]["sha256"] != sha256(video):
            blockers.append("Video changed after review")
        packet_path = project / "qa/video-review" / sha256(video) / "packet.json"
        packet_hash = sha256(packet_path)
        packet = read_json(packet_path)
        if packet.get("preparation_status") == "incomplete":
            raise VideoReviewError("Inspection packet publication is incomplete; explicitly reprepare before review")
        if packet["video"] != file_ref(video):
            blockers.append("Inspection packet names different video bytes")
        duration = _duration(packet["duration_seconds"], "packet duration")
        rendered_paths = {_resolve(project, packet["contact"]["path"]), video}
        rendered_paths.update(_resolve(project, ref["path"]) for ref in packet["frames"])
        expected_context = {ref["path"]: ref["sha256"] for ref in context_refs(project)}
        actual_context = {_resolve(project, ref["path"]).as_posix(): ref["sha256"] for ref in review["context"]}
        expected_context = {Path(path).as_posix(): digest for path, digest in expected_context.items()}
        if actual_context != expected_context or len(actual_context) != len(review["context"]):
            blockers.append("Planning or product-source context changed or is missing from review")
        packet_context = {_resolve(project, ref["path"]).as_posix(): ref["sha256"] for ref in packet["context"]}
        if packet_context != expected_context or len(packet_context) != len(packet["context"]):
            blockers.append("Inspection packet context changed or is missing")
        packet_evidence = [packet["contact"], *packet["frames"]]
        if packet.get("audio"):
            packet_evidence.append(packet["audio"])
        for ref in packet_evidence:
            if sha256(_resolve(project, ref["path"])) != ref["sha256"]:
                blockers.append("Prepared inspection evidence changed")
        by_id = {check["id"]: check for check in review["checks"]}
        if len(by_id) != len(review["checks"]):
            blockers.append("Duplicate check IDs")
        if set(by_id) != set(CHECKS):
            blockers.append("Required review checks are missing or unknown")
        for check_id, check in by_id.items():
            if check["status"] != "PASS":
                blockers.append(f"{check_id}: {check['status']} — {check['observation']}")
                continue
            method = check["method"]
            if check_id == "audio_quality" and method not in {"audio_listening", "multimodal_audio_video"}:
                blockers.append("audio_quality: requires actual listening; ASR/probe is insufficient")
            elif check_id == "technical" and method != "technical_analysis":
                blockers.append("technical: requires probe and full-decode evidence")
            elif check_id in {"action_physics", "edit_continuity"} and method not in {"video_playback", "multimodal_video", "multimodal_audio_video"}:
                blockers.append(f"{check_id}: temporal quality requires playback or video-capable inspection")
            elif check_id not in {"technical", "audio_quality"} and method not in VISUAL_METHODS | {"source_comparison", "multimodal_audio_video"}:
                blockers.append(f"{check_id}: requires rendered visual inspection")
            if not check["observation"].strip() or not check["evidence"]:
                blockers.append(f"{check_id}: PASS has no concrete observation/evidence")
            if check_id != "technical" and not check["time_ranges"]:
                blockers.append(f"{check_id}: no inspected time interval recorded")
            if any(not math.isfinite(start) or not math.isfinite(end) or start < 0
                   or end <= start or end > duration + .05 for start, end in check["time_ranges"]):
                blockers.append(f"{check_id}: invalid inspected time interval")
            paths = {_resolve(project, ref["path"]) for ref in check["evidence"]}
            if check_id == "technical":
                technical_path = packet_path.parent / "technical.json"
                if technical_path not in paths:
                    blockers.append("technical: prepared probe/decode evidence is missing")
                else:
                    script_path = project / "artifacts/script.json"
                    script = read_json(script_path) if script_path.is_file() else {}
                    blockers.extend("technical: " + issue for issue in
                                    _technical_issues(read_json(technical_path), file_ref(video), duration, script))
            if check_id not in {"technical", "audio_quality"} and not paths.intersection(rendered_paths):
                blockers.append(f"{check_id}: no final-render visual evidence")
            if check_id == "audio_quality":
                audio_ref = packet.get("audio")
                if not audio_ref or _resolve(project, audio_ref["path"]) not in paths:
                    blockers.append("audio_quality: final-mix listening evidence is missing")
            if check_id == "product_fidelity":
                source_path = project / "artifacts/product-source.json"
                original = read_json(source_path).get("originalPath") if source_path.is_file() else None
                if not original or _resolve(project, original) not in paths:
                    blockers.append("product_fidelity: original product reference comparison is missing")
            if check_id in {"action_physics", "edit_continuity"} and video not in paths:
                blockers.append(f"{check_id}: exact final video inspection evidence is missing")
            if check_id in {"action_physics", "edit_continuity", "audio_quality"}:
                covered_until = 0.0
                for start, end in sorted(check["time_ranges"]):
                    if start > covered_until + .05:
                        break
                    covered_until = max(covered_until, end)
                if covered_until < duration - .05:
                    blockers.append(f"{check_id}: full-duration inspection not recorded")
            for evidence in check["evidence"]:
                path = _resolve(project, evidence["path"])
                if not path.is_file() or sha256(path) != evidence["sha256"]:
                    blockers.append(f"{check_id}: evidence missing or changed: {path.name}")
        for finding in review["findings"]:
            if finding["severity"] == "blocker" and finding["status"] == "open":
                blockers.append(f"Unresolved blocker at {finding['start_seconds']}s: {finding['observation']}")
        if sha256(packet_path) != packet_hash or review["video"]["sha256"] != sha256(video):
            blockers.append("Video or inspection packet changed during evaluation")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        blockers.append(str(exc))
    except Exception as exc:
        # Schema errors are fail-closed; no best-effort success on malformed data.
        blockers.append(f"Invalid review: {exc}")
    return {"version": "1.0", "ready": not blockers, "status": "PASS" if not blockers else "BLOCKED",
            "video_path": str(video), "blockers": blockers}


def require_video_review(project: Path, video: Path, review: dict | None = None) -> dict:
    result = evaluate_review(project, video, review)
    if not result["ready"]:
        raise VideoReviewError("VIDEO REVIEW BLOCKED: " + "; ".join(result["blockers"]))
    return result


def enforce_checkpoint_review(project: Path, stage: str, status: str, artifacts: dict) -> None:
    if stage not in {"compose", "publish"} or status not in {"completed", "awaiting_human"}:
        return
    if not policy_enabled(project):
        return
    if stage == "compose":
        report = artifacts.get("render_report", {})
    else:
        path = project / "artifacts/render_report.json"
        if not path.is_file():
            raise VideoReviewError("VIDEO REVIEW BLOCKED: missing render report")
        report = read_json(path)
    try:
        outputs = report.get("outputs", [])
        if not isinstance(outputs, list) or not outputs:
            raise VideoReviewError("no rendered output to review")
        output_paths = [_resolve(project, output["path"]) for output in outputs]
        incoming = artifacts.get("video_review")
        if "video_review" in artifacts:
            validate_artifact("video_review", incoming)
        incoming_path = _resolve(project, incoming["video"]["path"]) if incoming is not None else None
        if incoming_path is not None and incoming_path not in output_paths:
            raise VideoReviewError("incoming receipt names an undeclared output")
        for output_path in output_paths:
            require_video_review(project, output_path, incoming if output_path == incoming_path else None)
    except VideoReviewError:
        raise
    except Exception as exc:
        raise VideoReviewError(f"VIDEO REVIEW BLOCKED: invalid render report or incoming review: {exc}") from exc


@contextmanager
def _preparation_lock(project: Path, video: Path | None = None):
    """Serialize this helper's writers; a crash leaves an explicit recovery signal."""
    lock = project / "qa/video-review/.prepare.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise VideoReviewError("Video review preparation is already active; inspect .prepare.lock before recovery") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat(),
                       "project": str(project.resolve()), "video": str(video.resolve()) if video else None}, stream)
        yield
    finally:
        lock.unlink()


def _archive_review(project: Path, old: dict, receipt_bytes: bytes) -> None:
    """Freeze the original verdict and mutable packet bytes before replacement."""
    digest = old["video"]["sha256"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive = project / "history/video_reviews" / f"{digest}-{stamp}"
    archive.mkdir(parents=True)
    receipt_snapshot = archive.with_suffix(".json")
    _save_bytes(receipt_snapshot, receipt_bytes)
    source = project / "qa/video-review" / digest
    refs = []
    if source.is_dir():
        for path in source.iterdir():
            if path.is_file():
                target = archive / path.name
                shutil.copyfile(path, target)
                original_ref, snapshot_ref = file_ref(path), file_ref(target)
                if original_ref["sha256"] != snapshot_ref["sha256"]:
                    raise VideoReviewError("Inspection evidence changed while archiving; retry with stable inputs")
                refs.append({"original": original_ref, "snapshot": snapshot_ref})
    save_json(archive / "evidence-map.json", {
        "receipt": {"original": {"path": str(project / "artifacts/video_review.json"),
                                 "sha256": hashlib.sha256(receipt_bytes).hexdigest()},
                    "snapshot": file_ref(receipt_snapshot)}, "files": refs})
    _save_bytes(project / "artifacts/video_reviews" / f"{digest}.json", receipt_bytes)


def _build_packet(project: Path, video: Path, folder: Path, destination: Path,
                  video_ref: dict, context: list[dict]) -> tuple[dict, list[str]]:
    def prepared_ref(path: Path) -> dict:
        return {"path": str(destination / path.name), "sha256": sha256(path)}

    probe = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)], text=True))
    duration = _duration(probe["format"]["duration"], "output duration")
    decode = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-map", "0:v?", "-map", "0:a?", "-f", "null", "-"],
                            capture_output=True, text=True)
    streams = probe["streams"]
    script_path = project / "artifacts/script.json"
    script = read_json(script_path) if script_path.is_file() else {}
    measured = {"video": video_ref, "probe": probe, "full_decode_exit_code": decode.returncode,
                "full_decode_stderr": decode.stderr, "issues": []}
    technical_issues = _technical_issues(measured, video_ref, duration, script)
    measured["issues"] = technical_issues
    technical_path = folder / "technical.json"
    save_json(technical_path, measured)
    contact = folder / "contact.jpg"
    rows = max(1, math.ceil(math.ceil(duration * 2) / 8))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vf",
                    f"fps=2,scale=180:320,tile=8x{rows}", "-frames:v", "1", str(contact)], check=True)
    # Compare native cuts as well as script beats. Adjacent frames reveal geometry resets.
    detection = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-vf",
                                "select='gt(scene,0.3)',showinfo", "-an", "-f", "null", "-"], capture_output=True, text=True, check=True)
    import re
    cut_times = [float(value) for value in re.findall(r"pts_time:([0-9.]+)", detection.stderr)]
    times = {0.0, max(0, duration - .2)}
    for section in script.get("sections", []):
        for key in ("start_seconds", "end_seconds"):
            if key in section:
                cut_times.append(float(section[key]))
    for cut in cut_times:
        times.update((max(0, cut - .1), min(duration - .05, cut + .1)))
    frames = []
    for time in sorted(times):
        path = folder / f"frame-{time:.3f}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(time), "-i", str(video),
                        "-frames:v", "1", str(path)], check=True)
        frames.append({"seconds": time, **prepared_ref(path)})
    audio = folder / "audio.wav"
    if any(stream["codec_type"] == "audio" for stream in streams):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn", "-ar", "48000",
                        "-ac", "2", str(audio)], check=True)
    packet = {"video": video_ref, "duration_seconds": duration, "context": context,
              "contact": prepared_ref(contact), "frames": frames, "audio": prepared_ref(audio) if audio.exists() else None,
              "contact_layout": {"fps": 2, "columns": 8, "sampled_frames": math.ceil(duration * 2), "padding_cells": rows * 8 - math.ceil(duration * 2)},
              "required_checks": CHECKS, "limitations": "Frames and ASR cannot establish pleasant/natural sound. Inspect temporal behavior; listen to the actual mix."}
    save_json(folder / "packet.json", packet)
    return packet, technical_issues


def _prepare_review(project: Path, video: Path, staged: Path) -> dict:
    video_ref = file_ref(video)
    digest = video_ref["sha256"]
    context = context_refs(project)
    folder = project / "qa/video-review" / digest
    path = project / "artifacts/video_review.json"
    original_review_bytes = path.read_bytes() if path.is_file() else None
    original_review_hash = hashlib.sha256(original_review_bytes).hexdigest() if original_review_bytes is not None else None
    old = _parse_json(original_review_bytes.decode("utf-8"), path.name) if original_review_bytes is not None else None
    if old is not None:
        validate_artifact("video_review", old)
    packet, technical_issues = _build_packet(project, video, staged, folder, video_ref, context)
    if file_ref(video) != video_ref or context_refs(project) != context:
        raise VideoReviewError("Video or planning context changed during preparation; retry with stable inputs")
    if (sha256(path) if path.is_file() else None) != original_review_hash:
        raise VideoReviewError("Reviewer verdict changed during preparation; preserving the newer verdict")
    technical_path = folder / "technical.json"
    technical_ref = {"path": str(technical_path), "sha256": sha256(staged / "technical.json")}
    same_video = old is not None and old["video"]["sha256"] == digest and _resolve(project, old["video"]["path"]) == video
    same_context = old is not None and len(old["context"]) == len(context) and {
        (_resolve(project, ref["path"]), ref["sha256"]) for ref in old["context"]
    } == {(_resolve(project, ref["path"]), ref["sha256"]) for ref in context}
    if same_video and same_context:
        review = copy.deepcopy(old)
        technical = next((check for check in review["checks"] if check["id"] == "technical"), None)
        if technical is not None:
            technical["evidence"] = [technical_ref if _resolve(project, ref["path"]) == technical_path else ref
                                     for ref in technical["evidence"]]
            if technical_issues:
                technical.update(status="FAIL", observation="; ".join(technical_issues))
        # Never promote an existing FAIL/NOT_TESTED or fabricate perceptual reinspection.
    else:
        review = {"version": "1.0", "reviewed_at": datetime.now(timezone.utc).isoformat(),
                  "reviewer": "PENDING", "video": video_ref, "context": context,
                  "checks": [], "findings": []}
        for check_id, purpose in CHECKS.items():
            review["checks"].append({"id": check_id, "status": "NOT_TESTED", "method": "not_performed",
                                     "observation": purpose + ": inspection pending", "time_ranges": [], "evidence": []})
        review["checks"][0].update(status="FAIL" if technical_issues else "PASS", method="technical_analysis",
                                   observation="; ".join(technical_issues) if technical_issues else "Measured probe and full decode match output duration; video and audio streams exist.",
                                   time_ranges=[[0, packet["duration_seconds"]]], evidence=[technical_ref])
    validate_artifact("video_review", review)
    changed_files = [candidate for candidate in staged.iterdir()
                     if not (folder / candidate.name).is_file()
                     or sha256(candidate) != sha256(folder / candidate.name)]
    if old and (changed_files or review != old):
        _archive_review(project, old, original_review_bytes)
    folder.mkdir(parents=True, exist_ok=True)
    if changed_files or review != old:
        # This is deliberately not a multi-file transaction. Publish a blocked
        # packet first and the complete packet last. Any intervening I/O failure
        # retains the archived bytes and requires explicit reprepare; never roll
        # back over an external writer's newer files.
        save_json(folder / "packet.json", {"video": video_ref, "preparation_status": "incomplete",
                                          "started_at": datetime.now(timezone.utc).isoformat()})
        for candidate in changed_files:
            if candidate.name != "packet.json":
                candidate.replace(folder / candidate.name)
        if (sha256(path) if path.is_file() else None) != original_review_hash:
            raise VideoReviewError("Reviewer verdict changed during publication; preserving the newer verdict")
        if review != old:
            save_json(path, review)
        (staged / "packet.json").replace(folder / "packet.json")
    return packet


def prepare_review(project: Path, video: Path) -> dict:
    """Stage measured evidence, archive prior bytes, and preserve reviewer judgments.

    This optional helper does not install a checkpoint hook. Callers must explicitly
    invoke enforce_checkpoint_review at their existing compose/publish boundary.
    """
    project, video = project.resolve(), video.resolve()
    with _preparation_lock(project, video):
        enable_policy(project)
        with tempfile.TemporaryDirectory(prefix=".prepare-", dir=project / "qa/video-review") as folder:
            return _prepare_review(project, video, Path(folder))
