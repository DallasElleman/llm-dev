# Conversation Transcripts Archive

This directory contains verbatim transcripts of development conversations for {{PROJECT_NAME}}. Each transcript is a complete record of dialogue, tool usage, and outcomes.

## Latest Conversation
**Current**: 0

## Conversation Index

### Examples and References
See llm-dev documentation for transcript format and examples.

## Transcript Format

Transcripts are stored as JSON documents containing:
- `project_id`: Project identifier
- `conversation_id`: Unique conversation ID (YYYYMMDD-title-in-kebab-case)
- `conversation_number`: Session number from initialization
- `date`: Date and time of conversation (ISO 8601)
- `participants`: Array of participant information
- `dialogue`: Verbatim conversation with tool calls
- `outcomes`: Files created/modified and decisions made

## How to Use This Directory

- **For Full Context**: Read complete transcripts for detailed understanding
- **For Changes**: Check referenced changelogs for specific project changes
- **For Cross-Project**: Multi-project conversations reference all affected projects
- **For Artifacts**: Check `.archive/artifacts/` for files created during conversations

## Maintenance

Transcripts are created using `/llm-dev:create-transcript`:
1. Converts Claude Code JSONL to llm-dev JSON format
2. Preserves verbatim dialogue and tool calls
3. Replaces session placeholder with actual summary
4. Updates changelog with reverse-chronological entry
