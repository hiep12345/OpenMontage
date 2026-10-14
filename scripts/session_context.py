"""Print compact source-bound OpenMontage context without selecting work implicitly."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Absolute script execution works from any cwd without installation.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.session_recovery import RecoveryError, recover  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--task-root", help="Exact workflow checkout within workspace")
    parser.add_argument("--session", help="Exact recorded workflow owner session")
    parser.add_argument("--task", help="Exact recorded task, paired with session")
    parser.add_argument("--project", help="Explicit absolute run directory within workspace")
    parser.add_argument("--stage", help="Optional exact manifest stage")
    args = parser.parse_args(argv)
    try:
        context = recover(**vars(args))
    except (RecoveryError, OSError, UnicodeError, TypeError, KeyError) as exc:
        # No source payload or underlying parser exception is printed on failure.
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(context, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
