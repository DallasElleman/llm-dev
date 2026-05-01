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
4. Creates a dated, numbered session notes file at
   `.archive/session-notes/YYYYMMDD-NNN-session-notes.md` for in-flight capture
   of lessons learned, mistakes made, and assumptions proven wrong
5. Reports the new session number and the path to the session notes file

## Session Notes

After init, you (Claude) should periodically update the current session's
notes file throughout the conversation with:

- Lessons learned
- Mistakes made and how they were corrected
- Assumptions that turned out to be wrong
- Other observations worth distilling later

These notes are intended to be reviewed across sessions to improve performance
on similar tasks and projects, so favor specific, durable observations over
play-by-play narration.

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
- The path to the created session notes file
- Remind them that at session end, they can run `/create-transcript` to archive the conversation

## Error Handling

If the script fails:
- Check that `.archive/transcripts/_index.md` exists
- Verify the index has the expected format with `**Current**: N` field
- Suggest running `/init-project` if archive infrastructure is missing
