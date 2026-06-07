#!/usr/bin/env python3
"""Migrate the current project's llm-dev archive to the unified-git-state format.

Resolves the `.archive/` dir for the current layout (container or in-place) and
runs the one-shot format migrator. Always exits 0; reports JSON.

Usage: python migrate-archive.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _archive
import _migrate


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate archive to unified-git-state format")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change without writing anything")
    args = parser.parse_args()

    archive_dir = _archive.resolve_archive_dir(Path.cwd())
    if archive_dir is None:
        print(json.dumps({
            "ok": False,
            "error": "no .archive/ found for this project (run from a project root)",
        }))
        return 0

    todos_path = archive_dir.parent / "CURRENT-TODOs.md"
    try:
        report = _migrate.migrate(
            archive_dir,
            todos_path if todos_path.exists() else None,
            dry_run=args.dry_run,
        )
    except Exception as e:  # never crash a handler
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        return 0

    print(json.dumps({"ok": True, **report}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
