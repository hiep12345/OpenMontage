"""Vertical / arbitrary-resolution support for video_compose's FFmpeg compose.

Regression test for a silent-dimension bug: the compose target resolution was
resolved from `profile` (and the documented `metadata.compose_target` hook) but
the per-segment scale/pad filter hardcoded 1920x1080, so vertical profiles like
`tiktok` silently produced landscape output. Dimension tests run the real FFmpeg
path on a tiny lavfi fixture and assert the output dimensions. Routing tests mock
renderers to verify explicit choices and unavailable-runtime refusal without
launching Node or providers.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tools.video.video_compose import VideoCompose
from tools.base_tool import ToolResult

requires_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not available",
)


def _make_clip(path: Path, w: int = 1280, h: int = 720, d: int = 2) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"color=c=teal:s={w}x{h}:d={d}:r=30",
         "-c:v", "libx264", "-crf", "28", "-pix_fmt", "yuv420p",
         "-g", "30", "-keyint_min", "30", str(path)],
        capture_output=True, check=True,
    )


def _dims(path: Path) -> tuple[int, int]:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)]
    ).decode().strip()
    w, h = out.split(",")
    return int(w), int(h)


def _edit_decisions(src: Path, metadata: dict | None = None) -> dict:
    ed = {
        "version": "1.0",
        "render_runtime": "ffmpeg",
        "cuts": [{"id": "c1", "source": str(src), "in_seconds": 0, "out_seconds": 2}],
    }
    if metadata:
        ed["metadata"] = metadata
    return ed


@requires_ffmpeg
def test_compose_default_is_landscape_hd(tmp_path):
    """No profile / no target → unchanged 1920x1080 default (backward compatible)."""
    src = tmp_path / "in.mp4"
    _make_clip(src)
    out = tmp_path / "out.mp4"
    r = VideoCompose().execute(
        {"operation": "compose", "edit_decisions": _edit_decisions(src), "output_path": str(out)}
    )
    assert r.success, r.error
    assert _dims(out) == (1920, 1080)


@requires_ffmpeg
def test_compose_vertical_profile(tmp_path):
    """profile='tiktok' → 1080x1920 (the bug: previously stayed 1920x1080)."""
    src = tmp_path / "in.mp4"
    _make_clip(src)
    out = tmp_path / "out.mp4"
    r = VideoCompose().execute(
        {"operation": "compose", "edit_decisions": _edit_decisions(src),
         "profile": "tiktok", "output_path": str(out)}
    )
    assert r.success, r.error
    assert _dims(out) == (1080, 1920)


@requires_ffmpeg
def test_compose_target_override_cover(tmp_path):
    """metadata.compose_target with fit='cover' → exact requested dims, cropped to fill."""
    src = tmp_path / "in.mp4"
    _make_clip(src)
    out = tmp_path / "out.mp4"
    ed = _edit_decisions(src, metadata={"compose_target": {"width": 720, "height": 1280, "fit": "cover"}})
    r = VideoCompose().execute(
        {"operation": "compose", "edit_decisions": ed, "output_path": str(out)}
    )
    assert r.success, r.error
    assert _dims(out) == (720, 1280)


def _render_inputs(tmp_path, runtime):
    decisions = _edit_decisions(Path("source.mp4"))
    decisions.update(render_runtime=runtime, renderer_family="explainer-data")
    return {
        "edit_decisions": decisions,
        "asset_manifest": {"assets": [{"id": "a1", "path": "source.mp4"}]},
        "output_path": str(tmp_path / "out.mp4"),
    }


def test_render_unavailable_selected_remotion_never_substitutes_ffmpeg(tmp_path, monkeypatch):
    tool = VideoCompose()
    monkeypatch.setattr(tool, "_pre_compose_validation", lambda *args: None)
    monkeypatch.setattr(tool, "_remotion_available", lambda: False)

    def unexpected_render(*args, **kwargs):
        pytest.fail("Unavailable selected Remotion must block before any renderer")

    for method in ("_remotion_render", "_compose", "_render_via_ffmpeg", "_render_via_hyperframes"):
        monkeypatch.setattr(tool, method, unexpected_render)

    inputs = _render_inputs(tmp_path, "remotion")
    result = tool._render(inputs)

    assert result.success is False
    assert "remotion" in result.error.lower()
    assert "unavailable" in result.error.lower()
    assert inputs["edit_decisions"]["render_runtime"] == "remotion"
    assert not Path(inputs["output_path"]).exists()


def test_render_simple_cuts_preserve_selected_remotion(tmp_path, monkeypatch):
    tool = VideoCompose()
    monkeypatch.setattr(tool, "_pre_compose_validation", lambda *args: None)
    monkeypatch.setattr(tool, "_remotion_available", lambda: True)
    captured = []

    def render_remotion(inputs):
        captured.append(inputs)
        return ToolResult(success=True, data={"runtime": "remotion"})

    def unexpected_ffmpeg(*args, **kwargs):
        pytest.fail("Simple video cuts do not change the selected runtime")

    monkeypatch.setattr(tool, "_remotion_render", render_remotion)
    monkeypatch.setattr(tool, "_compose", unexpected_ffmpeg)
    monkeypatch.setattr(tool, "_render_via_ffmpeg", unexpected_ffmpeg)
    result = tool._render(_render_inputs(tmp_path, "remotion"))

    assert result.success, result.error
    assert result.data["runtime"] == "remotion"
    assert len(captured) == 1
    assert captured[0]["edit_decisions"]["render_runtime"] == "remotion"
    assert captured[0]["edit_decisions"]["cuts"][0]["source"] == "source.mp4"


def test_render_explicit_ffmpeg_does_not_probe_or_select_remotion(tmp_path, monkeypatch):
    tool = VideoCompose()
    monkeypatch.setattr(tool, "_pre_compose_validation", lambda *args: None)
    captured = []

    def unexpected_remotion(*args, **kwargs):
        pytest.fail("An explicit FFmpeg choice must stay on its own path")

    def render_ffmpeg(**kwargs):
        captured.append(kwargs)
        return ToolResult(success=True, data={"runtime": "ffmpeg"})

    monkeypatch.setattr(tool, "_remotion_available", unexpected_remotion)
    monkeypatch.setattr(tool, "_remotion_render", unexpected_remotion)
    monkeypatch.setattr(tool, "_render_via_ffmpeg", render_ffmpeg)
    result = tool._render(_render_inputs(tmp_path, "ffmpeg"))

    assert result.success, result.error
    assert result.data["runtime"] == "ffmpeg"
    assert len(captured) == 1
    assert captured[0]["edit_decisions"]["render_runtime"] == "ffmpeg"
