"""Claude Code session helpers — shared by init-session, end-session, stream."""
import json
import re
import time
from pathlib import Path


PROJECTS_DIR = Path.home() / ".claude" / "projects"
RECENT_WINDOW_SECONDS = 300  # files modified within last 5 min are "ours"
RENAME_RE = re.compile(r'named this session "([^"]+)"')

MODEL_FAMILIES = ('opus', 'sonnet', 'haiku', 'fable')

# Bracketed variant suffix on a model id, e.g. `claude-opus-5[1m]` (the 1M
# context window build). It qualifies the deployment, not the model version.
MODEL_VARIANT_RE = re.compile(r'\[[^\]]*\]\s*$')


def derive_model_display_name(model_id: str | None) -> str:
    """Derive a human-readable display name from a Claude model id.

    Parses the family (opus/sonnet/haiku/fable) and version numbers out of
    ids like `claude-opus-4-8` or `claude-haiku-4-5-20251001` instead of
    relying on a hand-maintained id->name table that goes stale every time a
    new model ships. Falls back to the raw id — never a guessed name — when
    the id doesn't match the known shape.
    """
    if not model_id:
        return 'Claude'

    # Strip a bracketed variant suffix before parsing; leaving it attached to
    # the last segment makes that segment non-numeric and silently drops the
    # version (`claude-opus-5[1m]` -> 'Claude Opus' instead of 'Claude Opus 5').
    normalized = MODEL_VARIANT_RE.sub('', model_id.lower())

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


def find_session_id(cwd: Path | None = None) -> str:
    """Return the current Claude Code session UUID, or 'unknown'.

    Looks in ~/.claude/projects/ for the most recently modified *.jsonl,
    excluding agent-* files, modified within the last 5 minutes. When `cwd`
    is given and its encoded project dir exists, the search is scoped to that
    dir so a concurrent session in a *different* project can't be returned.
    Falls back to a global search when the encoded dir is absent.
    """
    if not PROJECTS_DIR.exists():
        return "unknown"

    search_root = PROJECTS_DIR
    if cwd is not None:
        encoded = str(cwd.resolve()).replace("/", "-")
        proj = PROJECTS_DIR / encoded
        if proj.is_dir():
            search_root = proj

    threshold = time.time() - RECENT_WINDOW_SECONDS
    candidates = []
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
        return "unknown"

    if not candidates:
        return "unknown"
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return latest.stem


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
    encoded = str(cwd.resolve()).replace("/", "-")
    candidate = PROJECTS_DIR / encoded / f"{session_id}.jsonl"
    if candidate.exists():
        return candidate
    # Fallback: search anywhere
    for jsonl in PROJECTS_DIR.rglob(f"{session_id}.jsonl"):
        return jsonl
    return None
