"""Offline source-consumption tests with a real temporary Git workspace."""
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess

import pytest

from lib import stage_context as sc
from lib import session_recovery as recovery
from lib.session_recovery import RecoveryError, recover
from tests.lib.test_stage_context import make_project
from tests.lib.test_session_recovery import make_run

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def bound(tmp_path, monkeypatch):
    outer = tmp_path / "owner-workspace"
    source = outer / "source"
    source.mkdir(parents=True)
    subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
    shutil.copyfile(REPO / "PROJECT_CONTEXT.md", source / "PROJECT_CONTEXT.md")
    (source / "AGENTS.md").write_text("# Owner production rules\n", encoding="utf-8")
    (outer / "AGENTS.md").write_text(
        "# Local owner context\n\n## Receiving owner boundary\n"
        "Read the selected receiving contract before packaging.\n\n"
        "## Website boundary\nUse the designated owner evidence.\n", encoding="utf-8")
    skills = source / ".agents/skills"
    skill = skills / "owner-method"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Selected canonical method\nPreserve owner constraints.\n", encoding="utf-8")
    data = {"schema_version": 1, "workspace_id": "test-workspace", "workspace_root": str(outer),
            "git_common_dir": str(source / ".git"), "canonical_source_dir": str(source),
            "projects_dir": str(outer / "projects"), "legacy_projects_dirs": [str(source / "projects")],
            "owner_context": str(outer / "AGENTS.md"), "private_skills_dir": str(skills),
            "private_skill_names": ["owner-method"]}
    marker = outer / ".codex/openmontage-workspace.json"
    marker.parent.mkdir()
    marker.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("OPENMONTAGE_WORKSPACE_CONFIG", str(marker))
    yield outer, source, skill, marker
    # Git creates read-only objects on Windows; leave invocation-owned scratch
    # deletable by the repository runner after the tests finish.
    for path in (source / ".git").rglob("*"):
        if path.is_file():
            path.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_owner_context_and_objectives_recovered_with_exact_source(bound):
    outer, source, _, marker = bound
    context_file = source / "PROJECT_CONTEXT.md"
    text = context_file.read_text(encoding="utf-8")
    objective = "\n\n## Owner's creative-production objective (fixture)\n\n" + "\n\n".join(
        ["Preserve supplied audience goals. " * 36, "Keep distinct channels and formats.",
         "Measured outputs and rework establish results; no extra spend is authorized."])
    context_file.write_text(text + objective, encoding="utf-8")
    result = recover(workspace=source)
    binding = result["workspace_binding"]
    assert binding["source"]["sha256"] == hashlib.sha256(marker.read_bytes()).hexdigest()
    owner = binding["owner_context"]
    assert owner["status"] == "AVAILABLE"
    assert owner["sections"]["Website boundary"]["data"] == "Use the designated owner evidence."
    assert owner["source"]["path"] == str(outer / "AGENTS.md")
    selected = result["overview"]["sections"]["Owner's creative-production objective (fixture)"]
    assert selected["truncated"] and not selected["paragraphs_truncated"]
    assert "no extra spend" in selected["operative_objectives"][-1]["data"]
    assert result["task"] is result["run"] is None


def test_worktree_and_outer_recovery_share_owner_identity_keep_executing_source(bound):
    outer, source, _, _ = bound
    subprocess.run(["git", "-C", str(source), "add", "PROJECT_CONTEXT.md"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
                    "commit", "-m", "Fixture"], check=True, capture_output=True)
    worktree = outer.parent / "worktree"
    subprocess.run(["git", "-C", str(source), "worktree", "add", "--detach", str(worktree)], check=True, capture_output=True)
    worktree_result = recover(workspace=worktree)
    canonical = worktree_result["workspace_binding"]["canonical_project_overview"]
    assert canonical["source_checkout"] == str(source)
    assert worktree_result["overview"]["source_checkout"] == str(worktree)
    # Outer recovery follows its validated canonical source, never a directory scan.
    outer_result = recover(workspace=outer)
    assert outer_result["workspace_binding"]["workspace_id"] == "test-workspace"
    assert outer_result["overview"]["source_checkout"] == str(source)


def test_missing_owner_context_visible_without_task_or_run_selection(bound):
    outer, source, _, _ = bound
    (outer / "AGENTS.md").unlink()
    result = recover(workspace=source)
    assert result["workspace_binding"]["owner_context"]["status"] == "MISSING"
    assert result["task"] is result["run"] is None


def test_invalid_binding_is_not_silently_ignored(bound):
    _, source, _, marker = bound
    marker.write_text("{}", encoding="utf-8")
    with pytest.raises(RecoveryError):
        recover(workspace=source)


def test_binding_change_cannot_claim_old_identity_with_new_source_hash(bound, monkeypatch):
    outer, source, _, marker = bound
    original = recovery._bytes
    def changing_read(path, *args):
        raw = original(path, *args)
        if path == outer / "AGENTS.md":
            data = json.loads(marker.read_text(encoding="utf-8"))
            data["workspace_id"] = "changed-workspace"
            marker.write_text(json.dumps(data), encoding="utf-8")
        return raw
    monkeypatch.setattr(recovery, "_bytes", changing_read)
    with pytest.raises(RecoveryError, match="binding changed"):
        recover(workspace=source)


