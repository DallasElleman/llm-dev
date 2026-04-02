---
name: cycle
description: Use when starting a development task that needs structured thinking before coding — especially greenfield features, unfamiliar domains, or tasks where jumping straight to implementation would likely require rework. Invoke at the start of work, not mid-task.
---

# Development Cycle

A structured 5-phase development loop: **Review → Brainstorm → Research → Plan → Execute**.

Each phase produces a markdown file documenting the work. Phases can be skipped explicitly, and deeper treatment is available via superpowers skills when present.

## On Invocation

1. Ask the user for a **working directory**. Propose `workspace/cycle/` as default; accept any override.
2. Determine the next iteration number by checking for existing `iteration-N/` directories. Create `iteration-N/` in the working directory.
3. Create a TodoWrite checklist (or if TodoWrite is unavailable, maintain a markdown checklist in the iteration directory):

| Phase | Output |
|-------|--------|
| Review | `review.md` |
| Brainstorm | `brainstorm.md` |
| Research | `research.md` |
| Plan | `plan.md` |
| Execute | `execute.md` |

4. Begin Phase 1: Review.

---

## Phase 1: Review

**Goal**: Load context and identify what you're working with.

**Activities:**
- Ask the user what files, documents, or context to read — don't assume
- Summarize requirements, constraints, and options
- Identify gaps or ambiguities in the requirements
- Narrow scope: use this phase to eliminate options, not add them

**Tips:**
- If summarizing user-provided documents, ask the user to verify accuracy

**Output:** Write `review.md` to the iteration directory with: context summary, constraints, and candidate approaches.

**Gate:** "Review written to `iteration-N/review.md`. Ready for Brainstorm, or want to revise?"

---

## Phase 2: Brainstorm

**Goal**: Explore what to build without writing code.

**Superpowers option:** If `superpowers:brainstorming` is available, offer the user a choice:
> **A)** Use the built-in Brainstorm phase — lighter, produces `brainstorm.md`
> **B)** Go deep with `superpowers:brainstorming` — visual companion, structured spec workflow

If they choose B, invoke `superpowers:brainstorming`. After it completes, synthesize results into `brainstorm.md` in the iteration directory before advancing.

**Activities:**
- Propose 2-3 approaches with trade-offs; recommend one
- Set explicit scope boundaries — what you will and won't build
- Document rejected alternatives and why
- Ask the user clarifying questions before proposing solutions

**Tips:**
- Resist coding. The value is in making decisions before committing to implementation

**Output:** Write `brainstorm.md` to the iteration directory with: chosen concept, alternatives considered and rejected, scope boundaries.

**Gate:** "Brainstorm written to `iteration-N/brainstorm.md`. Ready for Research, or want to revise?"

---

## Phase 3: Research

**Goal**: Identify the right tools and technologies for the chosen approach.

**Activities:**
- Evaluate tech stack options with trade-offs
- Recommend the simplest tool that meets requirements
- For unfamiliar tools, show a minimal working example before committing
- Verify that recommended libraries actually exist and are installable
- Confirm dependencies work in the user's environment

**Tips:**
- Models sometimes recommend deprecated or nonexistent packages — verify claims

**Output:** Write `research.md` to the iteration directory with: tech stack selection with rationale, dependencies, key technical decisions.

**Gate:** "Research written to `iteration-N/research.md`. Ready for Plan, or want to revise?"

---

## Phase 4: Plan

**Goal**: Turn research into a concrete, ordered build sequence.

**Superpowers option:** If `superpowers:writing-plans` is available, offer the user a choice:
> **A)** Use the built-in Plan phase — lighter, produces `plan.md`
> **B)** Go deep with `superpowers:writing-plans` — formal implementation plan with bite-sized tasks, TDD, and acceptance criteria

If they choose B, invoke `superpowers:writing-plans`. After it completes, synthesize results into `plan.md` in the iteration directory before advancing.

**Activities:**
- Define the file structure for the project
- Produce an ordered build sequence: what gets built first, second, third
- Write acceptance criteria — specific, testable conditions that define "done"
- Ensure the plan is self-contained: executable without re-reading earlier phases

**Tips:**
- If any single step would take more than an hour, break it into smaller steps
- The plan is a living document — update it if execution reveals problems

**Output:** Write `plan.md` to the iteration directory with: file structure, build sequence, acceptance criteria checklist.

**Gate:** "Plan written to `iteration-N/plan.md`. Ready for Execute, or want to revise?"

---

## Phase 5: Execute

**Goal**: Build the artifact according to the plan.

**Superpowers option:** If `superpowers:executing-plans` is available, offer the user a choice:
> **A)** Use the built-in Execute phase — work through the plan step by step
> **B)** Go deep with `superpowers:executing-plans` — structured execution with review checkpoints

If they choose B, invoke `superpowers:executing-plans`. After it completes, synthesize results into `execute.md` in the iteration directory before advancing.

**Activities:**
- Work through the build sequence step by step
- Test each component as you build it — don't wait until the end
- When something breaks, fix it or adjust the plan
- Read and understand generated code; explain it when asked

**Tips:**
- Test early and often — smoke testing catches bugs that LLMs miss
- If something doesn't work, describe the error precisely: "This function returns X but I expected Y"

**Output:** Write `execute.md` to the iteration directory with: summary of what was built, bugs found and fixed, acceptance criteria results.

**Gate:** "Execution complete. Iteration N finished."

---

## Gating Mechanics

Phase gates are **guided, not rigid**. Each gate presents a prompt and waits for the user's response. The skill does not programmatically verify file existence — it trusts the conversation flow.

| Response | Behavior |
|----------|----------|
| "yes" / "next" / "go" | Advance to next phase |
| "skip" | Advance without producing the output file; mark as skipped in checklist |
| "revise" | Stay in current phase, continue working |
| "back" / "back to [phase]" | Return to a previous phase |

Update the TodoWrite checklist as each phase completes or is skipped.

## Parallel Agent Dispatch

At any phase, if the work involves 2+ independent subtasks, proactively suggest dispatching parallel agents using Claude Code's Agent tool. This is a suggestion, not a requirement — the user can decline.

Examples:
- **Review**: Loading and summarizing multiple independent documents
- **Brainstorm**: Exploring alternative approaches concurrently
- **Research**: Evaluating competing tech stack options side by side
- **Plan**: Designing independent subsystems concurrently
- **Execute**: Building independent components in parallel

## Iteration

This skill handles one pass through the cycle. To iterate:

1. Re-invoke `/llm-dev:cycle` in the same working directory
2. The skill auto-increments to `iteration-N+1/`
3. The Review phase of the new iteration naturally reads prior iteration outputs

Each iteration should be smaller and more focused than the last.
