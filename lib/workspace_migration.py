"""Conservative offline packet migration; planning never proves owner closure.

Closure evidence is a local JSON attestation with exact ``source``, ``status``
(``CLOSED`` or ``PAUSED``), and ``migration_authorized: true``. It must live
outside the migrating trees. Root-bound receipts, live SQLite sidecars, links,
hardlinks and special files need a separately reviewed migration implementation.

Source permissions are frozen after copying, not its original receipts rewritten.
Locks protect cooperating OpenMontage writers; OS read-only bits are not an ACL
or a defense against an administrator/noncooperating writer. Every later stage
rechecks bytes and metadata and refuses changed owner results.

Atomic directory moves and JSON record updates are distinct operations. Hard
process termination can leave an intermediate record; automatic crash resume is
unsupported. Preserve the recorded stage/backup/original for explicit recovery.
Destination copies preserve file bytes, mode and modification time; security
descriptors/alternate streams are outside that copy contract. Finalization keeps
the actual original directory by rename, including its original security ACL.
"""
from __future__ import annotations

import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
import uuid

from lib.run_lock import run_write_lock
from lib.workspace import WorkspaceError, _canonical, is_redirect_path


class MigrationError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path | str) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _path(value, label):
    try:
        return _canonical(value, label)
    except (WorkspaceError, OSError) as exc:
        raise MigrationError(str(exc)) from exc


def _related(left, right):
    return left == right or left in right.parents or right in left.parents


def _paths(source, destination, evidence, rollback):
    paths = tuple(_path(value, label) for value, label in zip(
        (source, destination, evidence, rollback), ("source", "destination", "closure evidence", "rollback artifact")))
    for index, path in enumerate(paths):
        if any(_related(path, other) for other in paths[:index]):
            raise MigrationError("source, destination, evidence and rollback artifact must not overlap")
    if any(path == Path(path.anchor) for path in paths):
        raise MigrationError("filesystem roots are not migration packets")
    return paths


def _linked(path):
    try:
        return is_redirect_path(path)
    except (WorkspaceError, OSError) as exc:
        raise MigrationError(str(exc)) from exc


def _identity(path):
    info = path.stat()
    return [info.st_dev, info.st_ino]


def _same_volume(left, right):
    return left.stat().st_dev == right.stat().st_dev


def _inventory(root):
    _path(root, "packet root")
    if not root.is_dir():
        raise MigrationError("packet root must be an existing directory")
    entries = []
    def visit(path):
        if _linked(path):
            raise MigrationError(f"linked path is unsupported: {path.name}")
        before = path.lstat()
        item = {"path": path.relative_to(root).as_posix() if path != root else "",
                "mode": stat.S_IMODE(before.st_mode), "mtime_ns": before.st_mtime_ns}
        if stat.S_ISDIR(before.st_mode):
            item["kind"] = "directory"
            entries.append(item)
            for child in sorted(path.iterdir()):
                visit(child)
        elif stat.S_ISREG(before.st_mode):
            if before.st_nlink != 1:
                raise MigrationError(f"hardlinked file is unsupported: {item['path']}")
            item.update(kind="file", size=before.st_size, sha256=file_sha256(path))
            after = path.lstat()
            if (before.st_mtime_ns, before.st_size, before.st_ino) != (after.st_mtime_ns, after.st_size, after.st_ino):
                raise MigrationError("source changed while inventorying")
            entries.append(item)
        else:
            raise MigrationError(f"special file is unsupported: {item['path']}")
    visit(root)
    return entries


def _assert_inventory(root, expected):
    if _inventory(root) != expected:
        raise MigrationError(f"bytes or metadata changed: {root.name}")


def _closure(path, source):
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise MigrationError("closure evidence must be readable JSON") from exc
    if (not isinstance(data, dict) or data.get("status") not in {"CLOSED", "PAUSED"}
            or data.get("migration_authorized") is not True or data.get("source") != str(source)):
        raise MigrationError("closure evidence must explicitly authorize the exact CLOSED/PAUSED source")
    return {"path": str(path), "sha256": _digest(raw), "status": data["status"]}


