"""Tests for the export_bundle publisher tool.

Covers the tool contract, registry discovery, the export bundle layout, a
schema-valid publish_log, chapter formatting, and the missing-video error path.
"""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.publishers.export_bundle import ExportBundle
from tools.base_tool import ToolStatus, ToolTier
from tools.tool_registry import ToolRegistry
from schemas.artifacts import validate_artifact


def _make_video(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42fakevideo")


def test_contract_metadata():
    tool = ExportBundle()
    info = tool.get_info()
    assert info["name"] == "export_bundle"
    assert info["capability"] == "publish"
    assert info["tier"] == ToolTier.PUBLISH.value
    assert info["provider"] == "local"
    assert info["resource_profile"]["network_required"] is False
    assert tool.get_status() == ToolStatus.AVAILABLE
    assert tool.estimate_cost({}) == 0.0


def test_missing_video_errors(tmp_path):
    result = ExportBundle().execute(
        {"video_path": str(tmp_path / "nope.mp4"), "title": "X"}
    )
    assert result.success is False
    assert "not found" in (result.error or "")


def test_export_bundle_layout_and_publish_log(tmp_path):
    video = tmp_path / "projects" / "demo" / "renders" / "final.mp4"
    _make_video(video)
    subs = tmp_path / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")

    result = ExportBundle().execute(
        {
            "video_path": str(video),
            "title": "Vector Databases Explained in 60 Seconds",
            "export_dir": str(tmp_path / "out"),
            "description": "A quick explainer.",
            "tags": ["vector db", "explainer"],
            "hashtags": ["#ai", "#database"],
            "chapters": [
                {"start_seconds": 0, "title": "Intro"},
                {"start_seconds": 75, "title": "How it works"},
            ],
            "subtitles_path": str(subs),
            "thumbnail_concept": {"text_overlay": "100x FASTER"},
            "platform": "youtube",
            "visibility": "unlisted",
            "timestamp": "2026-06-29T10:30:00+00:00",
        }
    )
    assert result.success is True
    root = Path(result.data["export_path"])

    # Layout
    assert (root / "video" / "output.mp4").is_file()
    assert (root / "video" / "subtitles.srt").is_file()
    assert (root / "metadata" / "metadata.json").is_file()
    assert (root / "metadata" / "description.txt").is_file()
    assert (root / "metadata" / "tags.txt").is_file()
    assert (root / "metadata" / "chapters.txt").is_file()
    assert (root / "thumbnails" / "concept.json").is_file()

    # tags one-per-line
    assert (root / "metadata" / "tags.txt").read_text().splitlines() == ["vector db", "explainer"]
    # chapter formatting (75s -> 1:15)
    assert "1:15 - How it works" in (root / "metadata" / "chapters.txt").read_text()

    # publish_log is schema-valid and shaped right
    plog = result.data["publish_log"]
    validate_artifact("publish_log", plog)
    entry = plog["entries"][0]
    assert entry["status"] == "exported"
    assert entry["platform"] == "youtube"
    assert entry["visibility"] == "unlisted"
    assert entry["export_path"] == str(root)
    assert entry["metadata_used"]["title"].startswith("Vector Databases")


def test_chapter_time_formatting_hours(tmp_path):
    video = tmp_path / "p" / "renders" / "final.mp4"
    _make_video(video)
    result = ExportBundle().execute(
        {
            "video_path": str(video),
            "title": "Long",
            "export_dir": str(tmp_path / "out"),
            "chapters": [{"time_seconds": 3725, "label": "Deep dive"}],  # 1:02:05
        }
    )
    assert result.success is True
    txt = (Path(result.data["export_path"]) / "metadata" / "chapters.txt").read_text()
    assert "1:02:05 - Deep dive" in txt


def test_infer_project_name(tmp_path):
    video = tmp_path / "projects" / "my-cool-video" / "renders" / "final.mp4"
    _make_video(video)
    result = ExportBundle().execute(
        {"video_path": str(video), "title": "T", "export_dir": str(tmp_path / "out")}
    )
    # export still works; project name inference exercised via no-export_dir path below
    assert result.success is True


def test_missing_optional_asset_errors(tmp_path):
    video = tmp_path / "p" / "renders" / "final.mp4"
    _make_video(video)
    for key in ("subtitles_path", "thumbnail_path"):
        result = ExportBundle().execute(
            {
                "video_path": str(video),
                "title": "T",
                "export_dir": str(tmp_path / "out"),
                key: str(tmp_path / "does_not_exist.x"),
            }
        )
        assert result.success is False, key
        assert key in (result.error or "")


def test_default_export_dir_inside_project_workspace(tmp_path):
    # projects/<name>/renders/final.mp4 -> projects/<name>/exports (no export_dir given)
    video = tmp_path / "projects" / "demo" / "renders" / "final.mp4"
    _make_video(video)
    result = ExportBundle().execute({"video_path": str(video), "title": "T"})
    assert result.success is True
    assert Path(result.data["export_path"]) == (tmp_path / "projects" / "demo" / "exports").resolve()


def test_registry_discovers_export_bundle():
    reg = ToolRegistry()
    reg.discover()
    assert reg.get("export_bundle") is not None
    assert reg.get_by_capability("publish")[0].name == "export_bundle"


def test_owned_link_without_exact_review_writes_nothing(tmp_path):
    video = tmp_path / "final.mp4"
    _make_video(video)
    out = tmp_path / "export"
    result = ExportBundle().execute({"video_path": str(video), "title": "Recipe", "export_dir": str(out),
                                     "description": "https://mixtherapy.space/mix/historical-asphaltum-50-25-3/"})
    assert not result.success and "QA failed" in result.error and not out.exists()


def test_exact_review_and_http_seal_actual_export_bytes(monkeypatch, tmp_path):
    from datetime import datetime, timezone
    from lib import caption_links
    from lib.distribution_hub import bytes_digest, digest
    video = tmp_path / "final.mp4"
    _make_video(video)
    tool = ExportBundle()
    url = "https://mixtherapy.space/mix/historical-asphaltum-50-25-3/"
    external = "https://www.youtube.com/@mixtherapy"
    inputs = {"video_path": str(video), "title": "Recipe", "description": "Exact recipe: " + url + "\nChannel: " + external,
              "export_dir": str(tmp_path / "out"), "tags": ["paint"], "chapters": [{"start_seconds": 0, "title": "Mix"}]}
    review = {**tool.caption_review_scope(inputs), "websiteRelease": "a" * 64,
              "reviewer": {"name": "Named owner", "checkedAt": datetime.now(timezone.utc).isoformat(),
                           "semantic": "PASS", "browser": "PASS", "evidence": ["source-and-rendered-review.json"]}}
    inputs["caption_link_review"] = review
    monkeypatch.setattr(caption_links, "check_website", lambda urls, **kwargs: {
        "checkedAt": datetime.now(timezone.utc).isoformat(), "websiteRelease": "a" * 64,
        "checks": [{"url": url, "status": 200, "identity": "historical-asphaltum-50-25-3", "sourceReceiptSha256": "b" * 64}]})
    result = tool.execute(inputs)
    assert result.success
    root = Path(result.data["export_path"])
    qa = json.loads((root / "metadata/caption-link-qa.json").read_text(encoding="utf-8"))
    assert qa == result.data["caption_link_qa"] and qa["assetHash"] == bytes_digest(video.read_bytes())
    assert qa["receiptHash"] == digest({k: v for k, v in qa.items() if k != "receiptHash"})
    assert all(f["urls"] == sorted([url, external]) for f in qa["fields"] if f["id"] in {"file:metadata/metadata.json", "file:metadata/description.txt"})
    assert [c["url"] for c in qa["checks"]] == [url]
    for field in qa["fields"]:
        assert field["sha256"] == bytes_digest((root / field["id"][5:]).read_bytes())
    # A chapter-only edit changes the exact paste-ready description bytes.
    inputs["export_dir"] = str(tmp_path / "changed")
    inputs["chapters"][0]["title"] = "Changed after review"
    assert not tool.execute(inputs).success and not (tmp_path / "changed").exists()


def test_failed_render_review_never_auto_passes(monkeypatch, tmp_path):
    from datetime import datetime, timezone
    from lib import caption_links
    video = tmp_path / "final.mp4"
    _make_video(video)
    tool = ExportBundle()
    inputs = {"video_path": str(video), "title": "Recipe", "description": "https://mixtherapy.space/mix/a/",
              "export_dir": str(tmp_path / "out")}
    inputs["caption_link_review"] = {**tool.caption_review_scope(inputs), "websiteRelease": "a" * 64,
        "reviewer": {"name": "Owner", "checkedAt": datetime.now(timezone.utc).isoformat(), "semantic": "PASS",
                     "browser": "NOT_TESTED", "evidence": ["partial-review.json"]}}
    monkeypatch.setattr(caption_links, "check_website", lambda _, **kwargs: pytest.fail("Unreviewed export accessed website"))
    assert not tool.execute(inputs).success and not (tmp_path / "out").exists()


def test_export_preserves_prior_revision_metadata(tmp_path):
    video = tmp_path / "final.mp4"
    _make_video(video)
    inputs = {"video_path": str(video), "title": "Original", "export_dir": str(tmp_path / "out")}
    assert ExportBundle().execute(inputs).success
    original = (tmp_path / "out/metadata/metadata.json").read_bytes()
    inputs["title"] = "New revision"
    assert not ExportBundle().execute(inputs).success
    assert (tmp_path / "out/metadata/metadata.json").read_bytes() == original
