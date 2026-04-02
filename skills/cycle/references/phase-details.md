# Phase Details & Superpowers Integration

Extended guidance for each phase of the development cycle. Load this reference when the user wants deeper help with a specific phase or when superpowers delegation is in play.

---

## Superpowers Integration

### Delegation Map

| Phase | Superpowers skill | What it adds |
|-------|------------------|--------------|
| Brainstorm | `superpowers:brainstorming` | Visual companion, structured spec workflow, design doc output |
| Plan | `superpowers:writing-plans` | Formal implementation plan with bite-sized TDD tasks, exact file paths, acceptance criteria |
| Execute | `superpowers:executing-plans` | Structured execution with review checkpoints, subagent dispatch |

### How Delegation Works

1. At the start of a delegatable phase, check if the corresponding superpowers skill is available
2. Present the choice to the user (built-in vs. superpowers)
3. If superpowers is chosen, invoke the skill with the Skill tool
4. After the superpowers skill completes its workflow, synthesize results into the canonical output file (`brainstorm.md`, `plan.md`, or `execute.md`)
5. Advance through the gate as normal

### Canonical Output Rule

The iteration directory must always contain the canonical output files as the authoritative record. Superpowers skills may produce additional artifacts (spec docs, formal plans, etc.) — those coexist alongside the canonical files but do not replace them.

When synthesizing superpowers output into a canonical file:
- Capture the key decisions, rationale, and outcomes
- Reference the superpowers artifact location if relevant
- Keep the canonical file self-contained and readable

---

## Extended Phase Guidance

### Review — Going Deeper

The Review phase is about context loading, not analysis. Common mistakes:
- Jumping to solutions before understanding constraints
- Expanding scope instead of narrowing it
- Accepting LLM summaries without verification

**Useful prompts for this phase:**
- "Read these files and summarize the key constraints and requirements"
- "What gaps or ambiguities do you see in these requirements?"
- "Which of these N options is simplest to implement? Which lends itself best to demonstration?"

### Brainstorm — Going Deeper

The Brainstorm phase is about making decisions, not writing code. Common mistakes:
- Starting to code before deciding what to build
- Not documenting rejected alternatives
- Letting scope creep in through "nice to have" features

**Useful prompts for this phase:**
- "Before suggesting anything, ask me questions one at a time to understand what I'm trying to build"
- "Propose 2-3 approaches with trade-offs, then recommend one"
- "What should we explicitly NOT build?"

### Research — Going Deeper

The Research phase is about tool selection, not deep learning. Common mistakes:
- Choosing the most powerful tool instead of the simplest adequate one
- Not verifying that recommended packages exist and are maintained
- Committing to unfamiliar tools without seeing a minimal example

**Useful prompts for this phase:**
- "What's the simplest tool that meets these requirements?"
- "Show me a minimal working example with [tool] before I commit to it"
- "Does this library actually exist? When was it last updated?"

### Plan — Going Deeper

The Plan phase turns research into action. Common mistakes:
- Steps that are too large (> 1 hour each)
- Missing acceptance criteria
- Plans that require re-reading earlier phases to understand

**Useful prompts for this phase:**
- "Break this into steps where each takes less than an hour"
- "Add acceptance criteria: how will I know each step is done?"
- "Can someone execute this plan without reading the brainstorm or research?"

### Execute — Going Deeper

The Execute phase is about disciplined building. Common mistakes:
- Not testing until the end
- Pushing through a broken plan instead of updating it
- Not documenting bugs found and fixed

**Useful prompts for this phase:**
- "Test this component before moving to the next one"
- "The plan said X but we discovered Y — update the plan"
- "Summarize what was built, what broke, and what we learned"
