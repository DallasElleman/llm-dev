# {{WORKSPACE_NAME}} Projects

Individual project repositories for the {{WORKSPACE_NAME}} workspace.

## Creating New Projects

Use the llm-dev plugin to create new projects:

```
/llm-dev:init-project my-project-name
```

This creates a project from the llm-dev template with:
- Standard directory structure
- Archive infrastructure for transcripts
- CLAUDE.md for LLM assistant instructions

## Project Structure

Each project follows the llm-dev template:

```
project-name/
├── .archive/         # Project conversation archives
├── .claude/          # Project-specific commands
├── .docs/            # Project documentation
├── src/              # Source code
├── tests/            # Test suites
├── CLAUDE.md         # LLM instructions
└── README.md         # Project overview
```
