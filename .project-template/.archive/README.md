# Archive

This directory preserves the development history and evolution of the {{PROJECT_NAME}} project.

## Contents

- **`transcripts/`** - Comprehensive development conversation logs documenting discussions, decisions, and project evolution (see `transcripts/_index.md` for full index)
- **`session-notes/`** - Per-session notes captured live during conversations: lessons learned, mistakes made, and assumptions proven wrong. Distilled across sessions to improve future performance. Created automatically by `/llm-dev:init-session`.
- **`session-handoff/`** - Per-session handoff documents written at session end by `/llm-dev:end-session`. High-signal re-entry points for the next session: open threads, in-flight work, locked-in decisions, and a first-action pointer. The latest handoff is loaded automatically by `/llm-dev:init-session`.
- **`artifacts/`** - Files and outputs created during development conversations, renamed with date prefixes for archival purposes
- **`CHANGELOG.md`** - Chronological record of significant changes, milestones, and architectural decisions with references to source transcripts

## Purpose

The archive maintains institutional knowledge and traceability by:
- Documenting how and why design decisions were made
- Preserving artifacts created during development conversations
- Enabling conversation archaeology for understanding project evolution
- Supporting knowledge transfer and contributor onboarding
- Providing complete context for architectural and strategic choices

This preserves development history while keeping the main project structure focused on active work.
