#!/usr/bin/env python3
"""stream.py — /llm-dev:stream subcommand handler.

Dispatches the subcommand verbs (list, new, join, release, pause, resume,
archive, rename). Operates on the per-stream JSON store under
`.archive/streams/<slug>.json` in the current project.
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _streams
import _archive
import _manifest
import _session


SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _resolve_archive(start: Path) -> Path | None:
    """Locate the .archive directory for either layout."""
    return _archive.resolve_archive_dir(start)


def cmd_list(archive_dir: Path, all_streams: bool) -> int:
    streams = _streams.list_streams(archive_dir)
    visible = streams if all_streams else [s for s in streams if s.status != "archived"]
    # Active first, then by last_touched.
    visible.sort(key=lambda s: (s.status != "active", s.last_touched), reverse=False)

    if not visible:
        print("No streams" + ("" if all_streams else " (archived hidden; use --all)") + ".")
        return 0
    for s in visible:
        claim = "unclaimed" if s.claim is None else f"claimed by {s.claim[:8]}…"
        print(f"  {s.slug:24s} {s.status:8s} {claim:24s} last: {s.last_touched}")
    return 0


def cmd_new(archive_dir: Path, slug: str, name: str, today: str) -> int:
    if not SLUG_RE.match(slug):
        print(f"Invalid slug {slug!r}: must be kebab-case (a-z, 0-9, hyphens).",
              file=sys.stderr)
        return 2
    try:
        _streams.add_stream(archive_dir, slug=slug, name=name, now_date=today)
    except _streams.StreamError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"Created stream `{slug}`.")
    return 0


def cmd_set_status(archive_dir: Path, slug: str, status: str) -> int:
    try:
        _streams.set_status(archive_dir, slug=slug, new_status=status)
    except _streams.StreamError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"Stream `{slug}` status → {status}")
    return 0


def cmd_rename(archive_dir: Path, old_slug: str, new_slug: str) -> int:
    if not SLUG_RE.match(new_slug):
        print(f"Invalid slug {new_slug!r}: must be kebab-case.", file=sys.stderr)
        return 2
    try:
        _streams.rename_stream(archive_dir, old_slug=old_slug, new_slug=new_slug)
    except _streams.StreamError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"Renamed `{old_slug}` → `{new_slug}`")
    return 0


def cmd_join(archive_dir: Path, slug: str, session_id: str, nnn: str,
             yyyymmdd: str, notes_dir: Path, now_iso: str) -> int:
    """Claim `slug` from inside an in-flight free session. Renames the
    in-flight session-notes file to include the slug."""
    try:
        result = _streams.claim(archive_dir, slug=slug, session_id=session_id,
                                now_iso=now_iso, force=False)
    except _streams.StreamError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
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


def cmd_release(archive_dir: Path, slug: str, session_id: str,
                now_date: str) -> int:
    result = _streams.release(archive_dir, slug=slug, session_id=session_id,
                              new_handoff=None, now_date=now_date)
    if result.stolen:
        print(f"Cannot release: stream is claimed by {result.actual_holder}.",
              file=sys.stderr)
        return 1
    print(f"Released stream `{slug}`.")
    return 0


def _detect_inflight_nnn(archive_dir: Path, session_id: str | None) -> str | None:
    """Resolve the current session's NNN from the manifest set.

    Matches the in-progress manifest whose `session_id` equals `session_id`,
    returning its zero-padded `number`. Concurrency-safe: it keys on the
    session id rather than assuming a single in-flight session. Returns None
    when there is no match — callers should then require an explicit `--nnn`.
    """
    if not session_id or session_id == "unknown":
        return None
    for m in _manifest.iter_manifests(archive_dir):
        if m.get("status") != "in-progress":
            continue
        if m.get("session_id") == session_id:
            n = m.get("number")
            if isinstance(n, int):
                return f"{n:03d}"
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
    p_join.add_argument("--session-id", default=None,
                        help="Harness session id (default: live Grok/Claude discovery)")
    p_release = sub.add_parser("release", help="Release this session's stream claim")
    p_release.add_argument("--session-id", default=None,
                           help="Harness session id (default: live Grok/Claude discovery)")

    args = parser.parse_args(argv)
    archive_dir = _resolve_archive(Path.cwd())
    if archive_dir is None:
        print("No .archive/ found in this project. "
              "Run /llm-dev:init-session first to set it up.", file=sys.stderr)
        return 1
    today = datetime.now().strftime("%Y-%m-%d")

    if args.cmd == "list":
        return cmd_list(archive_dir, all_streams=args.all)
    if args.cmd == "new":
        name = args.name or args.slug.replace("-", " ").title()
        return cmd_new(archive_dir, slug=args.slug, name=name, today=today)
    if args.cmd == "pause":
        return cmd_set_status(archive_dir, slug=args.slug, status="paused")
    if args.cmd == "resume":
        return cmd_set_status(archive_dir, slug=args.slug, status="active")
    if args.cmd == "archive":
        return cmd_set_status(archive_dir, slug=args.slug, status="archived")
    if args.cmd == "rename":
        return cmd_rename(archive_dir, old_slug=args.old_slug, new_slug=args.new_slug)
    if args.cmd == "join":
        session_id = args.session_id or _session.find_session_id(Path.cwd())
        notes_dir = archive_dir / "session-notes"
        nnn = args.nnn or _detect_inflight_nnn(archive_dir, session_id)
        if nnn is None:
            print("Could not determine the session number. Pass --nnn <N> "
                  "(the number shown by /llm-dev:init-session).",
                  file=sys.stderr)
            return 1
        return cmd_join(archive_dir=archive_dir, slug=args.slug, session_id=session_id,
                        nnn=nnn, yyyymmdd=datetime.now().strftime("%Y%m%d"),
                        notes_dir=notes_dir,
                        now_iso=datetime.now().strftime("%Y-%m-%dT%H:%MZ"))
    if args.cmd == "release":
        session_id = args.session_id or _session.find_session_id(Path.cwd())
        held = next((s for s in _streams.list_streams(archive_dir)
                     if s.claim == session_id), None)
        if held is None:
            print("This session holds no stream claim.", file=sys.stderr)
            return 1
        return cmd_release(archive_dir=archive_dir, slug=held.slug,
                           session_id=session_id,
                           now_date=datetime.now().strftime("%Y-%m-%d %H:%M"))
    parser.error(f"Unknown subcommand: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
