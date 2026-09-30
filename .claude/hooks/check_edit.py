#!/usr/bin/env python3
"""PostToolUse hook: format and lint an edited Python file, and check an edited JSON file parses.

The app keeps serving the last good copy of a broken content file, so a JSON mistake would otherwise look like an edit
that did nothing. Exit code 2 shows Claude what's wrong; the edit itself has already happened.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]).resolve()


def main() -> int:
    try:
        tool_input = json.load(sys.stdin).get("tool_input") or {}
    except ValueError:
        return 0
    path = Path(tool_input.get("file_path") or "")
    if not path.is_file():
        return 0
    try:
        rel = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return 0  # outside the repository
    if path.suffix == ".json":
        try:
            json.loads(path.read_text())
        except ValueError as e:
            print(
                f"{rel} is not valid JSON: {e}. The app keeps using the last good copy until it's fixed.",
                file=sys.stderr,
            )
            return 2
    elif path.suffix == ".py" and shutil.which("uv"):
        subprocess.run(["uv", "run", "--quiet", "ruff", "format", rel], cwd=ROOT, capture_output=True)
        lint = subprocess.run(
            ["uv", "run", "--quiet", "ruff", "check", "--fix", rel], cwd=ROOT, capture_output=True, text=True
        )
        if lint.returncode:
            print(f"ruff found problems in {rel}:\n{lint.stdout.strip()}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
