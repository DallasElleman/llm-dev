---
description: Initialize a new workspace for multi-project llm-dev management
argument-hint: <workspace-name> [--path PATH]
allowed-tools: Bash(*), run_terminal_command, Read, read_file, Write, Glob, Edit, search_replace
---

# Initialize New Workspace

Create a new workspace structure for managing multiple llm-dev projects.

## Workspace vs Project

- **Workspace**: A root directory containing multiple projects, with shared configuration
- **Project**: An individual codebase with its own archive and settings

## Phase 1: Gather Information

**Workspace name**: $ARGUMENTS (first argument)

If workspace name not provided, ask the user for:
1. Workspace name (e.g., "dev", "work", "research")
2. Workspace description (1-2 sentences, optional)
3. Target path (default: current directory)

## How to Use

Run the init-workspace handler:

```bash
python3 <llm-dev-plugin-root>/commands/handlers/init-workspace.py "$@"
```

`<llm-dev-plugin-root>` is `$GROK_PLUGIN_ROOT` or `$CLAUDE_PLUGIN_ROOT` if
set; otherwise the plugin directory shown in this command's listing. Do not
expand an empty env var.

**Arguments**:
- `<workspace-name>` - Workspace name (or will prompt)
- `--path PATH` - Target directory (default: current directory)
- `--description DESC` - Workspace description (or will prompt)
- `--dry-run` - Preview without making changes

## Execution

The handler implements all 7 phases:

**Phase 2: Locate Template** - Validate .workspace-template exists

**Phase 3: Create Workspace Structure** - Copy template files

**Phase 4: Replace Placeholders** - Replace {{WORKSPACE_NAME}}, {{WORKSPACE_DESCRIPTION}}

**Phase 5: Initialize Git Repository** - Initialize git repo

**Phase 6: Initial Commit** - Create initial commit

Execute:
```bash
python3 <llm-dev-plugin-root>/commands/handlers/init-workspace.py "$@"
```

## Phase 7: Summary

Report to user:
- Workspace created at: `$WORKSPACE_PATH`
- Structure overview
- Next steps:
  - Customize CLAUDE.md with workspace-specific guidance
  - Create first project: `/llm-dev:init-project my-project`
  - Run `/llm-dev:init-session` to start tracking conversations
