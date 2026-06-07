"""Per-file JSON stream store for unified-git-state.

Replaces the markdown `## Streams` table (see _registry) with one JSON file per
stream at `.archive/streams/<slug>.json`. Each file is disjoint, so
different-stream claims never conflict; same-stream contention is handled by the
same optimistic-write concurrency as _registry (captured SHA256 vs on-disk
SHA256, atomic tempfile + os.replace). The Stream shape matches _registry plus
`branch` and `worktree`.

Stdlib only; Python 3.12+. JSON parsing is untrusted input — never raises on a
malformed file; list_streams skips-with-warning.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

VALID_STATUSES = ("active", "paused", "archived")
_FIELDS = ("slug", "name", "status", "claim", "since", "last_touched",
           "last_handoff", "branch", "worktree")


class StreamError(ValueError):
    """Raised on unknown slugs, duplicate slugs, or write-time drift."""


@dataclass
class Stream:
    slug: str
    name: str
    status: str
    claim: str | None = None
    since: str | None = None
    last_touched: str = ""
    last_handoff: str | None = None
    branch: str | None = None
    worktree: str | None = None


@dataclass
class ClaimResult:
    claimed: bool
    previous_holder: str | None = None


@dataclass
class ReleaseResult:
    released: bool
    stolen: bool = False
    actual_holder: str | None = None


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical(obj: dict) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def streams_dir(archive_dir: Path) -> Path:
    return Path(archive_dir) / "streams"


def stream_path(archive_dir: Path, slug: str) -> Path:
    return streams_dir(archive_dir) / f"{slug}.json"


def _from_dict(d: dict) -> Stream:
    return Stream(**{k: d.get(k) for k in _FIELDS})


def read_stream(archive_dir: Path, slug: str) -> Stream | None:
    """Read one stream, or None if missing / malformed (never raises)."""
    p = stream_path(archive_dir, slug)
    try:
        return _from_dict(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def write_stream(archive_dir: Path, stream: Stream, *,
                 expected_sha: str | None = None) -> None:
    """Atomically write one stream file.

    If `expected_sha` is given and the on-disk file's SHA256 differs (it changed
    since the caller read it), raise StreamError so the caller can re-read and
    retry. Mirrors _registry.optimistic_write, per-file.
    """
    p = stream_path(archive_dir, stream.slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    if expected_sha is not None and p.exists():
        actual = _sha256_bytes(p.read_bytes())
        if actual != expected_sha:
            raise StreamError(
                f"stream {stream.slug!r} changed between read and write; retry"
            )
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(_canonical(asdict(stream)), encoding="utf-8")
    os.replace(tmp, p)


def list_streams(archive_dir: Path) -> list[Stream]:
    """All streams, sorted by slug. Malformed files skipped-with-warning."""
    sd = streams_dir(archive_dir)
    out: list[Stream] = []
    if not sd.is_dir():
        return out
    for f in sorted(sd.glob("*.json")):
        try:
            out.append(_from_dict(json.loads(f.read_text(encoding="utf-8"))))
        except (OSError, ValueError, TypeError):
            print(f"warning: skipping malformed stream: {f}", file=sys.stderr)
    return out


def add_stream(archive_dir: Path, slug: str, name: str, now_date: str,
               status: str = "active", branch: str | None = None,
               worktree: str | None = None) -> Stream:
    """Create a new stream file. Raises if the slug already exists."""
    if stream_path(archive_dir, slug).exists():
        raise StreamError(f"stream slug already exists: {slug!r}")
    s = Stream(slug=slug, name=name, status=status, claim=None, since=None,
               last_touched=now_date, last_handoff=None,
               branch=branch, worktree=worktree)
    write_stream(archive_dir, s)
    return s


def _read_with_sha(archive_dir: Path, slug: str) -> tuple[Stream, str]:
    p = stream_path(archive_dir, slug)
    if not p.exists():
        raise StreamError(f"unknown stream slug: {slug!r}")
    raw = p.read_bytes()
    return _from_dict(json.loads(raw)), _sha256_bytes(raw)


def claim(archive_dir: Path, slug: str, session_id: str, now_iso: str,
          force: bool = False) -> ClaimResult:
    """Claim `slug` for `session_id`. Optimistic, retry-on-drift. Refuses a
    claim held by another session unless force=True."""
    while True:
        s, sha = _read_with_sha(archive_dir, slug)
        if s.claim is not None and s.claim != session_id and not force:
            return ClaimResult(claimed=False, previous_holder=s.claim)
        previous = s.claim if s.claim != session_id else None
        s.claim = session_id
        s.since = now_iso
        try:
            write_stream(archive_dir, s, expected_sha=sha)
        except StreamError:
            continue  # drift: re-read and retry
        return ClaimResult(claimed=True, previous_holder=previous)


def release(archive_dir: Path, slug: str, session_id: str,
            new_handoff: str | None, now_date: str) -> ReleaseResult:
    """Release `slug` if held by `session_id`. If stolen, leave it and report."""
    while True:
        s, sha = _read_with_sha(archive_dir, slug)
        if s.claim is not None and s.claim != session_id:
            return ReleaseResult(released=False, stolen=True, actual_holder=s.claim)
        s.claim = None
        s.since = None
        s.last_touched = now_date
        if new_handoff is not None:
            s.last_handoff = new_handoff
        try:
            write_stream(archive_dir, s, expected_sha=sha)
        except StreamError:
            continue
        return ReleaseResult(released=True)


def set_status(archive_dir: Path, slug: str, new_status: str) -> None:
    """Change status without touching the claim. Refuses to archive a claimed stream."""
    while True:
        s, sha = _read_with_sha(archive_dir, slug)
        if s.claim is not None and new_status == "archived":
            raise StreamError(f"cannot archive a claimed stream ({slug}); release first")
        s.status = new_status
        try:
            write_stream(archive_dir, s, expected_sha=sha)
        except StreamError:
            continue
        return


def rename_stream(archive_dir: Path, old_slug: str, new_slug: str) -> None:
    """Rename a stream (file + slug field). Refuses if claimed or target exists."""
    s, _ = _read_with_sha(archive_dir, old_slug)
    if stream_path(archive_dir, new_slug).exists():
        raise StreamError(f"target slug already exists: {new_slug!r}")
    if s.claim is not None:
        raise StreamError(f"cannot rename a claimed stream ({old_slug}); release first")
    s.slug = new_slug
    write_stream(archive_dir, s)
    os.remove(stream_path(archive_dir, old_slug))
