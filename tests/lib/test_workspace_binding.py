"""Portable workspace fixtures: never read an owner's binding or production."""
import json
from pathlib import Path
import subprocess
import stat

import pytest

from lib import workspace as ws


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()


@pytest.fixture
def binding(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENMONTAGE_WORKSPACE_CONFIG", raising=False)
    monkeypatch.delenv("OPENMONTAGE_PROJECTS_DIR", raising=False)
    outer = tmp_path / "workspace"
    source = outer / "source"
    source.mkdir(parents=True)
    git(source, "init")
    git(source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--allow-empty", "-m", "fixture")
    worktree = tmp_path / "worktree"
    git(source, "worktree", "add", "--detach", str(worktree))
    data = {"schema_version": 1, "workspace_id": "fixture-workspace",
            "workspace_root": str(outer), "canonical_source_dir": str(source),
            "git_common_dir": str(source / ".git"), "projects_dir": str(outer / "projects"),
            "legacy_projects_dirs": [str(source / "projects")], "owner_context": str(outer / "AGENTS.md"),
            "private_skills_dir": str(source / ".agents" / "skills"), "private_skill_names": ["private-example"]}
    config = outer / ws.MARKER
    config.parent.mkdir()
    config.write_text(json.dumps(data))
    monkeypatch.setattr(ws, "REPO_ROOT", worktree)
    try:
        yield data, config, source, worktree
    finally:
        # Git object files are read-only on Windows; the invocation-owned test
        # runner must be able to clean this fixture after successful checks.
        for path in (source / ".git").rglob("*"):
            if path.is_file():
                path.chmod(stat.S_IREAD | stat.S_IWRITE)


def rewrite(binding, **changes):
    data, config, *_ = binding
    data.update(changes)
    config.write_text(json.dumps(data))


def test_canonical_and_worktree_share_binding(binding):
    _, _, source, worktree = binding
    assert ws.resolve_workspace(source) == ws.resolve_workspace(worktree)
    assert ws.resolve_workspace(source.parent) == ws.resolve_workspace(worktree)
    assert ws.project_roots() == (source.parent / "projects", source / "projects")


def test_no_ancestor_scan_and_public_clone_default(binding, monkeypatch, tmp_path):
    _, _, source, _ = binding
    nested = source / "nested"
    nested.mkdir()
    git(nested, "init")
    monkeypatch.setattr(ws, "REPO_ROOT", nested)
    assert ws.resolve_workspace() is None
    assert ws.project_roots() == (nested / "projects",)


def test_explicit_marker_requires_matching_git_and_exact_location(binding, monkeypatch, tmp_path):
    _, config, _, _ = binding
    monkeypatch.setenv("OPENMONTAGE_WORKSPACE_CONFIG", str(config))
    assert ws.resolve_workspace().config_path == config
    rewrite(binding, git_common_dir=str(tmp_path / "different"))
    with pytest.raises(ws.WorkspaceError, match="mismatch"):
        ws.resolve_workspace()


@pytest.mark.parametrize("changes", [
    {"schema_version": True}, {"schema_version": 2}, {"workspace_id": "../bad"},
    {"projects_dir": "relative"}, {"private_skill_names": ["../bad"]},
    {"unexpected": True}, {"legacy_projects_dirs": "wrong"},
])
def test_invalid_binding_fails_closed(binding, changes):
    rewrite(binding, **changes)
    with pytest.raises(ws.WorkspaceError):
        ws.resolve_workspace()


def test_no_traversal_or_overlapping_roots(binding):
    data, _, source, _ = binding
    rewrite(binding, projects_dir=str(source / ".." / "projects"))
    with pytest.raises(ws.WorkspaceError, match="canonical"):
        ws.resolve_workspace()
    rewrite(binding, projects_dir=str(source.parent / "projects"), legacy_projects_dirs=[str(source.parent / "projects" / "nested")])
    with pytest.raises(ws.WorkspaceError, match="overlapping"):
        ws.resolve_workspace()


def test_runs_resume_legacy_create_primary_and_reject_collision(binding, tmp_path):
    _, _, source, _ = binding
    legacy = source / "projects" / "old"
    legacy.mkdir(parents=True)
    assert ws.resolve_project_dir("old", create=True) == legacy
    assert ws.resolve_project_dir("new", create=True) == source.parent / "projects" / "new"
    (source.parent / "projects" / "old").mkdir()
    with pytest.raises(ws.WorkspaceError, match="collision"):
        ws.resolve_project_dir("old")
    with pytest.raises(ws.WorkspaceError, match="collision"):
        list(ws.iter_project_dirs())
    assert ws.resolve_project_dir("old", source / "projects") == legacy
    assert ws.resolve_project_dir("fixture", tmp_path).parent == tmp_path


@pytest.mark.parametrize("project_id", ["", ".", "..", "a/b", "a\\b", "C:", "a\0b", "alias.", "alias ", "NUL", "con.txt"])
def test_invalid_project_id(binding, project_id):
    with pytest.raises(ws.WorkspaceError):
        ws.resolve_project_dir(project_id, create=True)


def test_explicit_root_override_is_isolated(binding, monkeypatch, tmp_path):
    override = tmp_path / "staging"
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(override))
    assert ws.project_roots() == (override,)
    assert ws.resolve_project_dir("new", create=True) == override / "new"


def test_private_sources_are_explicit_and_missing_is_an_error(binding):
    _, _, source, _ = binding
    assert ws.private_skill_dir("public-example") is None
    with pytest.raises(ws.WorkspaceError, match="missing"):
        ws.owner_context_path()
    (source.parent / "AGENTS.md").write_text("owner context")
    assert ws.owner_context_path() == source.parent / "AGENTS.md"
    with pytest.raises(ws.WorkspaceError, match="missing"):
        ws.private_skill_dir("private-example")
    private = source / ".agents" / "skills" / "private-example"
    private.mkdir(parents=True)
    (private / "SKILL.md").write_text("private fixture")
    assert ws.private_skill_dir("private-example") == private


def test_linked_project_is_rejected(binding, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    primary = ws.project_roots()[0]
    primary.mkdir()
    try:
        (primary / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    with pytest.raises(ws.WorkspaceError, match="links"):
        ws.resolve_project_dir("linked")


def test_events_and_board_find_legacy_and_reject_collisions(binding, monkeypatch):
    from lib import events
    from backlot import state
    primary, legacy = ws.project_roots()
    run = legacy / "legacy-film"
    run.mkdir(parents=True)
    monkeypatch.setattr(events, "PROJECTS_DIR", primary)
    monkeypatch.setattr(state, "PROJECTS_DIR", primary)
    assert events.infer_project_dir({"output_path": run / "assets" / "frame.png"}) == run
    assert [p["project_id"] for p in state.list_projects()] == ["legacy-film"]
    (primary / "legacy-film").mkdir(parents=True)
    assert events.infer_project_dir({"project_dir": run}) is None
    with pytest.raises(ws.WorkspaceError, match="collision"):
        state.list_projects()


def test_scaffold_and_handoff_reports_use_existing_legacy_run(binding):
    from scripts.scaffold_atelier_project import scaffold
    from lib.hub_diagnostics import HandoffReport
    _, _, source, worktree = binding
    legacy = source / "projects"
    (legacy / "atelier-film").mkdir(parents=True)
    (legacy / "hub-handoffs").mkdir()
    project = scaffold("atelier-film", "AtelierFilm", worktree)
    assert project == legacy / "atelier-film"
    assert scaffold("atelier-film", "AtelierFilm") == project
    assert project.as_posix() in (project / "README.md").read_text(encoding="utf-8")
    assert HandoffReport({"operation": "inspect"}).path.is_relative_to(legacy / "hub-handoffs")
    assert not (source.parent / "projects" / "atelier-film").exists()


def test_scaffold_default_honors_override_in_bound_workspace(binding, monkeypatch, tmp_path):
    from scripts.scaffold_atelier_project import main
    _, _, source, _ = binding
    override = tmp_path / "scaffold-override"
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(override))
    assert main(["override-film"]) == 0
    assert (override / "override-film" / "Composition.tsx").is_file()
    assert not (source.parent / "projects" / "override-film").exists()


@pytest.mark.parametrize("override_enabled", [False, True])
def test_scaffold_default_in_public_checkout(monkeypatch, tmp_path, override_enabled):
    from scripts.scaffold_atelier_project import main
    monkeypatch.delenv("OPENMONTAGE_WORKSPACE_CONFIG", raising=False)
    monkeypatch.delenv("OPENMONTAGE_PROJECTS_DIR", raising=False)
    source = tmp_path / "public-checkout"
    source.mkdir()
    git(source, "init")
    monkeypatch.setattr(ws, "REPO_ROOT", source)
    selected = tmp_path / "override" if override_enabled else source / "projects"
    if override_enabled:
        monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(selected))
    assert main(["public-film"]) == 0
    assert (selected / "public-film" / "Composition.tsx").is_file()
    if override_enabled:
        assert not (source / "projects").exists()


def test_scaffold_explicit_root_preserves_standalone_target(binding, monkeypatch, tmp_path):
    from scripts.scaffold_atelier_project import main
    override = tmp_path / "override"
    standalone = tmp_path / "standalone"
    standalone.mkdir()
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(override))
    assert main(["explicit-film", "--root", str(standalone)]) == 0
    assert (standalone / "projects" / "explicit-film" / "Composition.tsx").is_file()
    assert not override.exists()


