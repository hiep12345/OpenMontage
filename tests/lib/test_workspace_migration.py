"""Offline immutable packet fixtures; no production or provider operations."""
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess

import pytest

from lib import workspace_migration as migration


@pytest.fixture
def packet(tmp_path):
    source = tmp_path / "old" / "film"
    source.mkdir(parents=True)
    (source / "artifacts").mkdir()
    (source / "project.json").write_text('{"title":"closed fixture"}', encoding="utf-8")
    (source / "artifacts" / "receipt.json").write_text('{"result":"historical FAIL retained"}', encoding="utf-8")
    (tmp_path / "new").mkdir()
    destination = tmp_path / "new" / "film"
    rollback = tmp_path / "rollback"
    closure = tmp_path / "closure.json"
    closure.write_text(json.dumps({"source": str(source), "status": "CLOSED", "migration_authorized": True}))
    result = {"source": source, "destination": destination, "rollback": rollback, "closure": closure,
              "plan": tmp_path / "plan.json", "receipt": tmp_path / "copy.json", "verification": tmp_path / "verify.json"}
    try:
        yield result
    finally:
        # Windows runner teardown needs write access to deliberately frozen files.
        for root in (source, destination, rollback):
            if root.exists():
                for path in (root, *root.rglob("*")):
                    if not path.is_symlink():
                        path.chmod(stat.S_IRWXU if path.is_dir() else stat.S_IRUSR | stat.S_IWUSR)


def plan(packet):
    value = migration.build_plan(packet["source"], packet["destination"], packet["closure"], packet["rollback"])
    sha = migration.write_plan(value, packet["plan"])
    return value, sha


def apply(packet):
    value, sha = plan(packet)
    result = migration.apply_plan(packet["plan"], expected_plan_sha256=sha, receipt_path=packet["receipt"])
    return value, result, migration.file_sha256(packet["receipt"])


def verified(packet):
    value, result, sha = apply(packet)
    migration.verify_copy(packet["receipt"], expected_receipt_sha256=sha, verification_path=packet["verification"])
    return value, result, sha, migration.file_sha256(packet["verification"])


def test_plan_is_read_only_and_records_exact_inventory(packet):
    before = migration._inventory(packet["source"])
    value = migration.build_plan(packet["source"], packet["destination"], packet["closure"], packet["rollback"])
    assert value["status"] == "PLANNED"
    assert value["inventory"] == before
    assert value["owner_closure_evidence"]["sha256"] == migration.file_sha256(packet["closure"])
    assert not packet["destination"].exists() and not packet["rollback"].exists()
    assert before == migration._inventory(packet["source"])


@pytest.mark.parametrize("kind", ["source", "plan", "closure"])
def test_tampered_source_plan_or_closure_cannot_apply(packet, kind):
    _, sha = plan(packet)
    path = packet["source"] / "project.json" if kind == "source" else packet[kind]
    path.write_text(path.read_text() + " ")
    with pytest.raises(migration.MigrationError, match="changed|compare-and-swap"):
        migration.apply_plan(packet["plan"], expected_plan_sha256=sha, receipt_path=packet["receipt"])
    assert not packet["destination"].exists() and not packet["rollback"].exists()


def test_occupied_destination_is_never_overwritten(packet):
    _, sha = plan(packet)
    packet["destination"].mkdir()
    owned = packet["destination"] / "owner-result.txt"
    owned.write_text("preserve")
    with pytest.raises(migration.MigrationError, match="occupied"):
        migration.apply_plan(packet["plan"], expected_plan_sha256=sha, receipt_path=packet["receipt"])
    assert owned.read_text() == "preserve"


@pytest.mark.parametrize("content", ["self-path", "root-journal", "sqlite-sidecar"])
def test_root_bound_records_and_live_database_sidecars_are_blocked(packet, content):
    if content == "self-path":
        (packet["source"] / "record.json").write_text(json.dumps({"path": str(packet["source"] / "artifact.mp4")}))
    elif content == "root-journal":
        (packet["source"] / "journal.json").write_text('{"artifactRoot":"/other/pinned/root"}')
    else:
        (packet["source"] / "state.sqlite-wal").write_bytes(b"")
    value, sha = plan(packet)
    assert value["status"] == "BLOCKED" and value["blockers"]
    with pytest.raises(migration.MigrationError, match="BLOCKED"):
        migration.apply_plan(packet["plan"], expected_plan_sha256=sha, receipt_path=packet["receipt"])
    assert not packet["destination"].exists()


