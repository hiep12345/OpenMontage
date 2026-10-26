"""Cooperative per-run writer ownership and cross-process checkpoint exclusion.

Ownership is application state, not a substitute for the task's authorization.
Legacy runs without an owner retain their existing behavior. New native sessions
can bind ownership; reassignment is an explicit compare-and-swap operation.
"""

from __future__ import annotations

import ctypes
import hashlib
import inspect
import json
import os
import tempfile
import threading
import time
import math
from contextlib import contextmanager
from functools import wraps
from pathlib import Path


class RunWriterError(RuntimeError):
    pass


OWNER_FILE = ".writer-owner.json"
_held = threading.local()


def session_owner() -> str | None:
    return os.environ.get("CODEX_THREAD_ID") or None


@contextmanager
def run_write_lock(project_dir: Path, *, owner: str | None = None, timeout: float = 0):
    """Fail promptly if another process/thread owns this run's write operation."""
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0 or timeout > 60:
        raise ValueError("Writer lock timeout must be between 0 and 60 seconds")
    project = Path(project_dir).resolve()
    key = hashlib.sha256(os.path.normcase(str(project)).encode()).hexdigest()
    held = getattr(_held, "runs", None)
    if held is None:
        held = _held.runs = set()
    if key in held:
        _check_owner(project, owner)
        yield
        return
    handle = None
    kernel = None
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
        kernel.ReleaseMutex.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.CreateMutexW(None, False, "Local\\OpenMontageRun_" + key)
        if not handle:
            raise OSError(ctypes.get_last_error(), "Cannot create run writer mutex")
        result = kernel.WaitForSingleObject(handle, int(timeout * 1000))
        if result not in (0, 0x80):  # acquired, or acquired after an abandoned owner
            kernel.CloseHandle(handle)
            raise RunWriterError(f"Run has another active writer: {project}")
    else:
        import fcntl
        # Stable inode: do not unlink while another process may have opened it.
        lock_dir = Path(tempfile.gettempdir()) / "openmontage-run-locks"
        lock_dir.mkdir(exist_ok=True)
        handle = (lock_dir / (key + ".lock")).open("a+b")
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    handle.close()
                    raise RunWriterError(f"Run has another active writer: {project}") from exc
                time.sleep(min(0.01, max(0, deadline - time.monotonic())))
    held.add(key)
    try:
        _check_owner(project, owner)
        yield
    finally:
        held.remove(key)
        if kernel is not None:
            kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


def _check_owner(project: Path, owner: str | None) -> None:
    path = project / OWNER_FILE
    if not path.exists():
        return
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RunWriterError(f"Unreadable writer ownership: {path}") from exc
    assigned = record.get("owner")
    if not isinstance(assigned, str) or not assigned or record.get("version") != 1:
        raise RunWriterError(f"Invalid writer ownership: {path}")
    if assigned != (owner or session_owner()):
        raise RunWriterError(f"Run belongs to another session; explicit reassignment required: {project}")


def check_run_owner(project_dir: Path, *, owner: str | None = None) -> None:
    """Check ownership without serializing a safely transactional append."""
    _check_owner(Path(project_dir).resolve(), owner)


def claim_run_owner(project_dir: Path, owner: str, *, expected_owner: str | None = None) -> None:
    """Bind/reassign a run with CAS; callers must already own the task authority."""
    if not isinstance(owner, str) or not owner.strip():
        raise ValueError("An explicit writer owner is required")
    project = Path(project_dir).resolve(strict=True)
    # Use the current owner solely to acquire the serialization lock; verify CAS.
    with run_write_lock(project, owner=expected_owner or owner):
        path = project / OWNER_FILE
        current = json.loads(path.read_text(encoding="utf-8"))["owner"] if path.exists() else None
        if current != expected_owner:
            raise RunWriterError("Writer owner changed; refusing reassignment")
        fd, name = tempfile.mkstemp(prefix=".writer-owner-", suffix=".tmp", dir=project)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"version": 1, "owner": owner}, stream)
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)


def guarded_checkpoint_writer(function):
    """Resolve before locking; preserve the original public call signature."""
    signature = inspect.signature(function)

    @wraps(function)
    def guarded(*args, **kwargs):
        from lib.paths import resolve_project_dir
        bound = signature.bind(*args, **kwargs)
        project_id = bound.arguments["project_id"]
        base = bound.arguments.get("pipeline_dir") or function.__globals__["PROJECTS_DIR"]
        project = resolve_project_dir(project_id, projects_dir=base)
        bound.arguments["pipeline_dir"] = project.parent
        with run_write_lock(project):
            new = not (project / "project.json").exists()
            result = function(*bound.args, **bound.kwargs)
            if function.__name__ == "init_project" and new and session_owner():
                claim_run_owner(project, session_owner())
            return result

    return guarded
