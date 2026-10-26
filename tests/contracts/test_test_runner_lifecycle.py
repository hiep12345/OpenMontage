"""Pytest scratch data belongs to one invocation and never a held target."""

import json

import pytest

from scripts import run_tests as runner


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    for name in ("TMP", "TEMP", "TMPDIR"):
        monkeypatch.setenv(name, str(tmp_path))
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    return tmp_path


def _roots(scratch):
    return list(scratch.glob("openmontage-pytest-*"))


@pytest.mark.parametrize("args", [["--basetemp=held"], ["--basetemp", "held"], ["--baset=held"],
                                  ["-o", "addopts=--basetemp=held"]])
def test_cli_basetemp_override_is_rejected_without_side_effects(scratch, args):
    held = scratch / "held"
    held.mkdir()
    (held / "keep.txt").write_text("held")
    assert runner.main(args) == 2
    assert _roots(scratch) == []
    assert (held / "keep.txt").read_text() == "held"


@pytest.mark.parametrize("options", ["--basetemp=held", '--basetemp "held path"', "--baset=held"])
def test_env_basetemp_override_is_rejected(scratch, monkeypatch, options):
    monkeypatch.setenv("PYTEST_ADDOPTS", options)
    assert runner.main([]) == 2
    assert _roots(scratch) == []


def test_repo_local_temp_parent_is_rejected(scratch, monkeypatch):
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(runner.REPO_ROOT / "scratch"))
    assert runner.main([]) == 2
    assert _roots(scratch) == []


def test_success_removes_only_unique_owned_scratch_and_forces_cache(scratch, monkeypatch):
    held = scratch / "held"
    held.mkdir()
    (held / "keep.txt").write_text("held")
    calls = []

    class Process:
        def __init__(self, command, env):
            root = _roots(scratch)[0]
            assert root.is_absolute()
            assert runner.REPO_ROOT not in root.parents
            assert env["PYTHONDONTWRITEBYTECODE"] == "1"
            assert command[-3:] == [f"--basetemp={root / 'basetemp'}", "-o", f"cache_dir={root / 'cache'}"]
            receipt = json.loads((root / "invocation.json").read_text(encoding="utf-8"))
            assert receipt["checkout"] == str(runner.REPO_ROOT)
            assert receipt["command"] == command
            calls.append(root)

        def wait(self):
            return 0

    monkeypatch.setattr(runner.subprocess, "Popen", Process)
    for _ in range(2):
        assert runner.main(["-o", f"cache_dir={held}"]) == 0
        assert _roots(scratch) == []
    assert len(set(calls)) == 2
    assert (held / "keep.txt").read_text() == "held"


@pytest.mark.parametrize("code", [1, 2, 5])
def test_failure_preserves_exit_status_and_discoverable_diagnostics(scratch, monkeypatch, code, capsys):
    class Process:
        def __init__(self, command, env):
            (_roots(scratch)[0] / "diagnostic.txt").write_text("failure evidence")

        def wait(self):
            return code

    monkeypatch.setattr(runner.subprocess, "Popen", Process)
    assert runner.main(["tests/"]) == code
    root, = _roots(scratch)
    assert (root / "diagnostic.txt").read_text() == "failure evidence"
    assert str(root) in capsys.readouterr().err


def test_interruption_stops_child_and_retains_diagnostics(scratch, monkeypatch):
    actions = []

    class Process:
        def __init__(self, command, env):
            pass

        def wait(self, timeout=None):
            if timeout is None:
                raise KeyboardInterrupt
            actions.append("wait")
            return -15

        def poll(self):
            return None

        def terminate(self):
            actions.append("terminate")

    monkeypatch.setattr(runner.subprocess, "Popen", Process)
    assert runner.main([]) == 130
    assert actions == ["terminate", "wait"]
    root, = _roots(scratch)
    assert (root / "invocation.json").is_file()


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_real_pytest_uses_owned_basetemp_and_cache(scratch, outcome):
    test_file = scratch / "test_nested.py"
    test_file.write_text(
        "def test_nested(tmp_path, pytestconfig):\n"
        "    from pathlib import Path\n"
        "    base = pytestconfig._tmp_path_factory.getbasetemp()\n"
        "    assert base.name == 'basetemp'\n"
        "    assert Path(pytestconfig.cache._cachedir).parent == base.parent\n"
        f"    assert {outcome == 'success'}\n",
        encoding="utf-8",
    )
    assert runner.main([str(test_file), "-q"]) == (0 if outcome == "success" else 1)
    roots = _roots(scratch)
    if outcome == "success":
        assert roots == []
    else:
        root, = roots
        assert (root / "basetemp").is_dir()
        assert (root / "cache").is_dir()


def test_make_targets_use_owned_test_runner():
    makefile = (runner.REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "scripts/run_tests.py tests/ -v" in makefile
    assert "scripts/run_tests.py tests/contracts/ -v" in makefile
