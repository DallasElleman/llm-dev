#!/usr/bin/env python3
"""end-session.py - Archive an LLM session

Converts the Claude Code JSONL transcript to llm-dev JSON format and commits
it alongside the per-session notes and handoff documents.

Usage: python end-session.py <session-num> "<title>" [options]

Automatically:
- Finds session ID from README placeholder or most recent JSONL
- Converts JSONL to llm-dev JSON format with auto-generated outcomes
- Updates README.md (replaces placeholder with actual entry)
- Updates CHANGELOG.md (adds new entry at top)
- Commits transcript + session-notes + session-handoff (if present)

Examples:
    python end-session.py 4 "Setup automation framework"
    python end-session.py 5 "Refactor parser logic" --topics "python, refactoring"
    python end-session.py 6 "Debug API issues" --session-id abc123 --dry-run
    python end-session.py 9 "Session Title" \
        --topics "topic1, topic2" \
        --files-modified "orchestrate.py, CLAUDE.md" \
        --decisions "Use llm-dev template structure, Investigate root cause" \
        --next-steps "Implement context propagation fix, Add SAC agent"
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _session
import _streams
import _manifest
import _index_gen
import _archive
import _transcript
import _plugin


def build_transcript_filename(yyyymmdd: str, nnn: str, title_kebab: str,
                              stream_slug: str | None) -> str:
    """Construct the transcript JSON filename.

    Claimed: YYYYMMDD-NNN-<slug>-<title>.json
    Free:    YYYYMMDD-NNN-<title>.json
    """
    if stream_slug:
        return f"{yyyymmdd}-{nnn}-{stream_slug}-{title_kebab}.json"
    return f"{yyyymmdd}-{nnn}-{title_kebab}.json"


def build_session_doc_filename(yyyymmdd: str, nnn: str, suffix: str,
                               stream_slug: str | None) -> str:
    """Construct session-notes or session-handoff filename.

    suffix is the trailing part after the date+NNN: 'session-notes.md' or
    'session-handoff.md'.
    """
    if stream_slug:
        return f"{yyyymmdd}-{nnn}-{stream_slug}-{suffix}"
    return f"{yyyymmdd}-{nnn}-{suffix}"


def resolve_session_date(notes_dir: Path, index_path: Path, nnn: str,
                         fallback: str) -> str:
    """Resolve a session's canonical START date as YYYYMMDD.

    A session that spans midnight must file its whole bundle (transcript,
    notes, handoff) under one date. The notes file (created by init-session
    at session start) is the anchor; the index placeholder is the next-best
    source; `fallback` (typically today) is the last resort.
    """
    # 1. Existing session-notes file: {YYYYMMDD}-{NNN}[-slug]-session-notes.md
    if notes_dir.is_dir():
        notes_re = re.compile(rf"^(\d{{8}})-{nnn}(?:-.*)?-session-notes\.md$")
        dates = sorted(
            m.group(1) for p in notes_dir.iterdir()
            if (m := notes_re.match(p.name))
        )
        if dates:
            return dates[0]
    # 2. Index [In Progress] placeholder File line (immediately follows header)
    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
        m = re.search(
            rf"### {nnn} - \[In Progress\]\n\*\*File\*\*:\s*`?(\d{{8}})-placeholder\.json`?",
            content,
        )
        if m:
            return m.group(1)
    # 3. Fallback (e.g. today)
    return fallback


def resolve_canonical_date(manifest: dict | None, notes_dir: Path, index_path: Path,
                           nnn: str, fallback: str) -> str:
    """Resolve the bundle's canonical YYYYMMDD date prefix.

    The in-progress manifest written by init-session is the single source of
    truth: it records the date the session actually started. Deriving the date
    any other way (notes filename, index placeholder, today's clock) can
    disagree with it — a session spanning midnight, or a JSONL carrying earlier
    messages, then files its transcript/handoff under a different prefix than
    the manifest and notes, splitting the archive (issue #80).

    Only sessions that pre-date the manifest flow fall through to
    `resolve_session_date`.
    """
    date = (manifest or {}).get("date") or ""
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return date.replace("-", "")
    return resolve_session_date(notes_dir, index_path, nnn, fallback=fallback)


def message_span(jsonl_path: Path, fallback: str) -> tuple[str, str]:
    """Return (started_at, ended_at) ISO timestamps from the first and last
    non-meta user/assistant messages in the JSONL. Either end falls back to
    `fallback` when no qualifying message is found."""
    first = last = None
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") not in ("user", "assistant"):
                    continue
                if entry.get("isMeta"):
                    continue
                ts = entry.get("timestamp")
                if not ts:
                    continue
                if first is None:
                    first = ts
                last = ts
    except OSError:
        pass
    return (first or fallback, last or fallback)


def format_index_timestamp(iso_ts: str) -> str:
    """Format an ISO 8601 timestamp as 'YYYY-MM-DD HH:MM UTC' for _index.md.
    Returns the input unchanged if it cannot be parsed."""
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError, AttributeError):
        return iso_ts


def release_claim_for_session(archive_dir: Path, slug: str, session_id: str,
                              new_handoff, now_date: str):
    """Release `slug` if held by `session_id` (per-stream JSON). Returns the
    release result; if stolen, the stream file is left untouched."""
    return _streams.release(archive_dir, slug=slug, session_id=session_id,
                            new_handoff=new_handoff, now_date=now_date)


def is_container_layout(archive_dir: Path) -> bool:
    """True if archive_dir is the llm-dev-archive worktree of a container
    (vs an in-place .archive on the current branch)."""
    return _archive.archive_worktree(archive_dir.parent) is not None


def prepend_stolen_note(handoff_body: str, slug: str, actual_holder: str,
                       since: str) -> str:
    """Prepend a 'claim was reassigned' admonition to the handoff body."""
    note = (
        f"> **Note**: this session's claim on `{slug}` was reassigned "
        f"mid-flow. The current stream owner is `{actual_holder}` "
        f"as of {since}.\n\n"
    )
    return note + handoff_body


def _pii_review_needed_json(findings: list) -> str:
    """Return a PII_REVIEW_NEEDED structured signal for non-interactive contexts.

    Mirrors the STREAM_SELECTION_NEEDED pattern from init-session.py: callers
    print this string so Claude can relay findings and re-invoke with --sanitize.
    """
    return "PII_REVIEW_NEEDED: " + json.dumps({
        "findings": findings,
        "instruction": (
            "PII was detected in the transcript. Re-invoke with --sanitize to "
            "automatically redact, or run interactively to choose "
            "[c]ommit anyway / [s]anitize / [a]bort."
        ),
    })


class Version:
    """Semantic version parser and bumper."""

    def __init__(self, major: int, minor: int, patch: int):
        self.major = major
        self.minor = minor
        self.patch = patch

    @classmethod
    def parse(cls, version_str: str) -> 'Version | None':
        """Parse a semantic version string like '1.2.3'."""
        match = re.match(r'^(\d+)\.(\d+)\.(\d+)$', version_str)
        if not match:
            return None
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    def bump_major(self) -> 'Version':
        """Bump major version (e.g., 1.2.3 -> 2.0.0)."""
        return Version(self.major + 1, 0, 0)

    def bump_minor(self) -> 'Version':
        """Bump minor version (e.g., 1.2.3 -> 1.3.0)."""
        return Version(self.major, self.minor + 1, 0)

    def bump_patch(self) -> 'Version':
        """Bump patch version (e.g., 1.2.3 -> 1.2.4)."""
        return Version(self.major, self.minor, self.patch + 1)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


# Shared by _scan_pii and _sanitize_content so the detector and the redactor
# can never drift apart — a redaction keyed on a different pattern than the
# scan is how issue #97 shipped.
EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'


class TranscriptGenerator:
    """Generates structured JSON transcripts from Claude Code JSONL sessions."""

    def __init__(self, session_num: int, title: str, stream_slug: str | None = None, **kwargs):
        self.session_num = session_num
        self.title = title
        self.session_id = kwargs.get('session_id')
        self.topics = kwargs.get('topics')
        self.dry_run = kwargs.get('dry_run', False)
        self.model = kwargs.get('model')
        self.user = kwargs.get('user')
        self.bump_type = kwargs.get('bump_type', 'patch')  # 'major', 'minor', or 'patch'

        self.sanitize = kwargs.get('sanitize', False)
        self.push = kwargs.get('push', True)
        # Re-finalize a session whose manifest is already complete (re-run).
        self.force = kwargs.get('force', False)
        # Archive despite a found-but-empty transcript import (see #96).
        self.allow_empty = kwargs.get('allow_empty', False)
        # Archive without a session-handoff at the resolved stream slug.
        self.no_handoff = kwargs.get('no_handoff', False)
        # Explicit project root (`--project-path`), so end-session can be run
        # from a parent workspace like init-session / research-sweep /
        # update-agents-md. None means "use cwd" (the historical behavior).
        self.project_path = kwargs.get('project_path')
        # Opt-in to freshest-JSONL inference when no manifest carries this
        # session number (issue #108: the guess is no longer implicit).
        self.infer_session_id = kwargs.get('infer_session_id', False)

        # Additional outcome fields
        self.provided_files_modified = kwargs.get('files_modified', '')
        self.provided_artifacts = kwargs.get('artifacts', '')
        self.provided_decisions = kwargs.get('decisions', '')
        self.provided_next_steps = kwargs.get('next_steps', '')

        # Find archive directory
        self.archive_dir = self._find_archive_dir()
        if not self.archive_dir:
            raise FileNotFoundError("No .archive/transcripts directory found")

        self.project_dir = self.archive_dir.parent
        self.project_id = self.project_dir.name
        self.index_path = self.archive_dir / "transcripts" / "_index.md"
        self.changelog_path = self.archive_dir / "CHANGELOG.md"

        # Pad session number
        self.session_num_padded = f"{session_num:03d}"

        # Resolve session identity. The session NUMBER (argv) is authoritative —
        # init-session recorded it in an in-progress manifest. Adopting that
        # manifest's id/stream (instead of re-deriving the *live* id by file scan)
        # stays correct even when concurrent same-project conversations would make
        # the scan resolve a different conversation.
        self._resolved_manifest = None
        self._manifest_stream = None
        self._resolve_identity()
        self._warn_on_plugin_version_drift()

        if not self.session_id:
            raise ValueError(
                "Could not find session ID. "
                "Provide it with --session-id or ensure init-session was run"
            )

        # Locate the harness transcript (Grok updates.jsonl or Claude JSONL).
        # A missing/unsupported source is not a hard error — we still archive
        # notes + handoff and warn (#84 / #94 honesty: capability-negotiated).
        self.jsonl_path = self._find_jsonl_file()
        self._missing_transcript = self.jsonl_path is None
        if self._missing_transcript:
            print(
                f"\nWarning: no harness transcript for session "
                f"{self.session_id!r}; archiving notes and handoff only.",
                file=sys.stderr,
            )

        # Generate metadata. The canonical session date is the START date
        # recorded by init-session in the in-progress manifest — the single
        # source of truth. A session spanning midnight (or a JSONL that carries
        # earlier messages) can otherwise derive a different date from the notes
        # file or today's clock, creating a split archive. Fall back to the
        # notes-file / index-placeholder / today path only for sessions that
        # pre-date the manifest flow.
        now = datetime.now()
        self.date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.date_yyyymmdd = resolve_canonical_date(
            self._resolved_manifest,
            self.archive_dir / "session-notes",
            self.index_path,
            self.session_num_padded,
            fallback=now.strftime("%Y%m%d"),
        )
        canonical = datetime.strptime(self.date_yyyymmdd, "%Y%m%d")
        self.date_display = (
            canonical.strftime("%B %-d, %Y") if os.name != 'nt'
            else canonical.strftime("%B %d, %Y").replace(' 0', ' ')
        )
        self.date_changelog = canonical.strftime("%Y-%m-%d")

        self.title_kebab = self._to_kebab_case(title)
        self.stream_slug = stream_slug  # None when this session held no claim

        # If --stream wasn't passed, take the stream from the resolved in-progress
        # manifest (authoritative, survives an already-released/stolen claim);
        # otherwise fall back to scanning the per-stream JSON store by claim id.
        if not self.stream_slug:
            if self._manifest_stream:
                self.stream_slug = self._manifest_stream
            else:
                held = next((s for s in _streams.list_streams(self.archive_dir)
                             if s.claim == self.session_id), None)
                if held is not None:
                    self.stream_slug = held.slug

        transcript_filename = build_transcript_filename(
            self.date_yyyymmdd, self.session_num_padded,
            self.title_kebab, self.stream_slug,
        )
        self.conversation_id = transcript_filename[:-len(".json")]
        self.output_file = self.archive_dir / "transcripts" / transcript_filename

        # Get user info
        self.user_name = self._get_user_name()
        self.user_github = self._get_user_github()

    def _start_dir(self) -> Path:
        """Project root every path/session lookup starts from: `--project-path`
        when given, else cwd. Mirrors init-session's `start_dir`."""
        raw = getattr(self, "project_path", None)
        return Path(raw).resolve() if raw else Path.cwd()

    def _find_archive_dir(self) -> Path | None:
        """Resolve the .archive dir for both layouts via the shared resolver."""
        return _archive.resolve_archive_dir(self._start_dir())

    def _read_current_version(self) -> Version:
        """Read the latest semver version from CHANGELOG.md.

        Scans the CHANGELOG for the most recent semantic version entry,
        ignoring date-based entries like [2026-01-10].
        Falls back to 0.1.0 if no version is found.
        """
        if not self.changelog_path.exists():
            return Version(0, 1, 0)

        content = self.changelog_path.read_text(encoding='utf-8')

        # Find all version entries in the format ## [X.Y.Z]
        # Ignore date entries like [2026-01-10] and [Unreleased]
        pattern = r'## \[(\d+\.\d+\.\d+)\]'
        matches = re.findall(pattern, content)

        if matches:
            # Return the first (most recent) valid semver
            version = Version.parse(matches[0])
            if version:
                return version

        # Default to 0.1.0 if no version found
        return Version(0, 1, 0)

    def _resolve_manifest_by_number(self) -> dict | None:
        """Return the manifest for this session number, preferring the unique
        in-progress one. Falls back to a complete manifest for the same number
        (used by the already-archived guard / `--force` re-finalize). Returns
        None when no manifest carries this number.

        Raises ValueError if more than one *in-progress* manifest shares the
        number (ambiguous; init derives the number as max+1 so this shouldn't
        happen, but we refuse to guess).
        """
        def _as_int(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        matches = [m for m in _manifest.iter_manifests(self.archive_dir)
                   if _as_int(m.get("number")) == self.session_num]
        in_progress = [m for m in matches if m.get("status") == "in-progress"]
        if len(in_progress) > 1:
            raise ValueError(
                f"ambiguous: {len(in_progress)} in-progress manifests for "
                f"session number {self.session_num}; resolve manually"
            )
        if in_progress:
            return in_progress[0]
        complete = [m for m in matches if m.get("status") == "complete"]
        return complete[0] if complete else None

    def _resolve_identity(self) -> None:
        """Set self.session_id (+ _resolved_manifest / _manifest_stream) from the
        authoritative session number, falling back to the live-id scan only when
        no manifest records this number. Precedence:
          1. in-progress (or complete, for --force) manifest with number ==
             session_num — resolved first, even when --session-id is passed
             explicitly. An explicit override used to skip this entirely,
             which dropped the manifest's recorded stream (issue #98 #3) and
             left `finalize_manifest` unable to find the existing manifest by
             session_id, synthesizing a second `complete` manifest for the
             same number instead of correcting the original (issue #98 #2).
          2. explicit --session-id (operator override) — still wins as
             self.session_id, but the manifest found in (1), if any, is the
             one corrected and finalized, and its stream still applies.
          3. _find_session_id() live scan (back-compat for old-handler sessions)
        """
        mf = self._resolve_manifest_by_number()
        # A manifest with no usable session_id (malformed / hand-edited) is not
        # adopted — fall through to the live scan rather than carry a null id.
        usable = mf is not None and bool(mf.get("session_id"))

        if usable and mf.get("status") == "complete" and not self.force and not self.dry_run:
            raise SystemExit(
                f"Session {self.session_num} is already archived "
                f"(manifest status=complete). Re-run with --force to re-finalize."
            )

        if self.session_id:
            if usable:
                if mf.get("session_id") != self.session_id:
                    print(
                        f"\nNote: session {self.session_num}'s manifest recorded "
                        f"session_id {mf.get('session_id')!r}; correcting it to "
                        f"the explicit --session-id override {self.session_id!r} "
                        f"instead of creating a second manifest for this number.",
                        file=sys.stderr,
                    )
                self._resolved_manifest = mf
                self._manifest_stream = mf.get("stream")
            return  # explicit override wins as the id either way

        if usable:
            self._resolved_manifest = mf
            self.session_id = mf.get("session_id")
            self._manifest_stream = mf.get("stream")
            # A divergent live-id scan is the concurrency signature behind the
            # mis-resolution bug — surface it instead of silently masking it.
            self._warn_on_live_id_divergence()
            return

        # No manifest for this number (e.g. a session started under the old
        # handler, or a mistyped number). Guessing identity from the freshest
        # JSONL here is the root cause of four archive collisions (issue
        # #108), so the guess is no longer implicit: name the session with
        # --session-id, or opt into inference with --infer-session-id.
        # Dry-run binds nothing, so it may still preview via the live scan.
        infer = getattr(self, "infer_session_id", False)
        if not infer and not self.dry_run:
            raise SystemExit(
                f"Error: no in-progress manifest for session number "
                f"{self.session_num}. Refusing to guess the session id from "
                f"the freshest JSONL (issue #108) — re-run with --session-id "
                f"<this conversation's UUID> (plus --stream <slug> if a "
                f"released stream claim must be restored), or with "
                f"--infer-session-id to accept live-scan inference for a "
                f"genuinely pre-manifest session."
            )
        # Inference under ambiguity is how collisions happen: if any OTHER
        # session is in progress in this archive, the freshest JSONL may well
        # be theirs — refuse and require an explicit id.
        def _num(m):
            try:
                return int(m.get("number"))
            except (TypeError, ValueError):
                return None
        others = [m for m in _manifest.iter_manifests(self.archive_dir)
                  if m.get("status") == "in-progress"
                  and _num(m) != self.session_num]
        if others and not self.dry_run:
            nums = ", ".join(sorted(str(m.get("number")) for m in others))
            raise SystemExit(
                f"Error: --infer-session-id refused: {len(others)} other "
                f"in-progress manifest(s) exist (number(s) {nums}) — the "
                f"freshest JSONL may belong to one of them. Name this "
                f"session explicitly with --session-id (and --stream if "
                f"needed)."
            )
        print(
            f"\nWarning: no in-progress manifest for session number "
            f"{self.session_num}; falling back to live session-id resolution"
            f"{' (--infer-session-id)' if infer else ' (dry-run preview)'}.",
            file=sys.stderr,
        )
        self.session_id = self._find_session_id()
        print(f"Inferred session id: {self.session_id!r}", file=sys.stderr)

    def _warn_on_live_id_divergence(self) -> None:
        """Compare the live harness scan against the manifest this session
        number resolved to. A disagreement is the concurrency signature
        behind issue #98 #1 (init-session can bind a session number to the
        wrong same-project conversation) — surface concrete mtime evidence
        loudly rather than a quiet stderr note, since silently trusting a
        wrong manifest here produces a plausible-looking archive with no
        error.
        """
        live = self._find_session_id()
        if not live or live == self.session_id:
            return
        evidence = ""
        try:
            cwd = self._start_dir()
            manifest_src = _session.find_session_source(self.session_id, cwd)
            live_src = _session.find_session_source(live, cwd)
            if manifest_src is not None and live_src is not None:
                m_mtime = manifest_src.stat().st_mtime
                l_mtime = live_src.stat().st_mtime
                m_dt = datetime.fromtimestamp(m_mtime).strftime("%Y-%m-%d %H:%M")
                l_dt = datetime.fromtimestamp(l_mtime).strftime("%Y-%m-%d %H:%M")
                evidence = (
                    f" Manifest id's transcript last modified {m_dt}; live "
                    f"id's transcript last modified {l_dt}."
                )
                if m_mtime < l_mtime:
                    evidence += (
                        " The manifest id's transcript is OLDER than the live "
                        "one — strong evidence init-session bound the wrong "
                        "conversation to this session number."
                    )
        except OSError:
            pass
        print(
            f"\nWARNING: live session-id scan returned {live!r} but the "
            f"manifest for session {self.session_num} records "
            f"{self.session_id!r}; trusting the manifest (concurrent "
            f"same-project conversations can cause this).{evidence} If the "
            f"archived transcript looks empty or wrong, re-run with "
            f"--session-id {live!r} --force to correct it.",
            file=sys.stderr,
        )

    def _warn_on_plugin_version_drift(self) -> None:
        """Non-fatal notice when the plugin install ending this session is not
        the one that inited it.

        init-session stamps `plugin_version` into the manifest. A session can
        init from one install and end from another — ASWP session 122 inited
        from `plugins/marketplaces/…` and ended from `plugins/cache/…/0.21.0/`
        — which silently mixes two generations of handler behavior across one
        archive. Manifests written before the stamp existed carry no key; stay
        quiet for those rather than warning on every historical session.
        """
        manifest = getattr(self, "_resolved_manifest", None) or {}
        inited = manifest.get("plugin_version")
        ending = _plugin.plugin_version()
        if not inited or not ending or inited == ending:
            return
        print(
            f"\nWarning: session {self.session_num} was inited under llm-dev "
            f"plugin {inited} but is ending under {ending} — handlers may have "
            f"changed mid-session. Check the archived output before trusting it.",
            file=sys.stderr,
        )

    def _missing_handoff_stream_hint(self) -> str:
        """Hint for a missing handoff when no stream slug resolved.

        A session that claimed a stream after init has no stream on its
        manifest, so the slug comes from the live claim — and a re-run (after
        `--force`) finds that claim already released. The stream-qualified
        handoff on disk is then never looked for, and the bare
        "no session-handoff" error gives no clue that `--stream <slug>` is what
        restores it. Name the flag, and the slug when a matching file says which.
        """
        if self.stream_slug:
            return ""
        prefix = f"{self.date_yyyymmdd}-{self.session_num_padded}-"
        suffix = "-session-handoff.md"
        found = sorted(
            p.name[len(prefix):-len(suffix)]
            for p in (self.archive_dir / "session-handoff").glob(f"{prefix}*{suffix}")
        )
        hint = (
            " No stream slug resolved for this session, so the stream-qualified "
            "filename was never checked — a released stream claim (the usual "
            "cause when re-running with --force) drops it. Pass --stream <slug> "
            "to restore it"
        )
        if found:
            hint += f" (handoffs on disk for this session: {', '.join(found)})"
        return hint + "."

    def _check_handoff_present(self) -> None:
        """Hard-error if no session-handoff exists at the resolved stream slug,
        so a session can't be archived without a re-entry point. `--no-handoff`
        downgrades this to a notice (for sessions that intentionally have none).
        """
        handoff_path = (
            self.archive_dir / "session-handoff"
            / build_session_doc_filename(self.date_yyyymmdd, self.session_num_padded,
                                         "session-handoff.md", self.stream_slug)
        )
        if handoff_path.exists():
            return
        rel = handoff_path.relative_to(self.project_dir)
        if self.no_handoff:
            print(
                f"\nNotice: no session-handoff at {rel} (--no-handoff); "
                f"archiving without a re-entry point."
                f"{self._missing_handoff_stream_hint()}",
                file=sys.stderr,
            )
            return
        print(
            f"\nError: no session-handoff file found at {rel} — refusing to "
            f"archive without a re-entry point. Write the handoff first, or pass "
            f"--no-handoff to override.{self._missing_handoff_stream_hint()}",
            file=sys.stderr,
        )
        sys.exit(1)

    def _find_session_id(self) -> str | None:
        """Find session ID from index placeholder or most recent JSONL."""
        # Try to extract from index placeholder
        if self.index_path.exists():
            try:
                content = self.index_path.read_text(encoding='utf-8')
                # Look for placeholder entry
                pattern = rf"### {self.session_num_padded} - \[In Progress\].*?\*\*Session\*\*:\s*(\S+)"
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    session_id = match.group(1).strip()
                    if session_id and session_id != 'unknown':
                        return session_id
            except Exception:
                pass

        # Fall back to the scoped resolver (same encoding as init-session).
        # Supersedes _find_most_recent_jsonl (a divergent global rglob).
        sid = _session.find_session_id(self._start_dir())
        return None if sid == "unknown" else sid

    def _find_most_recent_jsonl(self) -> str | None:
        """Find most recent non-agent JSONL file modified in last 60 minutes."""
        claude_projects = Path.home() / ".claude" / "projects"
        if not claude_projects.exists():
            return None

        recent_files = []
        cutoff_time = datetime.now().timestamp() - (60 * 60)  # 60 minutes ago

        for jsonl_file in claude_projects.rglob("*.jsonl"):
            # Skip agent files
            if jsonl_file.name.startswith("agent-"):
                continue
            # Check modification time
            if jsonl_file.stat().st_mtime >= cutoff_time:
                recent_files.append((jsonl_file.stat().st_mtime, jsonl_file))

        if recent_files:
            # Sort by modification time (most recent first)
            recent_files.sort(reverse=True)
            return recent_files[0][1].stem  # Return filename without extension

        return None

    def _find_jsonl_file(self) -> Path | None:
        """Locate the harness transcript for this session id.

        Prefers the stored id (Grok session dir or Claude JSONL). If that
        id is missing — including the synthetic `claude-NNN-hex` minted
        before Grok discovery existed — fall back to the live harness
        session for this cwd and warn.
        """
        cwd = self._start_dir()
        found = _session.find_session_source(self.session_id, cwd)
        if found is not None:
            return found

        live = _session.detect_harness_context(cwd)

        # Substituting the live session for a *real* stored id archives some
        # other conversation under this session's number, then commits and
        # pushes it — a wrong artifact rather than an empty one, with no error.
        # Reported by session 122, which resolved a concurrent session's id
        # this way. The fallback is only legitimate for the synthetic
        # `claude-NNN-hex` / `grok-NNN-hex` ids minted when no live harness
        # session existed at init: those never had a transcript of their own,
        # so there is nothing to mis-attribute away from.
        if not _session.is_synthetic_session_id(self.session_id):
            hint = ""
            if live and live.session_id:
                hint = (f" The live {live.harness} session here is "
                        f"{live.session_id!r}; if that is genuinely this "
                        f"conversation, re-run with "
                        f"--session-id {live.session_id} --force "
                        f"--stream <slug>.")
            print(
                f"\nError: stored session id {self.session_id!r} has no "
                f"transcript on disk. Refusing to substitute a different "
                f"session — that would archive another conversation under "
                f"session {self.session_num}.{hint}",
                file=sys.stderr,
            )
            raise SystemExit(1)

        if live and live.transcript_path:
            print(
                f"\nWarning: synthetic session id {self.session_id!r} has no "
                f"transcript on disk; using live {live.harness} session "
                f"{live.session_id!r}.",
                file=sys.stderr,
            )
            return live.transcript_path
        return None

    def _to_kebab_case(self, text: str) -> str:
        """Convert text to kebab-case."""
        return re.sub(r'[^a-z0-9-]', '', text.lower().replace(' ', '-'))

    def _get_user_name(self) -> str:
        """Get user name from git config or override."""
        if self.user:
            return self.user

        try:
            import subprocess
            result = subprocess.run(
                ['git', 'config', 'user.name'],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        return "User"

    def _get_user_github(self) -> str | None:
        """Get GitHub username from git config."""
        try:
            import subprocess
            # Try github.user first
            result = subprocess.run(
                ['git', 'config', 'github.user'],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()

            # Try extracting from remote origin
            result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                # Extract username from github.com URL
                match = re.search(r'github\.com[:/]([^/]+)/', url)
                if match:
                    return match.group(1)
        except Exception:
            pass

        return None

    def _parse_comma_separated(self, value: str) -> list[str]:
        """Parse comma-separated string into list of strings."""
        if not value:
            return []
        return [item.strip() for item in value.split(',') if item.strip()]

    def _guard_empty_import(self, imported) -> None:
        """Refuse to archive zero dialogue when a transcript file was found.

        Issue #96 shipped because nothing checked this: the run printed
        `Messages: 0`, `Git commit successful`, `Pushed to remote` and
        `Done! … archived successfully` over an empty artifact, and it took a
        human noticing the word "transcript" in a summary to catch it. A
        genuinely empty session is rare; a file on disk that imported to
        nothing is almost always a broken importer. Make it loud.

        `--allow-empty` is the escape hatch for the legitimate case (a session
        with no transcript at all still archives its notes and handoff).
        """
        if imported.messages:
            return
        src = self.jsonl_path
        if src is None or not Path(src).exists():
            return  # nothing found on disk — notes+handoff only, expected
        if getattr(self, 'allow_empty', False):
            return
        print(
            f"\nError: {self.jsonl_path} exists but imported 0 dialogue "
            f"entries. Refusing to archive an empty transcript over a "
            f"transcript file that is sitting on disk — this is the signature "
            f"of a broken importer, not an empty session. Re-run with "
            f"--allow-empty if the session really had no dialogue.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    def parse_jsonl(self) -> dict:
        """Parse a harness transcript into the llm-dev JSON archive format."""
        imported = _transcript.import_source(self.jsonl_path, self.date_iso)
        for warning in imported.warnings:
            print(f"\nWarning: {warning}", file=sys.stderr)

        self._guard_empty_import(imported)

        messages = imported.messages
        model_id = imported.model_id
        model_name = imported.model_name
        files_created = imported.files_created
        files_modified = imported.files_modified
        tools_used = imported.tools_used

        # Override model if specified
        if self.model:
            model_name = _session.derive_model_display_name(self.model)
            model_id = self.model

        # Group consecutive tool-only messages
        messages = self._group_consecutive_tool_calls(messages)

        # Generate outcomes and topics
        outcomes = self._generate_outcomes(files_created, files_modified, messages)
        topics = self._generate_topics(tools_used)

        # Parse provided outcome fields
        provided_files_modified_list = self._parse_comma_separated(self.provided_files_modified)
        provided_artifacts_list = self._parse_comma_separated(self.provided_artifacts)
        provided_decisions_list = self._parse_comma_separated(self.provided_decisions)
        provided_next_steps_list = self._parse_comma_separated(self.provided_next_steps)

        # Merge provided files_modified with auto-detected ones
        # Convert auto-detected to paths list for easier merging
        auto_detected_paths = {f['path'] for f in files_modified}
        merged_files_modified = list(files_modified)  # Start with auto-detected

        # Add provided files that aren't already auto-detected
        for path in provided_files_modified_list:
            if path not in auto_detected_paths:
                merged_files_modified.append({
                    'path': path,
                    'changes': 'Modified file'
                })

        if self.jsonl_path and imported.harness == "claude":
            started_at, ended_at = message_span(self.jsonl_path, self.date_iso)
        else:
            started_at = imported.started_at or self.date_iso
            ended_at = imported.ended_at or self.date_iso

        # Build transcript
        transcript = {
            'project_id': self.project_id,
            'conversation_id': self.conversation_id,
            'conversation_number': self.session_num,
            'date': self.date_iso,
            'started_at': started_at,
            'ended_at': ended_at,
            'participants': [
                {
                    'name': self.user_name,
                    'github': self.user_github,
                    'role': 'user',
                    'model': None
                },
                {
                    'name': model_name or 'Claude',
                    'github': None,
                    'role': 'assistant',
                    'model': model_id
                }
            ],
            'summary': {
                'title': self.title,
                'topics': topics,
                'outcomes': outcomes
            },
            'dialogue': messages,
            'outcomes': {
                'files_created': files_created,
                'files_modified': merged_files_modified,
                'artifacts_archived': provided_artifacts_list,
                'decisions': provided_decisions_list,
                'next_steps': provided_next_steps_list
            }
        }

        return transcript

    def _parse_message_content(
        self,
        content,
        tools_used: Counter,
        files_created: list[dict],
        files_modified: list[dict]
    ) -> tuple[str, list[dict]]:
        """Parse message content and extract tool calls."""
        if isinstance(content, str):
            # Skip command-name tags
            if '<command-name>' in content or '<local-command' in content:
                return '', []
            return content, []

        elif isinstance(content, list):
            text_parts = []
            tool_calls = []

            for item in content:
                if not isinstance(item, dict):
                    continue

                if item.get('type') == 'text':
                    text_parts.append(item.get('text', ''))

                elif item.get('type') == 'tool_use':
                    tool_name = item.get('name', 'Unknown')
                    inp = item.get('input', {})
                    tools_used[tool_name] += 1

                    # Track file operations
                    if tool_name == 'Write':
                        path = inp.get('file_path', '')
                        if path and path not in [f['path'] for f in files_created]:
                            files_created.append({
                                'path': path,
                                'description': 'Created file'
                            })
                    elif tool_name == 'Edit':
                        path = inp.get('file_path', '')
                        if path and path not in [f['path'] for f in files_modified]:
                            files_modified.append({
                                'path': path,
                                'changes': 'Modified file'
                            })

                    # Format description
                    desc = self._format_tool_description(tool_name, inp)
                    tool_calls.append({'tool': tool_name, 'description': desc})

            message_text = '\n'.join(text_parts)
            return message_text, tool_calls

        return '', []

    def _format_tool_description(self, tool_name: str, inp: dict) -> str:
        """Format tool description based on tool type."""
        if tool_name == 'Read':
            return f"Read {inp.get('file_path', 'file')}"
        elif tool_name == 'Write':
            return f"Write to {inp.get('file_path', 'file')}"
        elif tool_name == 'Edit':
            return f"Edit {inp.get('file_path', 'file')}"
        elif tool_name == 'Bash':
            cmd = inp.get('command', '')
            if len(cmd) > 80:
                return f"Run: {cmd[:80]}..."
            return f"Run: {cmd}"
        elif tool_name == 'Glob':
            return f"Search pattern: {inp.get('pattern', '')}"
        elif tool_name == 'Grep':
            return f"Search for: {inp.get('pattern', '')}"
        elif tool_name == 'Task':
            return f"Spawn agent: {inp.get('description', '')}"
        elif tool_name == 'TodoWrite':
            return "Update todo list"
        else:
            return str(inp)[:100]

    def _generate_outcomes(
        self,
        files_created: list[dict],
        files_modified: list[dict],
        messages: list[dict]
    ) -> list[str]:
        """Auto-generate outcomes based on file operations."""
        outcomes = []

        if files_created:
            outcomes.append(f"Created {len(files_created)} file(s)")
        if files_modified:
            outcomes.append(f"Modified {len(files_modified)} file(s)")

        # Add specific outcomes based on common patterns
        for file_info in files_created:
            path = file_info['path']
            basename = os.path.basename(path)

            if basename.endswith('.sh'):
                outcomes.append(f"Created {basename} script")
            elif basename.endswith('.md') and 'command' in path.lower():
                outcomes.append(f"Created {basename} command")
            elif basename.endswith('.json') and 'transcript' in path.lower():
                outcomes.append(f"Created transcript {basename}")

        # Deduplicate and limit outcomes
        outcomes = list(dict.fromkeys(outcomes))[:5]

        if not outcomes:
            outcomes = [f"Completed conversation with {len(messages)} exchanges"]

        return outcomes

    def _generate_topics(self, tools_used: Counter) -> list[str]:
        """Auto-generate topics if not provided."""
        if self.topics:
            return [t.strip() for t in self.topics.split(',')]

        topics = []
        if tools_used.get('Write') or tools_used.get('Edit'):
            topics.append('code development')
        if tools_used.get('Bash'):
            topics.append('shell scripting')
        if tools_used.get('Task'):
            topics.append('agent tasks')

        if not topics:
            topics = ['development session']

        return topics

    def _group_consecutive_tool_calls(self, messages: list[dict]) -> list[dict]:
        """Group consecutive assistant messages that have only tool calls (no text).

        When multiple tool calls occur in rapid succession without accompanying
        text messages, they are merged into a single dialogue entry. The timestamp
        of the first message in the group is preserved.
        """
        if not messages:
            return messages

        grouped = []
        i = 0

        while i < len(messages):
            msg = messages[i]

            # Check if this is a tool-only assistant message
            if (msg.get('speaker') == 'assistant' and
                    not msg.get('message', '').strip() and
                    msg.get('tool_calls')):

                # Start a group - collect consecutive tool-only messages
                group_timestamp = msg['timestamp']
                group_tool_calls = list(msg['tool_calls'])

                j = i + 1
                while j < len(messages):
                    next_msg = messages[j]
                    # Continue grouping if next is also tool-only assistant
                    if (next_msg.get('speaker') == 'assistant' and
                            not next_msg.get('message', '').strip() and
                            next_msg.get('tool_calls')):
                        group_tool_calls.extend(next_msg['tool_calls'])
                        j += 1
                    else:
                        break

                # Create merged entry (only if we actually grouped multiple)
                grouped.append({
                    'speaker': 'assistant',
                    'timestamp': group_timestamp,
                    'message': '',
                    'tool_calls': group_tool_calls
                })
                i = j
            else:
                grouped.append(msg)
                i += 1

        return grouped

    def write_transcript(self, transcript: dict, content_override: str = None) -> None:
        """Write transcript to JSON file.

        If content_override is provided (e.g., sanitized content), write that
        directly instead of serializing the transcript dict.
        """
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_file, 'w', encoding='utf-8') as f:
            if content_override is not None:
                f.write(content_override)
            else:
                json.dump(transcript, f, indent=2, ensure_ascii=False)

    def finalize_manifest(self, transcript: dict) -> Path:
        """Locate this session's in-progress manifest (the one resolved by
        session number, else a session-id match) and finalize it: ended_at,
        status=complete, title, conversation_id, model, contributor (the author's
        git user.name — see below), and the files map. If no manifest exists
        (e.g. a session started under the old handler), synthesize one keyed on
        conversation_id.
        """
        # Prefer the manifest resolved by session number (the authoritative one);
        # fall back to a session-id match (old-handler sessions), else synthesize.
        match = getattr(self, "_resolved_manifest", None)
        if match is None:
            for m in _manifest.iter_manifests(self.archive_dir):
                if m.get("session_id") and m.get("session_id") == self.session_id:
                    match = m
                    break
        date = self.date_yyyymmdd
        if match is None:
            match = {
                "session_id": self.session_id, "number": self.session_num,
                "stream": self.stream_slug, "started_at": transcript.get("started_at"),
                "date": f"{date[:4]}-{date[4:6]}-{date[6:]}",
                # No init stamp to preserve (this manifest never had one), so
                # record the install doing the archiving rather than leaving the
                # provenance field absent.
                "plugin_version": _plugin.plugin_version(),
                "files": {},
            }
        # The manifest directory this session number previously resolved to
        # (if any), computed from the SAME date+session_id convention
        # init-session uses to name it. Captured before .update() overwrites
        # session_id below, so an explicit --session-id correction (issue
        # #98 #2) can be relocated instead of orphaned.
        old_session_id = match.get("session_id")
        old_dirname = f"{date}-{old_session_id}" if old_session_id else None
        assistant = next((p for p in transcript.get("participants", [])
                          if p.get("role") == "assistant"), {})
        notes_rel = build_session_doc_filename(date, self.session_num_padded,
                                               "session-notes.md", self.stream_slug)
        handoff_rel = build_session_doc_filename(date, self.session_num_padded,
                                                 "session-handoff.md", self.stream_slug)
        handoff_abs = self.archive_dir / "session-handoff" / handoff_rel
        match.update({
            "session_id": self.session_id,
            "title": self.title,
            "ended_at": _manifest.normalize_ts(transcript.get("ended_at")),
            "started_at": _manifest.normalize_ts(
                match.get("started_at") or transcript.get("started_at")),
            "status": "complete",
            "model": self.model or assistant.get("model"),
            # Author identity for the trust gate's own-match: git user.name (the
            # stable per-person id init-session + _trust both key on). NOT
            # user_github, which _get_user_github derives from the remote OWNER
            # (the repo-owner org — same for every contributor, so it can't
            # distinguish authors and would falsely flag own records untrusted).
            "contributor": self.user_name,
            "conversation_id": self.conversation_id,
            "files": {
                "transcript": f"transcripts/{self.conversation_id}.json",
                "notes": f"session-notes/{notes_rel}",
                "handoff": (f"session-handoff/{handoff_rel}"
                            if handoff_abs.exists() else None),
            },
        })
        dirname = f"{date}-{self.session_id}" if match.get("session_id") else self.conversation_id

        # An explicit --session-id correction changes the manifest's dirname
        # (date+session_id). Relocate the existing directory in place rather
        # than writing a fresh one and leaving the original orphaned as a
        # second `complete` manifest for the same number (issue #98 #2).
        if old_dirname and old_dirname != dirname:
            old_path = self.archive_dir / "sessions" / old_dirname
            new_path = self.archive_dir / "sessions" / dirname
            if old_path.is_dir() and not new_path.exists():
                old_path.rename(new_path)

        self._warn_on_split_manifest(dirname)

        return _manifest.write_manifest(self.archive_dir, dirname, match)

    def _warn_on_split_manifest(self, dirname: str) -> None:
        """Split-detection guardrail: if a manifest directory for this session
        already exists at a DIFFERENT path, writing to `dirname` would orphan it
        (issue #80). Warn rather than raise — the bundle is still written."""
        if not self.session_id:
            return
        sessions_dir = self.archive_dir / "sessions"
        if not sessions_dir.is_dir():
            return
        for d in sorted(sessions_dir.iterdir()):
            if (d.is_dir() and d.name != dirname
                    and d.name.endswith(f"-{self.session_id}")):
                print(
                    f"\nWarning: existing manifest directory {d.name!r} for "
                    f"session {self.session_id!r} differs from the target "
                    f"directory {dirname!r}. This indicates a date mismatch "
                    f"between init-session and end-session — the original "
                    f"in-progress manifest will be orphaned. Inspect "
                    f".archive/sessions/ and remove the duplicate manually.",
                    file=sys.stderr,
                )
                break

    def update_index(self, transcript: dict) -> None:
        """Regenerate the derived index from manifests (replaces the legacy
        placeholder-replacement regex)."""
        _index_gen.write_index(self.archive_dir)

    def _format_changelog_entry(self, transcript: dict) -> str:
        """Format changelog entry using proper Types of Changes categories.

        Categories: Added, Changed, Deprecated, Removed, Fixed, Security
        """
        # Read current version and bump it
        current_version = self._read_current_version()
        if self.bump_type == 'major':
            new_version = current_version.bump_major()
        elif self.bump_type == 'minor':
            new_version = current_version.bump_minor()
        else:  # patch
            new_version = current_version.bump_patch()

        files_created = transcript['outcomes'].get('files_created', [])
        files_modified = transcript['outcomes'].get('files_modified', [])
        title_lower = self.title.lower()
        topics = [t.lower() for t in transcript['summary'].get('topics', [])]

        lines = []
        lines.append(f"## [{new_version}] - {self.date_changelog}")
        lines.append(f"**Conversation**: {self.session_num_padded} - {self.title}")
        lines.append(f"**Transcript**: [{self.conversation_id}.json](transcripts/{self.conversation_id}.json)")

        # Detect if this is a fix (from title or topics)
        is_fix = 'fix' in title_lower or 'bug' in title_lower or any('fix' in t for t in topics)
        is_security = 'security' in title_lower or any('security' in t for t in topics)

        # Group changes by category
        added_items = []
        changed_items = []
        fixed_items = []
        security_items = []

        # Categorize file operations
        for f in files_created:
            path = f.get('path', '')
            basename = os.path.basename(path)
            added_items.append(basename)

        for f in files_modified:
            path = f.get('path', '')
            basename = os.path.basename(path)
            if is_security:
                security_items.append(f"Updated {basename}")
            elif is_fix:
                fixed_items.append(f"Fixed issues in {basename}")
            else:
                changed_items.append(f"Updated {basename}")

        # Build categorized output
        if added_items:
            lines.append("### Added")
            for item in added_items:
                lines.append(f"- {item}")

        if changed_items:
            lines.append("### Changed")
            for item in changed_items:
                lines.append(f"- {item}")

        if fixed_items:
            lines.append("### Fixed")
            for item in fixed_items:
                lines.append(f"- {item}")

        if security_items:
            lines.append("### Security")
            for item in security_items:
                lines.append(f"- {item}")

        # Fallback if no file operations detected
        if not (added_items or changed_items or fixed_items or security_items):
            lines.append("### Changed")
            lines.append(f"- Development session: {self.title}")

        return '\n'.join(lines)

    def update_changelog(self, transcript: dict) -> None:
        """Update CHANGELOG.md with new entry at top."""
        changelog_entry = self._format_changelog_entry(transcript)

        if self.changelog_path.exists():
            content = self.changelog_path.read_text(encoding='utf-8')

            # Insert after ## [Unreleased] section (before next ## [)
            if '## [Unreleased]' in content:
                pattern = r'(## \[Unreleased\].*?\n)(\n*)(## \[)'
                replacement = r'\1\n' + changelog_entry + r'\n\n\3'
                new_content = re.sub(pattern, replacement, content, count=1)
            else:
                # Insert after header (before first ## [ entry)
                lines = content.split('\n')
                insert_idx = len(lines)
                for i, line in enumerate(lines):
                    if line.startswith('## ['):
                        insert_idx = i
                        break
                lines.insert(insert_idx, '\n' + changelog_entry + '\n')
                new_content = '\n'.join(lines)

            self.changelog_path.write_text(new_content, encoding='utf-8')
        else:
            # Create new changelog
            changelog_content = f"""# Changelog

{changelog_entry}
"""
            self.changelog_path.write_text(changelog_content, encoding='utf-8')

    def _scan_pii(self, content: str) -> list[dict]:
        """Scan transcript content for PII patterns.

        Returns a list of findings, each with 'type', 'count', 'category', and
        (for pattern-based findings) 'pattern'/'replacement' used to drive
        `_sanitize_content`. 'category' marks which findings that method is
        actually able to redact ('home_path', 'participant_name') versus
        report-only ('email', 'secret').
        """
        findings = []

        # Home directory paths, both literal (/Users/<user>, /home/<user>) and
        # the hyphen-encoded form Claude Code uses for its own project dirs
        # under ~/.claude/projects/ (e.g. -Users-<user>-dev-...). Every distinct
        # match is redacted via re.sub over the *whole* pattern below — keying
        # off a single captured username (matches[0]) let any earlier, different
        # capture (e.g. a truncated example path) silently disarm the rest.
        home_patterns = [
            (r'/Users/([A-Za-z0-9._\-]+)', '/Users/<user>', 'macOS home path'),
            (r'/home/([A-Za-z0-9._\-]+)', '/home/<user>', 'Linux home path'),
            (r'C:\\\\Users\\\\([A-Za-z0-9._\-]+)', 'C:\\\\Users\\\\<user>', 'Windows home path'),
            # Hyphen-encoded project dirs (~/.claude/projects/-Users-<user>-...).
            # The username is the FIRST segment after the prefix, so the class
            # deliberately excludes '-': a greedy [A-Za-z0-9._\-]+ swallows the
            # whole encoded path, collapsing -Users-<user>-dev-projects-foo and
            # -Users-<user>-dev-bar to the same '-Users-<user>' token. That is
            # not merely lossy — issue #98 and the session-122 report were both
            # diagnosed *from* these directory names, in transcripts kept
            # specifically to debug the archiver. Redact the identity, keep the
            # path. (A username containing a hyphen is still fully redacted, by
            # the literal pass below, whenever it also appears in slash form.)
            (r'-Users-([A-Za-z0-9._]+)', '-Users-<user>',
             'macOS hyphen-encoded home path (project dir)'),
            (r'-home-([A-Za-z0-9._]+)', '-home-<user>',
             'Linux hyphen-encoded home path (project dir)'),
        ]
        for pattern, replacement, label in home_patterns:
            matches = re.findall(pattern, content)
            if matches:
                count = len(matches)
                usernames = sorted({m if isinstance(m, str) else m[0] for m in matches})
                # The label is printed to the console by _report_findings. An
                # unbounded join reprints every captured username and project
                # path — i.e. the redaction report becomes a listing of the PII
                # being redacted. Show at most three.
                shown = ', '.join(usernames[:3])
                if len(usernames) > 3:
                    shown += f', +{len(usernames) - 3} more'
                findings.append({
                    'type': f'{label} (username: {shown})',
                    'count': count,
                    'pattern': pattern,
                    'replacement': replacement,
                    'category': 'home_path',
                    'usernames': usernames,
                    # Kept for callers/tests that inspect a single example
                    # username; redaction itself uses 'pattern'/'replacement'
                    # above so it no longer depends on this being complete.
                    'username': usernames[0],
                })

        # Email addresses
        email_matches = re.findall(EMAIL_PATTERN, content)
        # Filter out known safe emails (Co-Authored-By, noreply)
        email_matches = [e for e in email_matches if 'noreply@' not in e]
        if email_matches:
            findings.append({
                'type': 'email address',
                'count': len(email_matches),
                'example': email_matches[0],
                'category': 'email',
                # Redacted, not merely reported: --sanitize is the default and
                # archives are pushed to public repos, so a detected address
                # that survives the "sanitized" run is the same failure this
                # issue is about, one category over. `noreply@` addresses are
                # preserved by the repl below — they are the Co-Authored-By
                # trailers, and stripping them would corrupt attribution.
                'pattern': EMAIL_PATTERN,
                'replacement': '<email>',
            })

        # API keys / tokens (high-entropy strings near keywords, handles JSON escaping)
        secret_pattern = r'(?:key|token|secret|password|api_key|apikey|auth)["\s:=\\]+["\']?([a-zA-Z0-9_\-]{20,})'
        secret_matches = re.findall(secret_pattern, content, re.IGNORECASE)
        if secret_matches:
            findings.append({
                'type': 'potential secret/token',
                'count': len(secret_matches),
                'example': secret_matches[0][:8] + '...',
                'category': 'secret',
            })

        # Participant name (from self.user_name if not generic)
        if self.user_name and self.user_name != 'User':
            name_count = content.count(self.user_name)
            if name_count > 0:
                findings.append({
                    'type': f'participant name ("{self.user_name}")',
                    'count': name_count,
                    'category': 'participant_name',
                })

        return findings

    def _sanitize_content(self, content: str, findings: list[dict]) -> str:
        """Apply redactions to transcript content based on scan findings.

        Pattern-based findings (home paths, both literal and hyphen-encoded)
        are redacted with re.sub over the full pattern, so every occurrence is
        replaced regardless of which specific capture produced the finding.
        """
        sanitized = content

        for finding in findings:
            if 'pattern' in finding and 'replacement' in finding:
                # A literal-string repl (not a callable) would have its own
                # backslashes reinterpreted as regex backreference escapes by
                # re.sub — corrupting the doubled backslashes in the
                # JSON-escaped Windows-path replacement. A lambda's return
                # value is substituted verbatim, sidestepping that.
                replacement = finding['replacement']
                if finding.get('category') == 'email':
                    # Keep Co-Authored-By / noreply trailers intact; _scan_pii
                    # excludes them, so redacting them here would make the
                    # guardrail's re-scan disagree with what was written.
                    def _repl(m, _r=replacement):
                        return m.group(0) if 'noreply@' in m.group(0) else _r
                else:
                    def _repl(m, _r=replacement):
                        return _r
                sanitized = re.sub(finding['pattern'], _repl, sanitized)

        # Hyphen-encoded usernames that contain a '-' are only partially caught
        # by the anchored pattern above (it stops at the first hyphen). The
        # slash forms are unambiguous, so any username learned from them is
        # redacted literally in the encoded form too, tail preserved.
        for finding in findings:
            if finding.get('category') != 'home_path':
                continue
            for username in finding.get('usernames', ()):
                if '-' not in username:
                    continue  # already fully handled by the anchored pattern
                for prefix, label in (('-Users-', '-Users-<user>'),
                                      ('-home-', '-home-<user>')):
                    sanitized = sanitized.replace(f'{prefix}{username}', label)

        # Replace participant name
        if self.user_name and self.user_name != 'User':
            sanitized = sanitized.replace(self.user_name, '<user>')

        return sanitized

    @staticmethod
    def _unredacted_note(findings: list[dict]) -> str:
        """Name the categories `_sanitize_content` never redacts.

        `_scan_pii` detects emails and secrets but only *reports* them, and
        `_assert_sanitized` excludes them for that reason. Printing a bare
        "Sanitized." over a scan that found an email address repeats the exact
        shape of issue #97 one category over: a true statement about work that
        did not happen. Say what was left.
        """
        left = sorted({f['type'] for f in findings
                       if f.get('category') == 'secret'})
        if not left:
            return ""
        return (f" Not redacted (report-only): {', '.join(left)}."
                " Review before publishing, or edit the transcript by hand.")

    def _assert_sanitized(self, content: str) -> None:
        """Post-sanitize guardrail: re-scan the sanitized content and abort
        loudly if any home-path or participant-name finding survives.

        A redaction step that cannot detect its own no-op is how issue #97
        shipped: the reported count was correct and the "sanitized" message
        was printed, but only the first captured username was ever redacted.
        Emails are enforced here too: they are redacted as of 0.21.2, so a
        surviving address is a real no-op. Secrets stay excluded and
        report-only — `_sanitize_content` cannot safely rewrite an arbitrary
        high-entropy match without risking the surrounding structure.
        """
        remaining = [f for f in self._scan_pii(content)
                     if f.get('category') in ('home_path', 'participant_name',
                                              'email')]
        if remaining:
            self._report_findings(remaining)
            print(
                "\nError: sanitize did not remove all PII (see findings above). "
                "Aborting before write/commit.",
                file=sys.stderr,
            )
            sys.exit(1)

    def _report_findings(self, findings: list[dict]) -> None:
        """Print PII scan results."""
        print(f"\n{'='*50}")
        print(f"PII SCAN: {len(findings)} type(s) of sensitive data found")
        print(f"{'='*50}")
        for f in findings:
            line = f"  - {f['type']}: {f['count']} occurrence(s)"
            if 'example' in f:
                line += f" (e.g., {f['example']})"
            print(line)
        print()

    def _is_git_repo(self) -> bool:
        """Check if project directory is a git repository.

        Accepts both a `.git` directory (normal in-place repo) and a `.git`
        gitdir FILE (the bare-repo container root, whose `.git` is the pointer
        `gitdir: ./.bare`). Requiring `is_dir()` here silently skipped the
        entire container-layout commit path.
        """
        return (self.project_dir / ".git").exists()

    def _git_commit_transcripts(self) -> None:
        """Auto-commit transcript, index, changelog, session-notes, and handoff."""
        if not self._is_git_repo():
            return

        try:
            # Build list of files to commit (relative to project_dir)
            files_to_commit = []

            # Transcript file (relative path)
            transcript_rel = self.output_file.relative_to(self.project_dir)
            files_to_commit.append(str(transcript_rel))

            # Index file
            index_rel = self.index_path.relative_to(self.project_dir)
            files_to_commit.append(str(index_rel))

            # Changelog file
            changelog_rel = self.changelog_path.relative_to(self.project_dir)
            files_to_commit.append(str(changelog_rel))

            # Session notes file (created by /init-session). Include if present
            # so cross-session learnings travel with the transcript commit.
            session_notes_path = (
                self.archive_dir
                / "session-notes"
                / build_session_doc_filename(self.date_yyyymmdd, self.session_num_padded,
                                             "session-notes.md", self.stream_slug)
            )
            if session_notes_path.exists():
                files_to_commit.append(
                    str(session_notes_path.relative_to(self.project_dir))
                )

            # Session handoff file (written by Claude during /end-session before
            # the handler runs). Without it, the next session has no high-signal
            # re-entry point — emit a warning but don't block the archive.
            session_handoff_path = (
                self.archive_dir
                / "session-handoff"
                / build_session_doc_filename(self.date_yyyymmdd, self.session_num_padded,
                                             "session-handoff.md", self.stream_slug)
            )
            if session_handoff_path.exists():
                files_to_commit.append(
                    str(session_handoff_path.relative_to(self.project_dir))
                )
            else:
                print(
                    f"\nWarning: no session-handoff file found at "
                    f"{session_handoff_path.relative_to(self.project_dir)} — "
                    f"the next session will have no re-entry point.",
                    file=sys.stderr,
                )

            # Finalized session manifest (written by finalize_manifest in run()).
            manifest_dir = (self.archive_dir / "sessions"
                            / f"{self.date_yyyymmdd}-{self.session_id}")
            if not (manifest_dir / "manifest.json").exists():
                # Synthesized (no UUID) manifests key on conversation_id.
                manifest_dir = self.archive_dir / "sessions" / self.conversation_id
            manifest_file = manifest_dir / "manifest.json"
            if manifest_file.exists():
                files_to_commit.append(
                    str(manifest_file.relative_to(self.project_dir))
                )

            if self.stream_slug:
                # Only record last_handoff if the handoff file actually exists;
                # otherwise the next session's prior-context lookup would point
                # at a nonexistent path.
                handoff_rel = (str(session_handoff_path.relative_to(self.archive_dir))
                               if session_handoff_path.exists() else None)
                result = release_claim_for_session(
                    archive_dir=self.archive_dir,
                    slug=self.stream_slug,
                    session_id=self.session_id,
                    new_handoff=handoff_rel,
                    now_date=datetime.now().strftime("%Y-%m-%d %H:%M"),
                )
                # Stage the per-stream JSON whenever release wrote to it.
                # Stolen claims leave the file untouched, so skip in that case.
                stream_file = _streams.stream_path(self.archive_dir, self.stream_slug)
                if not result.stolen and stream_file.exists():
                    files_to_commit.append(
                        str(stream_file.relative_to(self.project_dir))
                    )
                if result.stolen and session_handoff_path.exists():
                    held = _streams.read_stream(self.archive_dir, self.stream_slug)
                    body = session_handoff_path.read_text(encoding="utf-8")
                    session_handoff_path.write_text(
                        prepend_stolen_note(
                            body, slug=self.stream_slug,
                            actual_holder=result.actual_holder,
                            since=(held.since if held and held.since else "unknown"),
                        ),
                        encoding="utf-8",
                    )
                    print(f"WARNING: Stream `{self.stream_slug}` was reassigned to "
                          f"{result.actual_holder}; handoff prepended with note.")
                elif result.stolen:
                    print(f"WARNING: Stream `{self.stream_slug}` was reassigned to "
                          f"{result.actual_holder}, but no handoff file exists to annotate.",
                          file=sys.stderr)

            # Build commit message with date
            commit_message = f"Add transcript for session {self.date_display}"

            # Route the commit by layout: container → archive_sync (paths
            # relative to the archive worktree); in-place → git add/commit +
            # push (paths relative to the project dir).
            if is_container_layout(self.archive_dir):
                container_paths = [
                    str((self.project_dir / p).relative_to(self.archive_dir))
                    for p in files_to_commit
                ]
                _archive.archive_sync(self.archive_dir, container_paths,
                                      commit_message, push=getattr(self, 'push', True))
                print(f"\nArchive synced: {commit_message}")
            else:
                subprocess.run(
                    ['git', 'add'] + files_to_commit,
                    cwd=str(self.project_dir),
                    check=True,
                    capture_output=True
                )
                subprocess.run(
                    ['git', 'commit', '-m', commit_message],
                    cwd=str(self.project_dir),
                    check=True,
                    capture_output=True
                )
                print(f"\nGit commit successful: {commit_message}")
                self._git_push()

        except subprocess.CalledProcessError as e:
            # Don't fail if git commit fails - just report it
            print(f"\nWarning: Git commit failed: {e}")
        except Exception as e:
            print(f"\nWarning: Could not commit to git: {e}")

    def _git_push(self) -> None:
        """Best-effort push of the archive commit. No-op unless self.push.
        Non-fatal: a failure (no upstream, detached HEAD, no remote) warns
        and leaves the local commit in place."""
        if not getattr(self, 'push', True):
            return
        branch = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=str(self.project_dir), capture_output=True, text=True, check=False,
        ).stdout.strip() or 'HEAD'
        try:
            subprocess.run(['git', 'push'], cwd=str(self.project_dir),
                           check=True, capture_output=True)
            print("Pushed to remote.")
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode().strip() if isinstance(e.stderr, bytes) else str(e.stderr or '').strip()
            print(f"\nWarning: git push failed ({stderr}). "
                  f"Push manually with: git push -u origin {branch}")

    def _report_uncommitted_project_changes(self) -> None:
        """Report project-file changes left uncommitted by the archive commit.

        `/end-session` step 1 asks the agent to reconcile the project's living
        state (progress ledger, docs, issues) before archiving, but
        `_git_commit_transcripts` stages archive paths only. Without this
        notice those edits sit dirty while the handler reports a successful
        commit — the reconciliation looks done and isn't. Report-only: project
        files are not ours to commit under an "Add transcript" message.
        """
        if not self._is_git_repo():
            return
        try:
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=str(self.project_dir), capture_output=True, text=True, check=True,
            )
        except (subprocess.CalledProcessError, OSError):
            return  # never let a status probe break an otherwise-good archive

        try:
            archive_rel = self.archive_dir.relative_to(self.project_dir).as_posix()
        except ValueError:
            archive_rel = None

        paths = []
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            path = line[3:]
            # Renames read "old -> new"; the new path is what needs committing.
            if ' -> ' in path:
                path = path.split(' -> ', 1)[1]
            path = path.strip('"')
            if archive_rel and (path == archive_rel or path.startswith(archive_rel + '/')):
                continue
            paths.append(path)

        if not paths:
            return

        shown = paths[:10]
        listing = '\n'.join(f"  {p}" for p in shown)
        if len(paths) > len(shown):
            listing += f"\n  ... and {len(paths) - len(shown)} more"
        print(
            f"\nNotice: {len(paths)} project file(s) changed outside the archive and "
            f"are NOT in the archive commit:\n{listing}\n"
            f"If these are the ledger/doc updates from this session, commit them "
            f"with the work they describe (e.g. `git add -A && git commit`)."
        )

    def _assert_bundle_complete(self) -> None:
        """Post-finalization guardrail: verify exactly one complete manifest for
        this session_id and that every path in files.{transcript,notes,handoff}
        exists on disk. Reports problems to stderr without raising."""
        all_m = _manifest.iter_manifests(self.archive_dir)
        complete = [m for m in all_m
                    if m.get("session_id") == self.session_id
                    and m.get("status") == "complete"]
        orphaned = [m for m in all_m
                    if m.get("session_id") == self.session_id
                    and m.get("status") == "in-progress"]

        if len(complete) != 1:
            print(
                f"\nWarning: expected 1 complete manifest for session "
                f"{self.session_id!r}, found {len(complete)}. "
                f"Check .archive/sessions/ for duplicates.",
                file=sys.stderr,
            )
        if orphaned:
            print(
                f"\nWarning: {len(orphaned)} orphaned in-progress manifest(s) for "
                f"session {self.session_id!r} still exist in .archive/sessions/. "
                f"Remove the stale director(ies) to prevent the next init-session "
                f"from treating this session as still active.",
                file=sys.stderr,
            )

        if not complete:
            return

        files = complete[0].get("files") or {}
        for key in ("transcript", "notes", "handoff"):
            rel = files.get(key)
            if rel is None:
                continue
            if not (self.archive_dir / rel).exists():
                print(
                    f"\nWarning: finalized manifest references {key} at {rel!r} "
                    f"but the file does not exist on disk — it will not be "
                    f"committed. The date prefix in the manifest may not match "
                    f"the file written by init-session.",
                    file=sys.stderr,
                )

    def run(self) -> None:
        """Main execution flow."""
        print(f"Creating transcript for conversation {self.session_num_padded}: {self.title}")
        print(f"Session: {self.session_id}")
        print(f"Output: {self.output_file}")

        # Calculate new version
        current_version = self._read_current_version()
        if self.bump_type == 'major':
            new_version = current_version.bump_major()
        elif self.bump_type == 'minor':
            new_version = current_version.bump_minor()
        else:  # patch
            new_version = current_version.bump_patch()

        print(f"\nVersion: {current_version} -> {new_version} ({self.bump_type} bump)")

        # Prompt for confirmation (unless in dry-run mode)
        if not self.dry_run:
            if not sys.stdin.isatty():
                print(
                    f"Non-interactive: proceeding with version {new_version} "
                    f"({self.bump_type} bump). Pass --dry-run to preview."
                )
            else:
                try:
                    response = input("Continue with this version? [Y/n]: ").strip().lower()
                    if response and response not in ('y', 'yes'):
                        print("Aborted by user.")
                        sys.exit(0)
                except (KeyboardInterrupt, EOFError):
                    print("\nAborted by user.")
                    sys.exit(0)

        if self.dry_run:
            print("\n[DRY RUN MODE]")

        # Parse JSONL and generate transcript
        transcript = self.parse_jsonl()

        # Extract metadata for display
        message_count = len(transcript['dialogue'])
        topics = ', '.join(transcript['summary']['topics'])
        outcomes = '; '.join(transcript['summary']['outcomes'])

        print(f"Messages: {message_count}")
        print(f"Topics: {topics}")
        print(f"Outcomes: {outcomes}")

        if self.dry_run:
            print(f"\nWould write: {self.output_file}")
            print(f"Would update: {self.index_path} (replace placeholder)")
            print(f"Would update: {self.changelog_path} (add entry at top with version {new_version})")
            print("\n[DRY RUN COMPLETE]")
            return

        # Refuse to archive without a handoff at the resolved slug (before any
        # writes, so a failure leaves no partial bundle). --no-handoff overrides.
        self._check_handoff_present()

        # Serialize and scan for PII
        content = json.dumps(transcript, indent=2, ensure_ascii=False)
        findings = self._scan_pii(content)

        if findings and not self.sanitize:
            self._report_findings(findings)
            if not sys.stdin.isatty():
                print(_pii_review_needed_json(findings))
                print(
                    "\nAborted: PII detected in non-interactive context. "
                    "Re-invoke with --sanitize to auto-redact.",
                    file=sys.stderr,
                )
                sys.exit(1)
            try:
                response = input(
                    "Options: [c]ommit anyway / [s]anitize and commit / [a]bort: "
                ).strip().lower()
                if response in ('a', 'abort'):
                    print("Aborted by user.")
                    sys.exit(0)
                elif response in ('s', 'sanitize'):
                    content = self._sanitize_content(content, findings)
                    self._assert_sanitized(content)
                    print("Sanitized." + self._unredacted_note(findings))
                # 'c' or 'commit' or empty: proceed as-is
            except (KeyboardInterrupt, EOFError):
                print("\nAborted by user.")
                sys.exit(0)
        elif findings and self.sanitize:
            self._report_findings(findings)
            content = self._sanitize_content(content, findings)
            self._assert_sanitized(content)
            print("Auto-sanitized (--sanitize flag)."
                  + self._unredacted_note(findings))

        # Write files
        self.write_transcript(transcript, content_override=content)
        print(f"\nTranscript created: {self.output_file}")

        self.finalize_manifest(transcript)
        self._assert_bundle_complete()
        self.update_index(transcript)
        print(f"Index updated: {self.index_path}")

        self.update_changelog(transcript)
        print(f"CHANGELOG updated: {self.changelog_path}")

        # Auto-commit if in git repo
        self._git_commit_transcripts()
        self._report_uncommitted_project_changes()

        print(f"\nDone! Conversation {self.session_num_padded} archived successfully.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='End an LLM session: archive transcript, commit notes + handoff bundle',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 4 "Setup automation framework"
  %(prog)s 5 "Refactor parser logic" --topics "python, refactoring"
  %(prog)s 6 "Debug API issues" --session-id abc123 --dry-run
        """
    )

    parser.add_argument(
        'session_num',
        type=int,
        help='The conversation number (e.g., 4)'
    )
    parser.add_argument(
        'title',
        type=str,
        help='Brief conversation title (3-7 words)'
    )
    parser.add_argument(
        '--topics',
        type=str,
        help='Comma-separated topic list'
    )
    parser.add_argument(
        '--session-id',
        type=str,
        help='Session UUID (auto-detected if not provided)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview without writing files'
    )
    parser.add_argument(
        '--model',
        type=str,
        help='Override model name'
    )
    parser.add_argument(
        '--user',
        type=str,
        help='Override user name'
    )
    parser.add_argument(
        '--minor',
        action='store_true',
        help='Bump minor version (X.Y.Z -> X.Y+1.0)'
    )
    parser.add_argument(
        '--major',
        action='store_true',
        help='Bump major version (X.Y.Z -> X+1.0.0)'
    )
    parser.add_argument(
        '--sanitize',
        action='store_true',
        help='Automatically redact PII (home paths, names) without prompting (now the default; kept for backwards compatibility)'
    )
    parser.add_argument(
        '--no-sanitize',
        action='store_true',
        help='Disable automatic PII redaction (restores the interactive prompt / non-interactive abort)'
    )
    parser.add_argument(
        '--no-push',
        action='store_true',
        help='Skip pushing the archive commit to the remote (default: push)'
    )
    parser.add_argument(
        '--files-modified',
        type=str,
        help='Comma-separated list of modified files (e.g., "file1.py, file2.md")'
    )
    parser.add_argument(
        '--artifacts',
        type=str,
        help='Comma-separated list of archived artifacts (e.g., "artifact1.md, artifact2.md")'
    )
    parser.add_argument(
        '--decisions',
        type=str,
        help='Comma-separated list of decisions made (e.g., "decision1, decision2")'
    )
    parser.add_argument(
        '--next-steps',
        type=str,
        help='Comma-separated list of next steps (e.g., "step1, step2")'
    )
    parser.add_argument(
        '--stream',
        default=None,
        help='Stream slug this session belongs to (default: free)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help="Re-finalize even if this session number's manifest is already "
             "complete (a session whose stream claim was already released also "
             "needs an explicit --stream <slug>)"
    )
    parser.add_argument(
        '--project-path',
        default=None,
        metavar='PATH',
        help='Explicit project root to search from (default: cwd). '
             'Use this when running from a parent workspace to target a specific project.'
    )
    parser.add_argument(
        '--infer-session-id',
        action='store_true',
        help='Accept freshest-JSONL inference when no manifest carries this '
             'session number (pre-manifest legacy sessions only). Refused when '
             'any other in-progress manifest exists. Without this flag, a '
             'missing numbered manifest is a hard error (issue #108).'
    )
    parser.add_argument(
        '--allow-empty',
        action='store_true',
        help='Archive even when a transcript file was found but imported zero '
             'dialogue entries (normally a broken importer, not an empty session)'
    )
    parser.add_argument(
        '--no-handoff',
        action='store_true',
        help='Archive without requiring a session-handoff at the resolved stream slug'
    )

    args = parser.parse_args()

    # Determine bump type
    bump_type = 'patch'
    if args.major:
        bump_type = 'major'
    elif args.minor:
        bump_type = 'minor'

    try:
        generator = TranscriptGenerator(
            session_num=args.session_num,
            title=args.title,
            stream_slug=args.stream,
            session_id=args.session_id,
            topics=args.topics,
            dry_run=args.dry_run,
            sanitize=not args.no_sanitize,
            model=args.model,
            user=args.user,
            bump_type=bump_type,
            push=not args.no_push,
            force=args.force,
            allow_empty=args.allow_empty,
            no_handoff=args.no_handoff,
            project_path=args.project_path,
            infer_session_id=args.infer_session_id,
            files_modified=getattr(args, 'files_modified', ''),
            artifacts=getattr(args, 'artifacts', ''),
            decisions=getattr(args, 'decisions', ''),
            next_steps=getattr(args, 'next_steps', '')
        )
        generator.run()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
