#!/usr/bin/env python3
from __future__ import annotations
"""init-session.py - Initialize a new LLM session for transcript tracking

Usage: python init-session.py [--model MODEL] [--user USERNAME] [--dry-run]
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _session
import _registry as _reg


def find_transcripts_index(start_dir: Path) -> Path | None:
    """Search up from current directory to find .archive/transcripts/_index.md"""
    current = start_dir.resolve()

    # Search up to root
    while True:
        index_path = current / ".archive" / "transcripts" / "_index.md"
        if index_path.exists():
            return index_path

        parent = current.parent
        if parent == current:  # Reached root
            break
        current = parent

    return None


def get_current_number(index_path: Path) -> int:
    """Extract current conversation number from index"""
    content = index_path.read_text(encoding="utf-8")

    # Look for **Current**: N pattern
    match = re.search(r'\*\*Current\*\*:\s*(\d+)', content)
    if not match:
        raise ValueError("Could not parse current conversation number from index\n"
                        "Expected format: **Current**: N")

    return int(match.group(1))


def get_git_username() -> str:
    """Get username from git config, fallback to 'User'"""
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "User"


def get_model_display_name(model: str) -> str:
    """Convert model ID to display name"""
    if "sonnet" in model.lower():
        return f"Claude Sonnet 4.6 ({model})"
    elif "opus" in model.lower():
        return f"Claude Opus 4.7 ({model})"
    elif "haiku" in model.lower():
        return f"Claude Haiku 4.5 ({model})"
    else:
        return f"Claude ({model})"


def create_placeholder_entry(
    num_padded: str,
    date_display: str,
    date_yyyymmdd: str,
    username: str,
    model_display: str,
    session_id: str
) -> str:
    """Create the placeholder entry text"""
    return f"""### {num_padded} - [In Progress]
**File**: `{date_yyyymmdd}-placeholder.json`
**Date**: {date_display}
**Participants**: {username}, {model_display}
**Session**: {session_id}
**Topics**: [To be determined]
**Outcomes**: [Session in progress]"""


def create_session_notes(
    index_path: Path,
    num_padded: str,
    date_yyyymmdd: str,
    date_display: str,
    username: str,
    model_display: str,
    session_id: str,
) -> Path:
    """Create a session-notes markdown file alongside transcripts.

    Returns the path to the created file. The file lives in
    `.archive/session-notes/` next to `.archive/transcripts/`.
    """
    notes_dir = index_path.parent.parent / "session-notes"
    notes_dir.mkdir(parents=True, exist_ok=True)

    notes_path = notes_dir / f"{date_yyyymmdd}-{num_padded}-session-notes.md"

    # Don't clobber existing notes if the same session is re-initialized
    if notes_path.exists():
        return notes_path

    template = f"""# Session {num_padded} Notes — {date_display}

**Participants**: {username}, {model_display}
**Session**: {session_id}

> Living document. Update throughout the session with what worked, lessons
> learned, mistakes made, assumptions proven wrong, and any other observations
> worth distilling later to improve performance on similar tasks and projects.
> Capture both wins and misses — validated approaches are just as much fuel
> for future improvement as corrections.

## What Worked

- _(none yet)_

## Lessons Learned

- _(none yet)_

## Mistakes Made

- _(none yet)_

## Assumptions Proven Wrong

- _(none yet)_

## Other Observations