def test_snapshots_use_selected_external_root_without_rendering(binding, monkeypatch):
    import sys
    from types import SimpleNamespace
    from scripts import atelier_snapshots
    _, _, source, _ = binding
    project = source.parent / "projects" / "snapshot-film"
    (project / "artifacts").mkdir(parents=True)
    (project / "artifacts" / "scene_plan.json").write_text(json.dumps({"scenes": [{"id": "s1", "start_seconds": 0, "end_seconds": 1}]}))
    monkeypatch.setitem(sys.modules, "tools.video.video_compose", SimpleNamespace(
        VideoCompose=lambda: SimpleNamespace(_stage_atelier_project=lambda entry, composer: entry)))
    calls = []
    original_run = subprocess.run
    def fake_run(cmd, **kwargs):
        if cmd[0] == "git":
            return original_run(cmd, **kwargs)
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(atelier_snapshots.subprocess, "run", fake_run)
    assert atelier_snapshots.main(["snapshot-film", "--composition-id", "Film", "--fps", "30"]) == 0
    assert str(project / "snapshots" / "s1.png") in calls[0]


def test_backlot_serves_legacy_media_and_rejects_duplicate_id(binding, monkeypatch):
    from backlot import server
    from fastapi.testclient import TestClient
    primary, legacy = ws.project_roots()
    run = legacy / "film"
    run.mkdir(parents=True)
    (run / "frame.png").write_bytes(b"fixture image bytes")
    monkeypatch.setattr(server, "PROJECTS_DIR", primary)
    monkeypatch.setattr(server, "_summary_cache", {})
    async def no_watch():
        pass
    monkeypatch.setattr(server, "_watch_projects", no_watch)
    with TestClient(server.create_app()) as client:
        assert client.get("/api/projects").json()[0]["project_id"] == "film"
        assert client.get("/api/project/film/state").status_code == 200
        assert client.get("/media/film/frame.png").content == b"fixture image bytes"
        (primary / "film").mkdir(parents=True)
        assert client.get("/api/projects").status_code == 409
        assert client.get("/api/project/film/state").status_code == 409
        assert client.get("/media/film/frame.png").status_code == 409


def test_watcher_observes_both_explicit_roots(binding, monkeypatch):
    import asyncio
    import os
    import watchfiles
    from backlot import server
    primary, legacy = ws.project_roots()
    primary.mkdir(parents=True)
    legacy.mkdir(parents=True)
    monkeypatch.setattr(server, "PROJECTS_DIR", primary)
    monkeypatch.setattr(server, "_PROJECTS_ROOT_STR", os.path.normcase(str(primary)))
    seen = []
    published = []
    async def fake_awatch(*roots, **kwargs):
        seen.extend(roots)
        yield {(1, str(legacy / "film" / "project.json"))}
    monkeypatch.setattr(watchfiles, "awatch", fake_awatch)
    monkeypatch.setattr(server.hub, "publish", published.append)
    asyncio.run(server._watch_projects())
    assert seen == [primary, legacy]
    assert published == ["film"]
