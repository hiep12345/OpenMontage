"""Canonical repository paths — single source of truth.

The projects root is the most load-bearing path in the system: checkpoints
are written under it, tool events are attributed against it, and the Backlot
board watches it. Define it once.
"""

from __future__ import annotations

from pathlib import Path

from lib.workspace import project_roots, resolve_project_dir, iter_project_dirs
from lib.workspace import _canonical

REPO_ROOT = Path(__file__).resolve().parent.parent

# Overridable for staging/screenshots/tests. Everything — checkpoint writes,
# event attribution, the Backlot board — follows the same root.
PROJECTS_DIR = project_roots()[0]


def resolve_project_input(value: str | Path) -> Path:
    """Resolve CLI run selectors without letting cwd choose another data root.

    Absolute paths retain explicit selection. Relative selectors are a run ID or
    projects/<id>; other paths must be made explicit by the caller.
    """
    path = Path(value)
    if path.is_absolute():
        return _canonical(path, "explicit project")
    if len(path.parts) == 1:
        return resolve_project_dir(path.name)
    if len(path.parts) == 2 and path.parts[0] == "projects":
        return resolve_project_dir(path.name)
    raise ValueError("Use an absolute run path, a run ID, or projects/<run-id>")
