"""Enter stages and record explicit knowledge decisions/feedback without paid IO."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import stage_context as context
from lib.paths import resolve_project_input


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=resolve_project_input, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    enable = commands.add_parser("enable")
    enable.add_argument("--profile", help="JSON profile with explicit scope and source declarations")
    configure = commands.add_parser("configure")
    configure.add_argument("--profile", required=True)
    for name in ("enter", "context", "inspect", "application-template", "review-template"):
        command = commands.add_parser(name)
        command.add_argument("--stage", required=True)
        if name not in {"enter", "context", "inspect"}:
            command.add_argument("--artifact", required=True)
    read = commands.add_parser("read-item", help="Read bounded selected source content, including omitted preview sections")
    read.add_argument("--stage", required=True)
    read.add_argument("--id", required=True)
    read.add_argument("--context-hash", required=True)
    read.add_argument("--offset", type=int, default=0)
    read.add_argument("--limit", type=int, default=context.TEXT_LIMIT)
    handoff = commands.add_parser("handoff", help="Checkpoint explicit assessment files; never generate applied/PASS decisions")
    handoff.add_argument("--stage", required=True)
    handoff.add_argument("--artifacts", required=True, help="Canonical checkpoint artifacts JSON map")
    handoff.add_argument("--application", required=True, help="Reviewed application-template JSON")
    handoff.add_argument("--review", help="Reviewed script review-template JSON; required at script")
    handoff.add_argument("--status", choices=["completed", "awaiting_human"], default="awaiting_human")
    handoff.add_argument("--human-approved", action="store_true", help="Only for exact approval actually obtained")
    for name in ("record-application", "record-review"):
        command = commands.add_parser(name)
        command.add_argument("--stage", required=True)
        command.add_argument("--artifact", required=True)
        command.add_argument("--packet", required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--stage", required=True)
    evaluate.add_argument("--artifacts", required=True, help="JSON checkpoint artifacts map")
    evaluate.add_argument("--status", default="completed", choices=["completed", "awaiting_human"])
    feedback = commands.add_parser("feedback")
    feedback.add_argument("--packet", required=True)
    commands.add_parser("feedback-history")
    commands.add_parser("generation-readiness")
    args = parser.parse_args(argv)
    try:
        if args.command == "enable":
            output = context.enable_policy(args.project, read_json(args.profile) if args.profile else None)
        elif args.command == "configure":
            output = context.configure_profile(args.project, read_json(args.profile))
        elif args.command in {"enter", "context"}:
            output = context.build_stage_context(args.project, args.stage)
            diagnostics = context.consumption_status(output)
            for warning in diagnostics["warnings"]:
                print("WARNING: " + warning, file=sys.stderr)
        elif args.command == "inspect":
            stage = context.build_stage_context(args.project, args.stage)
            output = {"context": stage, "consumption": context.consumption_status(stage)}
        elif args.command == "read-item":
            output = context.read_context_item(args.project, args.stage, args.id,
                context_hash=args.context_hash, offset=args.offset, limit=args.limit)
        elif args.command == "application-template":
            stage = context.build_stage_context(args.project, args.stage)
            artifact = read_json(args.artifact)
            output = context.application_template(stage, artifact)
        elif args.command == "review-template":
            output = context.review_template(args.project, args.stage, read_json(args.artifact))
        elif args.command == "record-application":
            packet = read_json(args.packet)
            artifact = read_json(args.artifact)
            if packet["artifact_hash"] != context.digest(artifact):
                raise context.StageContextError("Application packet refers to changed output")
            output = context.record_application(args.project, args.stage, artifact, packet["decisions"],
                                                packet["reviewer"], context_hash=packet["context_hash"])
        elif args.command == "record-review":
            output = context.record_logic_review(args.project, args.stage, read_json(args.artifact), read_json(args.packet))
        elif args.command == "handoff":
            output = handoff_stage(args)
        elif args.command == "evaluate":
            context.enforce_stage_context(args.project, args.stage, args.status, read_json(args.artifacts))
            output = {"status": "PASS", "scope": "Recorded context/application/review preconditions only; no creative-quality inference"}
        elif args.command == "feedback":
            output = context.append_feedback(args.project, read_json(args.packet))
        elif args.command == "feedback-history":
            output = context.read_feedback(args.project)
        else:
            context.require_generation_context(args.project)
            output = {"status": "PASS", "scope": "Current prerequisite checkpoint provenance"}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (context.StageContextError, ValueError, OSError, KeyError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


def handoff_stage(args):
    """Keep assessment writes and checkpoint advancement under one run writer."""
    from lib.run_lock import RunWriterError, run_write_lock

    try:
        with run_write_lock(args.project.resolve()):
            return _handoff_stage_locked(args)
    except RunWriterError as exc:
        raise context.StageContextError(str(exc)) from exc


def _handoff_stage_locked(args):
    """Accept authored assessments, not an auto-filled loop over context IDs."""
    from lib.checkpoint import write_checkpoint

    project = args.project.resolve()
    marker = read_json(project / "project.json")
    if marker.get("project_id") != project.name:
        raise context.StageContextError("Project marker identity mismatch")
    stage = context.build_stage_context(project, args.stage)
    artifacts = read_json(args.artifacts)
    _, manifest = context._manifest(project)
    entry = next(item for item in manifest["stages"] if item["name"] == args.stage)
    name = context.CANONICAL.get(args.stage) or entry.get("produces", [None])[0]
    artifact = artifacts.get(name)
    if not isinstance(artifact, dict):
        raise context.StageContextError("Handoff requires the canonical output object")
    application = read_json(args.application)
    if application["context_hash"] != stage["context_hash"] or application["artifact_hash"] != context.digest(artifact):
        raise context.StageContextError("Application packet refers to changed context or output")
    # Validate all supplied assessment inputs before appending any receipts.
    context._decisions(stage, application["decisions"])
    review = None
    if args.stage == "script":
        if not args.review:
            raise context.StageContextError("Script handoff needs explicit --review; no automatic semantic PASS")
        review = read_json(args.review)
        context._validate("stage_logic_review", review)
        context._review_matches(stage, artifact, review)
    artifacts["stage_context"] = stage
    artifacts["knowledge_application"] = context.record_application(project, args.stage, artifact,
        application["decisions"], application["reviewer"], context_hash=application["context_hash"])
    if review is not None:
        artifacts["stage_logic_review"] = context.record_logic_review(project, args.stage, artifact, review)
    path = write_checkpoint(project.parent, project.name, args.stage, args.status, artifacts,
                            pipeline_type=marker["pipeline_type"], human_approved=args.human_approved)
    return {"checkpoint": str(path), "status": args.status,
            "scope": "Recorded application/semantic attestations and checkpoint prerequisites; no media-quality acceptance"}


if __name__ == "__main__":
    raise SystemExit(main())