def _blockers(source, inventory):
    blockers = []
    variants = {str(source), source.as_posix(), str(source).replace("\\", "\\\\")}
    needles = [value.encode().lower() for value in variants] + [value.encode("utf-16le").lower() for value in variants]
    markers = [b'"artifactroot"', b'"artifact_root"', b'"batchroot"', b'"batch_root"']
    for item in inventory:
        rel = item["path"]
        if rel == ".git" or rel.startswith(".git/"):
            blockers.append({"path": rel, "reason": "GIT_CHECKOUT_IS_NOT_A_DATA_PACKET"})
        if item["kind"] != "file":
            continue
        path = source / rel
        if path.name.endswith(("-wal", "-shm", "-journal")):
            blockers.append({"path": rel, "reason": "SQLITE_SIDECAR_REQUIRES_REVIEW"})
        # Scan all bytes in bounded chunks, including binary/UTF-16 journals.
        # False positives are deliberately reviewable blockers, never bypasses.
        overlap = max(map(len, [*needles, *markers]))
        tail = b""
        reasons = set()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                block = (tail + chunk).lower()
                if any(needle in block for needle in needles):
                    reasons.add("ABSOLUTE_SELF_REFERENCE_REQUIRES_REVIEW")
                if any(marker in block for marker in markers):
                    reasons.add("ROOT_BOUND_JOURNAL_REQUIRES_REVIEW")
                tail = block[-overlap:]
        blockers.extend({"path": rel, "reason": reason} for reason in sorted(reasons))
    return blockers


def build_plan(source, destination, owner_closure_evidence, rollback_artifact) -> dict:
    """Read-only plan. No exemption flag exists for unsupported root bindings."""
    source, destination, evidence, rollback = _paths(source, destination, owner_closure_evidence, rollback_artifact)
    if destination.exists() or rollback.exists():
        raise MigrationError("destination and predeclared rollback artifact must both be absent")
    if not destination.parent.is_dir() or not rollback.parent.is_dir():
        raise MigrationError("destination and rollback parents must already exist")
    inventory = _inventory(source)
    closure = _closure(evidence, source)
    blockers = _blockers(source, inventory)
    if not _same_volume(source, rollback.parent):
        blockers.append({"path": "", "reason": "CROSS_VOLUME_SOURCE_RETIREMENT_UNSUPPORTED"})
    return {"schema_version": 1, "migration_id": uuid.uuid4().hex, "created_at": _now(),
            "source": str(source), "destination": str(destination), "rollback_artifact": str(rollback),
            "retired_source": str(rollback / "original-source"),
            "owner_closure_evidence": closure, "inventory": inventory,
            "inventory_sha256": _digest(_bytes(inventory)), "blockers": blockers,
            "status": "BLOCKED" if blockers else "PLANNED"}


def _outside_record(path, plan):
    path = _path(path, "record path")
    if any(_related(path, Path(plan[key])) for key in ("source", "destination", "rollback_artifact")):
        raise MigrationError("migration records must remain outside source/destination/rollback trees")
    if path == Path(plan["owner_closure_evidence"]["path"]):
        raise MigrationError("migration record must not replace closure evidence")
    if not path.parent.is_dir():
        raise MigrationError("record parent must already exist")
    return path


def _write_new(path, value):
    raw = _bytes(value)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return _digest(raw)


def write_plan(plan: dict, path: Path | str) -> str:
    """Save exclusively and return the exact file SHA required by apply."""
    return _write_new(_outside_record(path, plan), plan)


def _read_exact(path, expected_sha):
    path = _path(path, "record")
    raw = path.read_bytes()
    if not isinstance(expected_sha, str) or _digest(raw) != expected_sha:
        raise MigrationError("record SHA compare-and-swap failed")
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise MigrationError("invalid migration record") from exc
    if not isinstance(value, dict):
        raise MigrationError("invalid migration record")
    return value


