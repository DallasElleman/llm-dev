#!/usr/bin/env python3
"""Initialize a new workspace for multi-project llm-dev management

Usage: python init_workspace.py [workspace-name] [--path PATH] [--description DESC] [--dry-run]
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
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


def validate_workspace_name(name: str) -> bool:
    """Validate workspace name (allow alphanumeric, hyphens, underscores)"""
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
    """Phase 1: Gather workspace information from args or prompts"""
    print("=== Phase 1: Gather Information ===\n")

    info = {}

    # Workspace name
    if args.workspace_name:
        workspace_name = args.workspace_name
    else:
        workspace_name = prompt_user("Workspace name (e.g., 'dev', 'work', 'research')")

    if not validate_workspace_name(workspace_name):
        print(f"Error: Invalid workspace name '{workspace_name}'", file=sys.stderr)
        print("Workspace name must contain only letters, numbers, hyphens, and underscores",
              file=sys.stderr)
        sys.exit(1)

    info['workspace_name'] = workspace_name

    # Description
    if args.description:
        info['description'] = args.description
    else:
        info['description'] = prompt_user(
            "Workspace description (1-2 sentences, optional)",
            default="A multi-project development workspace"
        )

    # Target path
    if args.path:
        target_base = Path(args.path).resolve()
    else:
        target_base = Path.cwd()
        use_cwd = prompt_yes_no(
            f"Create workspace in current directory ({target_base})?",
            default=True
        )
        if not use_cwd:
            custom_path = prompt_user("Enter target directory path")
            target_base = Path(custom_path).resolve()

    info['workspace_path'] = target_base / workspace_name

    print(f"\nWorkspace: {info['workspace_name']}")
    print(f"Path: {info['workspace_path']}")
    print(f"Description: {info['description']}")
    print()

    return info


def phase2_locate_template(plugin_root: Path) -> Path:
    """Phase 2: Locate and validate template directory"""
    print("=== Phase 2: Locate Template ===\n")

    template_path = plugin_root / ".workspace-template"

    if not template_path.exists() or not template_path.is_dir():
        print(f"Error: Workspace template not found at {template_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Using template: {template_path}\n")
    return template_path


def phase3_create_workspace_structure(info: dict, template_path: Path, dry_run: bool) -> None:
    """Phase 3: Create workspace directory structure"""
    print("=== Phase 3: Create Workspace Structure ===\n")

    workspace_path = info['workspace_path']

    if workspace_path.exists():
        print(f"Warning: Directory {workspace_path} already exists", file=sys.stderr)
        if not dry_run:
            overwrite = prompt_yes_no("Overwrite existing directory?", default=False)
            if not overwrite:
                print("Aborted by user.", file=sys.stderr)
                sys.exit(1)

    if dry_run:
        print(f"[DRY RUN] Would create directory: {workspace_path}")
        print(f"[DRY RUN] Would copy template from: {template_path}")
    else:
        # Create workspace directory
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Copy template contents (excluding .git and .gitmodules-template)
        for item in template_path.iterdir():
            if item.name in ('.git', '.gitmodules-template'):
                continue

            dest = workspace_path / item.name

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
        claude_dir = workspace_path / ".claude"
        claude_dir.mkdir(exist_ok=True)
        print(f"Created: .claude/")

    print()


def phase4_replace_placeholders(info: dict, dry_run: bool) -> None:
    """Phase 4: Replace placeholders in template files"""
    print("=== Phase 4: Replace Placeholders ===\n")

    workspace_path = info['workspace_path']

    replacements = {
        '{{WORKSPACE_NAME}}': info['workspace_name'],
        '{{WORKSPACE_DESCRIPTION}}': info['description'],
    }

    if dry_run:
        print("[DRY RUN] Would replace placeholders in all .md files:")
        for placeholder, value in replacements.items():
            print(f"  {placeholder} -> {value}")
    else:
        # Find all markdown files
        md_files = list(workspace_path.rglob("*.md"))

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
                    print(f"Updated: {md_file.relative_to(workspace_path)}")

            except Exception as e:
                print(f"Warning: Failed to process {md_file}: {e}", file=sys.stderr)

        print(f"\nReplaced placeholders in {replaced_count} file(s)")

    print()


def phase5_initialize_git(info: dict, dry_run: bool) -> bool:
    """Phase 5: Initialize git repository (required for workspace)"""
    print("=== Phase 5: Initialize Git Repository ===\n")

    workspace_path = info['workspace_path']

    # Check if git is available
    try:
        subprocess.run(['git', '--version'], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Error: git is required for workspace setup (needed for submodules)",
              file=sys.stderr)
        print("Please install git and try again", file=sys.stderr)
        return False

    if dry_run:
        print(f"[DRY RUN] Would initialize git repository in {workspace_path}")
        print()
        return True

    try:
        subprocess.run(['git', 'init'], cwd=str(workspace_path), check=True,
                      capture_output=True)
        print(f"Initialized git repository in {workspace_path}")
        print()
        return True

    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to initialize git repository: {e}", file=sys.stderr)
        return False


def phase6_initial_commit(info: dict, dry_run: bool) -> None:
    """Phase 6: Create initial commit"""
    print("=== Phase 6: Initial Commit ===\n")

    workspace_path = info['workspace_path']

    if dry_run:
        print("[DRY RUN] Would create initial commit")
        print()
        return

    try:
        # Stage all files
        subprocess.run(['git', 'add', '.'], cwd=str(workspace_path), check=True,
                      capture_output=True)
        print("Staged all files")

        # Create initial commit
        safe_desc = ' '.join(info['description'].split())[:200]
        commit_message = f"""Initialize workspace from llm-dev template

