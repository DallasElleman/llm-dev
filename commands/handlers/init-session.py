#!/usr/bin/env python3
"""init-session.py - Initialize a new LLM session for transcript tracking

Usage: python init-session.py [--model MODEL] [--user USERNAME] [--dry-run]
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


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
        return f"Claude Sonnet 4.5 ({model})"
    elif "opus" in model.lower():
        return f"Claude Opus 4.5 ({model})"
    elif "haiku" in model.lower():
        return f"Claude Haiku ({model})"
    else:
        return f"Claude ({model})"


def find_session_id() -> str:
    """Find the current Claude Code session ID from most recently modified JSONL file"""
    projects_dir = Path.home() / ".claude" / "projects"

    if not projects_dir.exists():
        return "unknown"

    try:
        # Find most recently modified .jsonl file (excluding agent- files)
        # Only consider files modified in last 5 minutes
        five_minutes_ago = datetime.now().timestamp() - 300

        recent_files = []
        for jsonl_file in projects_dir.glob("*.jsonl"):
            if jsonl_file.name.startswith("agent-"):
                continue

            if jsonl_file.stat().st_mtime >= five_minutes_ago:
                recent_files.append(jsonl_file)

        if recent_files:
            # Get the most recently modified
            latest = max(recent_files, key=lambda p: p.stat().st_mtime)
            return latest.stem
    except Exception:
        pass

    return "unknown"


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


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Initialize a new LLM session for transcript tracking"
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5-20250929",
        help="Model ID (default: claude-sonnet-4-5-20250929)"
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

    args = parser.parse_args()

    # Find the index file
    index_path = find_transcripts_index(Path.cwd())
    if index_path is None:
        print("Error: No .archive/transcripts/_index.md found in directory hierarchy",
              file=sys.stderr)
        print("Run /init-project to set up llm-dev infrastructure first",
              file=sys.stderr)
        sys.exit(1)

    # Get current conversation number
    try:
        current_num = get_current_number(index_path)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Calculate new number
    new_num = current_num + 1
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
    session_id = find_session_id()

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

    if args.dry_run:
        print()
        print("[DRY RUN MODE - No files will be modified]")
        print()
        print(f"Would update **Current**: {current_num} -> {new_num}")
        print()
        print("Would add entry:")
        print(entry)
        print()
        print("[DRY RUN COMPLETE - No changes were made]")
        return 0

    # Update the index
    try:
        update_index(index_path, new_num, entry)
    except Exception as e:
        print(f"Error updating index: {e}", file=sys.stderr)
        sys.exit(1)

    print()
    print(f"Session {new_num_padded} initialized successfully!")
    print()
    print("At session end, run /create-transcript to archive this conversation.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