def test_bound_external_run_uses_executing_schemas_and_explicit_roots(bound):
    outer, source, _, _ = bound
    for name in ("pipelines/pipeline_manifest", "checkpoints/checkpoint", "artifacts/decision_log"):
        relative = "schemas/" + name + ".schema.json"
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, destination)
    (source / "pipeline_defs").mkdir()
    (source / "pipeline_defs/test.yaml").write_text(
        'name: test\nversion: "1.0"\nstages:\n'
        '  - name: idea\n    human_approval_default: true\n'
        '  - name: assets\n    human_approval_default: false\n', encoding="utf-8")
    run = make_run(outer)
    result = recover(workspace=source, project=run)
    assert result["run"]["project"] == str(run)
    assert result["run"]["manifest"]["source"]["path"] == str(source / "pipeline_defs/test.yaml")
    assert result["task"] is None
    legacy = make_run(source, "legacy-episode")
    assert recover(workspace=source, project=legacy)["run"]["project"] == str(legacy)
    with pytest.raises(RecoveryError, match="outside the bound"):
        recover(workspace=source, project=source)


def test_public_clone_functional_without_owner_binding(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENMONTAGE_WORKSPACE_CONFIG", raising=False)
    shutil.copyfile(REPO / "PROJECT_CONTEXT.md", tmp_path / "PROJECT_CONTEXT.md")
    result = recover(workspace=tmp_path)
    assert result["workspace_binding"]["status"] == "UNBOUND_PUBLIC_CHECKOUT"
    assert result["workspace_binding"]["owner_context"]["status"] == "NOT_CONFIGURED"


def declaration(**changes):
    return {"id": "method", "version": "1", "private_skill": "owner-method",
            "scope": {"channel": ["assigned-channel"]}, **changes}


def public_director(source):
    target = source / "skills/pipelines/cinematic/script-director.md"
    target.parent.mkdir(parents=True)
    shutil.copyfile(REPO / "skills/pipelines/cinematic/script-director.md", target)


def test_private_knowledge_consumes_canonical_bytes_and_detects_change(bound, tmp_path, monkeypatch):
    _, source, skill, _ = bound
    monkeypatch.setattr(sc, "ROOT", source)
    # Retain repository directors and guidance without copying private packages.
    public_director(source)
    project = make_project(tmp_path, profile={"channel": "assigned-channel", "knowledge": [declaration()]})
    context = sc.build_stage_context(project, "script")
    item = next(item for item in context["items"] if item["id"] == "knowledge:method")
    assert item["content"] == (skill / "SKILL.md").read_bytes().decode("utf-8")
    assert item["reference"] == str(skill / "SKILL.md")
    assert item["sha256"] == hashlib.sha256((skill / "SKILL.md").read_bytes()).hexdigest()
    page = sc.read_context_item(project, "script", "knowledge:method", context_hash=context["context_hash"])
    assert page["content"] == item["content"]
    (skill / "SKILL.md").write_text("# Changed canonical method\n", encoding="utf-8")
    with pytest.raises(sc.StageContextError, match="stale context"):
        sc.read_context_item(project, "script", "knowledge:method", context_hash=context["context_hash"])


@pytest.mark.parametrize("kind", ["absent", "not-selected"])
def test_missing_private_selection_fails_without_local_fallback(bound, tmp_path, monkeypatch, kind):
    _, source, skill, _ = bound
    monkeypatch.setattr(sc, "ROOT", source)
    public_director(source)
    if kind == "absent":
        (skill / "SKILL.md").unlink()
    project = make_project(tmp_path, profile={"channel": "assigned-channel", "knowledge": [
        declaration(private_skill="owner-method" if kind == "absent" else "other-method")]})
    with pytest.raises(sc.StageContextError, match="missing|not selected"):
        sc.build_stage_context(project, "script")


def test_out_of_scope_private_skill_is_unread(bound, tmp_path, monkeypatch):
    _, source, skill, _ = bound
    monkeypatch.setattr(sc, "ROOT", source)
    public_director(source)
    (skill / "SKILL.md").unlink()
    project = make_project(tmp_path, profile={"channel": "different-channel", "knowledge": [declaration()]})
    item = next(item for item in sc.build_stage_context(project, "script")["items"] if item["id"] == "knowledge:method")
    assert item["applicability"] == "inapplicable" and "not read" in item["content"]


def test_manifest_director_selects_canonical_private_source(bound, tmp_path, monkeypatch):
    _, source, skill, _ = bound
    monkeypatch.setattr(sc, "ROOT", source)
    project = make_project(tmp_path)
    original = sc._manifest
    def selected(project):
        marker, manifest = original(project)
        manifest = {**manifest, "stages": [dict(stage, skill="owner-method")
                    if stage["name"] == "script" else stage for stage in manifest["stages"]]}
        return marker, manifest
    monkeypatch.setattr(sc, "_manifest", selected)
    context = sc.build_stage_context(project, "script")
    director = next(item for item in context["items"] if item["id"] == "director")
    assert director["reference"] == str(skill / "SKILL.md")
    assert director["content"] == (skill / "SKILL.md").read_bytes().decode("utf-8")


def test_stage_mutations_enforce_run_owner_while_inspection_stays_read_only(tmp_path, monkeypatch):
    from lib.run_lock import claim_run_owner
    monkeypatch.setenv("CODEX_THREAD_ID", "assigned-writer")
    project = make_project(tmp_path)
    claim_run_owner(project, "assigned-writer")
    before = {path.name: path.read_bytes() for path in project.iterdir() if path.is_file()}
    monkeypatch.setenv("CODEX_THREAD_ID", "other-writer")
    assert sc.build_stage_context(project, "script")["stage"] == "script"
    mutations = [
        lambda: sc.enable_policy(project),
        lambda: sc.configure_profile(project, {"channel": "different"}),
        lambda: sc.append_feedback(project, {}),
        lambda: sc.record_application(project, "script", {}, [], "fixture", context_hash="unused"),
        lambda: sc.record_logic_review(project, "script", {}, {}),
    ]
    for mutation in mutations:
        with pytest.raises(sc.StageContextError, match="another session"):
            mutation()
    assert {path.name: path.read_bytes() for path in project.iterdir() if path.is_file()} == before
