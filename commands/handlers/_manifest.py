"""Per-session manifest data format for unified-git-state.

A manifest is the source of truth for one session, stored at
`.archive/sessions/<dirname>/manifest.json` as canonical JSON. Live sessions
key the dir on `<YYYYMMDD>-<session-uuid>`; migrated historical sessions (no
UUID) key on `<conversation_id>`. The index generator reads manifest contents,
not dir names, so the two schemes coexist.

Stdlib only; Python 3.12+. Parsing tolerates malformed JSON without raising.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "manifest.json"


def canonical_json(obj) -> str:
    """Deterministic, byte-stable JSON: sorted keys, 2-space indent, UTF-8,
    trailing newline. The only serializer used for manifests and streams."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def normalize_ts(s: str | None) -> str | None:
    """Canonicalize a timestamp to ISO-8601 UTC `YYYY-MM-DDTHH:MM:SSZ`.

    Accepts a trailing `Z` and/or fractional seconds (3.11+ fromisoformat).
    A naive timestamp (no offset) is treated as UTC. Returns None for None and
    returns the input unchanged if it cannot be parsed (robust, never raises).
    """
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def new_manifest(
    *,
    session_id: str | None = None,
    number: int | None = None,
    title: str = "",
    stream: str | None = None,
    model: str = "",
    contributor: str = "",
    started_at: str | None = None,
    ended_at: str | None = None,
    status: str = "in-progress",
    conversation_id: str = "",
    date: str | None = None,
    transcript: str = "",
    notes: str = "",
    handoff: str = "",
) -> dict:
    """Build a fully-populated manifest dict with every key present.

    Timestamps (`started_at`, `ended_at`, `date`) are canonicalized. `date`
    defaults to `started_at` when not given.
    """
    started = normalize_ts(started_at)
    ended = normalize_ts(ended_at)
    d = normalize_ts(date) if date is not None else started
    return {
        "session_id": session_id,
        "number": number,
        "title": title,
        "stream": stream,
        "model": model,
        "contributor": contributor,
        "started_at": started or "",
        "ended_at": ended,
        "status": status,
        "conversation_id": conversation_id,
        "date": d or "",
        "files": {"transcript": transcript, "notes": notes, "handoff": handoff},
    }


def manifest_dirname(session_id: str | None, started_at: str | None,
                     conversation_id: str) -> str:
    """Directory name under sessions/. Live (UUID known): <YYYYMMDD>-<uuid>.
    Migrated (no UUID): <conversation_id>."""
    if session_id:
        ts = normalize_ts(started_at) or ""
        day = ts[:10].replace("-", "") if ts else "00000000"
        return f"{day}-{session_id}"
    return conversation_id


def write_manifest(archive_dir: Path, dirname: str, data: dict) -> Path:
    """Write `sessions/<dirname>/manifest.json` as canonical JSON. Returns the path."""
    archive_dir = Path(archive_dir)
    target = archive_dir / "sessions" / dirname / MANIFEST_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(canonical_json(data), encoding="utf-8")
    import os
    os.replace(tmp, target)
    return target


def read_manifest(path: Path) -> dict | None:
    """Read one manifest. Returns the dict, or None if missing / malformed
    (never raises — JSON is untrusted input)."""
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def iter_manifests(archive_dir: Path) -> list[dict]:
    """Scan `sessions/*/manifest.json`, returning the parsed dicts.

    Malformed manifests are skipped with a stderr warning (never raised), so a
    hostile manifest can't break consumers (index regen). Order is by dir name
    for determinism; callers re-sort by manifest contents.
    """
    import sys
    archive_dir = Path(archive_dir)
    sessions = archive_dir / "sessions"
    out: list[dict] = []
    if not sessions.is_dir():
        return out
    for d in sorted(p for p in sessions.iterdir() if p.is_dir()):
        mf = d / MANIFEST_NAME
        if not mf.exists():
            continue
        data = read_manifest(mf)
        if data is None:
            print(f"warning: skipping malformed manifest: {mf}", file=sys.stderr)
            continue
        out.append(data)
    return out
