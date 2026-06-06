"""Registry module — parses and writes the ## Streams table in CURRENT-TODOs.md.

The registry is the single source of truth for stream lifecycle state within
a project. It lives in CURRENT-TODOs.md as a markdown table under a
`## Streams` heading. Per-stream prose sections (`## Stream: <slug>`) live
below; this module does not parse those — they are pure human/Claude content.

This module is pure data manipulation: it parses markdown text into typed
objects and serializes typed objects back to markdown. File I/O and atomic
write semantics live in callers (see optimistic_write in same module).
"""
import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


VALID_STATUSES = ("active", "paused", "archived")
STREAM_HEADING_RE = re.compile(r'^## Streams[ \t]*$', re.MULTILINE)
NEXT_HEADING_RE = re.compile(r'^## ', re.MULTILINE)
EXPECTED_COLUMNS = (
    "Slug", "Name", "Status", "Claim", "Since", "Last Touched", "Last Handoff",
)


class RegistryError(ValueError):
    """Raised when the registry table is malformed or violates invariants."""


@dataclass
class Stream:
    slug: str
    name: str
    status: str
    claim: str | None = None             # session UUID or None when unclaimed
    since: str | None = None             # ISO-8601 string or None
    last_touched: str = ""                  # YYYY-MM-DD or YYYY-MM-DD HH:MM
    last_handoff: str | None = None      # project-relative path or None


@dataclass
class Registry:
    has_streams_section: bool = False
    streams: list[Stream] = field(default_factory=list)
    # Byte offsets of the streams table block (for surgical rewrites).
    # Defined when has_streams_section is True.
    table_start: int = -1
    table_end: int = -1
    source: str = ""

    def get(self, slug: str) -> Stream | None:
        for s in self.streams:
            if s.slug == slug:
                return s
        return None


def _parse_cell(cell: str) -> str | None:
    """Convert a table cell to its logical value: '—' or empty → None."""
    v = cell.strip()
    if v in ("", "—", "-", "unclaimed"):
        # 'unclaimed' is only used in the Claim column to mean None.
        # '—'/'-' and empty mean None universally.
        if v == "unclaimed":
            return None
        if v in ("—", "-", ""):
            return None
    return v


def parse(text: str) -> Registry:
    """Parse a CURRENT-TODOs.md document into a Registry.

    Always succeeds if there is no ## Streams section (returns empty registry).
    Raises RegistryError if the section exists but the table is malformed.
    """
    m = STREAM_HEADING_RE.search(text)
    if m is None:
        return Registry(has_streams_section=False, source=text)

    section_start = m.end()
    next_h = NEXT_HEADING_RE.search(text, pos=m.end())
    section_end = next_h.start() if next_h else len(text)
    section = text[section_start:section_end]

    # Find the table inside the section
    lines = section.splitlines()
    # Locate first line starting with '|'
    table_lines = []
    for line in lines:
        s = line.strip()
        if s.startswith("|"):
            table_lines.append(s)
        elif table_lines:
            # Table ended (blank line or other content after we saw rows)
            break

    if not table_lines:
        # Section heading present, no table → empty but valid
        return Registry(
            has_streams_section=True,
            table_start=section_start,
            table_end=section_end,
            source=text,
        )

    if len(table_lines) < 2:
        raise RegistryError(
            "## Streams section must contain a markdown table with header + separator rows."
        )

    header_cells = [c.strip() for c in table_lines[0].strip("|").split("|")]
    if tuple(header_cells) != EXPECTED_COLUMNS:
        raise RegistryError(
            f"## Streams table columns do not match expected schema.\n"
            f"  Expected: {EXPECTED_COLUMNS}\n"
            f"  Got:      {tuple(header_cells)}"
        )

    streams: list[Stream] = []
    seen_slugs = set()
    for row_idx, row in enumerate(table_lines[2:], start=3):  # skip header + separator
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) != len(EXPECTED_COLUMNS):
            raise RegistryError(
                f"## Streams table row {row_idx} has {len(cells)} columns, "
                f"expected {len(EXPECTED_COLUMNS)}: {row!r}"
            )
        slug, name, status, claim, since, last_touched, last_handoff = cells
        if not slug:
            raise RegistryError(f"## Streams row {row_idx} has empty slug.")
        if slug in seen_slugs:
            raise RegistryError(f"## Streams contains duplicate slug: {slug!r}")
        seen_slugs.add(slug)

        streams.append(Stream(
            slug=slug,
            name=name,
            status=status,
            claim=_parse_cell(claim),
            since=_parse_cell(since),
            last_touched=last_touched,
            last_handoff=_parse_cell(last_handoff),
        ))

    return Registry(
        has_streams_section=True,
        streams=streams,
        table_start=section_start,
        table_end=section_end,
        source=text,
    )


def render_table(streams: list[Stream]) -> str:
    """Render a list of Stream objects as the markdown table block.

    Output includes the header row and separator. Caller is responsible
    for placing this inside a ## Streams section.
    """
    header = "| " + " | ".join(EXPECTED_COLUMNS) + " |"
    sep = "| " + " | ".join("---" for _ in EXPECTED_COLUMNS) + " |"
    rows = []
    for s in streams:
        cells = [
            s.slug,
            s.name,
            s.status,
            s.claim if s.claim is not None else "unclaimed",
            s.since if s.since is not None else "—",
            s.last_touched,
            s.last_handoff if s.last_handoff is not None else "",
        ]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)


