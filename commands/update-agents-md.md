---
description: Maintain a project's AGENTS.md/CLAUDE.md — freshness check or full audit
argument-hint: [--mode refresh|verify-refs|targeted|audit] [--sections "<list>"] [--list]
allowed-tools: Bash(*), Read, Edit, Task, AskUserQuestion
---

# Update AGENTS.md / CLAUDE.md

Maintain the file that gets injected into every agent session in this
project. It's the highest-leverage file in the repo: a wasted line is a tax
paid thousands of times, a wrong line is a confident mistake repeated
thousands of times. This command runs the cheap freshness check by default
and offers the full audit protocol when drift looks structural.

## Step 1 — Discover

Run with **no** `--mode` flag. The handler does **not** act: it computes the
calibration facts and prints `AUDIT_SCOPE_NEEDED: <JSON>`, then exits.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/update-agents-md.py $ARGUMENTS
```

The JSON carries the facts that make the scope choice meaningful:
`last_edited` date and `days_stale`, total lines/chars, an
instruction-bearing line count (heuristic — see Editing Rules), a
per-section inventory with sizes, a count of dangling references (paths,
markdown links, numeric `§N` anchors that don't resolve to a section — text
anchors and module/symbol references still need manual verification), the
current git branch, and
whether it matches a `deploy`-adjacent branch claim found in the file. It
also carries a `recommended_mode` + `recommendation_reason` and the
session-boundary warning (see below).

**The handler owns the arithmetic.** Agent self-counts are unreliable even
when quotes are exact — don't recount by hand or trust a subagent's tally;
use the JSON.

## Step 2 — Present with AskUserQuestion

Build one question, one option per mode, description = what it does +
when it's recommended:

- **Refresh** — re-verify the volatile assertions (objective, deploy
  branch, key module roles), fix drift, re-date, commit. No subagents.
  *Recommended when only the date is stale.*
- **Verify references** — resolve every path/link/`§` anchor in the file,
  report what's broken. Cheap, no subagents.
- **Targeted audit** — the audit protocol applied to one or more specific
  sections (pick from the `sections` inventory in the JSON).
- **Full audit** — the whole protocol below, dispatching per-angle
  subagents. *Recommended when drift is structural* (dangling references,
  an oversized instruction budget, or a stale deploy-branch claim).

Mark the option matching `recommended_mode` as (Recommended), using
`recommendation_reason` as its description. The automatic **Other**
free-text box covers anything beyond the four options — free-form scope
notes, a specific file path (`--file`), etc.

**Before offering Full audit**, apply the session-boundary check yourself
(the handler can't see your context): has this file's content already been
read this session, or is it present in your injected project instructions?
If so, do not proceed with `--mode audit`. Tell the user why (see Debiasing
below) and suggest holding the file aside and starting a fresh session
instead — every dispatched agent gets a clean context for free there.

## Step 3 — Initialize once

Map the answer to a single re-invocation:

```bash
# Refresh
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/update-agents-md.py --mode refresh
# ... make the edits directly with Edit, then re-date:
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/update-agents-md.py --mode refresh --restamp

# Verify references
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/update-agents-md.py --mode verify-refs

# Targeted audit
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/update-agents-md.py --mode targeted --sections "Deploy Workflow, Known Risks"

