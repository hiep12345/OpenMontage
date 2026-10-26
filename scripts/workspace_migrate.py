"""Offline packet migration: default to planning; mutations need explicit stages.

Closure JSON: {"source": "<canonical absolute directory>", "status": "CLOSED",
               "migration_authorized": true}. This is supplied owner evidence,
not a status the tool infers. Root-bound receipts have no automatic override.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.workspace_migration import (MigrationError, apply_plan, build_plan, file_sha256,
                                     finalize_copy, rollback_copy, verify_copy, write_plan)
from lib.run_lock import RunWriterError


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    stages = {"plan", "apply", "verify", "finalize", "rollback"}
    if args and args[0] not in stages and args[0] not in {"-h", "--help"}:
        args.insert(0, "plan")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage", required=True)
    plan = sub.add_parser("plan", help="read-only eligibility and SHA inventory (default)")
    for flag in ("source", "destination", "owner-closure-evidence", "rollback-artifact"):
        plan.add_argument("--" + flag, required=True)
    plan.add_argument("--output", help="save a new immutable plan file exclusively")
    apply = sub.add_parser("apply", help="copy, verify, retain and freeze source")
    apply.add_argument("--plan", required=True)
    apply.add_argument("--expected-plan-sha256", required=True)
    apply.add_argument("--receipt", required=True)
    for name in ("verify", "finalize", "rollback"):
        command = sub.add_parser(name, help="retire original by recoverable rename" if name == "finalize" else None)
        command.add_argument("--receipt", required=True)
        command.add_argument("--expected-receipt-sha256", required=True)
        if name != "rollback":
            command.add_argument("--verification", required=True)
        if name == "finalize":
            command.add_argument("--expected-verification-sha256", required=True)
    options = parser.parse_args(args)
    try:
        if options.stage == "plan":
            value = build_plan(options.source, options.destination, options.owner_closure_evidence, options.rollback_artifact)
            if options.output:
                digest = write_plan(value, options.output)
                print(json.dumps({"plan_path": options.output, "plan_sha256": digest, "plan": value}, indent=2))
            else:
                print(json.dumps(value, indent=2))
            return 2 if value["status"] == "BLOCKED" else 0
        if options.stage == "apply":
            value = apply_plan(options.plan, expected_plan_sha256=options.expected_plan_sha256, receipt_path=options.receipt)
        elif options.stage == "verify":
            value = verify_copy(options.receipt, expected_receipt_sha256=options.expected_receipt_sha256, verification_path=options.verification)
        elif options.stage == "finalize":
            value = finalize_copy(options.receipt, expected_receipt_sha256=options.expected_receipt_sha256,
                                  verification_path=options.verification, expected_verification_sha256=options.expected_verification_sha256)
        else:
            value = rollback_copy(options.receipt, expected_receipt_sha256=options.expected_receipt_sha256)
        path = options.verification if options.stage == "verify" else options.receipt
        print(json.dumps({"record_path": path, "record_sha256": file_sha256(path), "result": value}, indent=2))
        return 0
    except (MigrationError, RunWriterError, OSError, sqlite3.Error) as exc:
        print(f"migration blocked: {exc}", file=sys.stderr)
        return 2
if __name__ == "__main__":
    raise SystemExit(main())
