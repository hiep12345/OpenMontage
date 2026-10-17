"""Offline integration coverage for the reusable photographic editorial method."""

import json
import re
import subprocess
from pathlib import Path

import jsonschema

from lib.checkpoint import init_project
from lib.hyperframes_style_bridge import style_bridge
from lib.pipeline_loader import load_pipeline
from styles.playbook_loader import load_playbook
from tools.base_tool import ToolResult
from tools.video.hyperframes_compose import HyperFramesCompose
from tools.video.video_compose import VideoCompose


ROOT = Path(__file__).resolve().parents[2]


def test_canonical_and_legacy_style_bridge_typography_and_muted_color():
    css, _ = style_bridge(load_playbook("photographic-editorial"))
    assert css["--font-heading"] == "Georgia"
    assert css["--font-body"] == "Arial"
    assert css["--color-bg"] == "#F4ECDF"
    assert css["--color-primary"] == "#41291E"
    assert css["--color-accent"] == "#A75F39"
    assert css["--color-muted"] == "#705B4D"

    # Legacy partial dictionaries are still consumed by existing callers.
    legacy, _ = style_bridge({
        "typography": {"heading": {"font": "Legacy Serif"}},
        "visual_language": {"color_palette": {"muted_text": "#654321"}},
    })
    assert legacy["--font-heading"] == "Legacy Serif"
    assert legacy["--color-muted"] == "#654321"


def test_reference_edit_decisions_matches_current_schema_and_animation_route():
    body = (ROOT / "skills/creative/photographic-editorial-motion.md").read_text(encoding="utf-8")
    example = json.loads(re.search(r"```json\n(.*?)\n```", body, re.S).group(1))
    schema = json.loads((ROOT / "schemas/artifacts/edit_decisions.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(example, schema)
    assert example["bespoke"]["composition_id"] == "room-editorial"
    assert example["render_runtime"] == "hyperframes"
    assert example["composition_mode"] == "atelier"
    assert example["renderer_family"] == "animation-first"
    pipeline = load_pipeline("animation")
    assert "photographic-editorial" in pipeline["compatible_playbooks"]["also_works"]


def test_two_projects_keep_assets_and_authored_route_independent(tmp_path, monkeypatch):
    """Use real init/staging/routing; replace CLI and media QA, never a provider."""
    playbook = load_playbook("photographic-editorial")
    projects = []
    for slug, content in (("room-a", b"photo-a"), ("room-b", b"photo-b")):
        project = init_project(
            slug, title=slug, pipeline_type="animation", pipeline_dir=tmp_path,
            style_playbook="photographic-editorial",
        )
        marker = json.loads((project / "project.json").read_text(encoding="utf-8"))
        assert marker["style_playbook"] == "photographic-editorial"
        image = project / "assets/images/before.png"
        image.write_bytes(content)
        workspace = project / "hyperframes"
        manifest = {"version": "1.0", "assets": [
            {"id": "before", "type": "image", "path": str(image),
             "source_tool": "user", "scene_id": "opening"},
        ]}
        scaffold = HyperFramesCompose().execute({
            "operation": "scaffold_workspace", "workspace_path": str(workspace),
            "edit_decisions": {"cuts": [{"id": "opening", "source": "before",
                                           "in_seconds": 0, "out_seconds": 30}]},
            "asset_manifest": manifest, "playbook": playbook,
            "profile": "tiktok_vertical",
        })
        assert scaffold.success, scaffold.error
        generated = (workspace / "index.html").read_text(encoding="utf-8")
        assert "--font-heading: Georgia" in generated
        assert "--color-bg: #F4ECDF" in generated
        assert "--color-muted: #705B4D" in generated
        assert any(p.read_bytes() == content for p in (workspace / "assets").iterdir() if p.is_file())
        # Assets phase hand-authors its final composition after selecting tokens.
        # The generic scaffold is only exercised as existing bridge/staging coverage.
        css, _ = style_bridge(playbook)
        tokens = ";".join(f"{key}:{value}" for key, value in css.items())
        staged = next(p for p in (workspace / "assets").iterdir() if p.is_file())
        authored = f'''<!doctype html><html><head><style>
        :root {{{tokens}}}
        body {{margin:0;background:var(--color-bg)}}
        #room-editorial {{position:relative;width:1080px;height:1920px;overflow:hidden}}
        .backing,.clip {{position:absolute;inset:0;background:var(--color-bg)}}
        </style><script src="vendor/gsap.min.js"></script></head><body>
        <!-- authored {slug} -->
        <main id="room-editorial" data-composition-id="room-editorial"
              data-width="1080" data-height="1920" data-fps="30" data-start="0" data-duration="30">
          <div class="backing"></div>
          <img id="room-photo" class="clip" src="assets/{staged.name}" alt="Before room"
               data-start="0" data-duration="30" data-track-index="0">
        </main><script>
        window.__timelines=window.__timelines||{{}};
        window.__timelines['room-editorial']=gsap.timeline({{paused:true}});
        window.__timelines['room-editorial'].to({{}},{{duration:30}},0);
        </script></body></html>'''
        (workspace / "vendor").mkdir()
        # CLI/browser are mocked: this is a local-file preservation sentinel.
        (workspace / "vendor/gsap.min.js").write_text("// local vendor sentinel", encoding="utf-8")
        (workspace / "index.html").write_text(authored, encoding="utf-8")
        projects.append((project, workspace, manifest, authored))

    calls = []
    monkeypatch.setattr(VideoCompose, "_hyperframes_available", lambda self: True)
    monkeypatch.setattr(HyperFramesCompose, "_runtime_check", lambda self: {"runtime_available": True})
    monkeypatch.setattr(HyperFramesCompose, "_check", lambda self, inputs: ToolResult(success=True, data={"mocked": True}))
    monkeypatch.setattr(VideoCompose, "_run_final_review", lambda self, *a, **k: {"status": "pass", "issues_found": []})

    def forbid_scaffold(self, inputs):
        raise AssertionError("Authored composition must never be scaffolded again")

    monkeypatch.setattr(HyperFramesCompose, "_scaffold", forbid_scaffold)

    def fake_cli(self, args, *, cwd, timeout, check):
        calls.append((args, cwd))
        Path(args[args.index("--output") + 1]).write_bytes(b"mock-render")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(HyperFramesCompose, "_run_hf", fake_cli)
    for project, workspace, manifest, authored in projects:
        result = VideoCompose().execute({
            "operation": "render", "workspace_path": str(workspace),
            "output_path": str(project / "renders/final.mp4"),
            "playbook_name": "photographic-editorial", "asset_manifest": manifest,
            "edit_decisions": {
                "version": "1.0", "cuts": [], "renderer_family": "animation-first",
                "render_runtime": "hyperframes", "composition_mode": "atelier",
                "bespoke": {"entry": str(workspace / "index.html"),
                            "composition_id": "room-editorial", "art_direction": "Warm editorial study"},
            },
        })
        assert result.success, result.error
        assert result.data["operation"] == "render_existing"
        assert result.data["authored_entry_preserved"] is True
        assert (workspace / "index.html").read_text(encoding="utf-8") == authored
    assert len(calls) == 2
    assert calls[0][1] != calls[1][1]
    # Rendering the second workspace cannot replace the first project's source.
    assert (projects[0][0] / "assets/images/before.png").read_bytes() == b"photo-a"
    assert (projects[1][0] / "assets/images/before.png").read_bytes() == b"photo-b"
    for _, workspace, _, _ in projects:
        assert (workspace / "vendor/gsap.min.js").read_text(encoding="utf-8") == "// local vendor sentinel"
