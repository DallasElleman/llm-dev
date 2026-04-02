---
description: Initialize a new LLM session for transcript tracking
argument-hint: [--model MODEL] [--user USERNAME]
allowed-tools: Bash(*)
---

# Initialize LLM Session

Initialize a new conversation session for llm-dev transcript tracking.

## What This Does

1. Reads the current conversation number from `.archive/transcripts/_index.md`
2. Increments the conversation number
3. Adds a placeholder entry to the transcript index
4. Reports the new session number

## Usage

Run the initialization script:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/init-session.py $ARGUMENTS
```

## Arguments

- `--model MODEL` - LLM model identifier (default: claude-sonnet-4-5-20250929)
- `--user USERNAME` - GitHub username for transcript attribution (default: prompts user)
- `--dry-run` - Show what would be done without modifying files

## After Running

Report to the user:
- The new session number that was assigned
- Remind them that at session end, they can run `/create-transcript` to archive the conversation

## Error Handling

If the script fails:
- Check that `.archive/transcripts/_index.md` exists
- Verify the index has the expected format with `**Current**: N` field
- Suggest running `/init-project` if archive infrastructure is missing
