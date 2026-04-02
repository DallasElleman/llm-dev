# Workspace Conversation Transcripts

This directory contains verbatim transcripts of development conversations for {{WORKSPACE_NAME}}.

## Latest Conversation

**Current**: 0

## Transcript Index

## Transcript Format

Transcripts are stored as JSON documents containing:
- `project_id`: Project/workspace identifier
- `conversation_id`: Unique conversation ID (YYYYMMDD-title-in-kebab-case)
- `conversation_number`: Session number from initialization
- `date`: Date and time of conversation (ISO 8601)
- `participants`: Array of participant information
- `dialogue`: Verbatim conversation with tool calls
- `outcomes`: Files created/modified and decisions made

## Maintenance

Transcripts are created using `/llm-dev:create-transcript`:
1. Converts Claude Code JSONL to llm-dev JSON format
2. Preserves verbatim dialogue and tool calls
3. Replaces session placeholder with actual summary
4. Updates changelog with reverse-chronological entry
