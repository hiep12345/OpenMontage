import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backlot import __main__ as cli
from backlot import server
from lib.workspace import runtime_identity


def response(payload):
    result = Mock()
    result.status = 200
    result.read.return_value = json.dumps(payload).encode()
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    return result


def test_health_has_frozen_source_and_root_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROJECTS_DIR", tmp_path)
    app = server.create_app()
    monkeypatch.setattr(server, "runtime_identity", lambda **kwargs: {"changed": True})
    with TestClient(app) as client:
        health = client.get("/api/health").json()
    assert health["identity"] == runtime_identity(projects_dir=tmp_path)
    assert health["identity"]["source_fingerprint"].startswith("sha256:")


def test_launcher_accepts_only_exact_runtime(monkeypatch):
    identity = runtime_identity()
    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda *a, **k: response({"ok": True, "app": "backlot", "identity": identity}))
    assert cli._server_alive(1234)
    for key in ("workspace_id", "projects_dir", "legacy_projects_dirs", "source_dir", "source_release", "source_fingerprint"):
        changed = {**identity, key: "different"}
        monkeypatch.setattr(cli.urllib.request, "urlopen", lambda *a, **k: response({"ok": True, "app": "backlot", "identity": changed}))
        with pytest.raises(cli.ServerIdentityMismatch):
            cli._server_alive(1234)


def test_wrong_http200_never_spawns_or_opens_browser(monkeypatch):
    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda *a, **k: response({"ok": True, "app": "backlot"}))
    spawn = Mock()
    browser = Mock()
    monkeypatch.setattr(cli, "_spawn_server", spawn)
    monkeypatch.setattr(cli.webbrowser, "open", browser)
    assert cli.cmd_open("film") == 1
    spawn.assert_not_called()
    browser.assert_not_called()


def test_watcher_rejects_shared_prefix_sibling(tmp_path, monkeypatch):
    import os
    root = tmp_path / "projects"
    monkeypatch.setattr(server, "PROJECTS_DIR", root)
    monkeypatch.setattr(server, "_PROJECTS_ROOT_STR", os.path.normcase(str(root)))
    assert server._project_of_change(str(root / "film" / "project.json")) == "film"
    assert server._project_of_change(str(tmp_path / "projects-other" / "film" / "project.json")) is None
