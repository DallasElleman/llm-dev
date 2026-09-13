"""Harness session helpers — shared by init-session, end-session, stream.

Claude Code stores conversations as `~/.claude/projects/<hyphen-cwd>/<uuid>.jsonl`.
Grok Build stores them as `$GROK_HOME/sessions/<urlencode(cwd)>/<uuidv7>/`
(directory; `updates.jsonl` is the ACP log). Codex stores exact-ID rollouts in
`$CODEX_HOME/sessions/YYYY/MM/DD/`. Live-session guessing remains limited to
Grok and Claude; Codex import requires the conversation UUID.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

PROJECTS_DIR = Path.home() / ".claude" / "projects"
GROK_HOME = Path(os.environ.get("GROK_HOME", Path.home() / ".grok"))
GROK_SESSIONS_DIR = GROK_HOME / "sessions"
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
CODEX_SESSIONS_DIR = CODEX_HOME / "sessions"
RECENT_WINDOW_SECONDS = 300  # files modified within last 5 min are "ours"
# Shortest stored id accepted as a prefix of a real transcript stem. A UUID's
# first block is 8 hex chars; anything shorter matches too much to be evidence.
_MIN_PREFIX_LEN = 8
RENAME_RE = re.compile(r'named this session "([^"]+)"')

MODEL_FAMILIES = ('opus', 'sonnet', 'haiku', 'fable')

# Bracketed variant suffix on a model id, e.g. `claude-opus-5[1m]` (the 1M
# context window build). It qualifies the deployment, not the model version.
MODEL_VARIANT_RE = re.compile(r'\[[^\]]*\]\s*$')

SYNTHETIC_ID_RE = re.compile(
    r'^(?:claude|grok)-\d{3}-[0-9a-f]{6}$', re.IGNORECASE
)
_EXPLICIT_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    re.IGNORECASE,
)
_UUIDISH_COMPACT_RE = re.compile(r'^(?:[0-9a-f]{8}|[0-9a-f]{31,33})$', re.IGNORECASE)
_SAFE_STEM_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')


def _looks_like_uuid(value: str) -> bool:
    """Keep malformed UUIDs and eight-hex job IDs out of legacy-stem fallback."""
    if _UUIDISH_COMPACT_RE.fullmatch(value):
        return True
    parts = value.split('-')
    return (len(parts) == 5 and 30 <= len(value) <= 40
            and 7 <= len(parts[0]) <= 9
            and bool(re.fullmatch(r'[0-9a-f]+', parts[0], re.IGNORECASE))
            and all(part.isascii() and part.isalnum() for part in parts[1:]))


def validate_explicit_session_id(session_id: str, cwd: Path) -> str:
    """Validate a newly supplied ID before it can bind archive state.

    Stored legacy IDs and the general transcript resolver have separate recovery
    rules. In particular, a unique *prefix* lookup is never proof that the
    prefix is the conversation's complete identity.
    """
    if isinstance(session_id, str):
        if _EXPLICIT_UUID_RE.fullmatch(session_id):
            return str(uuid.UUID(session_id))
        if SYNTHETIC_ID_RE.fullmatch(session_id):
            return session_id
        if (not _looks_like_uuid(session_id)
                and _SAFE_STEM_RE.fullmatch(session_id)
                and session_id.lower() != 'unknown'
                and not session_id.lower().startswith('agent-')):
            # Preserve non-UUID Claude stems actually present on disk. Only
            # exact, regular files count: find_session_jsonl also accepts
            # prefixes, which is the mistake this guard closes.
            scoped = PROJECTS_DIR / encode_claude_cwd(cwd) / f'{session_id}.jsonl'
            try:
                if scoped.is_file() and not scoped.is_symlink():
                    return session_id
                matches = list(PROJECTS_DIR.rglob(f'{session_id}.jsonl'))
                if (len(matches) == 1 and matches[0].is_file()
                        and not matches[0].is_symlink()):
                    return session_id
            except OSError:
                pass
    raise ValueError(
        f'Invalid --session-id {session_id!r}: supply the full conversation '
        'UUID or an exact Claude transcript stem. A Claude background-job '
        'directory uses a short job ID; read the full `sessionId` in '
        '~/.claude/jobs/<job-id>/state.json.'
    )


@dataclass(frozen=True)
class HarnessContext:
    """Resolved identity for the live conversation, if one can be found."""

    harness: str
    session_id: str
    cwd: Path | None
    model: str | None
    transcript_path: Path | None
    title: str | None
    mtime: float


def encode_claude_cwd(cwd: Path) -> str:
    """Claude project-dir encoding: slashes become hyphens."""
    return str(cwd.resolve()).replace("/", "-")


def encode_grok_cwd(cwd: Path) -> str:
    """Grok project-dir encoding: full URL-encode of the absolute cwd."""
    return quote(str(cwd.resolve()), safe="")


def derive_model_display_name(model_id: str | None) -> str:
    """Derive a human-readable display name from a model id.

    Parses Claude families (opus/sonnet/haiku/fable) and Grok `grok-*` ids.
    Falls back to the raw id — never a guessed name — when the id doesn't
    match a known shape. A missing id still returns 'Claude' (the historical
    default; callers that know the harness should pass an id).
    """
    if not model_id:
        return 'Claude'

    # Strip a bracketed variant suffix before parsing; leaving it attached to
    # the last segment makes that segment non-numeric and silently drops the
    # version (`claude-opus-5[1m]` -> 'Claude Opus' instead of 'Claude Opus 5').
    normalized = MODEL_VARIANT_RE.sub('', model_id.lower())

    if normalized.startswith('grok'):
        rest = normalized[4:].lstrip('-').replace('-', '.')
        return f'Grok {rest}' if rest else 'Grok'

    parts = normalized.split('-')
    if parts and parts[0] == 'claude':
        parts = parts[1:]

    # Drop a trailing snapshot date suffix, e.g. `...-20251001`.
    if parts and len(parts[-1]) == 8 and parts[-1].isdigit():
        parts = parts[:-1]

    family_idx = next((i for i, p in enumerate(parts) if p in MODEL_FAMILIES), None)
    if family_idx is None:
        return model_id

    family = parts[family_idx].capitalize()
    version = '.'.join(p for i, p in enumerate(parts) if i != family_idx and p.isdigit())

    return f'Claude {family} {version}' if version else f'Claude {family}'


def is_synthetic_session_id(session_id: str | None) -> bool:
    """True for the `claude-NNN-hex` / `grok-NNN-hex` fallback minted when
    no live harness session was found at init time."""
    return bool(session_id and SYNTHETIC_ID_RE.match(session_id))


def _is_grok_subagent(session_dir: Path) -> bool:
    summary = session_dir / "summary.json"
    if not summary.is_file():
        return False
    try:
        data = json.loads(summary.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    if data.get("session_kind") == "subagent":
        return True
    info = data.get("info") or {}
    return info.get("session_kind") == "subagent"


def _grok_title_and_model(session_dir: Path) -> tuple[str | None, str | None]:
    summary = session_dir / "summary.json"
    if not summary.is_file():
        return None, None
    try:
        data = json.loads(summary.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    title = data.get("generated_title")
    model = data.get("current_model_id")
    return (title if isinstance(title, str) and title else None,
            model if isinstance(model, str) and model else None)


def _grok_session_mtime(session_dir: Path) -> float:
    for name in ("updates.jsonl", "summary.json"):
        path = session_dir / name
        try:
            if path.is_file():
                return path.stat().st_mtime
        except OSError:
            continue
    try:
        return session_dir.stat().st_mtime
    except OSError:
        return 0.0


def _iter_grok_main_sessions(search_root: Path):
    """Yield (dir, mtime) for non-subagent Grok session directories."""
    try:
        children = list(search_root.iterdir())
    except OSError:
        return
    for child in children:
        if not child.is_dir():
            continue
        # Skip the nested `subagents/` container if present; sibling copies
        # of those sessions also carry session_kind=subagent.
        if child.name == "subagents":
            continue
        if _is_grok_subagent(child):
            continue
        if not (child / "summary.json").is_file() and not (child / "updates.jsonl").is_file():
            continue
        yield child, _grok_session_mtime(child)


def _recent_grok_context(cwd: Path | None, threshold: float) -> HarnessContext | None:
    if not GROK_SESSIONS_DIR.exists():
        return None

    search_roots: list[Path] = []
    scoped = None
    if cwd is not None:
        scoped = GROK_SESSIONS_DIR / encode_grok_cwd(cwd)
        if scoped.is_dir():
            search_roots.append(scoped)
    if not search_roots:
        try:
            search_roots.extend(
                p for p in GROK_SESSIONS_DIR.iterdir() if p.is_dir()
            )
        except OSError:
            return None

    best: tuple[float, Path] | None = None
    for root in search_roots:
        for session_dir, mtime in _iter_grok_main_sessions(root):
            if mtime < threshold:
                continue
            if best is None or mtime > best[0]:
                best = (mtime, session_dir)

    if best is None:
        return None
    mtime, session_dir = best
    updates = session_dir / "updates.jsonl"
    title, model = _grok_title_and_model(session_dir)
    return HarnessContext(
        harness="grok",
        session_id=session_dir.name,
        cwd=cwd,
        model=model,
        transcript_path=updates if updates.is_file() else session_dir,
        title=title,
        mtime=mtime,
    )


def _recent_claude_context(cwd: Path | None, threshold: float) -> HarnessContext | None:
    if not PROJECTS_DIR.exists():
        return None

    search_root = PROJECTS_DIR
    if cwd is not None:
        proj = PROJECTS_DIR / encode_claude_cwd(cwd)
        if proj.is_dir():
            search_root = proj

    candidates: list[Path] = []
    try:
        for jsonl in search_root.rglob("*.jsonl"):
            if jsonl.name.startswith("agent-"):
                continue
            try:
                if jsonl.stat().st_mtime >= threshold:
                    candidates.append(jsonl)
            except OSError:
                continue
    except OSError:
        return None

    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        mtime = latest.stat().st_mtime
    except OSError:
        mtime = 0.0
    return HarnessContext(
        harness="claude",
        session_id=latest.stem,
        cwd=cwd,
        model=None,
        transcript_path=latest,
        title=find_session_title(latest),
        mtime=mtime,
    )


def detect_harness_context(cwd: Path | None = None) -> HarnessContext | None:
    """Return the most recently active harness session in the 5-minute window.

    When `cwd` is given, both scanners scope to that project directory
    (URL-encoded for Grok, hyphen-encoded for Claude). A Grok `subagent`
    session is never chosen automatically.
    """
    threshold = time.time() - RECENT_WINDOW_SECONDS
    grok = _recent_grok_context(cwd, threshold)
    claude = _recent_claude_context(cwd, threshold)
    if grok and claude:
        return grok if grok.mtime >= claude.mtime else claude
    return grok or claude


def recent_claude_session_ids(cwd: Path | None = None) -> list[str]:
    """Every Claude session id active in the recency window for this project,
    newest first.

    `find_session_id` returns only `max(mtime)`. When two conversations are
    open on the same project, both sit inside the window and the winner is
    whichever one last wrote a line — not necessarily the one running the
    command. That is how a session number gets bound to the wrong
    conversation (issue #98 #1), and the binding is invisible until archive
    time. Callers use this to detect the ambiguity and say so.
    """
    if not PROJECTS_DIR.exists():
        return []
    search_root = PROJECTS_DIR
    if cwd is not None:
        proj = PROJECTS_DIR / encode_claude_cwd(cwd)
        if proj.is_dir():
            search_root = proj
    threshold = time.time() - RECENT_WINDOW_SECONDS
    found: list[tuple[float, str]] = []
    try:
        for jsonl in search_root.rglob("*.jsonl"):
            if jsonl.name.startswith("agent-"):
                continue
            try:
                mtime = jsonl.stat().st_mtime
            except OSError:
                continue
            if mtime >= threshold:
                found.append((mtime, jsonl.stem))
    except OSError:
        return []
    return [sid for _, sid in sorted(found, reverse=True)]


def find_session_id(cwd: Path | None = None) -> str:
    """Return the current harness session UUID, or 'unknown'.

    Looks for a Grok main session (skipping subagents) and a Claude Code
    JSONL modified within the last 5 minutes; the newer of the two wins.
    When `cwd` is given, each scanner is scoped to that project's encoded
    dir so a concurrent session in a *different* project can't be returned.
    Falls back to a global search when the encoded dir is absent.
    """
    ctx = detect_harness_context(cwd)
    return ctx.session_id if ctx else "unknown"


def find_session_title(jsonl_path: Path) -> str | None:
    """Extract the most recent /rename title from a Claude Code session JSONL.

    Returns the latest title (sessions can be renamed multiple times), or
    None if the file has no rename events.
    """
    if not jsonl_path.exists():
        return None
    latest_title: str | None = None
    try:
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                if "named this session" not in line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = d.get("message", {})
                content = msg.get("content", "")
                texts = []
                if isinstance(content, str):
                    texts.append(content)
                elif isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            texts.append(c.get("text", ""))
                for t in texts:
                    m = RENAME_RE.search(t)
                    if m:
                        latest_title = m.group(1)
    except OSError:
        return None
    return latest_title


def find_session_jsonl(session_id: str, cwd: Path) -> Path | None:
    """Locate the JSONL file for a given session ID under the encoded-cwd dir.

    Claude Code stores per-project sessions in ~/.claude/projects/<encoded-cwd>/.
    The encoded form replaces slashes with hyphens (the leading slash becomes the
    single leading hyphen).
    """
    if not PROJECTS_DIR.exists():
        return None
    encoded = encode_claude_cwd(cwd)
    candidate = PROJECTS_DIR / encoded / f"{session_id}.jsonl"
    if candidate.exists():
        return candidate
    # Fallback: search anywhere
    for jsonl in PROJECTS_DIR.rglob(f"{session_id}.jsonl"):
        return jsonl
    # Both lookups above are exact-stem. A stored id that is a *prefix* of the
    # real stem — a truncated paste, or a job id mistaken for a session id —
    # therefore misses a file whose name it is a prefix of, and the caller
    # falls through to substituting whatever session is live. Accept a prefix
    # only when it identifies exactly one transcript; an ambiguous prefix is
    # no better than none.
    if len(session_id) >= _MIN_PREFIX_LEN:
        hits = [p for p in PROJECTS_DIR.rglob(f"{session_id}*.jsonl")
                if not p.name.startswith("agent-")]
        if len(hits) == 1:
            return hits[0]
    return None


def find_grok_session_dir(session_id: str, cwd: Path | None = None) -> Path | None:
    """Locate a Grok session directory by id (does not skip subagents)."""
    if not session_id or session_id == "unknown" or not GROK_SESSIONS_DIR.exists():
        return None
    if cwd is not None:
        scoped = GROK_SESSIONS_DIR / encode_grok_cwd(cwd) / session_id
        if scoped.is_dir():
            return scoped
    try:
        for proj in GROK_SESSIONS_DIR.iterdir():
            if not proj.is_dir():
                continue
            cand = proj / session_id
            if cand.is_dir():
                return cand
    except OSError:
        return None
    return None


def _first_codex_session_meta(source: Path) -> dict | None:
    """Read the owning metadata, not later metadata copied during a fork."""
    try:
        with source.open("r", encoding="utf-8") as fh:
            for index, line in enumerate(fh):
                if index >= 100:
                    break
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict) or entry.get("type") != "session_meta":
                    continue
                payload = entry.get("payload")
                return payload if isinstance(payload, dict) else None
    except OSError:
        return None
    return None


def find_codex_rollout(session_id: str, cwd: Path) -> Path | None:
    """Find one rollout whose filename, owner id, and project all agree.

    A child rollout may repeat its parent's `session_id` in metadata. Only
    `payload.id` identifies the file's own conversation; accepting that other
    field would silently archive a subagent as its parent.
    """
    try:
        canonical_id = str(uuid.UUID(session_id))
    except (TypeError, ValueError, AttributeError):
        return None
    if session_id.lower() != canonical_id or not CODEX_SESSIONS_DIR.is_dir():
        return None

    matches: list[Path] = []
    try:
        candidates = CODEX_SESSIONS_DIR.rglob(f"rollout-*-{canonical_id}.jsonl")
        for source in candidates:
            if source.is_symlink() or not source.is_file():
                continue
            meta = _first_codex_session_meta(source)
            if not meta or meta.get("id") != canonical_id:
                continue
            session_cwd = meta.get("cwd")
            if not isinstance(session_cwd, str) or not session_cwd:
                continue
            try:
                # A session may start in a project subdirectory, but never
                # attribute a different project's rollout to this archive.
                Path(session_cwd).resolve().relative_to(cwd.resolve())
            except (OSError, ValueError):
                continue
            matches.append(source)
            if len(matches) > 1:
                return None  # ambiguous duplicate id; never pick by mtime
    except OSError:
        return None
    return matches[0] if matches else None


def find_session_source(session_id: str, cwd: Path) -> Path | None:
    """Locate the transcript file for a stored session id.

    Grok: `<sessions>/<urlencode(cwd)>/<id>/updates.jsonl` (or the session dir).
    Claude: `<projects>/<hyphen-cwd>/<id>.jsonl`.
    Codex: `<sessions>/YYYY/MM/DD/rollout-<timestamp>-<id>.jsonl`.
    """
    if not session_id or session_id == "unknown":
        return None
    grok_dir = find_grok_session_dir(session_id, cwd)
    if grok_dir is not None:
        updates = grok_dir / "updates.jsonl"
        return updates if updates.is_file() else grok_dir
    codex = find_codex_rollout(session_id, cwd)
    if codex is not None:
        return codex
    return find_session_jsonl(session_id, cwd)


def find_session_title_any(session_id: str, cwd: Path | None = None) -> str | None:
    """Best-effort title: Grok `generated_title`, else Claude /rename text."""
    if not session_id or session_id == "unknown":
        return None
    grok_dir = find_grok_session_dir(session_id, cwd)
    if grok_dir is not None:
        title, _ = _grok_title_and_model(grok_dir)
        if title:
            return title
    if cwd is None:
        return None
    jsonl = find_session_jsonl(session_id, cwd)
    if jsonl is not None:
        return find_session_title(jsonl)
    return None


def synthetic_session_id(num_padded: str, hex_suffix: str | None = None) -> str:
    """Mint a fallback id when no live harness session is visible.

    Prefers a `grok-` prefix when a Grok sessions tree exists, otherwise
    keeps the historical `claude-` prefix so Claude-only installs don't
    change on-disk identity.
    """
    import os as _os
    suffix = hex_suffix if hex_suffix is not None else _os.urandom(3).hex()
    prefix = "grok" if GROK_SESSIONS_DIR.exists() else "claude"
    return f"{prefix}-{num_padded}-{suffix}"


def decode_grok_cwd(encoded: str) -> str:
    """Inverse of `encode_grok_cwd` (for tests / diagnostics)."""
    return unquote(encoded)
