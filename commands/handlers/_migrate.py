"""One-shot, reversible archive FORMAT migrator for unified-git-state.

Converts the legacy archive — a markdown `_index.md` (### NNN entries) plus a
`## Streams` table in CURRENT-TODOs.md — into the new format: per-session
`sessions/<conversation_id>/manifest.json` + per-stream `streams/<slug>.json`,
then regenerates the derived `_index.md`.

Migration is a JOIN: the index entry is authoritative for number, ordering, and
the **File** name; each entry is enriched from its referenced transcript JSON.
No transcript stores a session UUID, so migrated manifests get session_id=null
and identity = conversation_id. Index-only entries (missing JSON) synthesize a
minimal manifest from the markdown alone.

Contract: `--dry-run` writes nothing; applying is idempotent (re-run is a
no-op); reversible (only adds files + one CURRENT-TODOs edit — revert via
`git checkout`). Parsing is robust: a bad entry is skipped-with-warning, never
corrupts the archive.

Stdlib only; Python 3.12+.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import _index_gen
import _manifest
import _streams

# `## Streams` heading + everything up to the next `## ` heading (or EOF).
_STREAMS_BLOCK_RE = re.compile(
    r"(?ms)^## Streams[ \t]*\n.*?(?=^## |\Z)")

_ENTRY_RE = re.compile(
    r"### (?P<num>\d+) - (?P<title>[^\n]+)\n"
    r"\*\*File\*\*:\s*(?P<file>[^\n]+)"
    r"(?:\n\*\*Date\*\*:\s*(?P<date>[^\n]+))?",
)

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}


def _parse_md_date(s: str | None) -> str | None:
    """Parse an index `**Date**: Month D, YYYY` into ISO-8601 UTC, or None."""
    if not s:
        return None
    m = re.match(r"\s*([A-Za-z]+)\s+(\d+),\s+(\d{4})", s.strip())
    if not m:
        return _manifest.normalize_ts(s.strip())
    mon = _MONTHS.get(m.group(1).lower())
    if not mon:
        return None
    return f"{int(m.group(3)):04d}-{mon:02d}-{int(m.group(2)):02d}T00:00:00Z"


def _stream_from_conversation_id(cid: str, known_slugs: tuple[str, ...] = ()) -> str | None:
    """Derive the stream slug from `YYYYMMDD-NNN-<stream>-<title>`.

    Stream slugs may contain hyphens (e.g. `unified-git-state`), so the slug↔title
    boundary is ambiguous from the id alone. Prefer matching against the KNOWN
    stream slugs (longest match wins); only fall back to the first hyphen-delimited
    segment for an unrecognized slug. Pre-stream ids (`YYYYMMDD-title`, no NNN) → None.
    """
    m = re.match(r"^\d{8}-\d{3}-(.+)$", cid)
    if not m:
        return None
    rest = m.group(1)  # "<slug>-<title…>"
    matches = [s for s in known_slugs if rest == s or rest.startswith(s + "-")]
    if matches:
        return max(matches, key=len)
    seg = re.match(r"([a-z0-9][a-z0-9-]*?)-", rest)  # best-effort for unknown slugs
    return seg.group(1) if seg else rest


def _known_stream_slugs(todos_path: Path) -> tuple[str, ...]:
    """Stream slugs from the legacy `## Streams` table, for manifest attribution.
    Empty tuple if the file is absent or the table is malformed."""
    import _registry as _reg
    try:
        reg = _reg.parse(Path(todos_path).read_text(encoding="utf-8"))
    except (OSError, _reg.RegistryError):
        return ()
    return tuple(s.slug for s in reg.streams)


def _doc_rel(archive_dir: Path, subdir: str, day: str, number: int,
             slug: str | None, suffix: str) -> str:
    """Return `<subdir>/<file>` for the conventional session doc if it exists,
    else ''. Convention: `YYYYMMDD-NNN[-slug]-<suffix>`."""
    if not day:
        return ""
    nnn = f"{number:03d}"
    name = f"{day}-{nnn}-{slug}-{suffix}" if slug else f"{day}-{nnn}-{suffix}"
    return f"{subdir}/{name}" if (Path(archive_dir) / subdir / name).exists() else ""


def _participant_model(participants: list) -> str:
    for p in participants or []:
        if p.get("role") == "assistant" and p.get("model"):
            return p["model"]
    return ""


def _participant_contributor(participants: list) -> str:
    for p in participants or []:
        if p.get("role") == "user":
            return p.get("github") or p.get("name") or ""
    return ""


def _entry_to_manifest(entry: dict, transcripts_dir: Path, archive_dir: Path,
                       known_slugs: tuple[str, ...] = ()) -> dict | None:
    """Build one manifest dict from an index entry, enriched from its JSON."""
    filename = entry["file"].strip().strip("`")
    # The derived `_index.md` renders **File** as `transcripts/<name>.json`,
    # whereas the legacy index used a bare `<name>.json`. Normalize to the bare
    # name so re-running over an already-derived index stays idempotent.
    if filename.startswith("transcripts/"):
        filename = filename[len("transcripts/"):]
    cid = filename[:-5] if filename.endswith(".json") else filename
    json_path = transcripts_dir / filename

    title = entry["title"].strip()
    number = int(entry["num"])
    md_date = _parse_md_date(entry.get("date"))
    started = ended = md_date
    model = contributor = ""

    data = None
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print(f"warning: unreadable transcript {json_path}; using markdown only",
                  file=sys.stderr)
    if data is not None:
        cid = data.get("conversation_id") or cid
        title = (data.get("summary") or {}).get("title") or title
        started = data.get("started_at") or data.get("date") or md_date
        ended = data.get("ended_at") or data.get("date") or md_date
        model = _participant_model(data.get("participants"))
        contributor = _participant_contributor(data.get("participants"))

    stream = _stream_from_conversation_id(cid, known_slugs)
    day = (started or "")[:10].replace("-", "")
    return _manifest.new_manifest(
        session_id=None,            # no UUID exists for any historical session
        number=number,
        title=title,
        stream=stream,
        model=model,
        contributor=contributor,
        started_at=started,
        ended_at=ended,
        status="complete",          # all migrated sessions are historical/done
        conversation_id=cid,
        date=started,
        transcript=f"transcripts/{filename}",
        notes=_doc_rel(archive_dir, "session-notes", day, number, stream, "session-notes.md"),
        handoff=_doc_rel(archive_dir, "session-handoff", day, number, stream, "session-handoff.md"),
    )


def _migrate_streams(archive_dir: Path, todos_path: Path,
                     dry_run: bool) -> int:
    """Write streams/*.json from the `## Streams` table, then remove the block.
    Returns the number of streams found. No-op for streams already present."""
    import _registry as _reg
    text = todos_path.read_text(encoding="utf-8")
    try:
        reg = _reg.parse(text)
    except _reg.RegistryError as e:
        # A malformed ## Streams table must not abort the whole migration —
        # the manifest migration (already done by the caller) is independent.
        print(f"warning: skipping ## Streams migration (malformed table): {e}",
              file=sys.stderr)
        return 0
    count = len(reg.streams)
    if dry_run:
        return count
    for s in reg.streams:
        if _streams.read_stream(archive_dir, s.slug) is not None:
            continue
        _streams.write_stream(archive_dir, _streams.Stream(
            slug=s.slug, name=s.name, status=s.status, claim=s.claim,
            since=s.since, last_touched=s.last_touched,
            last_handoff=s.last_handoff, branch=None, worktree=None))
    # Remove the `## Streams` block (idempotent: only if present).
    if _STREAMS_BLOCK_RE.search(text):
        new_text = _STREAMS_BLOCK_RE.sub("", text, count=1)
        new_text = re.sub(r"\n{3,}", "\n\n", new_text)
        tmp = todos_path.with_suffix(todos_path.suffix + ".tmp")
        tmp.write_text(new_text, encoding="utf-8")
        import os
        os.replace(tmp, todos_path)
    return count


def migrate(archive_dir: Path, todos_path: Path | None, *,
            dry_run: bool = True) -> dict:
    """Migrate the legacy archive to the new format.

    Returns a report dict: {dry_run, manifests, manifests_written, streams,
    warnings}. `manifests` = entries found; `manifests_written` = newly created
    (0 on an idempotent re-run).
    """
    archive_dir = Path(archive_dir)
    transcripts_dir = archive_dir / "transcripts"
    index_path = transcripts_dir / "_index.md"
    report: dict = {"dry_run": dry_run, "manifests": 0,
                    "manifests_written": 0, "streams": 0, "warnings": []}

    if not index_path.exists():
        report["warnings"].append(f"no index at {index_path}")
        return report

    # Known stream slugs up front, so hyphenated slugs (e.g. unified-git-state)
    # are attributed correctly rather than truncated at the first hyphen.
    known_slugs = (_known_stream_slugs(Path(todos_path))
                   if todos_path is not None and Path(todos_path).exists() else ())

    text = index_path.read_text(encoding="utf-8")
    entries = [m.groupdict() for m in _ENTRY_RE.finditer(text)]
    report["manifests"] = len(entries)

    for entry in entries:
        manifest = _entry_to_manifest(entry, transcripts_dir, archive_dir, known_slugs)
        if manifest is None:
            report["warnings"].append(f"skipped entry: {entry.get('title')}")
            continue
        dirname = _manifest.manifest_dirname(
            None, manifest["started_at"], manifest["conversation_id"])
        target = archive_dir / "sessions" / dirname / "manifest.json"
        if dry_run:
            continue
        if target.exists():
            continue  # idempotent: leave existing manifest untouched
        _manifest.write_manifest(archive_dir, dirname, manifest)
        report["manifests_written"] += 1

    if todos_path is not None and Path(todos_path).exists():
        report["streams"] = _migrate_streams(archive_dir, Path(todos_path), dry_run)

    if not dry_run:
        _index_gen.write_index(archive_dir)

    return report
