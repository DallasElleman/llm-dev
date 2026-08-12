---
description: Parallel, read-only, multi-angle research over a repository, synthesized into one evidence-backed report
argument-hint: [--types t1,t2] [--depth quick|standard|deep] [--publish]
allowed-tools: Bash(*), Read, Grep, Glob, Task, AskUserQuestion, SendUserFile
---

# Research Sweep

Calibrate a repository, fan out parallel read-only subagents across the
research types you pick, verify their findings adversarially, and synthesize
one evidence-backed report. For "audit this," "review the codebase," "find
contradictions," "is this ready to ship."

**Non-negotiable: this command never modifies the repository it's pointed
at.** No file writes, no mutating git, no deploys, at any stage. The report
goes to the scratchpad; publishing it anywhere durable is opt-in and asked
for explicitly at the end, regardless of what was selected in the menu.

## What This Does

1. **Calibrates first.** The handler gathers ground-truth facts itself —
   this is arithmetic, not analysis, so it doesn't belong in an agent
   prompt: LOC by language, module/test counts, commits and distinct authors
   over 90 days, branch divergence from the default branch, deploy config
   found, live URL if any, whether a substantive README entry point exists.
   *"12k LOC serving 1 user"* is a different report than *"12k LOC serving
   50k users"* — calibration is what makes the difference between generic
   advice and sharp analysis.
2. **Presents research types**, each breaking into 3-6 sub-domains, with a
   `recommended` flag derived from calibration (see Flags below).
3. **Fans out one read-only subagent per sub-domain**, each carrying the
   quality contract from
   [report-craft.md](./references/research-sweep/report-craft.md) and the
   matching prompt skeleton from
   [report-types.md](./references/research-sweep/report-types.md).
4. **Verifies adversarially, then synthesizes** one report per the
   synthesis rules in report-craft.md.

## Usage

**Step 1 — discover + calibrate** (no `--types`): the handler gathers
calibration facts and prints `RESEARCH_TYPES_NEEDED: <JSON>`, then exits
without dispatching anything.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/research-sweep.py $ARGUMENTS
```

**Step 3 — dispatch once** (after the user picks): re-run with the chosen
types. The handler prints `RESEARCH_SWEEP_PLAN: <JSON>` — the selected
types' sub-domains and the same calibration facts — and still dispatches
nothing itself; you do the fan-out.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/commands/handlers/research-sweep.py --types <slug1,slug2> --depth <depth> [--publish]
```

## Step 2 — Present With `AskUserQuestion`

Parse the `RESEARCH_TYPES_NEEDED` JSON. Report the calibration facts to the
user in a few lines first — the choice should be informed. **If calibration
turns up something surprising (branch is hundreds of commits ahead, no
README, a deploy config with no recent activity), say so before the menu** —
it changes which types are worth running.

**The 4-option constraint.** `AskUserQuestion` allows at most 4 options per
question, and there are 7 research types plus depth and publish config. This
command **splits the types into two questions by the JSON's `group` field**
(`code-health`: 4 types, `product-ops`: 3 types) rather than surfacing only
the top-4-by-`recommended` and pushing the rest into the automatic **Other**
box. Reasoning: `research-sweep`'s types are not mutually exclusive and none
are more "default" than the others the way `init-session`'s streams are (one
active stream is usually the obvious pick) — burying 3-4 legitimate options in
free text would make them easy to miss. A clean two-question split keeps
every option visible and still fits the cap. Send all four questions in a
**single `AskUserQuestion` call**:

1. **Code health** (`multiSelect: true`) — one option per `code-health`-group
   type, each described with its `preview` and sub-domain count; mark
   `recommended` types in the option description.
2. **Product & ops** (`multiSelect: true`) — same, for the `product-ops`
   group.
