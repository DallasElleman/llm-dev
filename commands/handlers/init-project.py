#!/usr/bin/env python3
from __future__ import annotations
"""Initialize a new project from llm-dev template

Usage: python init_project.py [project-name] [--path PATH] [--description DESC] [--dry-run]
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def get_plugin_root() -> Path:
    """Get the plugin root directory from environment or relative path"""
    plugin_root = os.environ.get('CLAUDE_PLUGIN_ROOT')
    if plugin_root:
        root = Path(plugin_root).resolve()
    else:
        # Fallback: handlers/ is inside commands/, which is inside plugin root
        root = Path(__file__).resolve().parent.parent.parent
    # Validate that this looks like a real plugin directory
    if not (root / ".claude-plugin" / "plugin.json").exists():
        raise ValueError(f"Plugin root does not contain .claude-plugin/plugin.json: {root}")
    return root


def validate_project_name(name: str) -> bool:
    """Validate project name (allow alphanumeric, hyphens, underscores)"""
    if not name:
        return False
    # Allow letters, numbers, hyphens, underscores
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))


def prompt_user(message: str, default: str = "") -> str:
    """Prompt user for input with optional default"""
    try:
        if default:
            response = input(f"{message} [{default}]: ").strip()
            return response if response else default
        else:
            response = input(f"{message}: ").strip()
            while not response:
                print("This field is required.")
                response = input(f"{message}: ").strip()
            return response
    except (KeyboardInterrupt, EOFError):
        print("\nAborted by user.", file=sys.stderr)
        sys.exit(1)


def prompt_yes_no(message: str, default: bool = True) -> bool:
    """Prompt user for yes/no confirmation"""
    default_str = "Y/n" if default else "y/N"
    try:
        response = input(f"{message} [{default_str}]: ").strip().lower()
        if not response:
            return default
        return response in ('y', 'yes')
    except (KeyboardInterrupt, EOFError):
        print("\nAborted by user.", file=sys.stderr)
        sys.exit(1)


def phase1_gather_information(args) -> dict:
    """Phase 1: Gather project information from args or prompts"""
    print("=== Phase 1: Gather Information ===\n")

    info = {}

    # Project name
    if args.project_name:
        project_name = args.project_name
    else:
        project_name = prompt_user("Project name (kebab-case recommended)")

    if not validate_project_name(project_name):
        print(f"Error: Invalid project name '{project_name}'", file=sys.stderr)
        print("Project name must contain only letters, numbers, hyphens, and underscores",
              file=sys.stderr)
        sys.exit(1)

    info['project_name'] = project_name

    # Description
    if args.description:
        info['description'] = args.description
    else:
        info['description'] = prompt_user(
            "Brief project description (1-2 sentences)",
            default="A new project"
        )

    # Target path
    if args.path:
        target_base = Path(args.path).resolve()
    else:
        target_base = Path.cwd()
        use_cwd = prompt_yes_no(
            f"Create project in current directory ({target_base})?",
            default=True
        )
        if not use_cwd:
            custom_path = prompt_user("Enter target directory path")
            target_base = Path(custom_path).resolve()

    info['project_path'] = target_base / project_name

    # Detect workspace path (if we're in one)
    workspace_path = detect_workspace(target_base)
    info['workspace_path'] = str(workspace_path) if workspace_path else ""

    print(f"\nProject: {info['project_name']}")
    print(f"Path: {info['project_path']}")
    print(f"Description: {info['description']}")
    if info['workspace_path']:
        print(f"Workspace: {info['workspace_path']}")
    print()

    return info


def detect_workspace(start_dir: Path) -> Path | None:
    """Detect if we're inside a workspace (has CLAUDE.md or .workspace-template marker)"""
    current = start_dir.resolve()

    while True:
        # Check for workspace markers
        if (current / "CLAUDE.md").exists() and (current / "projects").exists():
            return current

        parent = current.parent
        if parent == current:  # Reached root
            break
        current = parent

    return None


