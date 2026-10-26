"""Run pytest with invocation-owned scratch data outside the checkout.

The printed directory contains invocation.json, pytest basetemp and its cache.
Successful runs remove it; failures and interruptions retain it for diagnosis.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


REPO_ROOT = Path(__file__).resolve().parents[1]


def _validate_args(args: list[str]) -> None:
    # Pytest also accepts options from the environment. Never let a caller point
    # its destructive basetemp initialization at an arbitrary or held directory.
    options = [*args, *shlex.split(os.environ.get("PYTEST_ADDOPTS", ""))]
    for option in options:
        name = option.split("=", 1)[0]
        if "--basetemp" in option or (
            name.startswith("--") and name != "--" and "--basetemp".startswith(name)
        ):
            raise ValueError("Caller --basetemp overrides are unsupported; the runner owns pytest scratch data")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        _validate_args(args)
        temp_parent = Path(tempfile.gettempdir()).resolve()
        if temp_parent == REPO_ROOT or REPO_ROOT in temp_parent.parents:
            raise ValueError("The system temporary directory must be outside the checkout")
    except ValueError as exc:
        print(f"[tests] {exc}", file=sys.stderr)
        return 2

    root = Path(tempfile.mkdtemp(prefix="openmontage-pytest-", dir=temp_parent))
    command = [sys.executable, "-B", "-Xutf8", "-m", "pytest", *args,
               f"--basetemp={root / 'basetemp'}", "-o", f"cache_dir={root / 'cache'}"]
    print(f"[tests] artifacts: {root}", flush=True)
    receipt = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checkout": str(REPO_ROOT), "cwd": str(Path.cwd()),
        "command": command,
    }
    result = None
    try:
        (root / "invocation.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        process = subprocess.Popen(command, env=env)
        try:
            result = process.wait()
        except KeyboardInterrupt:
            # The child may already have received Ctrl-C. Ensure it has stopped
            # before returning while retaining its diagnostics.
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            result = 130
        return result
    finally:
        if result == 0:
            shutil.rmtree(root)
            print(f"[tests] cleaned successful run: {root}", flush=True)
        else:
            print(f"[tests] retained diagnostics: {root}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
