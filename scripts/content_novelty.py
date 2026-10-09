"""Maintained CLI for MT preflight, retained-fact import and fenced intent updates."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.content_novelty import NoveltyRegistry, validate_reservation_request
from lib.hub_access import configured_client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["check", "import-retained", "transition"])
    parser.add_argument("--channel", default="MT")
    parser.add_argument("--registry")
    parser.add_argument("--identity")
    parser.add_argument("--delivery-plan", help="Sealed proposal plan required for a Hub-bound MT generation reservation")
    parser.add_argument("--local-only", action="store_true", help="Explicit MT local-only reservation; no Hub delivery plan or delivery authority")
    parser.add_argument("--stage", choices=["PRE_GENERATION", "PRE_DELIVERY"], default="PRE_GENERATION")
    parser.add_argument("--reserve", action="store_true")
    parser.add_argument("--packet")
    parser.add_argument("--production-id")
    parser.add_argument("--expected-version", type=int)
    parser.add_argument("--state", choices=["GENERATING", "SUBMITTED_UNKNOWN", "FINISHED", "CANCELLED"])
    parser.add_argument("--reconciled", action="store_true")
    args = parser.parse_args()
    if args.local_only and args.operation != "check":
        parser.error("--local-only is only valid for check --reserve")
    if args.operation == "check":
        if not args.identity:
            parser.error("check requires --identity")
        identity = json.loads(Path(args.identity).read_text(encoding="utf-8"))
        plan = json.loads(Path(args.delivery_plan).read_text(encoding="utf-8")) if args.delivery_plan else None
        # Validate before loading credentials, reading Hub or reserving generation.
        validate_reservation_request(args.channel, identity, args.stage, args.reserve, plan, args.local_only)
        result = configured_client().novelty(args.channel, identity, args.stage,
                                            registry_path=args.registry, reserve=args.reserve, delivery_plan=plan, local_only=args.local_only)
    else:
        registry = NoveltyRegistry(args.registry)
        try:
            if args.operation == "import-retained":
                if not args.packet:
                    parser.error("import-retained requires --packet")
                result = registry.import_retained(args.packet, args.channel)
            else:
                if not args.production_id or args.expected_version is None or not args.state:
                    parser.error("transition requires production ID, expected version and state")
                result = {"version": registry.transition(args.production_id, args.expected_version, args.state, args.reconciled)}
        finally:
            registry.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, sqlite3.Error) as error:
        print(json.dumps({"status": "REVIEW_REQUIRED", "error": str(error) if str(error).startswith("ACTIVE_INTENT_CONFLICT") else "Preflight unavailable; inputs/access/registry require inspection"}))
        sys.exit(2)
