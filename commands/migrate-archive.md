---
description: Migrate this project's llm-dev archive to the unified-git-state format
---

# /llm-dev:migrate-archive

One-shot, reversible migration of the legacy archive format (markdown
`_index.md` + the `## Streams` table in `CURRENT-TODOs.md`) to the
unified-git-state format: per-session `.archive/sessions/<id>/manifest.json`,
per-stream `.archive/streams/<slug>.json`, and a derived `_index.md`.

## What it does

1. Resolves the project's `.archive/` (container or in-place layout).
2. Reads every `### NNN` entry in `_index.md` (authoritative for number,
   ordering, and the `**File**` name) and joins each with its referenced
   transcript JSON to build a manifest. Index entries whose JSON is missing get
   a minimal manifest synthesized from the markdown alone. Migrated manifests
   have `session_id: null` (no historical UUID exists); identity is the
   `conversation_id`.
3. Writes `streams/*.json` from the `## Streams` table, then removes that block
   from `CURRENT-TODOs.md` (prose `## Stream: <slug>` sections are preserved).
4. Regenerates `_index.md` as a derived artifact.

## Safety contract

- **`--dry-run`** writes nothing — it only reports what would change. Always run
  this first and review the report.
- **Idempotent**: re-running is a no-op (existing manifests/streams are left
  untouched).
- **Reversible**: the migrator only *adds* files plus one `CURRENT-TODOs.md`
  edit. To revert, use `git checkout`/`git clean` on the archive paths.

## Usage

```bash
# Preview (writes nothing):
python "${CLAUDE_PLUGIN_ROOT}/commands/handlers/migrate-archive.py" --dry-run

# Apply:
python "${CLAUDE_PLUGIN_ROOT}/commands/handlers/migrate-archive.py"
```

The handler always exits 0 and prints a JSON report
(`{"ok", "dry_run", "manifests", "manifests_written", "streams", "warnings"}`).
