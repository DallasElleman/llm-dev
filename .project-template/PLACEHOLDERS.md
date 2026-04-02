# Template Placeholders Reference

This document describes all placeholders used in llm-dev templates. Placeholders use the `{{PLACEHOLDER_NAME}}` syntax and should be replaced with actual values during project initialization.

## Core Placeholders (Required)

These must be replaced for every new project:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{PROJECT_NAME}}` | Project name (kebab-case recommended) | `my-awesome-project` |
| `{{PROJECT_DESCRIPTION}}` | Brief project description (1-2 sentences) | `A CLI tool for managing development workflows` |

## Workspace Placeholders

Used in workspace-level templates:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{workspace-path}}` | Absolute path to workspace root | `/Users/username/dev` |
| `{{WORKSPACE_NAME}}` | Name of the workspace | `dev` |

## README Placeholders

Used in README.md template:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{PROJECT_TAGLINE}}` | Short tagline or subtitle | `Streamline your dev workflow` |
| `{{PROJECT_SUMMARY}}` | Extended project summary | `A comprehensive toolkit for...` |
| `{{VERSION}}` | Current version number | `1.0.0` |
| `{{LICENSE_INFORMATION}}` | License type | `MIT License` |
| `{{CONTACT_INFORMATION}}` | Maintainer contact | `maintainer@example.com` |

## Technical Stack Placeholders

Used in FULLSPEC.md and technical documentation:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{LANGUAGE}}` | Primary programming language | `Python`, `TypeScript` |
| `{{BACKEND_TECH}}` | Backend framework/technology | `FastAPI`, `Express` |
| `{{FRONTEND_TECH}}` | Frontend framework/technology | `React`, `Vue` |
| `{{DATABASE_TECH}}` | Database technology | `PostgreSQL`, `MongoDB` |
| `{{TESTING_TECH}}` | Testing framework | `pytest`, `Jest` |
| `{{INFRASTRUCTURE_TECH}}` | Infrastructure/deployment | `Docker`, `Kubernetes` |

## Feature Placeholders

Used for feature documentation:

| Placeholder | Description |
|-------------|-------------|
| `{{FEATURE_1}}` through `{{FEATURE_4}}` | Feature names |
| `{{FEATURE_1_DESCRIPTION}}` through `{{FEATURE_4_DESCRIPTION}}` | Feature descriptions |

## Module Placeholders

Used for code organization documentation:

| Placeholder | Description |
|-------------|-------------|
| `{{MODULE_1}}` through `{{MODULE_3}}` | Module names |
| `{{MODULE_1_DESCRIPTION}}` through `{{MODULE_3_DESCRIPTION}}` | Module descriptions |
| `{{MAIN_MODULE}}`, `{{API_MODULE}}`, etc. | Specific module names |

## Development Placeholders

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{INSTALLATION_COMMANDS}}` | Install commands | `pip install -e .` |
| `{{DEV_SETUP_INSTRUCTIONS}}` | Development setup steps | `1. Clone repo...` |
| `{{TEST_COMMANDS}}` | How to run tests | `pytest tests/` |
| `{{CODING_STANDARDS}}` | Coding style reference | `PEP 8` |

## Transcript Placeholders

Used in transcript-related templates:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{Transcript Title}}` | Conversation summary | `Feature implementation discussion` |
| `{{list of participants}}` | Who participated | `@user, Claude Opus 4.5` |
| `{{list of conversation topics}}` | Topics covered | `Architecture, Testing` |
| `{{month, day, year}}` | Date of conversation | `January 9, 2026` |
| `{{XXX sequential number}}` | Zero-padded sequence | `001`, `042` |

## Replacement Strategy

### During /init-project

The initialization process replaces placeholders in this order:

1. **Core placeholders** - `PROJECT_NAME`, `PROJECT_DESCRIPTION`
2. **Auto-detected** - `workspace-path` (from directory structure)
3. **Prompted** - Technical stack placeholders (if FULLSPEC.md is being used)
4. **Deferred** - Feature/module placeholders (filled in during development)

### Manual Replacement

For placeholders not handled during initialization:

```bash
# Find all remaining placeholders
grep -r '{{[^}]*}}' . --include="*.md"

# Replace a specific placeholder across all files
find . -name "*.md" -exec sed -i '' 's/{{PLACEHOLDER}}/value/g' {} \;
```

## Notes

- Placeholders in `.references/` directories come from external frameworks and should generally not be modified
- The `{{project-specific guidance here, if applicable}}` placeholder in CLAUDE.md is meant to be replaced with actual guidance or removed entirely
- Some placeholders like `{{Change 1}}`, `{{Bug fix 1}}` are examples in changelog templates - replace with actual content