def test_linked_and_overlapping_paths_cannot_be_planned(packet, tmp_path):
    with pytest.raises(migration.MigrationError, match="overlap"):
        migration.build_plan(packet["source"], packet["source"] / "nested", packet["closure"], packet["rollback"])
    target = tmp_path / "outside.txt"
    target.write_text("external owner data")
    try:
        (packet["source"] / "linked.txt").symlink_to(target)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    with pytest.raises(migration.MigrationError, match="linked"):
        plan(packet)
    assert target.read_text() == "external owner data"


def test_hardlinked_files_are_unsupported(packet, tmp_path):
    target = tmp_path / "outside.txt"
    target.write_text("external owner data")
    os.link(target, packet["source"] / "linked.txt")
    with pytest.raises(migration.MigrationError, match="hardlinked"):
        plan(packet)


@pytest.mark.skipif(os.name != "nt", reason="native Windows junction fixture")
def test_junction_is_rejected_without_path_is_junction(packet, tmp_path, monkeypatch):
    target = tmp_path / "outside"
    target.mkdir()
    (target / "owner.txt").write_text("preserve")
    link = packet["source"] / "junction"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True)
    try:
        monkeypatch.delattr(Path, "is_junction", raising=False)
        with pytest.raises(migration.MigrationError, match="linked"):
            plan(packet)
        assert (target / "owner.txt").read_text() == "preserve"
    finally:
        link.rmdir()


def test_copy_preserves_original_receipts_freezes_source_and_rollback(packet):
    value, result, sha = apply(packet)
    assert result["status"] == "COPIED"
    assert migration._inventory(packet["destination"]) == value["inventory"]
    assert not ((packet["source"] / "project.json").stat().st_mode & stat.S_IWUSR)
    assert migration._inventory(packet["rollback"] / "source") == value["inventory"]
    migration.rollback_copy(packet["receipt"], expected_receipt_sha256=sha)
    assert not packet["destination"].exists()
    assert migration._inventory(packet["source"]) == value["inventory"]
    assert (packet["source"] / "artifacts" / "receipt.json").read_text() == '{"result":"historical FAIL retained"}'


def test_separate_verified_finalize_and_rollback_restore_absent_source(packet):
    value, _, sha, verified_sha = verified(packet)
    migration.finalize_copy(packet["receipt"], expected_receipt_sha256=sha,
                            verification_path=packet["verification"], expected_verification_sha256=verified_sha)
    assert not packet["source"].exists()
    retired = packet["rollback"] / "original-source"
    assert migration._inventory(retired) == json.loads(packet["receipt"].read_text())["frozen_source_inventory"]
    assert migration._inventory(packet["destination"]) == value["inventory"]
    final_sha = migration.file_sha256(packet["receipt"])
    migration.rollback_copy(packet["receipt"], expected_receipt_sha256=final_sha)
    assert not packet["destination"].exists()
    assert migration._inventory(packet["source"]) == value["inventory"]
    assert not retired.exists()


@pytest.mark.parametrize("changed", ["source", "destination", "rollback"])
def test_finalize_and_rollback_refuse_changed_bytes(packet, changed):
    _, _, sha, verified_sha = verified(packet)
    root = packet[changed] / "source" if changed == "rollback" else packet[changed]
    file = root / "project.json"
    file.chmod(stat.S_IRUSR | stat.S_IWUSR)
    file.write_text("new owner result")
    with pytest.raises(migration.MigrationError, match="changed"):
        migration.finalize_copy(packet["receipt"], expected_receipt_sha256=sha,
                                verification_path=packet["verification"], expected_verification_sha256=verified_sha)
    with pytest.raises(migration.MigrationError, match="changed"):
        migration.rollback_copy(packet["receipt"], expected_receipt_sha256=sha)
    assert file.read_text() == "new owner result"


def test_finalize_requires_exact_post_copy_attestation(packet):
    _, _, sha, _ = verified(packet)
    with pytest.raises(migration.MigrationError, match="compare-and-swap"):
        migration.finalize_copy(packet["receipt"], expected_receipt_sha256=sha,
                                verification_path=packet["verification"], expected_verification_sha256="0" * 64)
    assert packet["source"].exists()


def test_retirement_never_overwrites_occupied_rollback_location(packet):
    _, _, sha, verified_sha = verified(packet)
    retired = packet["rollback"] / "original-source"
    retired.mkdir()
    (retired / "owner-result.txt").write_text("preserve")
    with pytest.raises(migration.MigrationError, match="occupied"):
        migration.finalize_copy(packet["receipt"], expected_receipt_sha256=sha,
                                verification_path=packet["verification"], expected_verification_sha256=verified_sha)
    assert packet["source"].exists()
    assert (retired / "owner-result.txt").read_text() == "preserve"


