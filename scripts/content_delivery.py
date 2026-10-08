"""Seal/validate proposal plans and check final batches offline; no credentials/API."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.content_delivery import seal_plan, validate_batch, validate_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["seal", "validate", "check"])
    parser.add_argument("--plan", required=True)
    parser.add_argument("--payload")
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    if args.operation == "seal":
        result = seal_plan(plan)
    elif args.operation == "validate":
        result = {"status": "VALID", "planHash": validate_plan(plan)["planHash"]}
    else:
        if not args.payload:
            parser.error("check requires --payload")
        result = validate_batch(json.loads(Path(args.payload).read_text(encoding="utf-8")), plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, TypeError, KeyError, OSError):
        print(json.dumps({"status": "BLOCKED", "error": "Delivery plan or exact batch requires inspection"}))
        sys.exit(2)
