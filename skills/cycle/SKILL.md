---
name: cycle
description: Use when starting a development task that needs structured thinking before coding — especially greenfield features, unfamiliar domains, or tasks where jumping straight to implementation would likely require rework. Invoke at the start of work, not mid-task.
---

# Development Cycle

A structured 6-phase development loop: **Review/Reflect → Brainstorm → Research → Plan → Execute → Verify**.

Work through each phase in order, producing a markdown file for each. Phases can be skipped at the user's request. Deeper treatment is available via superpowers skills where noted.

## On Invocation

1. Ask the user for a **working directory**. Propose `workspace/cycle/` as default; accept any override.
2. Determine the next iteration number by checking for existing `iteration-N/` directories. Create `iteration-N/` in the working directory.
3. Create a TodoWrite checklist (or if TodoWrite is unavailable, maintain a markdown checklist in the iteration directory):

| Phase | Output |
|-------|--------|
| Review/Reflect | `review.md` |
| Brainstorm | `brainstorm.md` |
| Research | `research.md` |
| Plan | `plan.md` |
| Execute | `execute.md` |
| Verify | `verify.md` |

4. Begin Phase 1.

---

## Phase 1: Review/Reflect

**Goal**: Load context and identify what you're working with. On iteration 2+, reflect on the previous iteration first.

**Reflection (iteration 2+ only):** If a previous iteration directory exists, read its outputs — especially `execute.md` and `verify.md` — and address:
- What assumptions proved wrong?
- What worked well and should carry forward?
- What should change this iteration?
- Has scope or priority shifted based on what was learned?

Include a **Reflection** section at the top of `review.md`. Lead with this before loading new context — ground the iteration in concrete experience, not a fresh read of original requirements.

**Review:**
- Ask the user what files, documents, or context to read — don't assume
- Summarize requirements, constraints, and options
- Identify gaps or ambiguities in the requirements
- Narrow scope: eliminate options, not add them
- If summarizing user-provided documents, ask the user to verify accuracy

**Output:** Write `review.md` with: reflection (if applicable), context summary, constraints, and candidate approaches.

**Gate:** "Review written to `iteration-N/review.md`. Ready for Brainstorm, or want to revise?"

---

## Phase 2: Brainstorm

**Goal**: Explore what to build through interactive conversation, then converge on a path forward.

This phase is a **dialogue, not a monologue**. Ask questions, challenge assumptions, explore edge cases, and think outside the box *with* the user — don't just present a menu of options. Surface insights that neither party would reach alone.

**Superpowers option:** If `superpowers:brainstorming` is available, offer the user a choice:
> **A)** Use the built-in Brainstorm phase — lighter, produces `brainstorm.md`
> **B)** Go deep with `superpowers:brainstorming` — visual companion, structured spec workflow

If they choose B, invoke `superpowers:brainstorming`. After it completes, synthesize results into `brainstorm.md` in the iteration directory before advancing.

**Process:**
- Start with open-ended questions — understand intent before proposing solutions
- Ask one question at a time. Don't overwhelm with a list of ten questions at once
- Explore possibilities: what if we did X instead? What would the simplest version look like? What's the version you'd be embarrassed to ship?
- Push back constructively if scope seems too large or too vague
- Propose 2-3 approaches with trade-offs; recommend one
- Set explicit scope boundaries — what you will and won't build
- Document rejected alternatives and why

**Security boundaries:**
- Identify security-relevant boundaries: user input, authentication, authorization, data storage, external API calls
- Document trust boundaries and potential threats
- If the artifact handles sensitive data or faces untrusted input, note which boundaries need hardening in later phases

**Do not write code.** The value is in making decisions before committing to implementation.

**Output:** Write `brainstorm.md` with: chosen concept, alternatives considered and rejected, scope boundaries, and security-relevant boundaries (if applicable).

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
- Check dependencies for known vulnerabilities and maintenance status (e.g., `npm audit`, `pip audit`, or equivalent)
- Identify security-relevant configuration: secrets management, TLS, auth tokens, API keys

**Verify your own claims.** You sometimes recommend deprecated or nonexistent packages — check before committing.

**Output:** Write `research.md` with: tech stack selection with rationale, dependencies (including security posture), key technical decisions.

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
- Define testing strategy: unit, integration, and security tests as part of the build sequence, not after it
- Identify inputs that need validation and boundaries that need hardening (carry forward from Brainstorm security boundaries)
- Ensure the plan is self-contained: executable without re-reading earlier phases

