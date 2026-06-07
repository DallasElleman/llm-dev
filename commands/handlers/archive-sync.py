#!/usr/bin/env python3
"""Manually sync the current project's llm-dev archive (commit + best-effort push).

Resolves the `.archive` worktree for the container you're in and runs
`_archive.archive_sync`. Exits 0 always; reports JSON.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import _archive


def main() -> int:
    aw = _archive.archive_worktree(Path.cwd())
    if aw is None:
        print(json.dumps({
            "ok": False,
            "error": "not inside an llm-dev container (no .archive worktree found)",
        }))
        return 0
    result = _archive.archive_sync(aw, [], "manual archive sync")
    print(json.dumps({"ok": True, **result}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