def _load_plan(path, expected_sha):
    plan = _read_exact(path, expected_sha)
    try:
        if plan["schema_version"] != 1 or len(plan["migration_id"]) != 32 or uuid.UUID(plan["migration_id"]).hex != plan["migration_id"]:
            raise MigrationError("unsupported migration plan")
        _paths(plan["source"], plan["destination"], plan["owner_closure_evidence"]["path"], plan["rollback_artifact"])
        if plan["retired_source"] != str(Path(plan["rollback_artifact"]) / "original-source"):
            raise MigrationError("retired source must be the predeclared original-source rollback path")
        if _digest(_bytes(plan["inventory"])) != plan["inventory_sha256"]:
            raise MigrationError("inventory digest mismatch")
        for item in plan["inventory"]:
            rel = Path(item["path"])
            if rel.is_absolute() or ".." in rel.parts or "\\" in item["path"]:
                raise MigrationError("unsafe inventory path")
        if plan["status"] != "PLANNED" or plan["blockers"]:
            raise MigrationError("migration is BLOCKED; a separately reviewed handler is required")
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, MigrationError):
            raise
        raise MigrationError("invalid migration plan") from exc
    return plan


def _check_closure(plan):
    evidence = plan["owner_closure_evidence"]
    if _closure(Path(evidence["path"]), Path(plan["source"])) != evidence:
        raise MigrationError("owner closure evidence changed")


def _copy_tree(source, destination, inventory):
    destination.mkdir()  # exclusive; neither copytree nor rename may merge
    for item in inventory:
        if not item["path"]:
            continue
        target = destination / item["path"]
        if item["kind"] == "directory":
            target.mkdir()
        else:
            shutil.copy2(source / item["path"], target, follow_symlinks=False)
    for item in reversed(inventory):
        if item["kind"] == "directory":
            shutil.copystat(source / item["path"], destination / item["path"], follow_symlinks=False)


def _publish_no_replace(source, target):
    if sys.platform == "win32":
        os.rename(source, target)  # Windows rename refuses an occupied target.
    elif sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, "renameat2", None)
        if rename is None:
            raise MigrationError("atomic no-replace publication is unsupported on this platform")
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
    else:
        raise MigrationError("atomic no-replace publication is unsupported on this platform")


def _move_frozen_source(source, target, inventory, identity):
    # Linux checks write permission on a directory when moving its '..' entry
    # across parents. Keep the packet frozen except for its root during this
    # locked move; descendants never need additional permission.
    if not sys.platform.startswith("linux") or source.parent == target.parent:
        _publish_no_replace(source, target)
        return
    _assert_inventory(source, inventory)
    if _identity(source) != identity:
        raise MigrationError("source directory identity changed before move")
    frozen_mode = next(item["mode"] for item in inventory if not item["path"])
    move_mode = frozen_mode | stat.S_IWUSR
    moving_inventory = [dict(item, mode=move_mode) if not item["path"] else dict(item)
                        for item in inventory]

    def refreeze():
        # A caught interruption may follow the OS rename or chmod itself.
        # Locate only the original inode, never chmod a replacement owner tree.
        for candidate in (source, target):
            if not candidate.exists() or _linked(candidate):
                continue
            info = candidate.lstat()
            if [info.st_dev, info.st_ino] != identity:
                continue
            if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) not in {frozen_mode, move_mode}:
                raise MigrationError("source mode changed during move")
            if stat.S_IMODE(info.st_mode) != frozen_mode:
                candidate.chmod(frozen_mode)
            _assert_inventory(candidate, inventory)
            return
        raise MigrationError("source directory identity changed during move")

    try:
        source.chmod(move_mode)
        _assert_inventory(source, moving_inventory)
        if _identity(source) != identity:
            raise MigrationError("source directory identity changed before move")
        _publish_no_replace(source, target)
    except BaseException as exc:
        try:
            refreeze()
        except BaseException as recovery_exc:
            if hasattr(exc, "add_note"):
                exc.add_note(f"Source refreeze requires review: {type(recovery_exc).__name__}: {recovery_exc}")
        raise
    else:
        refreeze()


def _update_receipt(path, receipt, expected_sha):
    _read_exact(path, expected_sha)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        digest = _write_new(temporary, receipt)
        _read_exact(path, expected_sha)
        os.replace(temporary, path)
        return digest
    finally:
        temporary.unlink(missing_ok=True)


def _sqlite_snapshots(source, rollback, inventory):
    snapshots = []
    for item in inventory:
        if item["kind"] != "file":
            continue
        original = source / item["path"]
        with original.open("rb") as stream:
            if stream.read(16) != b"SQLite format 3\x00":
                continue
        target = rollback / "sqlite-snapshots" / (item["path"] + ".sqlite")
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(original.as_uri() + "?mode=ro", uri=True, timeout=1) as database:
            if database.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise MigrationError("SQLite source integrity check failed")
            with sqlite3.connect(target) as snapshot:
                database.backup(snapshot)
                if snapshot.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise MigrationError("SQLite snapshot integrity check failed")
        snapshots.append({"source": item["path"], "path": target.relative_to(rollback).as_posix(), "sha256": file_sha256(target)})
    return snapshots


