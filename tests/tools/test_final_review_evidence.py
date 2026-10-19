"""Technical evidence must never masquerade as watching/listening to a render."""

import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import jsonschema
import pytest

from tools.base_tool import ToolResult
from tools.video.video_compose import VideoCompose


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    root = tmp_path_factory.mktemp("review-media")
    files = {}
    for name, sound in (("tone", True), ("silent", False)):
        path = root / f"{name}.mp4"
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=2"]
        if sound:
            cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "aac"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", str(path)]
        subprocess.run(cmd, capture_output=True, check=True, timeout=30)
        files[name] = path
    return files


def review_media(media, tmp_path, name="tone", edit=None):
    output = tmp_path / f"{name}.mp4"
    shutil.copy2(media[name], output)
    return VideoCompose()._run_final_review(output, edit)


def validate(report):
    schema = Path(__file__).resolve().parents[2] / "schemas/artifacts/final_review.schema.json"
    jsonschema.validate(report, json.loads(schema.read_text(encoding="utf-8")))
    # jsonschema's Python number check alone does not reject NaN/Infinity.
    json.dumps(report, allow_nan=False)


def test_tone_and_frames_are_preparation_not_perceptual_acceptance(media, tmp_path):
    report = review_media(media, tmp_path)
    audio = report["checks"]["audio_spotcheck"]
    assert audio["technical_analysis_status"] == "PASS"
    assert isinstance(audio["mean_volume_dbfs"], float)
    for field in ("narration_present", "music_present", "mix_intelligible",
                  "unexpected_silence", "clipping_detected"):
        assert audio[field] is None
    visual = report["checks"]["visual_spotcheck"]
    assert visual["frames_sampled"] == 4
    assert all(Path(p).is_file() for p in visual["frame_paths"])
    assert visual["black_frames_detected"] is None  # Even this tiny, black PNG needs inspection.
    assert visual["broken_overlays"] is None
    assert visual["review_status"] == audio["review_status"] == "NOT_TESTED"
    assert report["status"] == "revise"
    assert report["recommended_action"] == "block"
    assert report["metadata"]["review_scope"] == "automated_technical_only"
    assert report["checks"]["promise_preservation"]["delivery_promise_honored"] is None
    validate(report)


def test_intentionally_silent_output_has_no_invented_missing_narration_defect(media, tmp_path):
    report = review_media(media, tmp_path, "silent")
    assert report["checks"]["technical_probe"]["has_audio"] is False
    assert report["checks"]["technical_probe"]["issues"] == []
    audio = report["checks"]["audio_spotcheck"]
    assert audio["technical_analysis_status"] == "NOT_APPLICABLE"
    assert audio["narration_present"] is None
    assert audio["unexpected_silence"] is None
    assert report["recommended_action"] == "block"  # Review intent, don't invent narration.
    validate(report)


@pytest.mark.parametrize("code,stderr", [
    (1, "mean_volume: -10 dB\nmax_volume: -1 dB"),
    (0, ""),
    (0, "mean_volume: nan dB\nmax_volume: -1 dB"),
    (0, "mean_volume: -inf dB\nmax_volume: -1 dB"),
    (0, "mean_volume: -10 dB\nmax_volume: inf dB"),
])
def test_failed_or_nonfinite_levels_never_become_audio_acceptance(
    media, tmp_path, monkeypatch, code, stderr
):
    run = subprocess.run

    def fake_run(cmd, **kwargs):
        if "volumedetect" in cmd:
            return SimpleNamespace(returncode=code, stderr=stderr)
        return run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    report = review_media(media, tmp_path)
    audio = report["checks"]["audio_spotcheck"]
    assert audio["technical_analysis_status"] == "FAIL"
    assert audio["narration_present"] is None
    assert "mean_volume_dbfs" not in audio
    assert report["status"] != "pass"
    validate(report)


def test_quiet_audio_is_a_measurement_not_an_unexpected_silence_verdict(media, tmp_path, monkeypatch):
    run = subprocess.run

    def fake_run(cmd, **kwargs):
        if "volumedetect" in cmd:
            return SimpleNamespace(returncode=0, stderr="mean_volume: -80 dB\nmax_volume: -0.1 dB")
        return run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    report = review_media(media, tmp_path)
    audio = report["checks"]["audio_spotcheck"]
    assert audio["mean_below_minus60_dbfs"] is True
    assert audio["peak_above_minus0_5_dbfs"] is True
    assert audio["unexpected_silence"] is audio["clipping_detected"] is None
    assert report["recommended_action"] == "block"


def test_failed_extraction_cannot_reuse_prior_review_frames(media, tmp_path, monkeypatch):
    first = review_media(media, tmp_path)
    paths = first["checks"]["visual_spotcheck"]["frame_paths"]
    assert len(paths) == 4
    run = subprocess.run

    def fail_frames(cmd, **kwargs):
        if "-frames:v" in cmd:
            # Even a partial file from this failed command must not be counted.
            Path(cmd[-1]).write_bytes(b"partial")
            return SimpleNamespace(returncode=1)
        return run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_frames)
    second = VideoCompose()._run_final_review(tmp_path / "tone.mp4")
    assert second["checks"]["visual_spotcheck"]["frames_sampled"] == 0
    assert all(Path(p).is_file() for p in paths)
    validate(second)


def test_invalid_container_still_fails_with_schema_valid_zero_frame_report(tmp_path):
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"not a video")
    report = VideoCompose()._run_final_review(path)
    assert report["status"] == "fail"
    assert report["recommended_action"] == "re_render"
    assert report["checks"]["visual_spotcheck"]["frames_sampled"] == 0
    validate(report)


def test_subtitle_source_is_not_proof_of_burn_in_or_coverage(media, tmp_path):
    source = tmp_path / "captions.srt"
    source.write_text("1\n00:00:00,000 --> 00:00:01,000\nNever burned in\n", encoding="utf-8")
    report = review_media(media, tmp_path, edit={"subtitles": {"enabled": True, "source": str(source)}})
    subs = report["checks"]["subtitle_check"]
    assert subs["subtitle_source_exists"] is True
    assert subs["subtitle_stream_present"] is False
    assert subs["subtitles_present"] is None
    assert "coverage_ratio" not in subs
    validate(report)


def test_legacy_boolean_report_remains_schema_compatible():
    validate({
        "version": "1.0", "output_path": "historical.mp4", "status": "pass",
        "checks": {
            "technical_probe": {"valid_container": True},
            "visual_spotcheck": {"frames_sampled": 4, "black_frames_detected": False},
            "audio_spotcheck": {"narration_present": True, "music_present": False},
            "promise_preservation": {"delivery_promise_honored": True, "runtime_swap_detected": False},
            "subtitle_check": {"subtitles_present": True, "coverage_ratio": 1.0},
        },
    })


def test_ffmpeg_caller_preserves_successful_render_and_pending_review(media, tmp_path, monkeypatch):
    output = tmp_path / "output.mp4"
    shutil.copy2(media["tone"], output)
    tool = VideoCompose()
    monkeypatch.setattr(tool, "_compose", lambda inputs: ToolResult(success=True, data={"output_path": str(output)}))
    result = tool._render_via_ffmpeg(
        inputs={}, edit_decisions={}, resolved_cuts=[], output_path=output, profile=None,
    )
    assert result.success is True
    assert result.data["final_review_status"] == "revise"
    assert result.data["final_review"]["recommended_action"] == "block"
    assert output.exists()
