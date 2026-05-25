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

Run with **neither** `--stream` nor `--no-stream` and the handler is in
**discovery mode**: it prints `STREAM_SELECTION_NEEDED: <JSON>` (visible
streams, each with claim status, last handoff, and a one-line `next_action`
preview) and **exits without initializing anything**. Drive selection like
this:

1. **Discover.** Run the handler with no `--stream`/`--no-stream` flag (see
   Usage). Parse the `STREAM_SELECTION_NEEDED:` JSON from its output.
2. **Present with `AskUserQuestion`.** Build one question whose options are:
   - one option per stream in the JSON (active first; mark the stream with
     the most recent handoff `(Recommended)`). Put its claim status and
     `next_action` preview in the option description.
   - a **"Free session (no stream)"** option.

   The automatic **"Other"** free-text box covers creating a new stream or
   picking a stream beyond the 4-option limit.
3. **Initialize once.** Map the answer to a single re-invocation, always
   passing `--model <your model id>` (e.g. `claude-opus-4-7`):
   - a stream → `--stream <slug> --model <id>`
   - "Free session" → `--no-stream --model <id>`
   - "Other" text: an existing slug → `--stream <slug>`; `new <slug>` or a
     new name → run `/llm-dev:stream new <slug> "<name>"` first, then
     `--stream <slug>`; "free"/"none" → `--no-stream`. If the text is
     ambiguous, ask again rather than guessing.

The session initializes **exactly once**, on step 3.

### Contention (chosen stream already claimed)

If `--stream <slug>` targets a claimed stream, the handler prints
`STREAM_RECLAIM_NEEDED: <JSON>` (holder session id, title, notes file) and
does not claim. Surface this with an `AskUserQuestion` confirm; if the user
chooses to reclaim, re-invoke `--stream <slug> --force-stream --model <id>`.

### Flags

- `--stream <slug>` — claim that stream and initialize.
- `--no-stream` — initialize a free session (no stream).
- `--force-stream` — skip the reclaim confirmation (after the user confirms).
- `--list-streams` — print the registry as JSON and exit (no init); an
  alternative discovery source.

The selected stream determines which prior handoff is loaded as resume
context, whether the notes/handoff/transcript filenames include the stream
slug, and whether `/end-session` updates the stream's registry row.

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

**Step 1 — discover** (no stream flag): the handler prints
`STREAM_SELECTION_NEEDED` and exits without initializing.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/init-session.py $ARGUMENTS
```

**Step 3 — initialize** (after the user picks): re-run with the chosen flag
and your model id.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/init-session.py --stream <slug> --model <your-model-id>
# or, for a free session:
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/init-session.py --no-stream --model <your-model-id>
```

## Arguments

- `--model MODEL` - LLM model identifier. **Always pass your own model id**
  (e.g. `claude-opus-4-7`) on the step-3 init call so the session records the
  correct model; the handler default (`claude-sonnet-4-6`) is only a fallback.
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
