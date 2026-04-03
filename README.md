# llm-dev

A Claude Code plugin for LLM-assisted development workflows.

## Overview

**llm-dev** provides:
- **Slash Commands**: `/init-session`, `/create-transcript`, `/init-project`, `/init-workspace`
- **Skills**: `/cycle` — a structured 6-phase development loop (Review/Reflect, Brainstorm, Research, Plan, Execute, Verify)
- **Project Templates**: Standardized scaffolding for new projects
- **Workspace Templates**: Multi-project workspace structure
- **Session Tracking**: Optional conversation archival for institutional memory

## Installation

### As Claude Code Plugin

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

Initialize a conversation session for transcript tracking.

```
/init-session [--model MODEL] [--user USERNAME]
```

### /create-transcript

Archive the current conversation with auto-generated summary.

```
/create-transcript <number> "<title>" [--topics "t1, t2"]
```

Automatically:
- Detects session ID from index placeholder
- Generates outcomes from file operations
- Updates transcript index (replaces placeholder)
- Updates CHANGELOG (adds entry at top)

## Skills

### /cycle

A structured 6-phase development loop for tasks that benefit from thinking before coding.

**Phases**: Review/Reflect → Brainstorm → Research → Plan → Execute → Verify

Each phase produces a markdown file in an iteration directory. Phases can be skipped, revisited, or delegated to superpowers skills when available. Re-invoking `/cycle` in the same working directory auto-increments to the next iteration.

See [skills/cycle/SKILL.md](skills/cycle/SKILL.md) for full details.

## Session Tracking

Session tracking is **optional** and **command-driven**:

1. Run `/init-session` to begin tracking (creates placeholder in transcript index)
2. At session end, run `/create-transcript` to archive the conversation

Archives include:
- Verbatim dialogue preservation
- Auto-generated outcomes from file operations
- Automatic index/CHANGELOG updates

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
│   ├── create-transcript.md
│   ├── init-project.md
│   ├── init-session.md
│   ├── init-workspace.md
│   └── handlers/             # Python command handlers
│       ├── create-transcript.py
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
