# llm-dev

A Claude Code plugin for LLM-assisted development workflows.

## Overview

**llm-dev** provides:
- **Slash Commands**: `/init-session`, `/end-session`, `/init-project`, `/init-workspace`
- **Skills**: `/cycle` — a structured 6-phase development loop (Review/Reflect, Brainstorm, Research, Plan, Execute, Verify)
- **Project Templates**: Standardized scaffolding for new projects
- **Workspace Templates**: Multi-project workspace structure
- **Session Tracking**: Optional conversation archival, in-flight notes, and forward-looking handoffs for institutional memory and seamless cross-session continuity

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

- **Python 3.8+**: Required for command handlers (init-session, create-transcript, init-project, init-workspace)
- Works natively on **Windows**, **macOS**, and **Linux**
- Commands invoke `python3`. On Windows, if `python3` is not recognized, either add it to your PATH or create an alias (e.g., `doskey python3=python $*` in CMD, or `Set-Alias python3 python` in PowerShell)

## Commands

### /init-project

Create a new project from llm-dev templates.

```
/init-project <project-name> [--path PATH] [--description DESC]
```

### /init-workspace

Set up a multi-project workspace structure.

```
/init-workspace <workspace-name> [--path PATH]
```

### /init-session

Initialize a conversation session for transcript tracking. Also:
- Creates a dated, numbered session-notes file at
  `.archive/session-notes/YYYYMMDD-NNN-session-notes.md` for capturing what
  worked, lessons learned, mistakes, and wrong assumptions throughout the
  session.
- Surfaces the prior session's transcript, notes, and **handoff** so Claude
  can pick up the thread where the last session left off.

```
/init-session [--model MODEL] [--user USERNAME]
```

### /end-session

Wind the session down. Claude writes a forward-looking **handoff document**
at `.archive/session-handoff/YYYYMMDD-NNN-session-handoff.md` (the next
session's high-signal re-entry point), then archives the conversation.

```
/end-session <number> "<title>" [--topics "t1, t2"]
```

Automatically:
- Prompts Claude to write a handoff: where we left off, wins, in-flight
  work, deferred items, locked-in decisions, key references, gotchas, and
  a first-action pointer for the next session
- Detects session ID from index placeholder
- Generates outcomes from file operations
- Updates transcript index (replaces placeholder)
- Updates CHANGELOG (adds entry at top)
- Commits transcript + session-notes + session-handoff in one bundle

> **Migrating from 0.7.x?** `/create-transcript` was renamed to `/end-session`
> in 0.8.0. The new command does everything `/create-transcript` did, plus
> the handoff step. Update any docs or aliases that reference the old name.

## Skills

### /cycle

A structured 6-phase development loop for tasks that benefit from thinking before coding.

**Phases**: Review/Reflect → Brainstorm → Research → Plan → Execute → Verify

Each phase produces a markdown file in an iteration directory. Phases can be skipped, revisited, or delegated to superpowers skills when available. Re-invoking `/cycle` in the same working directory auto-increments to the next iteration.

See [skills/cycle/SKILL.md](skills/cycle/SKILL.md) for full details.

## Session Tracking

Session tracking is **optional** and **command-driven**:

1. Run `/init-session` to begin tracking. This creates a placeholder in the
   transcript index, scaffolds a session-notes file, and surfaces the prior
   session's transcript / notes / handoff for context.
2. Throughout the session, update
   `.archive/session-notes/YYYYMMDD-NNN-session-notes.md` with what worked,
   lessons learned, mistakes made, and wrong assumptions.
3. At session end, run `/end-session`. Claude writes a forward-looking
   handoff document at `.archive/session-handoff/`, then the handler
   archives the conversation transcript and commits the bundle.

Archives include:
- Verbatim dialogue preservation
- Auto-generated outcomes from file operations
- Automatic index/CHANGELOG updates
- Per-session notes for cross-session learning distillation
- Per-session handoffs as high-signal re-entry points for the next session

## Template Placeholders

Templates use placeholders replaced during initialization:
- `{{PROJECT_NAME}}` — Project directory name
- `{{PROJECT_DESCRIPTION}}` — Brief project description
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
│   └── handlers/             # Python command handlers
│       ├── end-session.py
│       ├── init-project.py
│       ├── init-session.py
│       └── init-workspace.py
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
