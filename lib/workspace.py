"""Optional, local workspace binding. No ancestor search or checkout switching.

An ordinary clone needs no binding. A bound worktree discovers the one marker
beside its canonical checkout, using Git's common directory as the trust anchor.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKER = Path(".codex") / "openmontage-workspace.json"


class WorkspaceError(ValueError):
    """The selected workspace or run has an ambiguous or invalid identity."""


def is_redirect_path(path: Path | str) -> bool:
    """Reject links/name-surrogate reparse points, including pre-3.12 junctions.

    Cloud storage reparse points do not redirect path names and remain valid.
    Missing paths are allowed for creation; unreadable metadata fails closed.
    """
    try:
        metadata = Path(path).lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise WorkspaceError("cannot validate path redirect metadata") from exc
    if stat.S_ISLNK(metadata.st_mode):
        return True
    attributes = getattr(metadata, "st_file_attributes", None)
    if os.name == "nt" and attributes is None:
        raise WorkspaceError("cannot validate path redirect metadata")
    if attributes is not None and attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        tag = getattr(metadata, "st_reparse_tag", None)
        if type(tag) is not int or not 0 < tag <= 0xFFFFFFFF:
            raise WorkspaceError("cannot validate path redirect metadata")
        # Microsoft's IsReparseTagNameSurrogate bit covers junctions, symlinks
        # and other redirects, without treating OneDrive cloud tags as links.
        return bool(tag & 0x20000000)
    return False


def _canonical(value, label: str) -> Path:
    if not isinstance(value, (str, Path)) or not str(value):
        raise WorkspaceError(f"{label} must be an absolute canonical path")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise WorkspaceError(f"{label} must be an absolute canonical path")
    # Check every existing component, including junctions on Windows. resolve()
    # alone would silently accept a redirected tree.
    for part in (path, *path.parents):
        if is_redirect_path(part):
            raise WorkspaceError(f"{label} must not contain links")
    resolved = path.resolve()
    if os.path.normcase(str(path)) != os.path.normcase(str(resolved)):
        raise WorkspaceError(f"{label} must be canonical")
    return resolved


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL,
            timeout=10,
        ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkspaceError("cannot validate Git checkout identity") from exc


def _common_dir(root: Path) -> Path:
    pointer = _canonical(root / ".git", "Git directory pointer")
    try:
        stat = pointer.stat()
    except OSError as exc:
        raise WorkspaceError("cannot validate Git checkout identity") from exc
    return _cached_common_dir(root, (stat.st_mtime_ns, stat.st_size, stat.st_ino))


@lru_cache(maxsize=32)
def _cached_common_dir(root: Path, pointer_signature: tuple[int, int, int]) -> Path:
    top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    if top != root:
        raise WorkspaceError("repo_root must be the exact checkout root")
    return _canonical(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"), "git_common_dir")


@dataclass(frozen=True)
class Workspace:
    workspace_id: str
    workspace_root: Path
    git_common_dir: Path
    canonical_source_dir: Path
    projects_dir: Path
    legacy_projects_dirs: tuple[Path, ...]
    owner_context: Path | None
    private_skills_dir: Path | None
    private_skill_names: tuple[str, ...]
    resources_dir: Path | None
    config_path: Path


def resolve_workspace(repo_root: Path | str | None = None) -> Workspace | None:
    root = _canonical(repo_root or REPO_ROOT, "repo_root")
    explicit = os.environ.get("OPENMONTAGE_WORKSPACE_CONFIG")
    outer_marker = root / MARKER
    if explicit:
        candidate = _canonical(explicit, "workspace config")
    elif outer_marker.exists():
        # The outer workspace is also a supported entry point. This is an
        # exact marker lookup, never an ancestor walk.
        candidate = outer_marker
    else:
        try:
            common = _common_dir(root)
        except WorkspaceError:
            return None
        candidate = common.parent.parent / MARKER
    if not candidate.exists() and not explicit:
        return None
    candidate = _canonical(candidate, "workspace config")
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WorkspaceError("cannot read workspace binding") from exc
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise WorkspaceError("unsupported workspace schema_version")
    allowed = {"schema_version", "workspace_id", "workspace_root", "git_common_dir", "canonical_source_dir",
               "projects_dir", "legacy_projects_dirs", "owner_context", "private_skills_dir", "private_skill_names", "resources_dir"}
    if set(data) - allowed:
        raise WorkspaceError("unknown workspace binding fields")
    wid = data.get("workspace_id")
    if not isinstance(wid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", wid):
        raise WorkspaceError("invalid workspace_id")
    paths = {key: _canonical(data.get(key), key) for key in
             ("workspace_root", "git_common_dir", "canonical_source_dir", "projects_dir")}
    canonical = paths["canonical_source_dir"]
    common = _common_dir(canonical)
    if paths["git_common_dir"] != common or common.parent != canonical:
        raise WorkspaceError("workspace Git common directory or canonical source mismatch")
    if root != paths["workspace_root"] and _common_dir(root) != common:
        raise WorkspaceError("workspace Git common directory or canonical source mismatch")
    if paths["workspace_root"] != canonical.parent:
        raise WorkspaceError("workspace root does not own canonical checkout")
    if candidate != paths["workspace_root"] / MARKER:
        raise WorkspaceError("binding must be the workspace's exact marker")
    legacy = data.get("legacy_projects_dirs", [])
    names = data.get("private_skill_names", [])
    if not isinstance(legacy, list) or not isinstance(names, list):
        raise WorkspaceError("legacy roots and private skill names must be lists")
    legacy_paths = tuple(_canonical(p, "legacy_projects_dirs") for p in legacy)
    all_roots = (paths["projects_dir"], *legacy_paths)
    for index, path in enumerate(all_roots):
        if any(path == other or path in other.parents or other in path.parents for other in all_roots[:index]):
            raise WorkspaceError("project roots must be distinct and non-overlapping")
    if any(not isinstance(n, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", n) for n in names) or len(set(names)) != len(names):
        raise WorkspaceError("invalid private skill names")
    optional = {key: _canonical(data[key], key) if data.get(key) is not None else None
                for key in ("owner_context", "private_skills_dir", "resources_dir")}
    if names and optional["private_skills_dir"] is None:
        raise WorkspaceError("private skill names require private_skills_dir")
    return Workspace(wid, **paths, legacy_projects_dirs=legacy_paths,
                     private_skill_names=tuple(names), config_path=candidate, **optional)


def project_roots(projects_dir: Path | str | None = None) -> tuple[Path, ...]:
    explicit = Path(projects_dir) if projects_dir is not None else None
    workspace = resolve_workspace()
    override = os.environ.get("OPENMONTAGE_PROJECTS_DIR")
    if explicit is not None:
        if workspace and explicit.resolve() == workspace.projects_dir and not override:
            return (explicit, *workspace.legacy_projects_dirs)
        return (explicit,)
    if override:
        return (Path(override),)
    if workspace:
        return (workspace.projects_dir, *workspace.legacy_projects_dirs)
    return (REPO_ROOT / "projects",)


def validate_project_id(project_id: str) -> None:
    if (not isinstance(project_id, str) or not project_id or project_id.endswith((".", " "))
            or any(c in project_id for c in '/\\:\0<>"|?*') or any(ord(c) < 32 for c in project_id)
            or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", project_id)):
        raise WorkspaceError("invalid project id")


def resolve_project_dir(project_id: str, projects_dir: Path | str | None = None, create: bool = False) -> Path:
    return _resolve_in_roots(project_id, project_roots(projects_dir), create)


def _resolve_in_roots(project_id: str, roots: tuple[Path, ...], create: bool = False, *, validated_roots: bool = False) -> Path:
    validate_project_id(project_id)
    matches = []
    for root in roots:
        target = root / project_id
        if not validated_roots:
            _canonical(root.absolute(), "projects root")
        if is_redirect_path(target):
            raise WorkspaceError("project directory must not contain links")
        if target.exists():
            if not target.is_dir():
                raise WorkspaceError("project id is occupied by a non-directory")
            matches.append(target)
    if len(matches) > 1:
        raise WorkspaceError(f"project id collision across configured roots: {project_id}")
    target = matches[0] if matches else roots[0] / project_id
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def iter_project_dirs(projects_dir: Path | str | None = None):
    """Enumerate every explicit root; duplicate IDs fail before yielding any run."""
    ids = set()
    roots = project_roots(projects_dir)
    for root in roots:
        _canonical(root.absolute(), "projects root")
        if root.is_dir():
            ids.update(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))
    projects = [_resolve_in_roots(pid, roots, validated_roots=True) for pid in sorted(ids)]
    yield from projects


def owner_context_path(repo_root: Path | str | None = None) -> Path | None:
    workspace = resolve_workspace(repo_root)
    if workspace is None or workspace.owner_context is None:
        return None
    if not workspace.owner_context.is_file():
        raise WorkspaceError("configured owner context is missing")
    return workspace.owner_context


def private_skill_dir(name: str, repo_root: Path | str | None = None) -> Path | None:
    workspace = resolve_workspace(repo_root)
    if workspace is None or name not in workspace.private_skill_names:
        return None
    target = _canonical(workspace.private_skills_dir / name, "private skill")
    if not target.is_dir() or not (target / "SKILL.md").is_file():
        raise WorkspaceError(f"configured private skill is missing: {name}")
    _canonical(target / "SKILL.md", "private skill source")
    return target


def runtime_identity(repo_root: Path | str | None = None, projects_dir: Path | str | None = None) -> dict:
    """Fingerprint actual runtime source bytes, including uncommitted repairs."""
    root = Path(repo_root or REPO_ROOT).resolve()
    workspace = resolve_workspace(root)
    fingerprint = hashlib.sha256()
    files = set()
    for directory in ("lib", "backlot"):
        files.update(p for p in (root / directory).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts and p.suffix in {".py", ".html", ".js", ".css"})
    for path in sorted(files):
        fingerprint.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    try:
        release = _git(root, "rev-parse", "HEAD")
    except WorkspaceError:
        release = None
    roots = project_roots(projects_dir)
    return {"workspace_id": workspace.workspace_id if workspace else None,
            "projects_dir": str(roots[0].resolve()),
            "legacy_projects_dirs": [str(p.resolve()) for p in roots[1:]],
            "source_dir": str(root), "source_release": release,
            "source_fingerprint": "sha256:" + fingerprint.hexdigest()}
