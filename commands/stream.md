---
description: Manage work streams within a project — list, register, claim, release, pause, archive, rename
argument-hint: <subcommand> [args]
allowed-tools: Bash(*)
---

# Stream

Manage the multi-stream session tracking for this project. Streams are
named, persistent units of work registered in `CURRENT-TODOs.md`. Sessions
claim one stream (or stay "free") via `/llm-dev:init-session` or
`/llm-dev:stream join`.

## Subcommands

- `list [--all]` — show streams. By default hides archived.
- `new <slug> ["<name>"]` — register a new stream (status=active, unclaimed).
- `join <slug>` — claim a stream from inside an in-flight free session.
- `release` — release this session's stream claim (session becomes free).
- `pause <slug>` — set status to paused.
- `resume <slug>` — set status to active.
- `archive <slug>` — set status to archived (refuses if currently claimed).
- `rename <old-slug> <new-slug>` — change the slug (refuses if currently claimed).

## Usage

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/stream.py $ARGUMENTS
```

## Examples

```
/llm-dev:stream list
/llm-dev:stream new website "Public-facing website"
/llm-dev:stream join website
/llm-dev:stream pause website
/llm-dev:stream archive old-experiment
/llm-dev:stream rename web web-platform
```
