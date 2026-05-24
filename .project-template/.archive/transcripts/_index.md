# Conversation Transcripts Archive

This directory contains verbatim transcripts of development conversations for {{PROJECT_NAME}}. Each transcript is a complete record of dialogue, tool usage, and outcomes.

## Latest Conversation
**Current**: 0

## Transcript Format

Transcripts are stored as JSON documents containing:
- `project_id`: Project identifier
- `conversation_id`: Unique conversation ID (YYYYMMDD-NNN-title-in-kebab-case)
- `conversation_number`: Session number from initialization
- `date`: Date and time of conversation (ISO 8601)
- `participants`: Array of participant information
- `dialogue`: Verbatim conversation with tool calls
- `outcomes`: Files created/modified and decisions made

## How to Use This Directory

- **Transcripts**: Full verbatim records in `.archive/transcripts/` — read for complete context
- **Session Notes**: In-flight learnings in `.archive/session-notes/` — update throughout each session
- **Handoffs**: Forward-looking re-entry points in `.archive/session-handoff/` — read first when resuming

## Maintenance

Transcripts are managed via the session lifecycle:
1. `/llm-dev:init-session` writes a `### NNN - [In Progress]` placeholder entry and creates the session-notes file
2. `/llm-dev:end-session` archives the conversation JSON, replaces the placeholder with the real entry, and writes the session-handoff

## Transcript Index
