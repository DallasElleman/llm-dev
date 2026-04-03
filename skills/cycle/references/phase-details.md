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
| Verify | `superpowers:verification-before-completion` | Evidence-based verification, structured checks |
| Verify | `superpowers:requesting-code-review` | Structured code review (offer as optional addition) |

### How Delegation Works

1. At the start of a delegatable phase, check if the corresponding superpowers skill is available
2. Present the choice to the user (built-in vs. superpowers)
3. If superpowers is chosen, invoke the skill with the Skill tool
4. After the superpowers skill completes its workflow, synthesize results into the canonical output file (`brainstorm.md`, `plan.md`, `execute.md`, or `verify.md`)
5. Advance through the gate as normal

### Canonical Output Rule

The iteration directory must always contain the canonical output files as the authoritative record. Superpowers skills may produce additional artifacts (spec docs, formal plans, etc.) — those coexist alongside the canonical files but do not replace them.

When synthesizing superpowers output into a canonical file:
- Capture the key decisions, rationale, and outcomes
- Reference the superpowers artifact location if relevant
- Keep the canonical file self-contained and readable

---

## Extended Phase Guidance

### Review/Reflect — Going Deeper

The Review phase is about context loading, not analysis. On iteration 2+, reflection comes first. Common mistakes:
- Jumping to solutions before understanding constraints
- Expanding scope instead of narrowing it
- Accepting your own summaries without user verification
- On repeat iterations: ignoring lessons from the previous cycle

**Useful prompts for this phase:**
- "Read these files and summarize the key constraints and requirements"
- "What gaps or ambiguities do you see in these requirements?"
- "Which of these N options is simplest to implement? Which lends itself best to demonstration?"
- (Iteration 2+) "What went wrong last iteration and what should change?"

### Brainstorm — Going Deeper

This phase is about collaborative exploration and decision-making, not presenting options. Common mistakes:
- Presenting a list of options instead of having a conversation
- Starting to code before deciding what to build
- Not documenting rejected alternatives
- Letting scope creep in through "nice to have" features
- Ignoring security boundaries until implementation

**Useful prompts for this phase:**
- "Before suggesting anything, ask me questions one at a time to understand what I'm trying to build"
- "Propose 2-3 approaches with trade-offs, then recommend one"
- "What should we explicitly NOT build?"
- "Where does untrusted input enter this system?"

### Research — Going Deeper

This phase is about tool selection and validation, not deep learning. Common mistakes:
- Choosing the most powerful tool instead of the simplest adequate one
- Not verifying that recommended packages exist and are maintained
- Committing to unfamiliar tools without seeing a minimal example
- Ignoring dependency security posture

**Useful prompts for this phase:**
- "What's the simplest tool that meets these requirements?"
- "Show me a minimal working example with [tool] before I commit to it"
- "Does this library actually exist? When was it last updated?"
- "Run a dependency audit — are there known vulnerabilities?"

### Plan — Going Deeper

This phase turns research into action. Common mistakes:
- Steps that are too large (> 1 hour each)
- Missing acceptance criteria
- Plans that require re-reading earlier phases to understand
- Treating testing as an afterthought instead of part of the build sequence

**Useful prompts for this phase:**
- "Break this into steps where each takes less than an hour"
- "Add acceptance criteria: how will I know each step is done?"
- "Can someone execute this plan without reading the brainstorm or research?"
- "Where are the tests in this build sequence?"

### Execute — Going Deeper

This phase is about disciplined building. Common mistakes:
- Not testing until the end
- Pushing through a broken plan instead of updating it
- Not documenting bugs found and fixed

**Useful prompts for this phase:**
- "Test this component before moving to the next one"
- "The plan said X but we discovered Y — update the plan"
- "Summarize what was built, what broke, and what we learned"

### Verify — Going Deeper

This phase is about adversarial validation — assume problems exist and find them. Common mistakes:
- Trusting Execute's self-reported results without re-running tests
- Checking only the happy path
- Skipping security checks because "it's just an internal tool"
- Marking the iteration complete despite failing acceptance criteria

**Useful prompts for this phase:**
- "Run the tests again from scratch and show me the output"
- "Walk through each acceptance criterion and show evidence of pass/fail"
- "What happens if I send malformed input to this endpoint?"
- "Are there any hardcoded secrets, missing auth checks, or unsanitized inputs?"
