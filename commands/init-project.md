---
description: Initialize a new project from llm-dev template
argument-hint: <project-name> [--path PATH] [--description DESC]
allowed-tools: Bash(*), Read, Write, Glob, Grep, Edit
---

# Initialize New Project

Create a new project using the llm-dev template system.

## Phase 1: Gather Information

**Project name**: $ARGUMENTS (first argument)

If project name not provided, ask the user for:
1. Project name (kebab-case recommended)
2. Brief project description (1-2 sentences)
3. Target directory (default: current directory)

## How to Use

Run the init-project handler:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/commands/handlers/init-project.py" "$@"
```

**Arguments**:
- `<project-name>` - Project name (or will prompt)
- `--path PATH` - Target directory (default: cwd/project_name)
- `--description DESC` - Project description (or will prompt)
- `--dry-run` - Preview without making changes
- `--from-clone URL` - Onboard an existing remote by cloning it into a new container
- `--in-place` - Force the legacy single-directory layout instead of the container

## Layout

For a **brand-new project** (target dir absent or empty), `/init-project` creates the
**bare-repo container layout** — `<project>/.bare` (git database), `<project>/streams/main/`
(the product worktree), and `<project>/.archive/` (the `llm-dev-archive` worktree holding
session records). This keeps records branch-independent.

- `--from-clone <url>` — onboard an existing remote by cloning it into a new container.
- `--in-place` — force the legacy single-directory layout instead of the container.

**Existing non-empty directories** keep the legacy in-place layout (converting an existing
repo to the container is a separate, future step).

## Execution

The handler implements all 7 phases:

**Phase 2: Locate Template** - Validate .project-template exists

**Phase 3: Create Project Structure** - Copy template files

**Phase 4: Replace Placeholders** - Replace {{PROJECT_NAME}}, {{PROJECT_DESCRIPTION}}, {{workspace-path}}

**Phase 5: Initialize Archive** - Create .archive/transcripts, .archive/artifacts

**Phase 6: Git Setup (Optional)** - Prompt user for git initialization

Execute:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/commands/handlers/init-project.py" "$@"
```

## Phase 7: Summary

Report to user:
- Project created at: `$PROJECT_PATH`
- Structure overview (list key directories)
- Remaining placeholders to fill (if any found)
- Next steps:
  - Review and customize CLAUDE.md
  - Fill in README.md details
  - Run `/init-session` to start tracking conversations
