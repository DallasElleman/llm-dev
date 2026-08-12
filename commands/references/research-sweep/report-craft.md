# Report craft — the quality contract

Two things live here: the block every agent prompt must carry, and the rules for synthesizing agent output into one report.

---

## Part 1 — the block every agent prompt carries

Paste this into every subagent prompt, filled in.

```
STRICT: READ-ONLY. Do NOT create, edit, or delete ANY file in the repository.
No mutating git commands. No deploys. No writes to production systems.
You MAY read, grep, run read-only shell commands, and read databases via a COPY.
Scratch space for working files: <SCRATCHPAD_PATH>

CALIBRATION — these facts should shape your entire analysis:
<the Step 1 facts: scale, real usage, activity, shipping state, stack>

ALREADY CONFIRMED — do NOT re-derive these; extend beyond them:
<seeded findings from earlier waves, with file:line>

METHOD:
- Cite file:line for every claim. Verify before asserting — never report drift,
  dead code, or duplication you have not checked.
- Label every number: [measured] (you ran it), [estimated] (you reasoned to it,
  state the assumption), or [reported] (a doc claims it; say whether you checked).
- Rank findings by COST OF BEING WRONG — would this send someone down a wrong
  path, lose data, or mislead a decision? — not by abstract severity.
- Distinguish a real problem from a stylistic nit, and say which you think it is.
- Include a "Checked and cleared" section: suspicions you investigated and found
  to be NON-issues, with why. This is as valuable as the findings.
- Include a "What's genuinely good" section, specific and evidence-backed.
- Where a finding is checkable, give the exact command that checks it.
- State what you could NOT verify and what it would take.
- No padding. No restating the prompt. Findings ranked, evidence first.
```

### Why each rule is there

- **Calibration facts** — without them agents produce generic best-practice advice. With them, analysis gets specific: "12k LOC serving 1 user" produces a different and better report than "12k LOC."
- **Seeded findings** — prevents four agents independently rediscovering the same stale reference and burning the budget on it.
- **Cost-of-being-wrong ranking** — High/Medium/Low collapses under disagreement. "Would this mislead someone tomorrow" sorts cleanly and survives review.
- **Checked-and-cleared** — stops the next sweep re-deriving the same non-issues, and it is the section that makes a report trustworthy: a report with no cleared suspicions was not actually skeptical.
- **What's-genuinely-good** — not politeness. It constrains recommendations. A report that catalogues only defects will recommend a rewrite; one that names the load-bearing quality will recommend the smaller correct thing.
- **Measured vs. estimated labels** — the single biggest credibility lever. An unlabeled number is assumed measured, and when it turns out to be a guess the whole report loses standing.

---

## Part 2 — synthesis rules

### Structure

1. **Verdict** — a few sentences. If one finding reframes everything else, lead with it and say so plainly.
2. **Verified facts table** — the handful you re-checked yourself, with the evidence inline. This is what earns the reader's trust in the rest.
3. **Findings**, grouped by theme, ranked by cost of being wrong within each group.
4. **What's genuinely good** — before the recommendations, because it constrains them.
5. **Recommended actions** — sequenced (today / this week / this month / ongoing), each with rough effort.
6. **What not to do** — the paths you considered and rejected, with reasons. Prevents the reader over-correcting, and prevents the next reviewer re-proposing them.
7. **What you could not verify** — explicit, with what it would take.

### Rules

- **One report, not stapled agent output.** If two agents found the same thing, state it once. If they disagree, resolve it or say it's unresolved and why.
- **Report the adversarial pass.** "N findings dropped after verification" is a quality signal; hiding it isn't.
- **Corrections are load-bearing.** If your own verification overturned an agent claim, say so and show the method. That is often the most useful paragraph in the report.
- **Don't inflate.** If a sweep finds little, the report is short. A thin report on a healthy codebase is a real result.
- **Separate "this is broken" from "this is a judgment call."** Judgment calls get the trade-off stated and a recommendation, not a verdict.
- **Name bug classes.** A one-line label ("schema-accepts-but-runtime-ignores", "lazy-import defeated by a sibling module-level import") makes a lesson reusable in a way a paragraph doesn't.
- **Effort estimates are judgment, not measurement.** Label them as such.

### Tone

Direct, specific, and fair. The user asked for findings, not reassurance — but a pile-on is as useless as a whitewash, because neither tells them where to spend the next week. Disagree with the codebase where warranted, credit it where earned, and make every claim checkable.

---

## Part 3 — issue framings

When the user says yes to filing, match the framing to the content.

**Independent analysis** — for architecture and product work, where context you lack may change conclusions. Open with what the analysis is, how it was produced, and three caveats: it's an outside read that doesn't know the constraints behind the decisions; it's calibrated to today's state; directness isn't confidence. Close with open questions only the team can answer, and invite the specific disagreements you most expect.

**Observations to investigate** — for coherence and drift work, where individual claims are cheap to check and some will be wrong. Attach the verification command to each finding. Say plainly that a finding which doesn't reproduce is more useful than one that does. Include a "things that look wrong and aren't" section.

**Direct findings** — for security and correctness work, where the finding either holds or doesn't. State severity, exploit or failure scenario, and fix. Fewer caveats; the evidence carries it.

**All framings:** cross-link related issues, and put the ranked action list last so it's the thing a reader lands on.
