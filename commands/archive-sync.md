---
description: Commit and push the current project's llm-dev archive
allowed-tools: Bash(*), run_terminal_command
---

# Archive Sync

Commit any pending session records in the current project's `.archive` worktree
and best-effort push them to the remote `llm-dev-archive` branch.

Run from anywhere inside an llm-dev container project:

```bash
python3 <llm-dev-plugin-root>/commands/handlers/archive-sync.py
```

`<llm-dev-plugin-root>` is `$GROK_PLUGIN_ROOT` or `$CLAUDE_PLUGIN_ROOT` if
set; otherwise the plugin directory shown in this command's listing. Do not
expand an empty env var.

The handler resolves the container's `.archive` worktree, stages all changes,
commits them, and (if a remote is configured) rebases and pushes. Push failures
are non-fatal — the local commit is durable and pushes on the next sync. If you
are not inside a container project, it reports `{"ok": false}` and does nothing.

**Output keys:** `committed` (bool), `pushed` (bool), `warnings` (list of strings).
A `pushed: false` with a non-empty `warnings` list means the push failed but the
local commit is durable.
