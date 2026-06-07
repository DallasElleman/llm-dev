---
description: End an LLM session — write handoff doc and archive transcript
argument-hint: <conversation-number> "<title>" [--topics "t1, t2"]
allowed-tools: Bash(*)
---

# End Session

Wind the session down. Write a forward-looking **session handoff** for the
next session, then archive this conversation as a JSON transcript.

## Flow (you, Claude, perform these in order)

1. **Finalize the session notes.** Before writing the handoff, do a final pass
   on this session's notes file (`.archive/session-notes/{date_yyyymmdd}-{NNN}-*-session-notes.md`):
   capture what worked, lessons learned, mistakes made, and assumptions proven
   wrong from this session. The notes are the cross-session learning artifact and
   the handler commits them **as-is** — if you don't update them now, they archive
   stale. Follow the **Session Notes Nudge** section below.
2. **Read the prior handoff** (if it exists), so you can carry the chain
   forward. Look in `.archive/session-handoff/` for the most recent
   `*-session-handoff.md`. If one exists, read it. If not, skip.
3. **Write the new handoff file** at:
   `.archive/session-handoff/{date}-{NNN}-session-handoff.md`
   where `NNN` is the zero-padded session number (e.g., `010`) and `{date}` is
   the **same `YYYYMMDD` prefix as this session's notes file** — not today's
   date. The handler dates the whole bundle (transcript, notes, handoff) from
   that start-date prefix, so a session that spans midnight stays consistent.
   Follow the **Handoff Nudge** section below.
