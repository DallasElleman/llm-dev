#!/usr/bin/env python3
"""stream.py — /llm-dev:stream subcommand handler.

Dispatches the subcommand verbs (list, new, join, release, pause, resume,
archive, rename). Operates on CURRENT-TODOs.md in the current project.
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _registry as _reg
import _session


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _find_todos_path(start: Path) -> Path:
    """Search upward for CURRENT-TODOs.md."""
    cur = start.resolve()
    while True:
        candidate = cur / "CURRENT-TODOs.md"
        if candidate.exists():
            return candidate
        if cur.parent == cur:
            # Default to the start dir even if missing
            return start / "CURRENT-TODOs.md"
        cur = cur.parent


def cmd_list(todos_path: Path, all_streams: bool) -> int:
    if not todos_path.exists():
        print("No CURRENT-TODOs.md found in this project.", file=sys.stderr)
        return 1
    r = _reg.parse(todos_path.read_text())
    if not r.has_streams_section:
        print("No ## Streams section in CURRENT-TODOs.md.")
        return 0
    visible = r.streams if all_streams else [s for s in r.streams if s.status != "archived"]
    visible.sort(key=lambda s: (s.status != "active", s.last_touched), reverse=False)

    if not visible:
        print("No streams" + ("" if all_streams else " (archived hidden; use --all)") + ".")
        return 0
    for s in visible:
        claim = "unclaimed" if s.claim is None else f"claimed by {s.claim[:8]}…"
        print(f"  {s.slug:24s} {s.status:8s} {claim:24s} last: {s.last_touched}")
    return 0


def cmd_new(todos_path: Path, slug: str, name: str, today: str) -> int:
    if not todos_path.exists():
        print(f"No CURRENT-TODOs.md found at {todos_path}. "
              "Run /llm-dev:init-session first to create it.",
              file=sys.stderr)
        return 1
    if not SLUG_RE.match(slug):
        print(f"Invalid slug {slug!r}: must be kebab-case (a-z, 0-9, hyphens).",
              file=sys.stderr)
        return 2
    try:
        _reg.add_stream(todos_path, slug=slug, name=name, now_date=today)
    except _reg.RegistryError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Also add the prose section heading if not present
    text = todos_path.read_text()
    heading = f"\n## Stream: {slug}\n"
    if heading not in text:
        todos_path.write_text(text.rstrip() + "\n" + heading + "\n_(work here)_\n")
    print(f"Created stream `{slug}`.")
    return 0


def cmd_set_status(todos_path: Path, slug: str, status: str) -> int:
    try:
        _reg.set_status(todos_path, slug=slug, new_status=status)
    except _reg.RegistryError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"Stream `{slug}` status → {status}")
    return 0


def cmd_rename(todos_path: Path, old_slug: str, new_slug: str) -> int:
    if not SLUG_RE.match(new_slug):
        print(f"Invalid slug {new_slug!r}: must be kebab-case.", file=sys.stderr)
        return 2
    try:
        _reg.rename_stream(todos_path, old_slug=old_slug, new_slug=new_slug)
    except _reg.RegistryError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    # Update the per-stream prose heading if it exists
    text = todos_path.read_text()
    old_heading = f"## Stream: {old_slug}"
    new_heading = f"## Stream: {new_slug}"
    if old_heading in text:
        todos_path.write_text(text.replace(old_heading, new_heading))
    print(f"Renamed `{old_slug}` → `{new_slug}`")
    return 0


def cmd_join(todos_path: Path, slug: str, session_id: str, nnn: str,
             yyyymmdd: str, notes_dir: Path, now_iso: str) -> int:
    """Claim `slug` from inside an in-flight free session. Renames the
    in-flight session-notes file to include the slug."""
    result = _reg.claim(todos_path, slug=slug, session_id=session_id,
                        now_iso=now_iso, force=False)
    if not result.claimed:
        print(f"Stream `{slug}` is claimed by another session: "
              f"{result.previous_holder}", file=sys.stderr)
        return 1
    # Rename in-flight notes file
    old = notes_dir / f"{yyyymmdd}-{nnn}-session-notes.md"
    new = notes_dir / f"{yyyymmdd}-{nnn}-{slug}-session-notes.md"
    if old.exists() and not new.exists():
        old.rename(new)
        print(f"Renamed notes: {old.name} → {new.name}")
    print(f"Joined stream `{slug}`.")
    return 0


def cmd_release(todos_path: Path, slug: str, session_id: str,
                now_date: str) -> int:
    result = _reg.release(todos_path, slug=slug, session_id=session_id,
                          new_handoff=None, now_date=now_date)
    if result.stolen:
        print(f"Cannot release: stream is claimed by {result.actual_holder}.",
              file=sys.stderr)
        return 1
    print(f"Released stream `{slug}`.")
    return 0


def _detect_inflight_nnn(index_path: Path, session_id: str | None) -> str | None:
    """Resolve the current session's NNN from the transcript index.

    Matches the `### NNN - [In Progress]` entry whose `**Session**:` equals
    `session_id`. Concurrency-safe: it keys on the session id rather than
    assuming a single in-flight entry (multiple sessions in one project each
    add their own `[In Progress]` entry). Returns None when there is no match
    — callers should then require an explicit `--nnn`.
    """
    if not session_id or session_id == "unknown" or not index_path.exists():
        return None
    content = index_path.read_text(encoding="utf-8")
    # The tempered dot `(?:(?!###).)*?` keeps each match inside its own
    # entry: it never consumes across the next `###` header, so an entry
    # missing its `**Session**:` line can't borrow the following entry's id.
    for m in re.finditer(
        r"###\s+(\d{3})\s+-\s+\[In Progress\](?:(?!###).)*?\*\*Session\*\*:\s*(\S+)",
        content, re.DOTALL,
    ):
        if m.group(2).strip() == session_id:
            return m.group(1)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llm-dev:stream")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List streams")
    p_list.add_argument("--all", action="store_true", help="Include archived")

    p_new = sub.add_parser("new", help="Register a new stream")
    p_new.add_argument("slug")
    p_new.add_argument("name", nargs="?", default="")

    sub.add_parser("pause", help="Set status to paused").add_argument("slug")
    sub.add_parser("resume", help="Set status to active").add_argument("slug")
    sub.add_parser("archive", help="Set status to archived").add_argument("slug")
    p_rename = sub.add_parser("rename", help="Rename a stream's slug")
    p_rename.add_argument("old_slug")
    p_rename.add_argument("new_slug")

    p_join = sub.add_parser("join", help="Claim a stream mid-session")
    p_join.add_argument("slug")
    p_join.add_argument("--nnn", default=None,
                        help="Session number from /llm-dev:init-session "
                             "(e.g. 015). Used to find the in-flight notes file.")
    sub.add_parser("release", help="Release this session's stream claim")

    args = parser.parse_args(argv)
    todos = _find_todos_path(Path.cwd())
    today = datetime.now().strftime("%Y-%m-%d")

    if args.cmd == "list":
        return cmd_list(todos, all_streams=args.all)
    if args.cmd == "new":
        name = args.name or args.slug.replace("-", " ").title()
        return cmd_new(todos, slug=args.slug, name=name, today=today)
    if args.cmd == "pause":
        return cmd_set_status(todos, slug=args.slug, status="paused")
    if args.cmd == "resume":
        return cmd_set_status(todos, slug=args.slug, status="active")
    if args.cmd == "archive":
        return cmd_set_status(todos, slug=args.slug, status="archived")
    if args.cmd == "rename":
        return cmd_rename(todos, old_slug=args.old_slug, new_slug=args.new_slug)
    if args.cmd == "join":
        session_id = _session.find_session_id(Path.cwd())
        notes_dir = todos.parent / ".archive" / "session-notes"
        index_path = todos.parent / ".archive" / "transcripts" / "_index.md"
        nnn = args.nnn or _detect_inflight_nnn(index_path, session_id)
        if nnn is None:
            print("Could not determine the session number. Pass --nnn <N> "
                  "(the number shown by /llm-dev:init-session).",
                  file=sys.stderr)
            return 1
        return cmd_join(todos_path=todos, slug=args.slug, session_id=session_id,
                        nnn=nnn, yyyymmdd=datetime.now().strftime("%Y%m%d"),
                        notes_dir=notes_dir,
                        now_iso=datetime.now().strftime("%Y-%m-%dT%H:%MZ"))
    if args.cmd == "release":
        session_id = _session.find_session_id(Path.cwd())
        r = _reg.parse(todos.read_text())
        held = next((s for s in r.streams if s.claim == session_id), None)
        if held is None:
            print("This session holds no stream claim.", file=sys.stderr)
            return 1
        return cmd_release(todos_path=todos, slug=held.slug,
                           session_id=session_id,
                           now_date=datetime.now().strftime("%Y-%m-%d %H:%M"))
    parser.error(f"Unknown subcommand: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
