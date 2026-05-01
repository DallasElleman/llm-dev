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
   `.archive/session-notes/YYYYMMDD-NNN-session-notes.md` for in-flight
   capture of what worked, lessons learned, mistakes made, and assumptions
   proven wrong
5. Resolves and prints paths to the **prior session's** transcript, notes,
   and handoff (if any), so you can pick up the thread

## After Running — Pick Up the Thread

The handler prints three "prior-session context" paths. **Read them in this
order:**

1. **Handoff** — the high-signal re-entry point. It tells you where the
   prior session left off, what's in flight, what's already decided, and
   what your first action should be. Follow the **First Action** section
   at the bottom of the handoff: greet the user, relay your understanding,
   and ask whether anything has changed before resuming.
2. **Notes** — supplements the handoff with retrospective context (what
   worked, lessons learned, mistakes, wrong assumptions from the prior
   session).
3. **Transcript** — full conversation record. Read selectively if the
   handoff or notes reference specific exchanges; otherwise skim or skip.

If no prior session exists (this is session 001), the handler will say so
and you can proceed normally.

## Session Notes (Living Document)

Throughout the conversation, periodically update the new session's notes
file with:

- **What worked** — validated approaches, successful decisions, things
  worth repeating
- **Lessons learned** — broadly applicable insights from the session
- **Mistakes made** and how they were corrected
- **Assumptions** that turned out to be wrong
- **Other observations** worth distilling later

These notes are reviewed across sessions to improve performance on similar
tasks. Capture wins as readily as misses — positive validations are just
as much fuel for future improvement as corrections. Favor specific,
durable observations over play-by-play narration.

## Usage

Run the initialization script:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/init-session.py $ARGUMENTS
```

## Arguments

- `--model MODEL` - LLM model identifier (default: claude-sonnet-4-6)
- `--user USERNAME` - GitHub username for transcript attribution (default: prompts user)
- `--dry-run` - Show what would be done without modifying files

## After Running

Report to the user:
- The new session number that was assigned
- The path to the created session notes file
- Whether prior-session context was loaded (and which docs)
- Remind them that at session end, they can run `/end-session` to write the
  handoff and archive the conversation

## Error Handling

If the script fails:
- Check that `.archive/transcripts/_index.md` exists
- Verify the index has the expected format with `**Current**: N` field
- Suggest running `/init-project` if archive infrastructure is missing
