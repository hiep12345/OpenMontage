"""Redirect boundaries use Python 3.10 metadata, without Path.is_junction."""
import os
from pathlib import Path
import stat
import subprocess
from types import SimpleNamespace

import pytest

from lib import workspace as ws


def patch_metadata(monkeypatch, path, **fields):
    original = Path.lstat
    metadata = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400, **fields)
    monkeypatch.setattr(Path, "lstat", lambda self: metadata if self == path else original(self))
    monkeypatch.delattr(Path, "is_junction", raising=False)


@pytest.mark.parametrize("tag, redirected", [
    (0xA0000003, True),  # mount point/junction
    (0xA000000C, True),  # symlink
    (0x20000042, True),  # another name-surrogate tag
    (0x9000001A, False),  # OneDrive cloud
    (0x9000101A, False),  # OneDrive cloud variant
    (0x80000023, False),  # other non-name-surrogate reparse point
])
def test_redirect_tags_without_path_is_junction(tmp_path, monkeypatch, tag, redirected):
    path = tmp_path / "candidate"
    path.mkdir()
    patch_metadata(monkeypatch, path, st_reparse_tag=tag)
    assert ws.is_redirect_path(path) is redirected
    if redirected:
        with pytest.raises(ws.WorkspaceError, match="links"):
            ws._canonical(path / "child", "fixture")
        with pytest.raises(ws.WorkspaceError, match="links"):
            ws._resolve_in_roots("candidate", (tmp_path,))
    else:
        assert ws._canonical(path, "fixture") == path
        assert ws._resolve_in_roots("candidate", (tmp_path,)) == path


@pytest.mark.parametrize("fields", [{}, {"st_reparse_tag": 0}, {"st_reparse_tag": None}])
def test_reparse_metadata_unavailable_fails_closed(tmp_path, monkeypatch, fields):
    patch_metadata(monkeypatch, tmp_path, **fields)
    with pytest.raises(ws.WorkspaceError, match="metadata"):
        ws.is_redirect_path(tmp_path)


def test_unreadable_redirect_metadata_fails_closed(tmp_path, monkeypatch):
    def denied(self):
        raise PermissionError("fixture metadata access denied")
    monkeypatch.setattr(Path, "lstat", denied)
    with pytest.raises(ws.WorkspaceError, match="metadata"):
        ws.is_redirect_path(tmp_path)


def test_missing_path_is_not_a_redirect(tmp_path):
    assert not ws.is_redirect_path(tmp_path / "missing")


@pytest.mark.skipif(os.name != "nt", reason="native Windows junction check")
def test_real_windows_junction_rejected_without_path_is_junction(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    target = root / "target"
    primary = root / "projects"
    target.mkdir()
    primary.mkdir()
    marker = target / "retained.txt"
    marker.write_text("target data", encoding="utf-8")
    link = primary / "linked"
    # Both mklink operands are exact children of this invocation's temp root.
    assert target.resolve().is_relative_to(root)
    assert link.parent.resolve().is_relative_to(root)
    assert not link.exists()
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                            capture_output=True, text=True)
    if result.returncode:
        pytest.skip(f"junction creation unavailable: {result.stderr.strip()}")
    try:
        monkeypatch.delattr(Path, "is_junction", raising=False)
        assert ws.is_redirect_path(link)
        with pytest.raises(ws.WorkspaceError, match="links"):
            ws._canonical(link / "retained.txt", "fixture")
        with pytest.raises(ws.WorkspaceError, match="links"):
            ws._resolve_in_roots("linked", (primary,))
        with pytest.raises(ws.WorkspaceError, match="links"):
            ws._resolve_in_roots("new", (link,))
    finally:
        # Remove only the exact junction, never recursively traverse its target.
        assert link.parent.resolve() == primary
        link.rmdir()
        assert marker.read_text(encoding="utf-8") == "target data"
