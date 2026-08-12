# llm-dev

A Claude Code plugin for LLM-assisted development workflows.

## Overview

**llm-dev** provides:
- **Slash Commands**: `/init-session`, `/end-session`, `/stream`, `/init-project`, `/init-workspace`, `/update-agents-md`, `/research-sweep`
- **Skills**: `/cycle` — a structured 6-phase development loop (Review/Reflect, Brainstorm, Research, Plan, Execute, Verify)
- **Project Templates**: Standardized scaffolding for new projects
- **Workspace Templates**: Multi-project workspace structure
- **Session Tracking**: Optional conversation archival, in-flight notes, and forward-looking handoffs for institutional memory and seamless cross-session continuity
- **Multi-Stream Support**: Named, persistent work streams that sessions claim and hand off to each other

## Installation

### From Marketplace (recommended)

1. In Claude Code, run `/plugins`
2. Select **Marketplaces** → **Add Marketplace**
3. Enter `DallasElleman/llm-dev` as the marketplace source
4. Install the llm-dev plugin

### As Claude Code Plugin (manual)

```bash
git clone https://github.com/DallasElleman/llm-dev.git ~/.claude/plugins/llm-dev
```

Add to `~/.claude/settings.json`:
```json
{
  "plugins": ["~/.claude/plugins/llm-dev"]
}
```

### As Workspace Submodule

```bash
git submodule add https://github.com/DallasElleman/llm-dev.git llm-dev
```

Add to `.claude/settings.json`:
```json
{
  "plugins": ["./llm-dev"]
}
```

## Requirements

- **Python 3.12+**: Required for command handlers (`init-session`, `end-session`, `stream`, `init-project`, `init-workspace`, `research-sweep`)
- Works natively on **Windows**, **macOS**, and **Linux**
- No pip dependencies — standard library only
- Commands invoke `python3`. On Windows, if `python3` is not recognized, either add it to your PATH or create an alias (e.g., `doskey python3=python $*` in CMD, or `Set-Alias python3 python` in PowerShell)

## Commands

### /init-project

Create a new project from llm-dev templates.

```
/llm-dev:init-project <project-name> [--path PATH] [--description DESC] [--dry-run]
```

Copies `.project-template/` to the target directory, replaces `{{PROJECT_NAME}}`, `{{PROJECT_DESCRIPTION}}`, and related placeholders, initializes `.archive/` infrastructure, and optionally sets up a git repository.

### /init-workspace

Set up a multi-project workspace structure.

```
/llm-dev:init-workspace <workspace-name> [--path PATH] [--description DESC] [--dry-run]
```

Copies `.workspace-template/` to the target directory and initializes a git repository with an initial commit.

### /init-session

Initialize a conversation session for transcript tracking.

```
/llm-dev:init-session [--model MODEL] [--user USERNAME] [--stream SLUG] [--no-stream] [--dry-run]
```

What it does:
1. Reads the current conversation number from `.archive/transcripts/_index.md` and increments it
2. Adds a placeholder entry to the transcript index
3. Creates a dated session-notes file at `.archive/session-notes/YYYYMMDD-NNN-session-notes.md`
4. Resolves and prints paths to the **prior session's** transcript, notes, and handoff for continuity

**Stream Selection** — when run, the handler offers a stream to claim:
- **No arg** (interactive): prints the stream registry and prompts you to pick. When exactly one `active` stream exists, pressing Enter selects it.
- `--stream <slug>`: claim a specific stream non-interactively. If already claimed by another session, surfaces a contention warning with the holder's session ID and notes file, then asks to confirm reclaim.
- `--no-stream`: start a free session without stream association.

The selected stream determines which prior handoff loads as resume context, whether filenames include the stream slug, and whether `/end-session` updates the stream's registry row.