def _permissions(root, inventory, *, freeze=False):
    # Work from leaves upward when freezing; restore parents first otherwise.
    for item in reversed(inventory) if freeze else inventory:
        mode = item["mode"] & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH) if freeze else item["mode"]
        (root / item["path"]).chmod(mode)


def _freeze_permissions(root, inventory, changes, record):
    for item in reversed(inventory):
        path = _path(root / item["path"], "source permission entry")
        mode = item["mode"] & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        if mode == item["mode"]:
            continue
        # Persist identity and both allowed modes before chmod. A caught
        # interruption may happen after the OS changed the mode but before
        # Python returned, so recovery accepts either mode for this entry.
        info = path.lstat()
        changes.append({"path": item["path"], "identity": [info.st_dev, info.st_ino],
                        "original_mode": item["mode"], "frozen_mode": mode})
        record()
        path.chmod(mode)


def _restore_permissions(root, inventory, changes, source_identity):
    if _identity(root) != source_identity:
        raise MigrationError("source directory identity changed during permission recovery")
    by_path = {item["path"]: item for item in inventory}
    pending = {change["path"]: change for change in changes}
    for change in changes:
        if (change["path"] not in by_path
                or change["original_mode"] != by_path[change["path"]]["mode"]
                or change["frozen_mode"] != change["original_mode"] & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)):
            raise MigrationError("permission recovery mode does not match plan")

    def entry_state(change):
        path = _path(root / change["path"], "source permission recovery entry")
        info = path.lstat()
        if [info.st_dev, info.st_ino] != change["identity"]:
            raise MigrationError("source entry identity changed during permission recovery")
        if stat.S_IMODE(info.st_mode) not in {change["original_mode"], change["frozen_mode"]}:
            raise MigrationError("source mode changed during permission recovery")
        return path, info

    expected = [dict(item) for item in inventory]
    for item in expected:
        if item["path"] in pending:
            _, info = entry_state(pending[item["path"]])
            item["mode"] = stat.S_IMODE(info.st_mode)
    _assert_inventory(root, expected)
    # Parents first. Recheck the affected entry before each write, so a
    # retry is idempotent without hashing the entire packet for every chmod.
    for item in inventory:
        change = pending.get(item["path"])
        if change is not None:
            path, info = entry_state(change)
            if info.st_mtime_ns != item["mtime_ns"]:
                raise MigrationError("source metadata changed during permission recovery")
            if item["kind"] == "file":
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_size != item["size"] or file_sha256(path) != item["sha256"]):
                    raise MigrationError("source bytes changed during permission recovery")
            elif not stat.S_ISDIR(info.st_mode):
                raise MigrationError("source entry kind changed during permission recovery")
            _, after = entry_state(change)
            if (info.st_mtime_ns, info.st_size, info.st_mode) != (after.st_mtime_ns, after.st_size, after.st_mode):
                raise MigrationError("source changed during permission recovery")
            if stat.S_IMODE(info.st_mode) != change["original_mode"]:
                path.chmod(change["original_mode"])


def _cleanup_owned_stage(stage, identity):
    if not stage.exists() or _linked(stage) or _identity(stage) != identity:
        return
    # No traversal through links, including a link inserted during a failed copy.
    def remove(path):
        if _linked(path):
            if not path.is_symlink() and path.is_dir():
                path.rmdir()
            else:
                path.unlink()
        elif path.is_dir():
            path.chmod(stat.S_IRWXU)
            for child in path.iterdir():
                remove(child)
            path.rmdir()
        else:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            path.unlink()
    remove(stage)