**Tips:**
- If any single step would take more than an hour, break it into smaller steps
- The plan is a living document — update it if execution reveals problems

**Output:** Write `plan.md` with: file structure, build sequence, testing strategy, acceptance criteria checklist.

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

**Test early and often** — smoke testing catches bugs that you miss. If something doesn't work, describe the error precisely: "This function returns X but I expected Y."

**Output:** Write `execute.md` with: summary of what was built, bugs found and fixed, acceptance criteria results.

**Gate:** "Execution complete. Ready for Verify, or want to revise?"

---

## Phase 6: Verify

**Goal**: Independently confirm that what was built actually works, is secure, and meets acceptance criteria.

This phase exists because Execute self-reports its own results. Verify is the adversarial counterpart — assume the result has problems and check.

**Superpowers option:** If `superpowers:verification-before-completion` is available, offer the user a choice:
> **A)** Use the built-in Verify phase — run tests, check criteria, produce `verify.md`
> **B)** Go deep with `superpowers:verification-before-completion` — structured verification with evidence requirements

If they choose B, invoke `superpowers:verification-before-completion`. After it completes, synthesize results into `verify.md` in the iteration directory before advancing.

**Activities:**
- Run the full test suite and record results — don't trust prior Execute output
- Walk through each acceptance criterion from the plan and confirm pass/fail with evidence
- Run static analysis, linting, or security scanning if available in the project
- Check for common security issues: unsanitized input, hardcoded secrets, missing auth checks, exposed error details
- If `superpowers:requesting-code-review` is available, offer to invoke it for a structured code review

**If verification fails:** Do not mark the iteration complete. Either return to Execute to fix issues, or note failures for the next iteration's Review/Reflect phase.

**Output:** Write `verify.md` with: test results, acceptance criteria pass/fail with evidence, security check results, and any issues found.

**Gate:** "Verification complete. Iteration N finished." (Only if all acceptance criteria pass. Otherwise: "Verification found issues — return to Execute, or carry forward to next iteration?")

---

## Gating Mechanics

Phase gates are **guided, not rigid**. Present the gate prompt and wait for the user's response.

| Response | Behavior |
|----------|----------|
| "yes" / "next" / "go" | Advance to next phase |
| "skip" | Advance without producing the output file; mark as skipped in checklist |
| "revise" | Stay in current phase, continue working |
| "back" / "back to [phase]" | Return to a previous phase |

Update the TodoWrite checklist as each phase completes or is skipped.

## Parallel Agent Dispatch

At any phase, if the work involves 2+ independent subtasks, suggest dispatching parallel agents using the Agent tool. This is a suggestion — the user can decline.

Examples:
- **Review/Reflect**: Loading and summarizing multiple independent documents
- **Brainstorm**: Exploring alternative approaches concurrently
- **Research**: Evaluating competing tech stack options side by side
- **Plan**: Designing independent subsystems concurrently
- **Execute**: Building independent components in parallel
- **Verify**: Running independent test suites or security checks concurrently

## Iteration

This skill handles one pass through the cycle. To iterate:

1. Re-invoke `/llm-dev:cycle` in the same working directory
2. The skill auto-increments to `iteration-N+1/`
3. The Review/Reflect phase of the new iteration reads prior iteration outputs and reflects on what happened

Each iteration should be smaller and more focused than the last.

## When to Refactor

Refactoring is not a phase — it emerges from the existing phases when the code signals it's time. Two patterns:

**Small, targeted refactoring during Execute.** When implementation reveals that the code structure isn't right — a function doing too much, a module with tangled responsibilities — fix it as you go. This is normal engineering, not a separate activity.

**Refactoring as its own iteration.** When structural problems are large enough to warrant dedicated attention, run a full cycle with refactoring as the goal: Review/Reflect identifies the friction, Brainstorm explores alternative designs, Plan sequences the changes, Execute does the refactoring, Verify confirms nothing broke.

**Signals that it's time:**
- Verify reveals code that's hard to test or reason about
- Review/Reflect on successive iterations keeps noting the same friction points
- Adding a new feature requires touching too many files or understanding too much context
- You find yourself working around the structure rather than working with it

Don't refactor on a schedule. Don't refactor preemptively. Let the cycle surface the need.