# Full audit
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/update-agents-md.py --mode audit
```

"Other" free text: an existing section name → `--mode targeted --sections
"<text>"`; a request to check a different file → add `--file <name>` to
whichever mode was actually chosen; anything ambiguous → ask again rather
than guessing.

### Flags

- `--mode refresh|verify-refs|targeted|audit` — run that mode. Omit to
  discover.
- `--sections "<a>, <b>"` — required with `--mode targeted`.
- `--restamp` — update the `Last edited`/`Last Updated` metadata line to
  today. Mechanical only; run it after you've made and reviewed the edits,
  not before.
- `--list` — print the calibration JSON (no `AUDIT_SCOPE_NEEDED:` prefix)
  and exit; an alternative discovery source, e.g. for scripting.
- `--file NAME` — target an explicit filename instead of auto-detecting
  `CLAUDE.md` then `AGENTS.md`.
- `--project-path PATH` — explicit project root to search from (default:
  cwd).
- `--dry-run` — with `--restamp`, preview without writing.

If neither `CLAUDE.md` nor `AGENTS.md` exists at the project root, the
handler reports `no_target_file` and exits 1 — point the user at
`/llm-dev:init-project` or have them create one first.

---

## Debiasing via a Session Boundary, Not a Rename

An agent's copy of `AGENTS.md`/`CLAUDE.md` is a **session-start snapshot**:
it does not refresh on edit and does not disappear on delete — subagents
dispatched from a biased parent inherit the parent's snapshot either way
(same headings, same verbatim text, same token count before/after a rename
or hold-aside mid-session). The only clean channel is to hold the file
aside and **start a new session**, after which every dispatched agent gets
a clean context for free. Detect this and say so rather than silently
producing a biased audit; refuse `--mode audit` from a session that already
has the file loaded and print these hold-and-restart instructions instead.

## Audit Protocol (Full Audit)

- **One read-only agent per angle** — run/test, module map, each gotcha
  cluster, conventions, plus an omissions sweep over archived session notes
  for lessons that never got promoted into the file.
- **Falsifier before search.** Each agent must state the specific evidence
  that would make a claim *false*, then hunt for that evidence. A verdict
  with no articulated falsifier is rejected — confirmation-biased
  "verified" reads identically to a real one.
- **`UNVERIFIABLE-here` is a first-class verdict.** Claims settleable only
  against a live service get marked as such, with the probe named, rather
  than quietly asserted true or false.
- **Removal needs evidence too.** "Merely old but still true" must stay;
  the falsifier for removing a lesson is "the code no longer does this" or
  "a test now enforces it" — never "that was a while ago."
- **Discount findings that are artifacts of the audit setup** (e.g. "this
  link is dangling" because the audit process itself moved the file).
- **Verify every surviving reference before committing.** Stale `§`
  pointers are especially costly — run `--mode verify-refs` again as a
  final gate after edits land.
- **Measure with the handler, not the agents.** Use the calibration JSON's
  counts for the before/after comparison you report to the user; don't ask
  an agent to self-report line counts.

## Editing Rules

- **Budget is instructions, not lines** — roughly 150–200 for frontier
  models, with ~50 already spent by the Claude Code system prompt itself.
  The `instruction_bearing_lines` count in the calibration JSON is a
  heuristic proxy for this (it excludes blanks, headings, horizontal rules,
  and metadata-label lines) — use it as a signal, not a strict budget.
- **Never send an LLM to do a linter's job.** If a test already fails when
  a rule is violated, the rule is redundant in the file — cut it.
- **Cut by kind, not length.** Irreducible facts stay. Instances of a
  principle move to a linked `gotchas.md`, organized *under* the
  principle. Principles the workspace-level `CLAUDE.md` already carries
  get deleted here rather than restated.
- **Highest-harm facts at the top.** Models weight the peripheries of a
  document — don't bury a load-bearing fact (e.g. "a push is a publish")
  mid-file.
- **Progressive disclosure with a trigger.** Point to detail files by
  *when to read them*, not by what they contain — "read before writing a
  test, touching X, or verifying a deploy," not "gotchas.md — gotchas."
- **A metadata block earns its keep.** `Last edited` (+ a staleness
  contract), current main objective, and a pointer to this command are
  worth the few lines they cost — they're what makes `--mode refresh`
  cheap on every later run.

Prior art: [Writing a good CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md).

## After Running

Report to the user:
- Which mode ran and why (recommended vs. chosen via Other).
- For refresh/audit: a before/after size comparison from the calibration
  JSON (lines, chars, instruction-bearing lines) and a list of what
  changed and why.
- For verify-refs/audit: the dangling-reference list, resolved or still
  open.
- Whether `--restamp` was run (if not, remind the user it's the last step
  before committing).