def apply_plan(plan_path, *, expected_plan_sha256: str, receipt_path) -> dict:
    """Copy under a cooperative lock; source is retained with read-only modes."""
    plan_path = _path(plan_path, "plan")
    plan = _load_plan(plan_path, expected_plan_sha256)
    receipt_path = _outside_record(receipt_path, plan)
    if receipt_path == plan_path:
        raise MigrationError("receipt must be distinct from plan")
    source, destination, rollback = (Path(plan[key]) for key in ("source", "destination", "rollback_artifact"))
    stage = destination.parent / (".openmontage-migrate-" + plan["migration_id"] + ".staging")
    receipt = {"schema_version": 1, "status": "PREPARING", "plan_path": str(plan_path),
               "plan_sha256": expected_plan_sha256, "migration_id": plan["migration_id"], "started_at": _now(),
               "stage": str(stage)}
    with run_write_lock(source), run_write_lock(destination):
        _check_closure(plan)
        _assert_inventory(source, plan["inventory"])
        if _blockers(source, plan["inventory"]):
            raise MigrationError("source now has unsupported root-bound content")
        if destination.exists() or rollback.exists() or stage.exists():
            raise MigrationError("destination, rollback artifact or staging is occupied")
        receipt_sha = _write_new(receipt_path, receipt)
        stage_identity = None
        try:
            rollback.mkdir()
            _copy_tree(source, rollback / "source", plan["inventory"])
            _assert_inventory(rollback / "source", plan["inventory"])
            receipt["sqlite_snapshots"] = _sqlite_snapshots(source, rollback, plan["inventory"])
            receipt["backup_manifest_sha256"] = _write_new(rollback / "manifest.json", {
                "schema_version": 1, "plan_sha256": expected_plan_sha256,
                "inventory_sha256": plan["inventory_sha256"], "sqlite_snapshots": receipt["sqlite_snapshots"]})
            receipt["status"] = "BACKED_UP"
            receipt_sha = _update_receipt(receipt_path, receipt, receipt_sha)
            # Create the stage exclusively before copying, retaining its inode
            # identity for cleanup even when copy is interrupted part way.
            stage.mkdir()
            stage_identity = _identity(stage)
            receipt.update(status="STAGING", stage_identity=stage_identity)
            receipt_sha = _update_receipt(receipt_path, receipt, receipt_sha)
            for item in plan["inventory"]:
                if not item["path"]:
                    continue
                target = stage / item["path"]
                if item["kind"] == "directory":
                    target.mkdir()
                else:
                    shutil.copy2(source / item["path"], target, follow_symlinks=False)
            for item in reversed(plan["inventory"]):
                if item["kind"] == "directory":
                    shutil.copystat(source / item["path"], stage / item["path"], follow_symlinks=False)
            _assert_inventory(stage, plan["inventory"])
            _assert_inventory(source, plan["inventory"])
            _check_closure(plan)
            receipt["destination_identity"] = stage_identity
            receipt["source_identity"] = _identity(source)
            receipt["permission_changes"] = []
            receipt["status"] = "SOURCE_FREEZING"
            receipt_sha = _update_receipt(receipt_path, receipt, receipt_sha)
            def record_permissions():
                nonlocal receipt_sha
                receipt_sha = _update_receipt(receipt_path, receipt, receipt_sha)
            _freeze_permissions(source, plan["inventory"], receipt["permission_changes"], record_permissions)
            receipt.update(status="SOURCE_FROZEN", frozen_source_inventory=_inventory(source))
            receipt_sha = _update_receipt(receipt_path, receipt, receipt_sha)
            _publish_no_replace(stage, destination)
            receipt.update(status="COPIED", copied_at=_now())
            _update_receipt(receipt_path, receipt, receipt_sha)
            return receipt
        except BaseException as exc:
            receipt.update(status="FAILED", failure_type=type(exc).__name__, failed_at=_now())
            recovery_errors = []
            try:
                published = destination.exists() and receipt.get("destination_identity") == _identity(destination)
                if published:
                    receipt["status"] = "FAILED_PUBLISHED"
                elif receipt.get("permission_changes"):
                    _restore_permissions(source, plan["inventory"], receipt["permission_changes"], receipt["source_identity"])
                    receipt["permission_recovery"] = "RESTORED"
            except BaseException as recovery_exc:
                receipt["permission_recovery"] = "REQUIRED"
                recovery_errors.append({"operation": "restore_permissions", "type": type(recovery_exc).__name__,
                                        "message": str(recovery_exc)})
            try:
                if stage_identity is not None:
                    _cleanup_owned_stage(stage, stage_identity)
            except BaseException as cleanup_exc:
                recovery_errors.append({"operation": "cleanup_stage", "type": type(cleanup_exc).__name__,
                                        "message": str(cleanup_exc)})
            if recovery_errors:
                receipt["recovery_errors"] = recovery_errors
            try:
                _update_receipt(receipt_path, receipt, receipt_sha)
            except BaseException as receipt_exc:
                if hasattr(exc, "add_note"):
                    exc.add_note(f"Failure receipt could not be updated: {type(receipt_exc).__name__}: {receipt_exc}")
            raise


