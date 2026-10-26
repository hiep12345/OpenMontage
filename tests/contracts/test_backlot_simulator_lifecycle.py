"""The demo owns a new synthetic run, never an existing production directory."""

import json

import pytest

from scripts import backlot_simulate_run as simulator


@pytest.fixture
def projects(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    monkeypatch.setattr(simulator, "PROJECTS_DIR", root)
    monkeypatch.setattr(simulator.time, "sleep", lambda *_: None)
    return root


@pytest.mark.parametrize("project_id", ["", ".", "..", "../held", "a/b", "a\\b", "/tmp/run",
                                        "C:\\held", "CON", "nul", "COM1", "LPT9", "run.", "run "])
def test_invalid_id_is_rejected_before_creating_projects(projects, project_id):
    with pytest.raises(SystemExit) as error:
        simulator.main(["--project", project_id, "--cleanup"])
    assert error.value.code == 2
    assert not projects.exists()


@pytest.mark.parametrize("kind", ["directory", "file"])
def test_existing_target_is_preserved_even_with_cleanup(projects, kind):
    projects.mkdir()
    target = projects / "held-run"
    if kind == "directory":
        target.mkdir()
        sentinel = target / "keep.txt"
    else:
        sentinel = target
    sentinel.write_bytes(b"held production bytes")

    with pytest.raises(SystemExit) as error:
        simulator.main(["--project", "held-run", "--cleanup"])

    assert error.value.code == 2
    assert sentinel.read_bytes() == b"held production bytes"


@pytest.mark.parametrize("cleanup", [False, True])
@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_partial_initialization_cleanup_covers_errors_and_interruptions(projects, monkeypatch, cleanup, failure):
    def partial_init(pid, **kwargs):
        (projects / pid / "partial.txt").write_text("partially initialized")
        raise failure("interrupted init")

    monkeypatch.setattr(simulator, "init_project", partial_init)
    argv = ["--project", "partial-run"] + (["--cleanup"] if cleanup else [])
    with pytest.raises(failure, match="interrupted init"):
        simulator.main(argv)
    assert (projects / "partial-run").exists() is (not cleanup)


def test_checkpoint_failure_cleans_owned_root_and_preserves_other_runs(projects, monkeypatch):
    held = projects / "held"
    held.mkdir(parents=True)
    (held / "keep.txt").write_text("held")

    def fail_checkpoint(*args, **kwargs):
        assert (projects / "new-run" / "project.json").is_file()
        raise RuntimeError("checkpoint failure")

    monkeypatch.setattr(simulator, "write_checkpoint", fail_checkpoint)
    with pytest.raises(RuntimeError, match="checkpoint failure"):
        simulator.main(["--project", "new-run", "--cleanup"])
    assert not (projects / "new-run").exists()
    assert (held / "keep.txt").read_text() == "held"


@pytest.mark.parametrize("cleanup", [False, True])
def test_synthetic_journey_preserves_contract_and_optional_cleanup(projects, cleanup):
    argv = ["--project", "new-run", "--fast"] + (["--cleanup"] if cleanup else [])
    assert simulator.main(argv) == 0
    target = projects / "new-run"
    if cleanup:
        assert not target.exists()
        return
    marker = json.loads((target / "project.json").read_text(encoding="utf-8"))
    assert marker["pipeline_type"] == "cinematic"
    for stage in ("proposal", "script", "scene_plan", "assets"):
        checkpoint = json.loads((target / f"checkpoint_{stage}.json").read_text(encoding="utf-8"))
        assert checkpoint["status"] == "completed"
        assert checkpoint["human_approved"] is True
    manifest = json.loads((target / "artifacts" / "asset_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["assets"]) == 4
    assert all(asset["model"] == "flux-sim" for asset in manifest["assets"])


def test_cleanup_refuses_replaced_root(projects, monkeypatch):
    def replace_owned_root(pid, pdir, wait):
        pdir.rename(projects / "original-owned-root")
        pdir.mkdir()
        (pdir / "keep.txt").write_text("replacement")
        return 0

    monkeypatch.setattr(simulator, "simulate", replace_owned_root)
    with pytest.raises(RuntimeError, match="ownership changed"):
        simulator.main(["--project", "new-run", "--cleanup"])
    assert (projects / "new-run" / "keep.txt").read_text() == "replacement"
