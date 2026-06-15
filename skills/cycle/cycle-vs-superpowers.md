# `llm-dev:cycle` vs. the superpowers skills

**Date**: 2026-06-06
**Plugin version**: 0.17.2
**Status**: Reference doc

A comparison of the `llm-dev:cycle` skill against the four related Claude Code
superpowers skills it overlaps with: `brainstorming`, `writing-plans`,
`executing-plans`, and `verification-before-completion`.

## The fundamental difference: one orchestrator vs. four specialists

**`llm-dev:cycle` is a single end-to-end orchestrator.** It defines the whole
arc of a development task as six ordered phases — Review/Reflect → Brainstorm →
Research → Plan → Execute → Verify — each producing a numbered markdown artifact
(`1-review.md` … `6-verify.md`) inside a versioned `iteration-N/` directory. It
owns the loop: phase gates, a TodoWrite checklist, iteration numbering, and
reflection-on-prior-iteration.

**The superpowers skills are four independent, single-purpose specialists** that
each go *much deeper* on one slice of that arc. They're designed to be chained
(brainstorming → writing-plans → executing-plans, with
verification-before-completion as a gate before any "done" claim), but each is
self-contained and rigid about its own job.

Notably, cycle is explicitly built to *defer to* superpowers. Four of its six
phases (Brainstorm, Plan, Execute, Verify) offer the user an "A) lighter
built-in / B) go deep with superpowers" choice, and on B they invoke the
superpowers skill, then synthesize its output back into the numbered artifact.
So cycle is the scaffold; superpowers are the optional power tools that slot
into it.

## Phase-by-phase

### Brainstorm

| `cycle` Phase 2 | `superpowers:brainstorming` |
|---|---|
| Dialogue to converge on what to build; documents chosen concept, rejected alternatives, scope, **and security boundaries** (trust boundaries, threats). Produces `2-brainstorm.md`. Explicitly "do not write code." | Heavier, more prescriptive: a 9-item mandatory checklist, a `<HARD-GATE>` forbidding *any* implementation action before an approved design, an explicit "this is too simple to need a design" anti-pattern, a **Visual Companion** (browser-based mockups/diagrams), scope-decomposition for multi-subsystem projects, a spec self-review pass, and a user-review gate. Writes a dated design doc to `docs/superpowers/specs/` **and commits it.** Terminal state: must hand off to writing-plans. |

Differences: superpowers is stricter (hard gate, mandatory checklist), adds the
visual companion, large-project decomposition, and a committed spec doc. cycle
is lighter, conversational, and uniquely folds in **security-boundary
identification** — superpowers brainstorming has none of that.

### Research

This phase **has no superpowers equivalent.** It's cycle-only: evaluate tech
stack, verify libraries actually exist and install, run dependency
vuln/maintenance checks (`npm audit` etc.), identify secrets/TLS/auth config.
Superpowers folds technology choice into brainstorming's design and otherwise
doesn't have a dedicated research/spike step.

### Plan

| `cycle` Phase 4 | `superpowers:writing-plans` |
|---|---|
| File structure, ordered build sequence, testing strategy, acceptance-criteria checklist → `4-plan.md`. "If a step takes >1hr, break it down." | A rigorous plan-authoring discipline: "assume the engineer has zero context and questionable taste." **Bite-sized 2-5 minute steps**, an explicit TDD task template (write failing test → run it fails → minimal impl → run pass → commit), a "No Placeholders" failure list, a required plan header, a self-review for spec coverage + type consistency, and an execution handoff offering subagent-driven vs. inline. Saves to `docs/superpowers/plans/`. |

Difference: superpowers bakes TDD and extreme granularity into the plan *as a
deliverable for a context-free executor*; cycle's plan is lighter and
acceptance-criteria-oriented.

### Execute

| `cycle` Phase 5 | `superpowers:executing-plans` |
|---|---|
| Work the build sequence, test each component as you go, fix/adjust plan, record bugs and acceptance-criteria results → `5-execute.md`. | Narrow: load plan → review critically → execute steps *exactly* → stop and ask when blocked → hand off to `finishing-a-development-branch`. Strongly recommends using **subagent-driven-development** instead if subagents are available. Worktree-isolation oriented. |

Difference: superpowers executing-plans assumes a *separate session*
mechanically following a rigid pre-written plan, emphasizes "follow exactly /
stop don't guess / never start on main," and chains to branch-finishing.
cycle's Execute is a more fluid same-session build with self-reported artifacts.

### Verify

| `cycle` Phase 6 | `superpowers:verification-before-completion` |
|---|---|
| Adversarial counterpart to Execute: run full test suite fresh, walk each acceptance criterion with evidence, run linting/security scans, check for unsanitized input/hardcoded secrets/missing auth. On fail: don't mark complete. → `6-verify.md`. | Not a phase — a **gate/discipline** that applies *any time* you're about to claim success. "The Iron Law: no completion claims without fresh verification evidence." A gate function, a claim→requirement table, red-flag phrases ("Great!", "should"), rationalization-prevention table, red-green regression checks, and "trusting agent self-report = not verified." |

Difference: cycle's Verify is a *scheduled stage at the end of an iteration*
with a security checklist and an artifact. superpowers verification is a
*cross-cutting behavioral rule* with no artifact and no fixed timing — it fires
whenever a success claim is imminent. cycle uniquely adds security scanning into
the verify step.

## Structural / philosophical differences

- **Artifacts & state.** cycle is opinionated about *where work lives*:
  versioned `iteration-N/` dirs with numbered files, co-located with llm-dev
  archive conventions (`.archive/cycle-artifacts/`). superpowers writes to
  `docs/superpowers/specs/` and `plans/`, commits them, and otherwise carries
  state in git branches/worktrees.

- **Iteration & reflection.** cycle has a first-class **Review/Reflect** phase
  and an explicit iterate-the-whole-loop model (re-invoke → auto-increment →
  reflect on the last iteration's execute/verify). Superpowers has no equivalent
  meta-loop; each skill runs once and chains forward. (Refactoring in cycle is
  also "not a phase" but emergent — either inline during Execute or as a whole
  dedicated iteration.)

- **Rigidity.** Superpowers skills are deliberately *rigid* (hard gates, iron
  laws, mandatory checklists, "follow exactly") — they're disciplines that
  resist being talked out of. cycle's gates are explicitly **"guided, not
  rigid"**: yes/skip/revise/back, phases skippable at the user's request.

- **Security.** cycle threads security through Brainstorm (trust boundaries),
  Research (deps, secrets), Plan (input validation/hardening), and Verify
  (scanning, secret/auth checks). The superpowers four are essentially silent on
  security.

- **Coverage.** cycle covers context-loading and tech-selection (Review,
  Research) that the superpowers four simply don't address. Conversely,
  superpowers reaches *outside* these four into a richer ecosystem cycle only
  partially taps — subagent-driven-development, using-git-worktrees,
  finishing-a-development-branch, requesting/receiving-code-review, TDD,
  systematic-debugging.

## In one line

cycle is a lightweight, security-aware, iterating *project loop* with numbered
artifacts and soft gates that can delegate its heavy phases to superpowers; the
superpowers four are deep, rigid, single-purpose disciplines (design-gate, TDD
plan-authoring, exact-execution, evidence-before-claims) meant to be chained,
that go deeper than cycle but cover a narrower slice and skip Research, security,
and the reflect-and-iterate meta-loop.