def _receipt_and_plan(receipt_path, expected_sha, *, allow_failed=False):
    receipt_path = _path(receipt_path, "receipt")
    receipt = _read_exact(receipt_path, expected_sha)
    statuses = {"COPIED", "FINALIZED", "FAILED_PUBLISHED"}
    if allow_failed:
        statuses.add("FAILED")
    if receipt.get("schema_version") != 1 or receipt.get("status") not in statuses:
        raise MigrationError("receipt does not describe a completed copy")
    plan = _load_plan(receipt["plan_path"], receipt["plan_sha256"])
    if receipt.get("migration_id") != plan["migration_id"]:
        raise MigrationError("receipt migration identity mismatch")
    _outside_record(receipt_path, plan)
    return receipt, plan


def _verify_backup(plan, receipt):
    rollback = Path(plan["rollback_artifact"])
    _path(rollback, "rollback artifact")
    _assert_inventory(rollback / "source", plan["inventory"])
    manifest = _read_exact(rollback / "manifest.json", receipt["backup_manifest_sha256"])
    if manifest != {"schema_version": 1, "plan_sha256": receipt["plan_sha256"],
                   "inventory_sha256": plan["inventory_sha256"], "sqlite_snapshots": receipt["sqlite_snapshots"]}:
        raise MigrationError("backup manifest identity mismatch")
    for item in receipt["sqlite_snapshots"]:
        target = _path(rollback / item["path"], "SQLite snapshot")
        if not target.is_relative_to(rollback) or file_sha256(target) != item["sha256"]:
            raise MigrationError("SQLite snapshot changed")


def _verify_copy(plan, receipt):
    source, destination = Path(plan["source"]), Path(plan["destination"])
    _check_closure(plan)
    if _identity(destination) != receipt["destination_identity"]:
        raise MigrationError("destination directory identity changed")
    _assert_inventory(destination, plan["inventory"])
    if source.exists():
        if receipt["status"] == "FINALIZED":
            raise MigrationError("source was recreated by another owner; refusing replacement")
        if _identity(source) != receipt["source_identity"]:
            raise MigrationError("source directory identity changed")
        _assert_inventory(source, receipt["frozen_source_inventory"])
    elif receipt["status"] != "FINALIZED":
        raise MigrationError("preserved source is missing")
    if receipt["status"] == "FINALIZED":
        retired = _path(plan["retired_source"], "retired original source")
        if _identity(retired) != receipt["source_identity"]:
            raise MigrationError("retired source directory identity changed")
        _assert_inventory(retired, receipt["frozen_source_inventory"])
    _verify_backup(plan, receipt)


def verify_copy(receipt_path, *, expected_receipt_sha256: str, verification_path) -> dict:
    """Write a separate immutable post-copy attestation for explicit finalize."""
    receipt, plan = _receipt_and_plan(receipt_path, expected_receipt_sha256)
    verification_path = _outside_record(verification_path, plan)
    if verification_path in {Path(receipt_path), Path(receipt["plan_path"])}:
        raise MigrationError("verification record must be distinct")
    with run_write_lock(Path(plan["source"])), run_write_lock(Path(plan["destination"])):
        _verify_copy(plan, receipt)
        result = {"schema_version": 1, "status": "VERIFIED", "receipt_path": str(Path(receipt_path)),
                  "receipt_sha256": expected_receipt_sha256, "plan_sha256": receipt["plan_sha256"],
                  "verified_at": _now(), "inventory_sha256": plan["inventory_sha256"]}
        _write_new(verification_path, result)
        return result