def phase2_locate_template(plugin_root: Path) -> Path:
    """Phase 2: Locate and validate template directory"""
    print("=== Phase 2: Locate Template ===\n")

    template_path = plugin_root / ".project-template"

    if not template_path.exists() or not template_path.is_dir():
        print(f"Error: Project template not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Using template: {template_path}\n")
    return template_path


def phase3_create_project_structure(info: dict, template_path: Path, dry_run: bool) -> None:
    """Phase 3: Create project directory structure"""
    print("=== Phase 3: Create Project Structure ===\n")

    project_path = info['project_path']

    if project_path.exists():
        print(f"Warning: Directory {project_path} already exists", file=sys.stderr)
        if not dry_run:
            overwrite = prompt_yes_no("Overwrite existing directory?", default=False)
            if not overwrite:
                print("Aborted by user.", file=sys.stderr)
                sys.exit(1)

    if dry_run:
        print(f"[DRY RUN] Would create directory: {project_path}")
        print(f"[DRY RUN] Would copy template from: {template_path}")
    else:
        # Create project directory
        project_path.mkdir(parents=True, exist_ok=True)

        # Copy template contents (excluding .git)
        for item in template_path.iterdir():
            if item.name == '.git':
                continue

            dest = project_path / item.name

            try:
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
                print(f"Copied: {item.name}")
            except Exception as e:
                print(f"Warning: Failed to copy {item.name}: {e}", file=sys.stderr)

        # Create .claude directory
        claude_dir = project_path / ".claude"
        claude_dir.mkdir(exist_ok=True)
        print(f"Created: .claude/")

    print()


def phase4_replace_placeholders(info: dict, dry_run: bool) -> None:
    """Phase 4: Replace placeholders in template files"""
    print("=== Phase 4: Replace Placeholders ===\n")

    project_path = info['project_path']

    replacements = {
        '{{PROJECT_NAME}}': info['project_name'],
        '{{PROJECT_DESCRIPTION}}': info['description'],
    }

    if info['workspace_path']:
        replacements['{{workspace-path}}'] = info['workspace_path']

    if dry_run:
        print("[DRY RUN] Would replace placeholders in all .md files:")
        for placeholder, value in replacements.items():
            print(f"  {placeholder} -> {value}")
    else:
        # Find all markdown files
        md_files = list(project_path.rglob("*.md"))

        replaced_count = 0
        for md_file in md_files:
            try:
                content = md_file.read_text(encoding='utf-8')
                original_content = content

                for placeholder, value in replacements.items():
                    content = content.replace(placeholder, value)

                if content != original_content:
                    md_file.write_text(content, encoding='utf-8')
                    replaced_count += 1
                    print(f"Updated: {md_file.relative_to(project_path)}")

            except Exception as e:
                print(f"Warning: Failed to process {md_file}: {e}", file=sys.stderr)

        print(f"\nReplaced placeholders in {replaced_count} file(s)")

    print()


def phase5_initialize_archive(info: dict, dry_run: bool) -> None:
    """Phase 5: Initialize archive directory structure"""
    print("=== Phase 5: Initialize Archive ===\n")

    project_path = info['project_path']
    archive_path = project_path / ".archive"
    transcripts_path = archive_path / "transcripts"
    artifacts_path = archive_path / "artifacts"

    if dry_run:
        print(f"[DRY RUN] Would create: {transcripts_path}")
        print(f"[DRY RUN] Would create: {artifacts_path}")
        print(f"[DRY RUN] Would create: {artifacts_path / '.gitkeep'}")
    else:
        transcripts_path.mkdir(parents=True, exist_ok=True)
        artifacts_path.mkdir(parents=True, exist_ok=True)

        # Create .gitkeep for artifacts directory
        gitkeep = artifacts_path / ".gitkeep"
        gitkeep.touch()

        print(f"Created: .archive/transcripts/")
        print(f"Created: .archive/artifacts/")
        print(f"Created: .archive/artifacts/.gitkeep")

    print()


