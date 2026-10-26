"""Analysis outputs are created only for valid sources and isolated per call."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tools.analysis import video_analyzer


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("source_kind", ["missing", "directory"])
def test_invalid_local_source_has_no_output_side_effects(tmp_path, monkeypatch, explicit, source_kind):
    projects = tmp_path / "projects"
    monkeypatch.setattr(video_analyzer, "PROJECTS_DIR", projects)
    source = tmp_path / source_kind
    if source_kind == "directory":
        source.mkdir()
    output = tmp_path / "explicit"
    inputs = {"source": str(source)}
    if explicit:
        inputs["output_dir"] = str(output)

    result = video_analyzer.VideoAnalyzer().execute(inputs)

    assert not result.success
    assert "not a file" in result.error
    assert not projects.exists()
    assert not output.exists()


def test_default_outputs_are_canonical_and_unique_even_concurrently(tmp_path, monkeypatch):
    projects = tmp_path / "canonical-projects"
    monkeypatch.setattr(video_analyzer, "PROJECTS_DIR", projects)
    monkeypatch.setattr(video_analyzer.VideoAnalyzer, "_get_duration", lambda *_: 12)
    monkeypatch.setattr(video_analyzer.time, "time", lambda: 123456)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    foreign_cwd = tmp_path / "foreign-cwd"
    foreign_cwd.mkdir()
    monkeypatch.chdir(foreign_cwd)

    def analyze(_):
        return video_analyzer.VideoAnalyzer().execute({
            "source": str(source), "analysis_depth": "transcript_only",
        })

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(analyze, range(8)))

    outputs = [Path(result.artifacts[0]) for result in results]
    assert all(result.success for result in results)
    assert len(set(outputs)) == 8
    assert all(path.parent.parent == projects / "_analysis" for path in outputs)
    assert all(path.is_file() for path in outputs)
    assert not (foreign_cwd / "projects").exists()


def test_explicit_output_and_partial_brief_are_preserved(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture")
    output = tmp_path / "requested"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("existing output")

    def fail_metadata(*_):
        raise RuntimeError("probe unavailable")

    monkeypatch.setattr(video_analyzer.VideoAnalyzer, "_get_duration", fail_metadata)
    result = video_analyzer.VideoAnalyzer().execute({
        "source": str(source), "analysis_depth": "transcript_only", "output_dir": str(output),
    })

    assert result.success
    assert result.artifacts == [str(output / "video_analysis_brief.json")]
    brief = json.loads(Path(result.artifacts[0]).read_text(encoding="utf-8"))
    assert brief["_analysis_meta"]["steps_failed"] == ["metadata: probe unavailable"]
    assert sentinel.read_text() == "existing output"