3. **Depth** (single-select) — `quick` / `standard` (default) / `deep`, each
   described per [report-types.md](./references/research-sweep/report-types.md#depth-levels).
4. **Publish when done?** (single-select) — `No, scratchpad only` (default) /
   `Yes, ask me where when the report is ready`.

**Initialize once.** Map the answers to a single re-invocation on step 3,
combining the selections from questions 1 and 2 into one `--types` list. If
the user selected nothing in a question, omit that group entirely — do not
re-prompt unless the combined selection across both questions is empty.

### Config the user may adjust — always honor it

Depth and publish are asked directly. The rest have defaults; the automatic
**Other** free-text box is where a user overrides them (e.g. *"2,6 deep, 8
agents, sonnet"*).

| Setting | Default | Notes |
|---|---|---|
| Max concurrent subagents | **20** | Hard cap on one dispatch wave; batch if the plan exceeds it (`agent_count.exceeds_cap` in the plan JSON) |
| Model | **opus** | `opus` / `sonnet` / `haiku`. Sonnet is acceptable for dependency and onboarding sweeps; use opus for code-quality, architecture, and coherence |
| Depth | **standard** | `quick` = merge each type into 1 agent · `standard` = all sub-domains · `deep` = sub-domains + the extra angles listed per type |
| Adversarial pass | **on** | A skeptic agent per report, prompted to refute. Turn off only if the user asks |

## Step 4 — Dispatch

Parse the `RESEARCH_SWEEP_PLAN` JSON. Build each agent prompt from the section
of [report-types.md](./references/research-sweep/report-types.md) named by the
type's `report_types_section`, and give **every** prompt:

1. **The read-only constraint**, verbatim from the Part 1 block in
   [report-craft.md](./references/research-sweep/report-craft.md), plus the
   scratchpad path for working files.
2. **The calibration facts.** This is the highest-leverage thing in the prompt.
3. **Seeded findings** — any already-confirmed items from earlier waves, framed
   as *"ALREADY CONFIRMED — do not re-derive; extend beyond these."* Yield rises
   sharply and duplicate work collapses.
4. **The quality contract** from report-craft.md (evidence, ranking, required
   sections).

**State the fan-out before dispatching** — the plan JSON's `agent_count` gives
it: *"7 types × sub-domains = 31 agents, then 7 verifiers. Proceed?"* If
`exceeds_cap` is true, batch the waves and say so.

Launch every agent for a wave **in a single message** so they run concurrently.
Never launch one, wait, then launch the next.

Order the waves so types producing reusable facts run first — `code-quality-security`
and `coherence-sweep` tend to seed the others.

## Step 5 — Adversarial verification

Unless the user turned it off, dispatch one skeptic per completed report, all in
one message:

> You are verifying a research report. Your job is to REFUTE, not confirm. For
> each of the top N findings: attempt to disprove it by reading the code/docs
> directly. Default to "refuted" when evidence is ambiguous. Report per finding:
> CONFIRMED (with the evidence you found) / REFUTED (with why) / OVERSTATED
> (true but the significance is inflated). Also flag any finding whose severity
> ranking you disagree with. Read-only; do not modify anything.

Drop refuted findings. Downgrade overstated ones. **Say in the final report how
many findings were dropped** — that number is a quality signal for the reader.

## Step 6 — Verify the headlines yourself

**Do not skip this.** Agents narrate plausibly and will be confidently wrong.
Before writing anything, independently re-check the **top 5–8 claims per
report** — the ones that would change what the user does tomorrow.

Run the actual command. Read the actual file. Hit the actual endpoint. Two traps
seen repeatedly:

- **Tool output that looks clean but answered a different question.** Flags that
  filter one dimension while silently evaluating another against the host;
  queries that return everything when you assumed they filtered.
- **A measurement taken under the wrong constraint**, producing a plausible
  number for a configuration that doesn't exist.

When a headline claim fails verification, say so in the report and correct it —
a corrected claim with the method shown is worth more than a confident wrong one.

## Step 7 — Synthesize and deliver

One report, not a stack of agent outputs. Follow the synthesis rules in
report-craft.md. Lead with the single finding that reframes the rest, if there
is one.

1. Write the report to the scratchpad directory (never the repo). Name it
   `<repo>-<type>-<date>.md`.
2. Send it with `SendUserFile`.
3. Summarize inline: the verdict, the 3–5 findings that matter, and anything you
   could not verify.
4. **Then ask** whether to file a GitHub issue, and with which framing —
   *independent analysis*, *observations to investigate*, or *direct findings*
   (see report-craft.md Part 3).

**Only offer to publish after the report is complete.** `--publish` records the
user's stated intent from the menu; it is not standing permission to skip that
final confirmation. Never file an issue without an explicit yes.

**Redaction rule:** if the sweep finds live credentials, private user data, or
exploitable security detail, do not put the coordinates in a public or shared
issue. Reference it as handled out-of-band, keep specifics in the local report,
and tell the user why.

## Flags

- `--types <slug1,slug2,...>` — comma-separated research type slugs to
  dispatch. Omit for discovery mode. Valid slugs: `code-quality-security`,
  `dependency-supply-chain`, `accessibility`, `coherence-sweep`,
  `architecture-product`, `onboarding`, `pre-launch-readiness`.
- `--depth quick|standard|deep` — sweep depth (default: `standard`). See
  [report-types.md](./references/research-sweep/report-types.md#depth-levels).
- `--publish` — records that the user opted into publishing the report from
  the menu. The command still asks for explicit confirmation before writing
  the report anywhere durable.
- `--project-path PATH` — explicit project root to calibrate (default: cwd).

## Recommended-Type Heuristics

Derived purely from calibration, computed by the handler:

- **`pre-launch-readiness`** — branch is 10+ commits ahead of the detected
  default branch *and* a deploy config was found (nothing to launch-check
  without one).
- **`dependency-supply-chain`** — a dependency manifest (`package.json`,
  `requirements.txt`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `Gemfile`,
  `composer.json`) changed in the last 90 days.
- **`onboarding`** — no substantive `README.md` entry point (missing, or
  under ~200 characters).

These are signals to weight the menu, not gates — every type is always
offered regardless of its `recommended` value.

## Error Handling

If the handler fails:
- `--types` with an unrecognized slug prints the valid slug list to stderr
  and exits 1 — re-check the `RESEARCH_TYPES_NEEDED` JSON for the exact
  slugs.
- Calibration facts that can't be determined (no git remote, shallow clone,
  no `.git` at all) come back as `null` rather than failing the whole run —
  treat a `null` calibration fact as "unknown," not "zero."