def update_table_in_text(registry: Registry) -> str:
    """Return a new markdown document with the table block replaced.

    Preserves the heading line, blank lines around the table, and all
    content outside the ## Streams section.
    """
    if not registry.has_streams_section:
        # Append a new ## Streams section to the end of the source.
        sep = "\n\n" if registry.source and not registry.source.endswith("\n\n") else ""
        return registry.source + sep + "## Streams\n\n" + render_table(registry.streams) + "\n"

    before = registry.source[:registry.table_start]
    after = registry.source[registry.table_end:]
    new_block = "\n\n" + render_table(registry.streams) + "\n"
    return before + new_block + after


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def optimistic_write(target: Path, registry: Registry) -> None:
    """Write the updated document atomically.

    If the file has drifted from `registry.source` since the caller parsed
    it, raises RegistryError so the caller can re-parse, re-apply mutations,
    and retry. Write itself uses temp-file + os.replace for atomicity.
    """
    captured_sha = hashlib.sha256(registry.source.encode("utf-8")).hexdigest()

    if target.exists():
        actual_sha = _sha256(target)
        if actual_sha != captured_sha:
            raise RegistryError(
                "Registry file changed between parse and write. "
                "Re-parse and retry."
            )

    new_text = update_table_in_text(registry)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, target)


@dataclass
class ClaimResult:
    claimed: bool
    previous_holder: str | None = None


@dataclass
class ReleaseResult:
    released: bool
    stolen: bool = False
    actual_holder: str | None = None


def claim(target: Path, slug: str, session_id: str, now_iso: str,
          force: bool = False) -> ClaimResult:
    """Claim `slug` on behalf of `session_id`. Returns a result describing
    what happened. Does not write if the stream is already claimed by
    another session unless `force=True`."""
    r = parse(target.read_text())
    stream = r.get(slug)
    if stream is None:
        raise RegistryError(f"Unknown stream slug: {slug!r}")

    if stream.claim is not None and stream.claim != session_id and not force:
        return ClaimResult(claimed=False, previous_holder=stream.claim)

    previous = stream.claim if stream.claim != session_id else None
    stream.claim = session_id
    stream.since = now_iso
    optimistic_write(target, r)
    return ClaimResult(claimed=True, previous_holder=previous)


def release(target: Path, slug: str, session_id: str, new_handoff: str | None,
            now_date: str) -> ReleaseResult:
    """Release `slug` if held by `session_id`. Updates last_handoff/last_touched.

    If the registry shows the stream is held by a different session
    (claim was stolen), does NOT modify the row and returns stolen=True.
    """
    r = parse(target.read_text())
    stream = r.get(slug)
    if stream is None:
        raise RegistryError(f"Unknown stream slug: {slug!r}")

    if stream.claim is not None and stream.claim != session_id:
        return ReleaseResult(released=False, stolen=True, actual_holder=stream.claim)

    stream.claim = None
    stream.since = None
    stream.last_touched = now_date
    if new_handoff is not None:
        stream.last_handoff = new_handoff
    optimistic_write(target, r)
    return ReleaseResult(released=True)


def add_stream(target: Path, slug: str, name: str, now_date: str,
               status: str = "active") -> None:
    """Append a new stream row to the registry. Creates the ## Streams
    section if missing."""
    if status not in VALID_STATUSES:
        # Allow but warn — design lets unknown statuses pass through.
        pass
    r = parse(target.read_text())
    if r.get(slug) is not None:
        raise RegistryError(f"Stream slug already exists: {slug!r}")
    r.has_streams_section = True
    r.streams.append(Stream(
        slug=slug, name=name, status=status,
        claim=None, since=None,
        last_touched=now_date, last_handoff=None,
    ))
    optimistic_write(target, r)


def set_status(target: Path, slug: str, new_status: str) -> None:
    """Change a stream's status without touching its claim."""
    r = parse(target.read_text())
    stream = r.get(slug)
    if stream is None:
        raise RegistryError(f"Unknown stream slug: {slug!r}")
    if stream.claim is not None and new_status == "archived":
        raise RegistryError(
            f"Cannot archive a claimed stream ({slug}); release it first."
        )
    stream.status = new_status
    optimistic_write(target, r)


def rename_stream(target: Path, old_slug: str, new_slug: str) -> None:
    """Rename a stream's slug. Refuses if the stream is currently claimed."""
    r = parse(target.read_text())
    stream = r.get(old_slug)
    if stream is None:
        raise RegistryError(f"Unknown stream slug: {old_slug!r}")
    if r.get(new_slug) is not None:
        raise RegistryError(f"Target slug already exists: {new_slug!r}")
    if stream.claim is not None:
        raise RegistryError(
            f"Cannot rename a claimed stream ({old_slug}); release it first."
        )
    stream.slug = new_slug
    optimistic_write(target, r)
