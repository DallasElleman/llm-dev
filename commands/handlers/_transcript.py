"""Harness transcript importers.

Provider parsers produce the same dialogue / file-op / model fields that
`end-session` already archives. Claude JSONL stays the reference shape;
Grok `updates.jsonl` (ACP `session/update` chunks) is a second importer
behind the same `TranscriptImporter` probe/import contract (#84 / #94).

Stdlib only. Unknown or missing sources degrade to an empty import plus
a warning — they must not raise.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import _session


# Grok tool names → the Claude names end-session already keys topics/outcomes on.
_GROK_TOOL_ALIAS = {
    "write": "Write",
    "search_replace": "Edit",
    "run_terminal_command": "Bash",
    "spawn_subagent": "Task",
    "todo_write": "TodoWrite",
    "read_file": "Read",
    "grep": "Grep",
    "list_dir": "Glob",
    "ask_user_question": "AskUserQuestion",
}


@dataclass
class ImportResult:
    """Canonical fields extracted from a harness transcript."""

    harness: str
    source_format: str
    messages: list[dict] = field(default_factory=list)
    model_id: str | None = None
    model_name: str | None = None
    files_created: list[dict] = field(default_factory=list)
    files_modified: list[dict] = field(default_factory=list)
    tools_used: Counter = field(default_factory=Counter)
    started_at: str | None = None
    ended_at: str | None = None
    warnings: list[str] = field(default_factory=list)
    title: str | None = None


class TranscriptImporter(Protocol):
    def probe(self, source: Path) -> bool: ...
    def import_transcript(self, source: Path, fallback_ts: str) -> ImportResult: ...


def unix_to_iso(ts) -> str | None:
    """Convert a unix timestamp (int/float/numeric string) to ISO-8601 Z."""
    try:
        value = float(ts)
    except (TypeError, ValueError):
        return None
    # Heuristic: ms timestamps are > 1e12.
    if value > 1e12:
        value = value / 1000.0
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (OverflowError, OSError, ValueError):
        return None


def _decode_params(raw):
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    if isinstance(raw, dict):
        return raw
    return {}


_CLAUDE_PROBE_SKIP_NAMES = {"updates.jsonl", "chat_history.jsonl", "events.jsonl"}
_CLAUDE_TURN_TYPES = ("user", "assistant")
# A real session opens with metadata envelopes (last-prompt, mode,
# permission-mode, bridge-session, attachment, ...) before the first turn;
# bound the scan instead of reading an entire multi-MB transcript to answer
# a yes/no.
_CLAUDE_PROBE_MAX_LINES = 500


class ClaudeJsonlImporter:
    """Claude Code `~/.claude/projects/<hyphen-cwd>/<uuid>.jsonl`."""

    def probe(self, source: Path) -> bool:
        if not source.is_file() or source.suffix != ".jsonl":
            return False
        if source.name in _CLAUDE_PROBE_SKIP_NAMES:
            return False
        try:
            with source.open("r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i >= _CLAUDE_PROBE_MAX_LINES:
                        break
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("type") in _CLAUDE_TURN_TYPES:
                        return True
                    if entry.get("type") and "message" in entry:
                        return True
                    # Otherwise: a metadata envelope — keep scanning.
        except OSError:
            return False
        return False

    def import_transcript(self, source: Path, fallback_ts: str) -> ImportResult:
        messages: list[dict] = []
        model_id = None
        files_created: list[dict] = []
        files_modified: list[dict] = []
        tools_used: Counter = Counter()
        first_ts = last_ts = None

        try:
            fh = source.open("r", encoding="utf-8")
        except OSError as exc:
            return ImportResult(
                harness="claude",
                source_format="claude_jsonl",
                warnings=[f"Could not read Claude JSONL: {exc}"],
                started_at=fallback_ts,
                ended_at=fallback_ts,
            )

        with fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg_type = entry.get("type")
                if msg_type not in ("user", "assistant"):
                    continue
                if entry.get("isMeta"):
                    continue

                timestamp = entry.get("timestamp") or fallback_ts
                if timestamp:
                    if first_ts is None:
                        first_ts = timestamp
                    last_ts = timestamp

                message_obj = entry.get("message", {}) or {}
                content = message_obj.get("content", "")

                if msg_type == "assistant" and "model" in message_obj:
                    model_id = message_obj.get("model")

                message_text, tool_calls = _parse_claude_content(
                    content, tools_used, files_created, files_modified
                )
                if not message_text.strip() and not tool_calls:
                    continue

                msg = {
                    "speaker": msg_type,
                    "timestamp": timestamp,
                    "message": message_text,
                }
                if msg_type == "assistant" and tool_calls:
                    msg["tool_calls"] = tool_calls
                messages.append(msg)

        return ImportResult(
            harness="claude",
            source_format="claude_jsonl",
            messages=messages,
            model_id=model_id,
            model_name=_session.derive_model_display_name(model_id) if model_id else None,
            files_created=files_created,
            files_modified=files_modified,
            tools_used=tools_used,
            started_at=first_ts or fallback_ts,
            ended_at=last_ts or fallback_ts,
        )


def _parse_claude_content(
    content,
    tools_used: Counter,
    files_created: list[dict],
    files_modified: list[dict],
) -> tuple[str, list[dict]]:
    if isinstance(content, str):
        if "<command-name>" in content or "<local-command" in content:
            return "", []
        return content, []

    if not isinstance(content, list):
        return "", []

    text_parts: list[str] = []
    tool_calls: list[dict] = []
    created_paths = {f["path"] for f in files_created}
    modified_paths = {f["path"] for f in files_modified}

    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            text_parts.append(item.get("text", ""))
        elif item.get("type") == "tool_use":
            tool_name = item.get("name", "Unknown")
            inp = item.get("input", {}) or {}
            tools_used[tool_name] += 1
            if tool_name == "Write":
                path = inp.get("file_path", "")
                if path and path not in created_paths:
                    files_created.append({"path": path, "description": "Created file"})
                    created_paths.add(path)
            elif tool_name == "Edit":
                path = inp.get("file_path", "")
                if path and path not in modified_paths:
                    files_modified.append({"path": path, "changes": "Modified file"})
                    modified_paths.add(path)
            tool_calls.append({
                "tool": tool_name,
                "description": _format_tool_description(tool_name, inp),
            })

    return "\n".join(text_parts), tool_calls


def _format_tool_description(tool_name: str, inp: dict) -> str:
    if tool_name == "Read":
        return f"Read {inp.get('file_path') or inp.get('target_file') or 'file'}"
    if tool_name == "Write":
        return f"Write to {inp.get('file_path') or inp.get('path') or 'file'}"
    if tool_name == "Edit":
        return f"Edit {inp.get('file_path') or inp.get('path') or 'file'}"
    if tool_name == "Bash":
        cmd = inp.get("command", "")
        if len(cmd) > 80:
            return f"Run: {cmd[:80]}..."
        return f"Run: {cmd}"
    if tool_name == "Glob":
        return f"Search pattern: {inp.get('pattern') or inp.get('target_directory') or ''}"
    if tool_name == "Grep":
        return f"Search for: {inp.get('pattern', '')}"
    if tool_name == "Task":
        return f"Spawn agent: {inp.get('description', '')}"
    if tool_name == "TodoWrite":
        return "Update todo list"
    return str(inp)[:100]


class GrokUpdatesImporter:
    """Grok Build `$GROK_HOME/sessions/<urlencode(cwd)>/<uuidv7>/updates.jsonl`."""

    def probe(self, source: Path) -> bool:
        if source.is_dir():
            return (source / "updates.jsonl").is_file() or (source / "summary.json").is_file()
        if source.is_file() and source.name == "updates.jsonl":
            return True
        return False

    def import_transcript(self, source: Path, fallback_ts: str) -> ImportResult:
        session_dir = source if source.is_dir() else source.parent
        updates = session_dir / "updates.jsonl"
        summary = _read_grok_summary(session_dir)

        model_id = (summary or {}).get("current_model_id")
        title = (summary or {}).get("generated_title")
        warnings: list[str] = []

        if not updates.is_file():
            return ImportResult(
                harness="grok",
                source_format="grok_updates_jsonl",
                model_id=model_id,
                model_name=_session.derive_model_display_name(model_id) if model_id else None,
                title=title,
                started_at=_grok_summary_ts(summary, "created_at") or fallback_ts,
                ended_at=_grok_summary_ts(summary, "updated_at") or fallback_ts,
                warnings=["Grok session dir has no updates.jsonl; archived without dialogue"],
            )

        messages: list[dict] = []
        files_created: list[dict] = []
        files_modified: list[dict] = []
        tools_used: Counter = Counter()
        first_ts = last_ts = None

        pending_kind: str | None = None
        pending_text: list[str] = []
        pending_ts: str | None = None

        def flush() -> None:
            nonlocal pending_kind, pending_text, pending_ts
            if not pending_kind:
                return
            text = "".join(pending_text)
            if text.strip():
                speaker = "user" if pending_kind == "user_message_chunk" else "assistant"
                messages.append({
                    "speaker": speaker,
                    "timestamp": pending_ts or fallback_ts,
                    "message": text,
                })
            pending_kind = None
            pending_text = []
            pending_ts = None

        try:
            fh = updates.open("r", encoding="utf-8")
        except OSError as exc:
            return ImportResult(
                harness="grok",
                source_format="grok_updates_jsonl",
                model_id=model_id,
                model_name=_session.derive_model_display_name(model_id) if model_id else None,
                title=title,
                warnings=[f"Could not read Grok updates.jsonl: {exc}"],
                started_at=fallback_ts,
                ended_at=fallback_ts,
            )

        with fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                iso_ts = unix_to_iso(entry.get("timestamp")) or fallback_ts
                if iso_ts:
                    if first_ts is None:
                        first_ts = iso_ts
                    last_ts = iso_ts

                params = _decode_params(entry.get("params"))
                update = params.get("update") or {}
                if isinstance(update, str):
                    try:
                        update = json.loads(update)
                    except json.JSONDecodeError:
                        update = {}
                kind = update.get("sessionUpdate") or update.get("session_update")

                if kind in ("user_message_chunk", "agent_message_chunk"):
                    if pending_kind and pending_kind != kind:
                        flush()
                    if pending_kind is None:
                        pending_kind = kind
                        pending_ts = iso_ts
                    content = update.get("content") or {}
                    if isinstance(content, dict):
                        pending_text.append(content.get("text") or "")
                    meta = update.get("_meta") or {}
                    if not model_id:
                        model_id = meta.get("modelId") or meta.get("model_id")
                    continue

                if kind == "tool_call":
                    flush()
                    tool_name, inp = _grok_tool(update)
                    canonical = _GROK_TOOL_ALIAS.get(tool_name, tool_name)
                    tools_used[canonical] += 1
                    _record_file_op(canonical, inp, files_created, files_modified)
                    messages.append({
                        "speaker": "assistant",
                        "timestamp": iso_ts,
                        "message": "",
                        "tool_calls": [{
                            "tool": canonical,
                            "description": _format_tool_description(canonical, inp),
                        }],
                    })
                    continue

                # thought / plan / tool_call_update / turn_completed / unknown
                flush()

        flush()

        if not messages:
            warnings.append("Grok updates.jsonl parsed but produced no dialogue turns")

        return ImportResult(
            harness="grok",
            source_format="grok_updates_jsonl",
            messages=messages,
            model_id=model_id,
            model_name=_session.derive_model_display_name(model_id) if model_id else None,
            files_created=files_created,
            files_modified=files_modified,
            tools_used=tools_used,
            started_at=first_ts or _grok_summary_ts(summary, "created_at") or fallback_ts,
            ended_at=last_ts or _grok_summary_ts(summary, "updated_at") or fallback_ts,
            warnings=warnings,
            title=title,
        )


def _read_grok_summary(session_dir: Path) -> dict | None:
    path = session_dir / "summary.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _grok_summary_ts(summary: dict | None, key: str) -> str | None:
    if not summary:
        return None
    raw = summary.get(key)
    if isinstance(raw, str) and raw:
        # Already ISO-ish; normalize trailing Z if present.
        return raw.replace("+00:00", "Z") if raw.endswith("+00:00") else raw
    return unix_to_iso(raw)


def _grok_tool(update: dict) -> tuple[str, dict]:
    meta = update.get("_meta") or {}
    xai = meta.get("x.ai/tool") or meta.get("xai_tool") or {}
    name = xai.get("name") or update.get("title") or "Unknown"
    if isinstance(name, str):
        name = name.strip()
    else:
        name = "Unknown"
    inp = update.get("rawInput") or xai.get("input") or {}
    if not isinstance(inp, dict):
        inp = {}
    # Normalize Grok path keys onto the Claude names the formatter expects.
    if "file_path" not in inp:
        for alt in ("target_file", "path"):
            if alt in inp:
                inp = {**inp, "file_path": inp[alt]}
                break
    return name, inp


def _record_file_op(
    tool_name: str,
    inp: dict,
    files_created: list[dict],
    files_modified: list[dict],
) -> None:
    path = inp.get("file_path") or inp.get("path") or ""
    if not path:
        return
    if tool_name == "Write":
        if path not in {f["path"] for f in files_created}:
            files_created.append({"path": path, "description": "Created file"})
    elif tool_name == "Edit":
        if path not in {f["path"] for f in files_modified}:
            files_modified.append({"path": path, "changes": "Modified file"})


class NoneImporter:
    """Degrade: notes + handoff still archive; dialogue is empty."""

    def probe(self, source: Path) -> bool:
        return True

    def import_transcript(self, source: Path, fallback_ts: str) -> ImportResult:
        label = str(source) if source else "(none)"
        return ImportResult(
            harness="none",
            source_format="none",
            started_at=fallback_ts,
            ended_at=fallback_ts,
            warnings=[
                f"No supported harness transcript at {label}; "
                "archiving notes and handoff only"
            ],
        )


_IMPORTERS: list[TranscriptImporter] = [
    GrokUpdatesImporter(),
    ClaudeJsonlImporter(),
]


def import_source(source: Path | None, fallback_ts: str) -> ImportResult:
    """Probe registered importers; fall back to an empty import with a warning."""
    if source is None:
        return NoneImporter().import_transcript(Path("."), fallback_ts)
    for importer in _IMPORTERS:
        try:
            if importer.probe(source):
                return importer.import_transcript(source, fallback_ts)
        except OSError as exc:
            return ImportResult(
                harness="none",
                source_format="none",
                started_at=fallback_ts,
                ended_at=fallback_ts,
                warnings=[f"Importer failed on {source}: {exc}"],
            )
    return NoneImporter().import_transcript(source, fallback_ts)
