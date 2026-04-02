```BEGIN {{WORKSPACE_NAME}}/CLAUDE.md```
# Principles:
1. Everything should be made as simple as possible, but not simpler.
2. When problems arise, look for elegant, optimal solutions.
3. Think critically about the information you are presented with.
4. If agreement is warranted, do so without excessive enthusiasm.
5. If disagreement is warranted, do so constructively.
6. Preserve context window length and coherence to improve performance.
7. Ensure that written code is clean and well-documented.
8. Strive for clarity and efficiency in all your writing.

# Structure:
```
{{WORKSPACE_NAME}}/
├── .archive/             # Workspace-level conversation archives
│   ├── artifacts/        # Archived conversation artifacts
│   ├── transcripts/      # Conversation logs with LLM assistant
│   └── CHANGELOG.md      # Workspace changelog
├── .claude/              # Claude Code configuration
├── .references/          # Reference materials (submodules)
│   ├── 12-factor-agents/ # Twelve-factor methodology for agents
│   └── ccpm/             # Critical Chain Project Management
├── projects/             # Individual project repositories
│   ├── .archive/         # Cross-project conversation archives
│   └── CLAUDE.md         # Projects-level instructions
├── CLAUDE.md             # (this) Workspace instructions
└── scratch.md            # Temporary notes and scratchpad
```

# Guidance:
- When generating file trees: ensure comprehensive inclusion of top-level directories, alphabetize entries.
- When working with git submodules or multiple repositories: always use absolute paths.
- When asked about the current state of a particular project: check the project directory and git history.
```END {{WORKSPACE_NAME}}/CLAUDE.md```
