# {{WORKSPACE_NAME}}

{{WORKSPACE_DESCRIPTION}}

## Structure

```
{{WORKSPACE_NAME}}/
├── .archive/             # Workspace conversation archives
├── .references/          # Reference materials
├── projects/             # Individual projects
├── CLAUDE.md             # LLM assistant instructions
└── README.md             # This file
```

## Projects

<!-- List active projects here -->

## Getting Started

1. Review `CLAUDE.md` for workspace conventions
2. Create projects with `/llm-dev:init-project`
3. Initialize sessions with `/llm-dev:init-session`

## Reference Materials

Located in `.references/` (git submodules):
- **12-factor-agents**: Methodology for building reliable LLM agents
- **ccpm**: Critical Chain Project Management framework

## Session Tracking

Conversation transcripts are stored in `.archive/transcripts/`. See the README there for format details.