def _remove_verified_tree(root, inventory, identity):
    if _identity(root) != identity:
        raise MigrationError("directory identity changed before removal")
    _assert_inventory(root, inventory)
    # Only enumerated bytes are removed. A new file is preserved and makes
    # rmdir fail; a changed file is detected again immediately before unlink.
    for item in inventory:
        if item["kind"] == "directory":
            (root / item["path"]).chmod(item["mode"] | stat.S_IWUSR | stat.S_IXUSR)
    for item in reversed(inventory):
        path = root / item["path"]
        if _linked(path):
            raise MigrationError("linked path appeared during removal")
        if item["kind"] == "file":
            info = path.stat()
            if info.st_size != item["size"] or info.st_mtime_ns != item["mtime_ns"] or file_sha256(path) != item["sha256"]:
                raise MigrationError("file changed during removal")
            path.chmod(item["mode"] | stat.S_IWUSR)
            path.unlink()
        else:
            path.rmdir()


def finalize_copy(receipt_path, *, expected_receipt_sha256: str, verification_path, expected_verification_sha256: str) -> dict:
    """Retire original by same-volume rename after post-copy verification/CAS.

    The original directory and its ACL survive in the predeclared rollback
    artifact. No source bytes are permanently deleted by finalization.
    """
    receipt, plan = _receipt_and_plan(receipt_path, expected_receipt_sha256)
    if receipt["status"] != "COPIED":
        raise MigrationError("only a copied packet may be finalized")
    verification = _read_exact(verification_path, expected_verification_sha256)
    if (verification.get("status") != "VERIFIED" or verification.get("receipt_path") != str(Path(receipt_path))
            or verification.get("receipt_sha256") != expected_receipt_sha256
            or verification.get("plan_sha256") != receipt["plan_sha256"]):
        raise MigrationError("post-copy verification does not match this receipt")
    source, destination = Path(plan["source"]), Path(plan["destination"])
    with run_write_lock(source), run_write_lock(destination):
        _read_exact(receipt_path, expected_receipt_sha256)
        _verify_copy(plan, receipt)
        retired = _path(plan["retired_source"], "retired original source")
        if retired.exists():
            raise MigrationError("retired source location is occupied")
        if not _same_volume(source, retired.parent):
            raise MigrationError("cross-volume source retirement is unsupported")
        _move_frozen_source(source, retired, receipt["frozen_source_inventory"], receipt["source_identity"])
        receipt.update(status="FINALIZED", finalized_at=_now(), retired_source=str(retired))
        _update_receipt(Path(receipt_path), receipt, expected_receipt_sha256)
        return receipt


def rollback_copy(receipt_path, *, expected_receipt_sha256: str) -> dict:
    """Restore an unchanged source/copy, or retry a caught freeze failure.

    FAILED recovery only restores journaled permissions; it preserves backups
    and any destination belonging to another owner. Hard-kill intermediate
    records still require manual review rather than automatic crash resume.
    """
    receipt, plan = _receipt_and_plan(receipt_path, expected_receipt_sha256, allow_failed=True)
    source, destination = Path(plan["source"]), Path(plan["destination"])
    with run_write_lock(source), run_write_lock(destination):
        _read_exact(receipt_path, expected_receipt_sha256)
        if receipt["status"] == "FAILED":
            if not receipt.get("permission_changes"):
                raise MigrationError("failed copy has no permission recovery journal")
            _restore_permissions(source, plan["inventory"], receipt["permission_changes"], receipt["source_identity"])
            receipt.update(status="ROLLED_BACK", permission_recovery="RESTORED", rolled_back_at=_now())
            _update_receipt(Path(receipt_path), receipt, expected_receipt_sha256)
            return receipt
        _verify_copy(plan, receipt)
        if receipt["status"] == "FINALIZED":
            retired = Path(plan["retired_source"])
            if source.exists():
                raise MigrationError("source is occupied; refusing replacement")
            if not _same_volume(retired, source.parent):
                raise MigrationError("cross-volume source restoration is unsupported")
            _move_frozen_source(retired, source, receipt["frozen_source_inventory"], receipt["source_identity"])
        _remove_verified_tree(destination, plan["inventory"], receipt["destination_identity"])
        _permissions(source, plan["inventory"])
        receipt.update(status="ROLLED_BACK", rolled_back_at=_now())
        _update_receipt(Path(receipt_path), receipt, expected_receipt_sha256)
        return receipt