4. **Run the transcript handler** to archive everything:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/end-session.py <number> "<title>" [--topics "topic1, topic2"] [--no-sanitize] [--no-push] [--dry-run]
   ```

## Session Notes Nudge

> Before the handoff, take a moment to finalize the session notes — they're the
> retrospective, cross-session learning artifact (the handoff is forward-looking;
> don't duplicate between them).
>
> Update the notes file with anything from this session not already captured:
>
> - **What worked** — validated approaches, decisions worth repeating.
> - **Lessons learned** — broadly applicable insights.
> - **Mistakes made** — and how they were corrected.
> - **Assumptions proven wrong** — what you believed that turned out false.
> - **Other observations** — durable, non-obvious findings worth distilling later.
>
> Favor specific, durable observations over play-by-play narration. Capture wins
> as readily as misses — positive validations fuel future improvement too. If the
> notes were kept current throughout the session, this is a quick confirmation
> pass, not a rewrite.

## Handoff Nudge

> Alright — good place to wind the session down. Let's write a handoff
> document for the next session.
>
> The audience is a fresh Claude instance picking up this thread cold. Your
> job is to help them retain and resume the progress made here without
> losing the thread. Try to include only high-signal context toward that
> end. This document is the next session's high-signal **re-entry point**.
>
> **The bar:** A reader with only this handoff (no transcript, no
> session-notes) should know (a) where we left off, (b) what's in flight,
> (c) what's already decided so they don't re-litigate it, and (d) which
> artifacts to read first.
>
> **Rules:**
> - **Forward-looking, not retrospective.** Lessons-learned go in
>   session-notes; what's *next* goes here. Don't duplicate either document.
> - **Specific over general.** Branch names, PR numbers, file paths, line
>   refs. "Resume the migration after PR #29 merges" beats "continue with
>   migrations."
> - **Reasoning for course-corrections.** If the session deviated from its
>   original plan — dropped, deferred, or pivoted — write the *why* in one
>   sentence.
> - **Carry the chain forward.** Read the prior handoff before writing this
>   one. If threads from session N-1 (or earlier) are still unresolved and
>   didn't land this session, reference them here by path so the chain
>   doesn't snap when this becomes the only handoff loaded next time.
>
> **Sections** (omit any that have no content — do not write "(none)"):
>
> 1. **Where We Left Off** — 1–3 sentences, the situation at session end.
> 2. **Wins This Session** — concrete things that landed cleanly: PRs
>    merged, features verified, tests passing, decisions resolved. The next
>    session uses this to know what *not* to redo and what to build on.
>    Capture wins as readily as you capture course-corrections — positive
>    progress is also context worth carrying forward.
> 3. **Active Branches / PRs / Issues** — names, numbers, current state.
> 4. **In-Flight Work** — tasks mid-implementation, with file paths and
>    what specifically remains.
> 5. **Deferred or Course-Corrected** — planned-but-not-done items, each
>    with the reason in one sentence.
> 6. **Locked-In Decisions** — durable conclusions reached this session.
> 7. **Key References** — paths/links to plans, design specs, prior
>    handoffs with live threads, related external docs.
> 8. **Gotchas** — specific traps in the *current* work-in-flight (not
>    generalized lessons).
> 9. **First Action for Next Session** — write this as an instruction the
>    next Claude will read at the top of `/init-session`. Format:
>    *"Start by reading X, Y, and Z. Then greet the user, relay your
>    understanding of where we left off, and ask whether anything has
>    changed since the last session or whether we should resume where we
>    left off. Don't jump into action — pick up the thread first."*
>    Adapt the specific reads and the A/B/C items to this session's state.
>
> **Length:** roughly 1–2 screens of markdown. Longer means you're keeping
> noise; much shorter means you're leaving threads dangling.

## Stream Behavior

If the session held a stream claim at end time:
- Handoff and transcript filenames include the stream slug.
- The stream's `.archive/streams/<slug>.json` file is updated: `claim` →
  `null`, `since` → `null`, `last_touched` → now, `last_handoff` → new path.
- If another session reclaimed the stream mid-flow, the handoff body is
  prepended with a "claim was reassigned" note and the stream file is
  left untouched.

If the session was free, today's behavior is preserved: flat filenames
and no stream interaction.

## What the Handler Does Automatically

1. **Finds session ID** — From the in-progress manifest (written by
   `/init-session`), falling back to the scoped session resolver
2. **Converts JSONL** — Claude Code's native format → llm-dev JSON format
3. **Generates outcomes** — Analyzes conversation for files created/modified
4. **Scans for PII** — Checks for home paths, names, emails, potential secrets before commit
5. **Finalizes the manifest** — Sets `ended_at`, `status: complete`, `title`,
   `conversation_id`, and the `files` map on this session's manifest
6. **Regenerates the derived index** — `.archive/transcripts/_index.md` is
   re-rendered from the manifests + per-stream JSON (a build artifact, never
   hand-edited)
7. **Updates CHANGELOG** — Adds new entry at top (reverse-chronological)
8. **Commits the bundle by layout** — container (`.archive/` worktree of
   `llm-dev-archive`) → archive sync; in-place `.archive/` → `git add`/`commit`
   on the current branch. Stages transcript + manifest + per-stream JSON +
   index + CHANGELOG + session-notes + session-handoff (warns if handoff missing).
9. **Pushes the commit** — Pushes by default (best-effort and non-fatal; a missing upstream just warns). Pass `--no-push` to skip.

## Arguments

- `conversation-number` — The session number (from `/init-session`)
- `title` — Brief title, 3-7 words (e.g., "Plugin Development and Testing")
- `--stream <slug>` — Override stream slug for this session. By default, end-session looks up which stream (if any) is claimed by this session's ID in `.archive/streams/<slug>.json`; pass `--stream` only to force a specific slug or override.
- `--topics "t1, t2"` — Optional comma-separated topics (auto-generated if omitted)
- `--no-sanitize` — Disable automatic PII redaction. By default `/end-session` redacts home paths and participant names; pass this to restore the interactive commit/sanitize/abort prompt (or, non-interactively, the `PII_REVIEW_NEEDED` abort). (`--sanitize` is still accepted but redundant.)
- `--no-push` — Skip pushing the archive commit. By default the handler pushes the current branch to its remote (best-effort; a missing upstream just warns).
- `--dry-run` — Preview without writing files

## Example

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/end-session.py 10 "Session Handoff Feature" --topics "session-handoff, end-session, plugin"
```

## After Running

Verify the output:
- Handoff file at `.archive/session-handoff/YYYYMMDD-NNN-session-handoff.md`
- Transcript file in `.archive/transcripts/`
- The session manifest at `.archive/sessions/<dir>/manifest.json` finalized
  (`status: complete`)
- The derived `.archive/transcripts/_index.md` regenerated with the entry
- CHANGELOG has new entry at top
- The bundle (transcript + manifest + per-stream JSON + index + CHANGELOG +
  session-notes + session-handoff) included in the same commit

If the auto-generated outcomes need refinement, edit the transcript JSON directly.
