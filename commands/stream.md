---
description: Manage work streams within a project — list, register, claim, release, pause, archive, rename
argument-hint: <subcommand> [args]
allowed-tools: Bash(*), run_terminal_command
disable-model-invocation: true
---

# Stream

Manage the multi-stream session tracking for this project. Streams are
named, persistent units of work, each stored as its own JSON file at
`.archive/streams/<slug>.json` (the legacy `## Streams` table in
`CURRENT-TODOs.md` is retired — it was migrated into per-stream JSON). The
human-readable stream table is rendered into the derived
`.archive/transcripts/_index.md`. Sessions claim one stream (or stay "free")
via `/llm-dev:init-session` or `/llm-dev:stream join`.

## Subcommands

- `list [--all]` — show streams. By default hides archived.
- `new <slug> ["<name>"]` — register a new stream (status=active, unclaimed).
- `join <slug>` — claim a stream from inside an in-flight free session. Pass
  `--nnn <N>` with the session number shown by `/llm-dev:init-session` (e.g.
  `join main --nnn 015`) so the correct in-flight notes file is renamed;
  without it the handler falls back to matching your session id against the
  in-progress session manifests (less reliable when multiple sessions run
  concurrently). Optional `--session-id` overrides live Grok/Claude discovery.
- `release` — release this session's stream claim (session becomes free).
  Optional `--session-id` overrides live discovery.
- `pause <slug>` — set status to paused.
- `resume <slug>` — set status to active.
- `archive <slug>` — set status to archived (refuses if currently claimed).
- `rename <old-slug> <new-slug>` — change the slug (refuses if currently claimed).

## Usage

```bash
python3 <llm-dev-plugin-root>/commands/handlers/stream.py $ARGUMENTS
```

`<llm-dev-plugin-root>` is `$GROK_PLUGIN_ROOT` or `$CLAUDE_PLUGIN_ROOT` if
set; otherwise the plugin directory shown in this command's listing. Do not
expand an empty env var.

## Examples

```
/llm-dev:stream list
/llm-dev:stream new website "Public-facing website"
/llm-dev:stream join website --nnn 015
/llm-dev:stream pause website
/llm-dev:stream archive old-experiment
/llm-dev:stream rename web web-platform
```