def test_cross_volume_retirement_is_blocked_at_plan_and_rechecked(packet, monkeypatch):
    value, _, sha, verified_sha = verified(packet)
    monkeypatch.setattr(migration, "_same_volume", lambda *args: False)
    with pytest.raises(migration.MigrationError, match="cross-volume"):
        migration.finalize_copy(packet["receipt"], expected_receipt_sha256=sha,
                                verification_path=packet["verification"], expected_verification_sha256=verified_sha)
    assert packet["source"].exists()


def test_plan_marks_cross_volume_retirement_blocked(packet, monkeypatch):
    monkeypatch.setattr(migration, "_same_volume", lambda *args: False)
    value, _ = plan(packet)
    assert value["status"] == "BLOCKED"
    assert value["blockers"][-1]["reason"] == "CROSS_VOLUME_SOURCE_RETIREMENT_UNSUPPORTED"


def test_rollback_refuses_recreated_source_after_retirement(packet):
    _, _, sha, verified_sha = verified(packet)
    migration.finalize_copy(packet["receipt"], expected_receipt_sha256=sha,
                            verification_path=packet["verification"], expected_verification_sha256=verified_sha)
    packet["source"].mkdir()
    (packet["source"] / "owner.txt").write_text("new result")
    with pytest.raises(migration.MigrationError, match="recreated"):
        migration.rollback_copy(packet["receipt"], expected_receipt_sha256=migration.file_sha256(packet["receipt"]))
    assert (packet["source"] / "owner.txt").read_text() == "new result"
    assert packet["destination"].exists()
    assert (packet["rollback"] / "original-source").is_dir()


def test_atomic_publication_cannot_replace_racing_owner_target(packet, monkeypatch):
    value, sha = plan(packet)
    original = migration._publish_no_replace
    def race(source, target):
        target.mkdir()
        (target / "owner-result.txt").write_text("preserve")
        original(source, target)
    monkeypatch.setattr(migration, "_publish_no_replace", race)
    with pytest.raises(OSError):
        migration.apply_plan(packet["plan"], expected_plan_sha256=sha, receipt_path=packet["receipt"])
    assert (packet["destination"] / "owner-result.txt").read_text() == "preserve"
    assert migration._inventory(packet["source"]) == value["inventory"]
    assert not list(packet["destination"].parent.glob(".openmontage-migrate-*.staging"))


def test_interrupted_apply_cleans_only_owned_staging_and_preserves_backup(packet, monkeypatch):
    value, sha = plan(packet)
    unrelated = packet["destination"].parent / ".other-staging"
    unrelated.mkdir()
    (unrelated / "owner.txt").write_text("preserve")
    original = migration._publish_no_replace
    def interrupted(source, target):
        raise KeyboardInterrupt("fixture interruption")
    monkeypatch.setattr(migration, "_publish_no_replace", interrupted)
    with pytest.raises(KeyboardInterrupt):
        migration.apply_plan(packet["plan"], expected_plan_sha256=sha, receipt_path=packet["receipt"])
    stage = packet["destination"].parent / (".openmontage-migrate-" + value["migration_id"] + ".staging")
    assert not stage.exists() and not packet["destination"].exists()
    assert migration._inventory(packet["source"]) == value["inventory"]
    assert migration._inventory(packet["rollback"] / "source") == value["inventory"]
    assert (unrelated / "owner.txt").read_text() == "preserve"
    assert json.loads(packet["receipt"].read_text())["status"] == "FAILED"


@pytest.mark.parametrize("failure_type", [OSError, KeyboardInterrupt])
@pytest.mark.parametrize("after_chmod", [False, True])
def test_partial_freeze_restores_permissions_on_second_chmod(packet, monkeypatch, failure_type, after_chmod):
    value, sha = plan(packet)
    original = Path.chmod
    count = 0
    failure = failure_type("second source chmod")

    def interrupted(path, mode, *args, **kwargs):
        nonlocal count
        if path == packet["source"] or packet["source"] in path.parents:
            count += 1
            if count == 2:
                if after_chmod:
                    original(path, mode, *args, **kwargs)
                raise failure
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "chmod", interrupted)
    with pytest.raises(failure_type) as caught:
        migration.apply_plan(packet["plan"], expected_plan_sha256=sha, receipt_path=packet["receipt"])
    assert caught.value is failure
    assert migration._inventory(packet["source"]) == value["inventory"]
    receipt = json.loads(packet["receipt"].read_text())
    assert receipt["status"] == "FAILED" and receipt["permission_recovery"] == "RESTORED"
    assert len(receipt["permission_changes"]) == 2
    assert not packet["destination"].exists()


