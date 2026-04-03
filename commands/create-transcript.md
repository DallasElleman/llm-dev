---
description: Create JSON transcript and update archive index/changelog
argument-hint: <conversation-number> "<title>" [--topics "t1, t2"]
allowed-tools: Bash(*)
---

# Create Conversation Transcript

Archive the current conversation as a JSON transcript.

## Usage

Run the transcript handler with conversation number and title:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/create-transcript.py <number> "<title>" [--topics "topic1, topic2"] [--sanitize] [--dry-run]
```

## What It Does Automatically

1. **Finds session ID** - From README placeholder (set by init-session) or most recent JSONL
2. **Converts JSONL** - Claude Code's native format → llm-dev JSON format
3. **Generates outcomes** - Analyzes conversation for files created/modified
4. **Scans for PII** - Checks for home paths, names, emails, and potential secrets before commit
5. **Updates README** - Replaces `[In Progress]` placeholder with actual entry
6. **Updates CHANGELOG** - Adds new entry at top (reverse-chronological)

## Arguments

- `conversation-number` - The session number (from init-session)
- `title` - Brief title, 3-7 words (e.g., "Plugin Development and Testing")
- `--topics "t1, t2"` - Optional comma-separated topics (auto-generated if omitted)
- `--sanitize` - Automatically redact PII (home paths, participant names) without prompting
- `--dry-run` - Preview without writing files

## Example

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/create-transcript.py 4 "Create Transcript Command" --topics "transcript, automation, plugin"
```

## After Running

Verify the output:
- Transcript file created in `.archive/transcripts/`
- README placeholder replaced with actual entry
- CHANGELOG has new entry at top

If the auto-generated outcomes need refinement, edit the transcript JSON directly.
