# Cross-Project Conversation Transcripts

This directory contains transcripts of conversations that span multiple projects within the {{WORKSPACE_NAME}} workspace.

## Latest Conversation

**Current**: 0

## Transcript Format

Transcripts are stored as JSON documents containing:
- `project_id`: Project/workspace identifier
- `conversation_id`: Unique conversation ID (YYYYMMDD-NNN-title-in-kebab-case)
- `conversation_number`: Session number from initialization
- `date`: Date and time of conversation (ISO 8601)
- `participants`: Array of participant information
- `dialogue`: Verbatim conversation with tool calls
- `outcomes`: Files created/modified and decisions made

## How to Use This Directory

- **Transcripts**: Full verbatim records in `.archive/transcripts/` — read for complete context
- **Artifacts**: Files created during conversations in `.archive/artifacts/`

When a conversation affects multiple projects:
1. Archive here with references to all affected projects
2. Update each project's changelog with a reference to this transcript
3. Use project-specific `.archive/` for single-project conversations

## Maintenance

Transcripts are managed via the session lifecycle:
1. `/llm-dev:init-session` writes a `### NNN - [In Progress]` placeholder entry and creates the session-notes file
2. `/llm-dev:end-session` archives the conversation JSON, replaces the placeholder with the real entry, and writes the session-handoff

## Transcript Index