**Picking up the thread** — after running, read prior-session context in this order:
1. **Handoff** — high-signal re-entry point (where we left off, what's in flight, first action)
2. **Notes** — retrospective context from the prior session
3. **Transcript** — full record; skim or skip unless the handoff references specific exchanges

### /end-session

Wind the session down — finalize session notes, write a handoff document, and archive the transcript.

```
/llm-dev:end-session <number> "<title>" [--topics "t1, t2"] [--stream SLUG] [--sanitize] [--dry-run]
```

**Flow (Claude performs these in order):**
1. **Finalize session notes** — do a final pass on `.archive/session-notes/YYYYMMDD-NNN-*-session-notes.md`, capturing what worked, lessons learned, mistakes made, and assumptions proven wrong. The handler commits notes as-is; update them before running.
2. **Read the prior handoff** — load the most recent `*-session-handoff.md` from `.archive/session-handoff/` to carry the chain forward.
3. **Write the new handoff** at `.archive/session-handoff/YYYYMMDD-NNN-session-handoff.md` — forward-looking context for the next session: where we left off, wins, in-flight work, deferred items, locked-in decisions, key references, gotchas, and a first-action pointer.
4. **Run the handler** to archive everything.

**What the handler does automatically:**
- Finds session ID from the index placeholder set by `/init-session`
- Converts JSONL → llm-dev JSON transcript format
- Generates outcomes from file operations in the conversation
- Scans for PII (home paths, names, emails, potential secrets) before commit
- Updates transcript index (replaces `[In Progress]` placeholder)
- Updates CHANGELOG (adds entry at top, reverse-chronological)
- Commits the bundle: transcript + session-notes + session-handoff

**Stream behavior** — if the session held a stream claim:
- Handoff and transcript filenames include the stream slug
- The stream's registry row is updated: `Claim` → `unclaimed`, `Since` → `—`, `Last Touched` → now, `Last Handoff` → new path

**Arguments:**
- `<number>` — session number (from `/init-session`)
- `<title>` — brief title, 3–7 words
- `--stream SLUG` — override stream slug (normally auto-detected from registry)
- `--topics "t1, t2"` — comma-separated topics (auto-generated if omitted)
- `--sanitize` — automatically redact PII without prompting
- `--dry-run` — preview without writing files

### /stream

Manage work streams within a project. Streams are named, persistent units of work registered in the `## Streams` table of `CURRENT-TODOs.md`. Sessions claim one stream (or run free) at `/init-session` time, and release the claim when `/end-session` runs.

```
/llm-dev:stream <subcommand> [args]
```

| Subcommand | Description |
|---|---|
| `list [--all]` | Show streams; hides archived by default |
| `new <slug> ["<name>"]` | Register a new stream (status=active, unclaimed) |
| `join <slug>` | Claim a stream from inside an in-flight free session |
| `release` | Release this session's stream claim (session becomes free) |
| `pause <slug>` | Set stream status to paused |
| `resume <slug>` | Set stream status to active |
| `archive <slug>` | Set stream status to archived (refuses if currently claimed) |
| `rename <old-slug> <new-slug>` | Change the slug (refuses if currently claimed) |

**Examples:**
```
/llm-dev:stream list
/llm-dev:stream new website "Public-facing website"
/llm-dev:stream join website
/llm-dev:stream pause website
/llm-dev:stream archive old-experiment
/llm-dev:stream rename web web-platform
```

### /update-agents-md

Maintain the project's `AGENTS.md` / `CLAUDE.md` — the file injected into every
agent session, where a wasted line is a tax paid thousands of times and a wrong
line is a confident mistake repeated thousands of times.

```
/llm-dev:update-agents-md [--mode refresh|verify-refs|targeted|audit] [--sections "<list>"] [--list]
```

Run with no `--mode` and the handler computes calibration facts — staleness,
size, instruction-bearing line count, a per-section inventory, dangling
references, current branch vs. the file's deploy-branch claim — prints
`AUDIT_SCOPE_NEEDED: <JSON>`, and exits without acting. Claude presents the
scope menu, then re-invokes exactly once with the chosen mode.

| Mode | What it does |
|---|---|
| `refresh` | Re-verify volatile assertions (objective, deploy branch, module roles), fix drift, re-date. No subagents. |
| `verify-refs` | Resolve every path, markdown link, and numeric `§N` anchor; report what's broken. |
| `targeted` | Apply the audit protocol to specific sections (`--sections`). |
| `audit` | Full protocol, dispatching one read-only agent per angle. |

**Key behaviors:**
- The handler owns the arithmetic — agent self-counts are unreliable, so the counts come from the JSON, not a subagent's tally
- Audits use falsifier-before-search, and `UNVERIFIABLE-here` is a first-class verdict; removal needs evidence, not just age
- `--restamp` updates the `Last edited` date as a separate mechanical step, run after edits land
- A full audit is refused from a session that already has the file in context — an agent's copy is a session-start snapshot that subagents inherit, so the only clean channel is to hold the file aside and start a fresh session

### /research-sweep

Parallel, read-only, multi-angle research over a repository, synthesized into
one evidence-backed report. For "audit this," "review the codebase," "find
contradictions," "is this ready to ship." **Never modifies the repository** —
no file writes, no mutating git, no deploys; publishing the report anywhere
durable is opt-in and asked for explicitly at the end.

```
/llm-dev:research-sweep [--types t1,t2] [--depth quick|standard|deep] [--publish]
```

**Discovery-then-single-dispatch** (same pattern as `/init-session`'s stream
selection):
1. Run with no `--types` — the handler calibrates the repo itself (LOC by
   language, module/test counts, 90-day commit activity, branch divergence
   from the default branch, deploy config, live URL, README entry point) and
   prints the available research types with a `recommended` flag per type,
   then exits without dispatching anything.
2. Claude reports the calibration facts, then presents the seven research
   types via `AskUserQuestion` (`multiSelect: true`), split into two
   questions — **code health** (code quality/security/efficiency,
   dependency & supply chain, accessibility, coherence sweep) and **product
   & ops** (architecture & product, onboarding, pre-launch readiness) — plus
   depth and publish-preference questions, all within the tool's 4-option
   cap.
3. Claude re-invokes once with `--types <selected slugs>`, dispatching one
   read-only subagent per sub-domain, verifying findings adversarially, and
   synthesizing one report.

See [commands/research-sweep.md](commands/research-sweep.md) for the full
flow and [commands/references/research-sweep/](commands/references/research-sweep/)
for the quality contract and per-type prompt skeletons.

## Skills

### /cycle

A structured 6-phase development loop for tasks that benefit from thinking before coding.

**Phases**: Review/Reflect → Brainstorm → Research → Plan → Execute → Verify

Each phase produces a markdown file in an iteration directory (`iteration-N/`). Phases can be skipped, revisited, or delegated to superpowers skills where available. Re-invoking `/llm-dev:cycle` in the same working directory auto-increments to the next iteration.

**Key behaviors:**
- Phase gates are guided, not rigid — the user can advance, skip, revise, or go back to a prior phase
- Phases 2 (Brainstorm), 4 (Plan), 5 (Execute), and 6 (Verify) offer superpowers skill integration when those skills are available
- At any phase, parallel agent dispatch can be suggested for independent subtasks
- Iteration N+1 starts with a Review/Reflect that reads prior iteration outputs and reflects on what changed

See [skills/cycle/SKILL.md](skills/cycle/SKILL.md) for full phase details, and [skills/cycle/cycle-vs-superpowers.md](skills/cycle/cycle-vs-superpowers.md) for how `/cycle` compares to the related superpowers skills (brainstorming, writing-plans, executing-plans, verification-before-completion).

## Session Tracking

Session tracking is **optional** and **command-driven**:

1. Run `/llm-dev:init-session` to begin tracking. Creates a placeholder in the transcript index, scaffolds a session-notes file, and surfaces the prior session's transcript / notes / handoff for continuity.
2. Throughout the session, update `.archive/session-notes/YYYYMMDD-NNN-session-notes.md` with what worked, lessons learned, mistakes made, and wrong assumptions. Capture wins as well as corrections.
3. At session end, run `/llm-dev:end-session`. Claude finalizes the session notes, writes a forward-looking handoff document, and the handler archives the conversation and commits the bundle.

Archives include:
- Verbatim dialogue preservation (JSONL → llm-dev JSON)
- Auto-generated outcomes from file operations
- Automatic index/CHANGELOG updates
- Per-session notes for cross-session learning
- Per-session handoffs as high-signal re-entry points for the next session

## Multi-Stream Session Tracking

Streams let multiple parallel workstreams (features, bugfixes, experiments) live in the same project without interfering with each other's handoffs and transcripts.

**How it works:**
- Streams are registered in the `## Streams` table in `CURRENT-TODOs.md`
- Each stream has a slug, name, status (`active`/`paused`/`archived`), and a `Claim` column showing which session currently owns it
- A session can claim one stream at `/init-session` time; the claim is released automatically when `/end-session` runs
- Claimed-stream sessions use `YYYYMMDD-NNN-<slug>-session-handoff.md` filenames so handoffs and transcripts are scoped to the stream
- A free session (no stream) runs the normal flat filename scheme

**Stream lifecycle:**
```
new → active (unclaimed) → claimed → active (unclaimed) → ... → archived
                        ↘ paused ↗
```

**Registry table** (in `CURRENT-TODOs.md`):

| Slug | Name | Status | Claim | Since | Last Touched | Last Handoff |
|---|---|---|---|---|---|---|
| website | Public-facing website | active | unclaimed | — | 2026-05-01 | `.archive/session-handoff/...` |

Use `/llm-dev:stream list` to inspect the registry and `/llm-dev:stream new <slug>` to add streams.

## Template Placeholders

Templates use placeholders replaced during initialization:
- `{{PROJECT_NAME}}` — Project directory name
- `{{PROJECT_DESCRIPTION}}` — Brief project description
- `{{TODAY_YYYY_MM_DD}}` — Initialization date
- `{{WORKSPACE_NAME}}` — Workspace directory name
- `{{WORKSPACE_DESCRIPTION}}` — Brief workspace description

See [.project-template/PLACEHOLDERS.md](.project-template/PLACEHOLDERS.md) for the full reference.

## Structure

```
llm-dev/
├── .claude-plugin/           # Plugin metadata
│   ├── marketplace.json
│   └── plugin.json
├── .project-template/        # Project scaffolding template
│   ├── .archive/
│   ├── .claude/
│   ├── .docs/
│   └── PLACEHOLDERS.md
├── .workspace-template/      # Multi-project workspace template
│   ├── .archive/
│   └── projects/
├── commands/                 # Slash commands
│   ├── end-session.md
│   ├── init-project.md
│   ├── init-session.md
│   ├── init-workspace.md
│   ├── research-sweep.md
│   ├── stream.md
│   ├── references/
│   │   └── research-sweep/
│   │       ├── report-craft.md
│   │       └── report-types.md
│   └── handlers/             # Python command handlers
│       ├── end-session.py
│       ├── init-project.py
│       ├── init-session.py
│       ├── init-workspace.py
│       ├── research-sweep.py
│       └── stream.py
├── hooks/                    # Hook configuration
│   └── hooks.json
├── skills/                   # Skill definitions
│   └── cycle/
│       ├── SKILL.md
│       └── references/
│           └── phase-details.md
└── README.md
```

## Updating

```bash
cd ~/.claude/plugins/llm-dev
git pull origin main
```

Or with submodule:
```bash
git submodule update --remote llm-dev
```

## License

MIT License

## Author

Dallas Elleman ([@DallasElleman](https://github.com/DallasElleman))