Workspace: {info['workspace_name']}
Description: {safe_desc}

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"""

        subprocess.run(
            ['git', 'commit', '-m', commit_message],
            cwd=str(workspace_path),
            check=True,
            capture_output=True
        )
        print("Created initial commit")

    except subprocess.CalledProcessError as e:
        print(f"Warning: git commit failed: {e}", file=sys.stderr)
        print("You can commit manually later", file=sys.stderr)

    print()


def phase7_summary(info: dict) -> None:
    """Phase 7: Display summary and next steps"""
    print("=== Phase 7: Summary ===\n")

    workspace_path = info['workspace_path']

    print(f"Workspace created successfully!")
    print(f"\nLocation: {workspace_path}")
    print(f"\nStructure:")
    print(f"  {info['workspace_name']}/")
    print(f"    .archive/")
    print(f"    .claude/")
    print(f"    projects/")
    print(f"    CLAUDE.md")
    print(f"    README.md")

    # Check for remaining placeholders
    remaining_placeholders = find_remaining_placeholders(workspace_path)
    if remaining_placeholders:
        print(f"\nRemaining placeholders to fill:")
        for placeholder in sorted(set(remaining_placeholders)):
            print(f"  - {placeholder}")

    print(f"\nNext steps:")
    print(f"  1. cd {workspace_path}")
    print(f"  2. Customize CLAUDE.md with workspace-specific guidance")
    print(f"  3. Create first project: /llm-dev:init-project my-project")
    print(f"  4. Run /llm-dev:init-session to start tracking conversations")
    print()


def find_remaining_placeholders(workspace_path: Path) -> list:
    """Find any remaining {{PLACEHOLDER}} values in markdown files"""
    placeholders = []
    pattern = re.compile(r'\{\{([^}]+)\}\}')

    try:
        for md_file in workspace_path.rglob("*.md"):
            content = md_file.read_text(encoding='utf-8')
            matches = pattern.findall(content)
            placeholders.extend(matches)
    except Exception:
        pass

    return placeholders


def main() -> int:
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Initialize a new workspace for multi-project llm-dev management"
    )
    parser.add_argument(
        'workspace_name',
        nargs='?',
        help="Workspace name (will prompt if not provided)"
    )
    parser.add_argument(
        '--path',
        help="Target directory (default: current directory)"
    )
    parser.add_argument(
        '--description',
        help="Workspace description (will prompt if not provided)"
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
        phase3_create_workspace_structure(info, template_path, args.dry_run)
        phase4_replace_placeholders(info, args.dry_run)

        if not phase5_initialize_git(info, args.dry_run):
            if not args.dry_run:
                return 1

        phase6_initial_commit(info, args.dry_run)

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
