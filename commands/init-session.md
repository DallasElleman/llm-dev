---
description: Initialize a new LLM session for transcript tracking
argument-hint: [--model MODEL] [--user USERNAME] [--project-path PATH]
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

## Stream Selection

The handler cannot block on terminal input when running under Claude Code's
Bash tool. Stream selection is a **two-step, Claude-mediated flow**:

### Standard flow (no contention)

1. Run the handler with no `--stream`/`--no-stream` arg. The handler detects
   a non-TTY context and prints `STREAM_SELECTION_NEEDED: <JSON>` listing all
   visible streams, then returns without initializing.
2. Present the streams to the user and ask which to claim (or free session).
3. Re-invoke with `--stream <slug>` or `--no-stream`.

Alternatively, call `--list-streams` first to get the full registry as JSON
(with claim status, last handoff path, etc.), present options, then re-invoke.

### Contention flow (stream already claimed)

If `--stream <slug>` targets an already-claimed stream, the handler prints
`STREAM_RECLAIM_NEEDED: <JSON>` with the holder's session ID, title, and notes
file, and returns without claiming.

1. Surface the contention warning to the user.
2. If they confirm reclaim, re-invoke with `--stream <slug> --force-stream`.

### Non-interactive flags

- `--stream <slug>`: claim that stream non-interactively.
- `--no-stream`: start a free session without prompting.
- `--list-streams`: emit the stream registry as JSON and exit (no session init).
- `--force-stream`: skip the reclaim confirmation dialog (use after user confirms).

The selected stream determines:
- Which prior handoff is loaded as resume context.
- Whether the session-notes/handoff/transcript filenames include the
  stream slug.
- Whether `/end-session` updates the stream's registry row.

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
- `--stream <slug>` - Claim a specific stream non-interactively
- `--no-stream` - Start a free session without stream selection
- `--list-streams` - Print the stream registry as JSON and exit (no session init)
- `--force-stream` - Skip reclaim confirmation when `--stream` targets a claimed stream
- `--dry-run` - Show what would be done without modifying files
- `--project-path PATH` - Explicit project root to search from (default: cwd). Use
  this when running from a parent workspace so the correct project's
  `.archive/transcripts/_index.md` is targeted instead of the workspace's.

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