- _(none yet)_
"""
    notes_path.write_text(template, encoding="utf-8")
    return notes_path


def find_latest_transcript(index_path: Path, prev_num_padded: str) -> Path | None:
    """Find the path to the previous session's transcript JSON.

    Looks up the entry by session number in the index, extracts the **File**:
    line, and returns the full path. Returns None if not found or missing.
    """
    if not index_path.exists():
        return None
    content = index_path.read_text(encoding="utf-8")
    # Match `### NNN - <title>` where title is NOT `[In Progress]`,
    # then capture the next **File**: <filename> line.
    pattern = (
        rf"### {re.escape(prev_num_padded)} - (?!\[In Progress\])[^\n]+\n"
        r"\*\*File\*\*:\s*([^\n]+)"
    )
    match = re.search(pattern, content)
    if not match:
        return None
    filename = match.group(1).strip().strip("`")
    transcript_path = index_path.parent / filename
    return transcript_path if transcript_path.exists() else None


def find_latest_in_dir(
    dir_path: Path, prev_num_padded: str, suffix: str
) -> Path | None:
    """Find the most recent file matching *-{NNN}-{suffix} in dir_path.

    Sorts by filename (filenames begin with YYYYMMDD, so lexical sort is
    chronological). Returns None if dir missing or no matches.
    """
    if not dir_path.is_dir():
        return None
    matches = sorted(dir_path.glob(f"*-{prev_num_padded}-{suffix}"))
    return matches[-1] if matches else None


def update_index(index_path: Path, new_num: int, entry: str) -> None:
    """Update index with new current number and placeholder entry"""
    content = index_path.read_text(encoding="utf-8")

    # 1. Update the Current field
    content = re.sub(
        r'\*\*Current\*\*:\s*\d+',
        f'**Current**: {new_num}',
        content
    )

    # 2. Find insertion point for new entry
    # Try different markers in order of preference
    markers = [
        r'^## Transcript Format',
        r'^### Examples and References',
        r'^## '  # Any ## heading after line 10
    ]

    insertion_line = None
    lines = content.split('\n')

    for marker in markers:
        for i, line in enumerate(lines):
            # Skip first 10 lines for generic ## heading search
            if marker == r'^## ' and i < 10:
                continue

            if re.match(marker, line):
                insertion_line = i
                break

        if insertion_line is not None:
            break

    # 3. Insert the entry
    if insertion_line is not None:
        # Insert before the marker line with blank lines around entry
        lines.insert(insertion_line, '')
        lines.insert(insertion_line, entry)
        lines.insert(insertion_line, '')
        content = '\n'.join(lines)
    else:
        # No marker found, append to end
        content = content.rstrip() + '\n\n' + entry + '\n'

    # Write back to file
    index_path.write_text(content, encoding="utf-8")


def max_numbered_file(directory: Path, suffix: str) -> int:
    """Find the highest NNN in filenames matching YYYYMMDD-NNN-<suffix> in directory.

    Returns 0 if no matches.
    """
    if not directory.is_dir():
        return 0
    pattern = re.compile(rf"^\d{{8}}-(\d{{3}})(?:-[^/]+)?-{re.escape(suffix)}$")
    best = 0
    for p in directory.iterdir():
        m = pattern.match(p.name)
        if m:
            best = max(best, int(m.group(1)))
    return best


def max_transcript_number(transcripts_dir: Path) -> int:
    """Find the highest NNN in transcript filenames (YYYYMMDD-NNN-<title>.json).

    Ignores legacy transcripts without NNN. Returns 0 if no matches.
    """
    if not transcripts_dir.is_dir():
        return 0
    pattern = re.compile(r"^\d{8}-(\d{3})-[^/]+\.json$")
    best = 0
    for p in transcripts_dir.iterdir():
        m = pattern.match(p.name)
        if m:
            best = max(best, int(m.group(1)))
    return best


def next_session_number(archive_dir: Path) -> int:
    """Compute the next session number from four sources, taking the max.

    Source 1: _index.md's `**Current**: N` (today's behavior + 1)
    Source 2: highest NNN in session-notes/ (+ 1)
    Source 3: highest NNN in session-handoff/ (+ 1)
    Source 4: highest NNN in transcripts/ (+ 1)

    Closes the May-3 collision-bug pattern where _index.md drifts behind
    the filesystem.
    """
    index_path = archive_dir / "transcripts" / "_index.md"
    try:
        idx_current = get_current_number(index_path)
    except (FileNotFoundError, ValueError):
        idx_current = 0

    candidates = [
        idx_current + 1,
        max_numbered_file(archive_dir / "session-notes", "session-notes.md") + 1,
        max_numbered_file(archive_dir / "session-handoff", "session-handoff.md") + 1,
        max_transcript_number(archive_dir / "transcripts") + 1,
    ]
    return max(candidates)


def ensure_streams_section(todos_path: Path, today: str) -> None:
    """If the file is missing or has no ## Streams section, seed it with a
    `main` stream. Idempotent — no-op if the section already exists."""
    if not todos_path.exists():
        todos_path.write_text(
            "# Current TODOs\n\n"
            "## Streams\n\n"
            + _reg.render_table([_reg.Stream(
                slug="main", name="Main", status="active",
                last_touched=today,
            )]) + "\n\n"
            "<!-- Add streams with: /llm-dev:stream new <slug> \"<name>\" -->\n\n"
            "## Stream: main\n\n"
            "_(work here; add per-stream prose as it accumulates)_\n"
        )
        return
    r = _reg.parse(todos_path.read_text())
    if r.has_streams_section:
        return
    # has_streams_section remains False — update_table_in_text will append
    # the heading + table block automatically.
    r.streams = [_reg.Stream(slug="main", name="Main", status="active",
                             last_touched=today)]
    _reg.optimistic_write(todos_path, r)


def _derive_next_action_preview(handoff_path_str: str | None,
                                 project_root: Path) -> str:
    """Read the linked handoff and extract the first sentence of the
    'First Action for Next Session' section. Returns '(no prior handoff yet)'
    if the file doesn't exist or the section isn't found."""
    if not handoff_path_str:
        return "(no prior handoff yet)"
    p = project_root / handoff_path_str
    if not p.exists():
        return "(no prior handoff yet)"
    text = p.read_text(encoding="utf-8")
    m = re.search(r"##?\s*First Action for Next Session\s*\n+(.+?)(?:\n\n|\Z)",
                  text, re.DOTALL | re.IGNORECASE)
    if not m:
        return "(no First Action section in handoff)"
    first = m.group(1).strip().split(".")[0].strip()
    return (first[:120] + "…") if len(first) > 120 else first


def pick_stream_interactively(todos_path: Path) -> str | None:
    """Print the registry and prompt the user. Returns selected slug or None
    on skip. Default-selection rules per the design spec:
    - exactly one `active` stream → Enter selects it
    - 0 or 2+ active streams → no default, user must type a choice
    """
    r = _reg.parse(todos_path.read_text())
    active = [s for s in r.streams if s.status == "active"]
    visible = [s for s in r.streams if s.status != "archived"]

    project_root = todos_path.parent
    print("\nStreams in this project:")
    default_idx: int | None = None
    if len(active) == 1:
        default_idx = visible.index(active[0]) + 1

    for i, s in enumerate(visible, start=1):
        marker = " (default)" if default_idx == i else ""
        claim_disp = "unclaimed" if s.claim is None else f"CLAIMED by {s.claim[:8]}…"
        preview = _derive_next_action_preview(s.last_handoff, project_root)
        print(f"  {i}. {s.slug:20s} {s.status:8s} {claim_disp}")
        print(f"     → {preview}{marker}")

    suffix = f" [default: {default_idx}]" if default_idx else ""
    prompt = f"\nWhich stream? [1-{len(visible)}, 'new <slug>', or 's' to skip]{suffix}: "
    try:
        raw = input(prompt).strip()
    except EOFError:
        raw = ""

    if raw == "" and default_idx is not None:
        return visible[default_idx - 1].slug
    if raw.lower() == "s":
        return None
    if raw.startswith("new "):
        slug = raw[4:].strip()
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", slug):
            print(f"Invalid slug {slug!r}: must be kebab-case (a-z, 0-9, -).")
            return pick_stream_interactively(todos_path)
        try:
            _reg.add_stream(todos_path, slug=slug, name=slug.replace("-", " ").title(),
                            now_date=datetime.now().strftime("%Y-%m-%d"))
            return slug
        except _reg.RegistryError as e:
            print(f"Could not create stream: {e}")
            return pick_stream_interactively(todos_path)
    if raw.isdigit() and 1 <= int(raw) <= len(visible):
        return visible[int(raw) - 1].slug
    print(f"Unrecognized input: {raw!r}")
    return pick_stream_interactively(todos_path)


def rename_notes_for_claim(notes_path: Path | None, slug: str) -> Path | None:
    """Rename an in-flight session-notes file to include the stream slug.

    Called from init-session main() after a successful claim. The notes file
    was created with the flat name YYYYMMDD-NNN-session-notes.md before the
    claim was processed; this renames it to YYYYMMDD-NNN-<slug>-session-notes.md
    so end-session can find it via build_session_doc_filename.

    Returns the new path (or the original path if no rename happened).
    """
    if notes_path is None:
        return None
    expected_suffix = "-session-notes.md"
    if not notes_path.name.endswith(expected_suffix):
        return notes_path
    stem = notes_path.name[:-len(expected_suffix)]
    # If the slug is already in the name, no-op
    if stem.endswith(f"-{slug}"):
        return notes_path
    new_name = f"{stem}-{slug}-session-notes.md"
    new_path = notes_path.parent / new_name
    if notes_path.exists() and not new_path.exists():
        notes_path.rename(new_path)
        return new_path
    return notes_path


def attempt_claim(todos_path: Path, slug: str, session_id: str, now_iso: str,
                  force: bool) -> bool:
    """Try to claim `slug`. If already claimed by another session, surface
    evidence and prompt the user to confirm reclaim. Returns True on
    successful claim, False if the user declined or the claim couldn't be
    made."""
    result = _reg.claim(todos_path, slug=slug, session_id=session_id,
                        now_iso=now_iso, force=False)
    if result.claimed:
        return True

    # Contention path
    r = _reg.parse(todos_path.read_text())
    stream = r.get(slug)
    holder = result.previous_holder or "unknown"
    title = _lookup_session_title(holder)
    notes_path = _lookup_notes_file_for_holder(todos_path.parent, slug, holder)

    print()
    print(f"WARNING: Stream `{slug}` is claimed by:")
    print(f"    Session ID:  {holder}")
    print(f"    Title:       {title or '(no /rename event found)'}")
    print(f"    Claimed at:  {stream.since}")
    if notes_path:
        print(f"    Notes:       {notes_path}")
        try:
            mtime = notes_path.stat().st_mtime
            from datetime import datetime as _dt
            print(f"    Last edited: {_dt.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')}")
        except OSError:
            pass
    print()
    print("Inspect the notes and the Claude Code session title before reclaiming.")
    print("Conventions: `open-` prefix → prior session hasn't run /end-session.")
    print("             `closed-` prefix → prior session ended cleanly; if you see")
    print("             `closed-` here, the registry is out of sync — reclaim flags it.")
    print()
    try:
        ans = input("Reclaim? [y/N]: ").strip().lower()
    except EOFError:
        ans = "n"
    if ans != "y":
        return False
    result = _reg.claim(todos_path, slug=slug, session_id=session_id,
                        now_iso=now_iso, force=True)
    return result.claimed


def _lookup_session_title(session_id: str) -> str | None:
    """Best-effort title lookup. Searches ~/.claude/projects/*/<id>.jsonl."""
    if session_id == "unknown":
        return None
    p = _session.PROJECTS_DIR
    if not p.exists():
        return None
    for jsonl in p.rglob(f"{session_id}.jsonl"):
        return _session.find_session_title(jsonl)
    return None


def _lookup_notes_file_for_holder(project_root: Path, slug: str,
                                  holder: str) -> Path | None:
    """Find the in-flight session-notes file for the holder of `slug`."""
    notes_dir = project_root / ".archive" / "session-notes"
    if not notes_dir.exists():
        return None
    # Slug-bearing files first
    for p in sorted(notes_dir.glob(f"*-{slug}-session-notes.md"), reverse=True):
        return p
    return None


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Initialize a new LLM session for transcript tracking"
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Model ID (default: claude-sonnet-4-6)"
    )
    parser.add_argument(
        "--user",
        default="",
        help="Username for the session (default: from git config)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument("--stream", default=None,
                        help="Claim this stream non-interactively")
    parser.add_argument("--no-stream", action="store_true",
                        help="Start a free session without prompting")

    args = parser.parse_args()

    # Find the index file
    index_path = find_transcripts_index(Path.cwd())
    if index_path is None:
        print("Error: No .archive/transcripts/_index.md found in directory hierarchy",
              file=sys.stderr)
        print("Run /init-project to set up llm-dev infrastructure first",
              file=sys.stderr)
        sys.exit(1)

    # Get current conversation number and compute next via cross-check
    try:
        current_num = get_current_number(index_path)
        archive_dir = index_path.parent.parent
        new_num = next_session_number(archive_dir)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    new_num_padded = f"{new_num:03d}"

    # Format dates
    now = datetime.now()
    date_display = now.strftime("%B %-d, %Y") if sys.platform != "win32" else now.strftime("%B %d, %Y").replace(" 0", " ")
    date_yyyymmdd = now.strftime("%Y%m%d")

    # Get username
    username = args.user if args.user else get_git_username()

    # Get model display name
    model_display = get_model_display_name(args.model)

    # Get session ID
    session_id = _session.find_session_id()
    if session_id == "unknown":
        import os as _os
        session_id = f"claude-{new_num_padded}-{_os.urandom(3).hex()}"

    # Create placeholder entry
    entry = create_placeholder_entry(
        new_num_padded,
        date_display,
        date_yyyymmdd,
        username,
        model_display,
        session_id
    )

    # Print status
    print(f"Current conversation number: {current_num}")
    print(f"Initializing conversation: {new_num_padded}")

    notes_dir_preview = index_path.parent.parent / "session-notes"
    notes_path_preview = notes_dir_preview / f"{date_yyyymmdd}-{new_num_padded}-session-notes.md"

    # Resolve prior-session context for the next session to load
    prev_num = current_num
    prev_num_padded = f"{prev_num:03d}"
    if prev_num > 0:
        prior_transcript = find_latest_transcript(index_path, prev_num_padded)
        prior_notes = find_latest_in_dir(
            archive_dir / "session-notes", prev_num_padded, "session-notes.md"
        )
        prior_handoff = find_latest_in_dir(
            archive_dir / "session-handoff", prev_num_padded, "session-handoff.md"
        )
    else:
        prior_transcript = prior_notes = prior_handoff = None

    if args.dry_run:
        print()
        print("[DRY RUN MODE - No files will be modified]")
        print()
        print(f"Would update **Current**: {current_num} -> {new_num}")
        print()
        print("Would add entry:")
        print(entry)
        print()
        print(f"Would create session notes: {notes_path_preview}")
        print()
        print("Prior-session context that would be surfaced:")
        print(f"  Transcript: {prior_transcript or '(none found)'}")
        print(f"  Notes:      {prior_notes or '(none found)'}")
        print(f"  Handoff:    {prior_handoff or '(none found)'}")
        print()
        print("[DRY RUN COMPLETE - No changes were made]")
        return 0

    # Update the index
    try:
        update_index(index_path, new_num, entry)
    except Exception as e:
        print(f"Error updating index: {e}", file=sys.stderr)
        sys.exit(1)

    # Create session notes file for in-flight learnings capture
    try:
        notes_path = create_session_notes(
            index_path,
            new_num_padded,
            date_yyyymmdd,
            date_display,
            username,
            model_display,
            session_id,
        )
    except Exception as e:
        print(f"Warning: failed to create session notes file: {e}", file=sys.stderr)
        notes_path = None

    # Stream selection
    todos_path = archive_dir.parent / "CURRENT-TODOs.md"
    ensure_streams_section(todos_path, today=now.strftime("%Y-%m-%d"))

    selected_slug: str | None = None
    if args.no_stream:
        selected_slug = None
    elif args.stream:
        if not attempt_claim(todos_path, slug=args.stream, session_id=session_id,
                             now_iso=datetime.now().strftime("%Y-%m-%dT%H:%MZ"),
                             force=False):
            print(f"\nAborted: could not claim stream `{args.stream}`.")
            return 1
        selected_slug = args.stream
    else:
        selected_slug = pick_stream_interactively(todos_path)
        if selected_slug:
            if not attempt_claim(todos_path, slug=selected_slug, session_id=session_id,
                                 now_iso=datetime.now().strftime("%Y-%m-%dT%H:%MZ"),
                                 force=False):
                print(f"\nAborted: could not claim stream `{selected_slug}`.")
                return 1

    if selected_slug:
        notes_path = rename_notes_for_claim(notes_path, selected_slug)
        print(f"Claimed stream: {selected_slug}")
    else:
        print("Starting session with no stream. Run /llm-dev:stream join <slug> "
              "to attach later.")

    print()
    print(f"Session {new_num_padded} initialized successfully!")
    if notes_path is not None:
        print(f"Session notes: {notes_path}")
        print("Update this file throughout the session with lessons, mistakes,")
        print("and assumptions proven wrong — it will be distilled later.")

    # Surface prior-session context paths for Claude to Read after init
    print()
    if prev_num > 0:
        print("Prior-session context (read these to pick up the thread):")
        print(f"  Transcript: {prior_transcript or '(none found)'}")
        print(f"  Notes:      {prior_notes or '(none found)'}")
        print(f"  Handoff:    {prior_handoff or '(none found)'}")
        if prior_handoff is not None:
            print()
            print(
                "Follow the First Action instruction inside the handoff: greet the "
                "user, relay your understanding, and ask before acting."
            )
    else:
        print("No prior session detected — this is session 001.")

    print()
    print("At session end, run /end-session to archive this conversation.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
