#!/usr/bin/env python3
"""UserPromptSubmit hook: set conversation title to reflect the claimed stream.

Emits sessionTitle once per session (idempotent via flag file at
~/.claude/llm-dev-title-set/<session_id>). No-op when:
  - session_id is missing from the hook payload
  - no .archive/ is found from cwd (not an llm-dev project)
  - session has no stream claim (--no-stream sessions)
  - title has already been set this session (flag file present)

Output format (stdout, on first claim resolution):
  {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "sessionTitle": "[<slug>]"}}

SPIKE-GATED: Whether sessionTitle in UserPromptSubmit actually changes the
conversation title at runtime must be verified in a live interactive Claude Code
session before this feature is considered working. The implementation is
intentionally clean and revertable: remove the UserPromptSubmit entry from
hooks.json and delete this file to fully revert.
"""
import json
import os
import sys
from pathlib import Path


FLAG_DIR = Path.home() / ".claude" / "llm-dev-title-set"


def flag_path(session_id: str) -> Path:
    return FLAG_DIR / session_id


def find_transcripts_index(start_dir: Path) -> Path | None:
    """Search up from start_dir for .archive/transcripts/_index.md.

    Stops at a CLAUDE.md boundary to avoid crossing project roots.
    """
    current = start_dir.resolve()
    while True:
        index_path = current / ".archive" / "transcripts" / "_index.md"
        if index_path.exists():
            return index_path
        if (current / "CLAUDE.md").exists():
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def find_claimed_slug(todos_path: Path, session_id: str) -> str | None:
    """Return the stream slug claimed by session_id, or None if unclaimed."""
    try:
        import _registry as _reg
    except ImportError:
        # When running as a real hook (not in tests), _registry lives next to
        # the command handlers, two levels up from this file.
        sys.path.insert(
            0, str(Path(__file__).parent.parent / "commands" / "handlers")
        )
        try:
            import _registry as _reg
        except ImportError:
            return None
    try:
        r = _reg.parse(todos_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    for stream in r.streams:
        if stream.claim == session_id:
            return stream.slug
    return None


def resolve_todos_path(index_path: Path) -> Path:
    """Derive CURRENT-TODOs.md path from the transcripts index path.

    index_path: .archive/transcripts/_index.md
    project_root: .archive/transcripts/_index.md -> ../../.. -> project root
    """
    return index_path.parent.parent.parent / "CURRENT-TODOs.md"


def build_output(slug: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "sessionTitle": f"[{slug}]",
        }
    }


def main() -> None:
    # Read hook payload from stdin (CC sends JSON with session_id and cwd)
    payload: dict = {}
    try:
        raw = sys.stdin.read()
        if raw.strip():
            payload = json.loads(raw)
    except Exception:
        pass

    session_id: str = (
        payload.get("session_id") or os.environ.get("CLAUDE_SESSION_ID", "")
    )
    cwd_str: str = (
        payload.get("cwd") or os.environ.get("CLAUDE_CWD") or os.getcwd()
    )

    if not session_id:
        return

    # Idempotency: title already set for this session → no-op
    if flag_path(session_id).exists():
        return

    cwd = Path(cwd_str)
    index_path = find_transcripts_index(cwd)
    if index_path is None:
        return

    todos_path = resolve_todos_path(index_path)
    if not todos_path.exists():
        return

    slug = find_claimed_slug(todos_path, session_id)
    if slug is None:
        return

    print(json.dumps(build_output(slug)))

    # Mark as done so subsequent prompts in this session are no-ops
    try:
        FLAG_DIR.mkdir(parents=True, exist_ok=True)
        flag_path(session_id).touch()
    except OSError:
        pass


if __name__ == "__main__":
    main()
