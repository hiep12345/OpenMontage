"""Independent processes must not contend for the same run's checkpoint files."""

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from lib.checkpoint import init_project, read_checkpoint, write_checkpoint
from lib.run_lock import OWNER_FILE, RunWriterError, claim_run_owner, run_write_lock


def test_cli_run_selectors_do_not_depend_on_cwd(tmp_path, monkeypatch):
    import lib.paths as paths
    monkeypatch.setattr(paths, "resolve_project_dir", lambda name: tmp_path / name)
    monkeypatch.chdir(tmp_path)
    assert paths.resolve_project_input("projects/example") == tmp_path / "example"
    assert paths.resolve_project_input("example") == tmp_path / "example"
    assert paths.resolve_project_input(tmp_path / "absolute") == tmp_path / "absolute"
    with pytest.raises(ValueError):
        paths.resolve_project_input("../projects/example")


def test_parallel_process_excludes_same_run_but_not_other_run(tmp_path):
    project = tmp_path / "one"
    code = """import sys
from pathlib import Path
from lib.run_lock import run_write_lock
with run_write_lock(Path(sys.argv[1])):
    print('ready', flush=True)
    sys.stdin.read(1)
"""
    child = subprocess.Popen(
        [sys.executable, "-B", "-c", code, str(project)],
        cwd=Path(__file__).resolve().parents[2],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    output = queue.Queue()
    threading.Thread(target=lambda: output.put(child.stdout.readline()), daemon=True).start()
    try:
        assert output.get(timeout=10).strip() == "ready"
        with pytest.raises(RunWriterError, match="active writer"):
            with run_write_lock(project):
                pytest.fail("A concurrent writer acquired the same run")
        with run_write_lock(tmp_path / "two"):
            pass
    finally:
        try:
            _, err = child.communicate("x", timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            raise
    assert child.returncode == 0, err
    with run_write_lock(project):
        with run_write_lock(project):
            pass


def test_native_new_run_ownership_is_explicit_and_reassigns_with_cas(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_THREAD_ID", "session-a")
    project = init_project("one", title="one", pipeline_type="unknown", pipeline_dir=tmp_path,
                           stage_context_required=False)
    assert json.loads((project / OWNER_FILE).read_text())["owner"] == "session-a"
    monkeypatch.setenv("CODEX_THREAD_ID", "session-b")
    with pytest.raises(RunWriterError, match="another session"):
        write_checkpoint(tmp_path, "one", "research", "in_progress", {})
    with pytest.raises(RunWriterError):
        claim_run_owner(project, "session-b", expected_owner="wrong")
    claim_run_owner(project, "session-b", expected_owner="session-a")
    write_checkpoint(tmp_path, "one", "research", "in_progress", {})
    assert read_checkpoint(tmp_path, "one", "research")["status"] == "in_progress"


def test_legacy_run_is_not_silently_claimed_and_failure_creates_no_run(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    project = init_project("old", title="old", pipeline_type="unknown", pipeline_dir=tmp_path,
                           stage_context_required=False)
    assert not (project / OWNER_FILE).exists()
    monkeypatch.setenv("CODEX_THREAD_ID", "new-session")
    write_checkpoint(tmp_path, "old", "research", "in_progress", {})
    assert not (project / OWNER_FILE).exists()
    with pytest.raises(ValueError):
        init_project("invalid", title="bad", pipeline_type="unknown", pipeline_dir=tmp_path,
                     stage_context_profile={"channel": "MT"}, stage_context_required=False)
    assert not (tmp_path / "invalid").exists()


def test_bad_ownership_fails_closed_and_lock_is_released(tmp_path):
    project = tmp_path / "one"
    project.mkdir()
    (project / OWNER_FILE).write_text("not json", encoding="utf-8")
    with pytest.raises(RunWriterError, match="Unreadable"):
        with run_write_lock(project):
            pass
    (project / OWNER_FILE).unlink()
    with run_write_lock(project):
        pass


def test_failed_checkpoint_serialization_keeps_original_and_cleans_temp(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    project = init_project("one", title="one", pipeline_type="unknown", pipeline_dir=tmp_path,
                           stage_context_required=False)
    target = write_checkpoint(tmp_path, "one", "research", "in_progress", {})
    before = target.read_bytes()
    with pytest.raises(TypeError):
        write_checkpoint(tmp_path, "one", "research", "in_progress", {}, metadata={"bad": object()})
    assert target.read_bytes() == before
    assert not list(project.glob("*.tmp"))