def phase6_git_setup(info: dict, dry_run: bool) -> None:
    """Phase 6: Optional git repository initialization"""
    print("=== Phase 6: Git Setup (Optional) ===\n")

    project_path = info['project_path']

    # Check if git is available
    try:
        subprocess.run(['git', '--version'], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Warning: git not found, skipping git initialization", file=sys.stderr)
        print()
        return

    if dry_run:
        print("[DRY RUN] Would ask user about git initialization")
        print()
        return

    # Ask user
    init_git = prompt_yes_no("Initialize git repository?", default=True)

    if not init_git:
        print("Skipping git initialization\n")
        return

    try:
        # Initialize repository
        subprocess.run(['git', 'init'], cwd=str(project_path), check=True,
                      capture_output=True)
        print("Initialized git repository")

        # Stage all files
        subprocess.run(['git', 'add', '.'], cwd=str(project_path), check=True,
                      capture_output=True)
        print("Staged all files")

        # Create initial commit
        safe_desc = ' '.join(info['description'].split())[:200]
        commit_message = f"""Initial project setup from llm-dev template

Project: {info['project_name']}
Description: {safe_desc}

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"""

        subprocess.run(
            ['git', 'commit', '-m', commit_message],
            cwd=str(project_path),
            check=True,
            capture_output=True
        )
        print("Created initial commit")

    except subprocess.CalledProcessError as e:
        print(f"Warning: git operation failed: {e}", file=sys.stderr)
        print("You can initialize git manually later", file=sys.stderr)

    print()


def phase7_summary(info: dict) -> None:
    """Phase 7: Display summary and next steps"""
    print("=== Phase 7: Summary ===\n")

    project_path = info['project_path']

    print(f"Project created successfully!")
    print(f"\nLocation: {project_path}")
    print(f"\nStructure:")
    print(f"  {info['project_name']}/")
    print(f"    .archive/")
    print(f"      transcripts/")
    print(f"      artifacts/")
    print(f"    .claude/")
    print(f"    CLAUDE.md")
    print(f"    README.md")

    # Check for remaining placeholders
    remaining_placeholders = find_remaining_placeholders(project_path)
    if remaining_placeholders:
        print(f"\nRemaining placeholders to fill:")
        for placeholder in sorted(set(remaining_placeholders)):
            print(f"  - {placeholder}")

    print(f"\nNext steps:")
    print(f"  1. cd {project_path}")
    print(f"  2. Review and customize CLAUDE.md")
    print(f"  3. Fill in README.md details")
    print(f"  4. Run /llm-dev:init-session to start tracking conversations")
    print()


def find_remaining_placeholders(project_path: Path) -> list:
    """Find any remaining {{PLACEHOLDER}} values in markdown files"""
    placeholders = []
    pattern = re.compile(r'\{\{([^}]+)\}\}')

    try:
        for md_file in project_path.rglob("*.md"):
            content = md_file.read_text(encoding='utf-8')
            matches = pattern.findall(content)
            placeholders.extend(matches)
    except Exception:
        pass

    return placeholders


def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Initialize a new project from llm-dev template"
    )
    parser.add_argument(
        'project_name',
        nargs='?',
        help="Project name (will prompt if not provided)"
    )
    parser.add_argument(
        '--path',
        help="Target directory (default: current directory)"
    )
    parser.add_argument(
        '--description',
        help="Project description (will prompt if not provided)"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Preview without making changes"
    )

    args = parser.parse_args()

    # Get plugin root
    plugin_root = get_plugin_root()

    # Execute phases
    try:
        info = phase1_gather_information(args)
        template_path = phase2_locate_template(plugin_root)
        phase3_create_project_structure(info, template_path, args.dry_run)
        phase4_replace_placeholders(info, args.dry_run)
        phase5_initialize_archive(info, args.dry_run)
        phase6_git_setup(info, args.dry_run)

        if args.dry_run:
            print("\n[DRY RUN COMPLETE - No changes were made]\n")
        else:
            phase7_summary(info)

        return 0

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        if args.dry_run:
            print("\n[DRY RUN FAILED]\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