def test_inventory_failure_immediately_after_freeze_restores_permissions(packet, monkeypatch):
    value, sha = plan(packet)
    original = migration._inventory
    failed = False

    def interrupted(root):
        nonlocal failed
        if root == packet["source"] and not root.stat().st_mode & stat.S_IWUSR and not failed:
            failed = True
            raise OSError("post-freeze inventory failed")
        return original(root)

    monkeypatch.setattr(migration, "_inventory", interrupted)
    with pytest.raises(OSError, match="post-freeze"):
        migration.apply_plan(packet["plan"], expected_plan_sha256=sha, receipt_path=packet["receipt"])
    assert failed
    assert original(packet["source"]) == value["inventory"]
    receipt = json.loads(packet["receipt"].read_text())
    assert receipt["permission_recovery"] == "RESTORED"
    assert "frozen_source_inventory" not in receipt


def test_failed_restore_preserves_original_failure_and_can_be_retried(packet, monkeypatch):
    value, sha = plan(packet)
    original = Path.chmod
    count = 0
    failure = KeyboardInterrupt("primary freeze failure")

    def interrupted(path, mode, *args, **kwargs):
        nonlocal count
        if path == packet["source"] or packet["source"] in path.parents:
            count += 1
            if count == 2:
                raise failure
            if count > 2:
                raise OSError("permission restore denied")
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "chmod", interrupted)
    with pytest.raises(KeyboardInterrupt) as caught:
        migration.apply_plan(packet["plan"], expected_plan_sha256=sha, receipt_path=packet["receipt"])
    assert caught.value is failure
    receipt = json.loads(packet["receipt"].read_text())
    assert receipt["status"] == "FAILED" and receipt["failure_type"] == "KeyboardInterrupt"
    assert receipt["permission_recovery"] == "REQUIRED"
    assert receipt["recovery_errors"][0]["message"] == "permission restore denied"
    monkeypatch.setattr(Path, "chmod", original)
    recovered = migration.rollback_copy(packet["receipt"], expected_receipt_sha256=migration.file_sha256(packet["receipt"]))
    assert recovered["status"] == "ROLLED_BACK"
    assert migration._inventory(packet["source"]) == value["inventory"]
    assert migration._inventory(packet["rollback"] / "source") == value["inventory"]
    assert not packet["destination"].exists()


def test_partial_freeze_recovery_refuses_modified_source(packet, monkeypatch):
    _, sha = plan(packet)
    original = Path.chmod
    count = 0
    changed = packet["source"] / "project.json"

    def interrupted(path, mode, *args, **kwargs):
        nonlocal count
        if path == packet["source"] or packet["source"] in path.parents:
            count += 1
            if count == 2:
                original(changed, stat.S_IRUSR | stat.S_IWUSR)
                changed.write_text("new owner result")
                raise KeyboardInterrupt("source changed during freeze")
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "chmod", interrupted)
    with pytest.raises(KeyboardInterrupt, match="source changed"):
        migration.apply_plan(packet["plan"], expected_plan_sha256=sha, receipt_path=packet["receipt"])
    receipt = json.loads(packet["receipt"].read_text())
    assert receipt["permission_recovery"] == "REQUIRED"
    assert changed.read_text() == "new owner result"
    mode = stat.S_IMODE(changed.stat().st_mode)
    failed_sha = migration.file_sha256(packet["receipt"])
    with pytest.raises(migration.MigrationError, match="changed"):
        migration.rollback_copy(packet["receipt"], expected_receipt_sha256=failed_sha)
    assert migration.file_sha256(packet["receipt"]) == failed_sha
    assert stat.S_IMODE(changed.stat().st_mode) == mode
    assert changed.read_text() == "new owner result"


def test_database_backup_api_snapshot_is_consistent(packet):
    database = packet["source"] / "state.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE state (value TEXT)")
        connection.execute("INSERT INTO state VALUES ('known')")
    value, receipt, _ = apply(packet)
    assert len(receipt["sqlite_snapshots"]) == 1
    snapshot = packet["rollback"] / receipt["sqlite_snapshots"][0]["path"]
    with sqlite3.connect(snapshot) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("SELECT value FROM state").fetchall() == [("known",)]
    assert migration._inventory(packet["destination"]) == value["inventory"]


def test_cli_defaults_to_plan_and_does_not_create_destination(packet, capsys):
    from scripts.workspace_migrate import main
    result = main(["--source", str(packet["source"]), "--destination", str(packet["destination"]),
                   "--owner-closure-evidence", str(packet["closure"]), "--rollback-artifact", str(packet["rollback"])])
    assert result == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PLANNED"
    assert not packet["destination"].exists() and not packet["rollback"].exists()
