#!/usr/bin/env python3
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

import _archive


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
    if not sys.stdin.isatty():
        if default:
            print(f"Non-interactive: {message!r} not set — using default: {default!r}")
            return default
        print(
            f"Error: non-interactive context — '{message}' is required. "
            "Supply it via a CLI argument.",
            file=sys.stderr,
        )
        sys.exit(1)
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
    if not sys.stdin.isatty():
        default_str = "yes" if default else "no"
        print(f"Non-interactive: {message!r} not set — using default: {default_str!r}")
        return default
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


def _strip_trailing_blank(lines: list) -> list:
    """Return copy of lines with trailing blank lines removed."""
    lines = list(lines)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _make_minimal_streams_block(today: str) -> list:
    """Return lines for a minimal ## Streams section."""
    return [
        '## Streams',
        '',
        '| Slug | Name | Status | Claim | Since | Last Touched | Last Handoff |',
        '|------|------|--------|-------|-------|--------------|--------------|',
        f'| main | Main | active | unclaimed | — | {today} | |',
        '',
        '<!-- Add streams with: /llm-dev:stream new <slug> "<name>" -->',
    ]


def _remove_orphaned_streams_table(lines: list) -> tuple:
    """Strip Streams-table blocks that appear outside a ## Streams section.

    A Streams-table block starts with a '| Slug |' header row and includes all
    immediately following pipe-delimited rows.  Returns (cleaned_lines, was_changed).
    """
    result = []
    changed = False
    in_streams_section = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r'^## Streams\s*$', line):
            in_streams_section = True
            result.append(line)
            i += 1
        elif re.match(r'^## ', line):
            in_streams_section = False
            result.append(line)
            i += 1
        elif not in_streams_section and re.match(r'^\| *Slug *\|', line, re.IGNORECASE):
            # Orphaned Streams table header — skip it and all following table rows.
            changed = True
            while i < len(lines) and lines[i].strip().startswith('|'):
                i += 1
        else:
            result.append(line)
            i += 1
    return result, changed


def _migrate_streams_to_top(content: str, today: str) -> tuple:
    """Ensure ## Streams is the first ## section in the document.

    Idempotent: second call on already-migrated content returns (content, False).
    If no ## Streams section exists, synthesizes a minimal one.
    Returns (new_content, was_changed).
    """
    lines = content.splitlines()
    h2_pos = [i for i, ln in enumerate(lines) if re.match(r'^## ', ln)]

    if not h2_pos:
        streams_lines = _make_minimal_streams_block(today)
        new_lines = _strip_trailing_blank(lines) + [''] + streams_lines
        return '\n'.join(new_lines) + '\n', True

    streams_h2_idx = None
    for idx, ln_i in enumerate(h2_pos):
        if lines[ln_i].strip() == '## Streams':
            streams_h2_idx = idx
            break

    if streams_h2_idx is None:
        insert_at = h2_pos[0]
        header = _strip_trailing_blank(lines[:insert_at])
        streams_block = _make_minimal_streams_block(today)
        # Remove any bare Streams table rows left by a previous partial migration.
        rest, _ = _remove_orphaned_streams_table(lines[insert_at:])
        new_lines = header + [''] + streams_block + [''] + rest
        new_lines = _strip_trailing_blank(new_lines)
        return '\n'.join(new_lines) + '\n', True

    if streams_h2_idx == 0:
        # Already at top — clean up any orphaned Streams table rows elsewhere.
        cleaned, orphans_removed = _remove_orphaned_streams_table(lines)
        if orphans_removed:
            cleaned = _strip_trailing_blank(cleaned)
            return '\n'.join(cleaned) + '\n', True
        return content, False

    def get_section(idx):
        start = h2_pos[idx]
        end = h2_pos[idx + 1] if idx + 1 < len(h2_pos) else len(lines)
        return _strip_trailing_blank(lines[start:end])

    header = _strip_trailing_blank(lines[:h2_pos[0]])
    sections = [get_section(i) for i in range(len(h2_pos))]

    streams_sec = sections.pop(streams_h2_idx)
    sections.insert(0, streams_sec)

    result = list(header)
    for sec in sections:
        result.append('')
        result.extend(sec)

    result = _strip_trailing_blank(result)
    new_content = '\n'.join(result) + '\n'
    return new_content, new_content != content


def phase3_create_project_structure(info: dict, template_path: Path, dry_run: bool) -> None:
    """Phase 3: Create project directory structure"""
    print("=== Phase 3: Create Project Structure ===\n")

    project_path = info['project_path']
    already_exists = project_path.exists()

    if already_exists:
        print(f"Note: Directory {project_path} already exists — updating in place\n")

    if dry_run:
        action = "Would update" if already_exists else "Would create"
        print(f"[DRY RUN] {action} directory: {project_path}")
        print(f"[DRY RUN] Would copy template from: {template_path}")
    else:
        project_path.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime('%Y-%m-%d')

        for item in template_path.iterdir():
            if item.name == '.git':
                continue

            dest = project_path / item.name

            try:
                if item.is_dir():
                    if not dest.exists():
                        shutil.copytree(item, dest)
                        print(f"Copied: {item.name}/")
                    else:
                        print(f"Skipped: {item.name}/ (already exists)")
                elif item.name == 'CURRENT-TODOs.md':
                    if dest.exists():
                        existing = dest.read_text(encoding='utf-8')
                        new_content, changed = _migrate_streams_to_top(existing, today)
                        if changed:
                            dest.write_text(new_content, encoding='utf-8')
                            print(f"Migrated: {item.name} (## Streams moved to top)")
                        else:
                            print(f"Already current: {item.name}")
                    else:
                        shutil.copy2(item, dest)
                        print(f"Copied: {item.name}")
                else:
                    if not dest.exists():
                        shutil.copy2(item, dest)
                        print(f"Copied: {item.name}")
                    else:
                        print(f"Skipped: {item.name} (already exists)")
            except Exception as e:
                print(f"Warning: Failed to process {item.name}: {e}", file=sys.stderr)

        claude_dir = project_path / ".claude"
        claude_dir.mkdir(exist_ok=True)
        print(f"Created: .claude/")

    print()


def is_new_project(path: Path) -> bool:
    """True if `path` is a brand-new project target (absent, or an empty dir)."""
    p = Path(path)
    if not p.exists():
        return True
    if p.is_dir():
        return not any(p.iterdir())
    return False


def _replacements_for(info: dict) -> dict:
    """Build the placeholder->value map used to fill template files."""
    repl = {
        '{{PROJECT_NAME}}': info['project_name'],
        '{{PROJECT_DESCRIPTION}}': info['description'],
        '{{TODAY_YYYY_MM_DD}}': datetime.now().strftime('%Y-%m-%d'),
    }
    if info.get('workspace_path'):
        repl['{{workspace-path}}'] = info['workspace_path']
    return repl


def _replace_placeholders_in(root: Path, replacements: dict) -> int:
    """Replace placeholders in every *.md under `root`. Returns files changed."""
    changed = 0
    for md_file in Path(root).rglob("*.md"):
        try:
            content = md_file.read_text(encoding='utf-8')
            new_content = content
            for placeholder, value in replacements.items():
                new_content = new_content.replace(placeholder, value)
            if new_content != content:
                md_file.write_text(new_content, encoding='utf-8')
                changed += 1
        except Exception as e:
            print(f"Warning: Failed to process {md_file}: {e}", file=sys.stderr)
    return changed


def _copy_into(src_dir: Path, dest_dir: Path, skip: set[str] = frozenset()) -> None:
    """Copy each entry of src_dir into dest_dir (dirs merged), skipping names in `skip`."""
    for item in Path(src_dir).iterdir():
        if item.name in skip:
            continue
        dest = Path(dest_dir) / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


def build_container_project(container: Path, template_path: Path,
                            replacements: dict, dry_run: bool) -> None:
    """Create a new bare-repo container project from the template.

    Product template files go to `streams/main/` (committed on main); the
    template's `.archive/` content goes to the `.archive/` worktree (committed
    on llm-dev-archive). Placeholders are filled in both worktrees.
    """
    container = Path(container)
    if dry_run:
        print(f"[DRY RUN] Would create container at {container}:")
        print(f"[DRY RUN]   .bare/ (bare repo), .git (pointer)")
        print(f"[DRY RUN]   streams/main/ (product template, branch main)")
        print(f"[DRY RUN]   .archive/ (archive template, branch llm-dev-archive)")
        return

    _archive.bootstrap_greenfield(container)
    main_wt = container / "streams" / "main"
    archive_wt = container / ".archive"

    # Product files -> streams/main (everything except the template's .archive)
    _copy_into(template_path, main_wt, skip={".archive", ".git"})
    (main_wt / ".claude").mkdir(exist_ok=True)
    # Archive content -> .archive worktree (merges over the skeleton)
    tmpl_archive = Path(template_path) / ".archive"
    if tmpl_archive.is_dir():
        _copy_into(tmpl_archive, archive_wt)

    # Fill placeholders in both worktrees
    _replace_placeholders_in(main_wt, replacements)
    _replace_placeholders_in(archive_wt, replacements)

    # Commit product on main, archive on llm-dev-archive
    subprocess.run(["git", "add", "-A"], cwd=str(main_wt), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add llm-dev project template"],
                   cwd=str(main_wt), check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=str(archive_wt), check=True, capture_output=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"],
                      cwd=str(archive_wt)).returncode != 0:
        subprocess.run(["git", "commit", "-m", "Seed llm-dev archive from template"],
                       cwd=str(archive_wt), check=True, capture_output=True)
    print(f"Created container project at {container}")


def clone_container_project(container: Path, url: str, dry_run: bool) -> None:
    """Clone an existing remote into a new container (onboarding an existing project)."""
    container = Path(container)
    if dry_run:
        print(f"[DRY RUN] Would clone {url} into container at {container}")
        return
    if not is_new_project(container):
        raise ValueError(f"--from-clone target already exists and is not empty: {container}")
    _archive.bootstrap_from_clone(container, url)
    # bootstrap_from_clone sets upstream on llm-dev-archive; set it on main too.
    main_wt = container / "streams" / "main"
    subprocess.run(["git", "branch", "--set-upstream-to=origin/main", "main"],
                   cwd=str(main_wt), check=False, capture_output=True)
    print(f"Cloned container project into {container}")


def phase4_replace_placeholders(info: dict, dry_run: bool) -> None:
    """Phase 4: Replace placeholders in template files"""
    print("=== Phase 4: Replace Placeholders ===\n")

    project_path = info['project_path']
    replacements = _replacements_for(info)

    if dry_run:
        print("[DRY RUN] Would replace placeholders in all .md files:")
        for placeholder, value in replacements.items():
            print(f"  {placeholder} -> {value}")
    else:
        replaced_count = _replace_placeholders_in(project_path, replacements)
        print(f"\nReplaced placeholders in {replaced_count} file(s)")

    print()


def phase5_initialize_archive(info: dict, dry_run: bool) -> None:
    """Phase 5: Initialize archive directory structure"""
    print("=== Phase 5: Initialize Archive ===\n")

    project_path = info['project_path']
    archive_path = project_path / ".archive"
    transcripts_path = archive_path / "transcripts"
    artifacts_path = archive_path / "artifacts"
    session_notes_path = archive_path / "session-notes"
    session_handoff_path = archive_path / "session-handoff"

    if dry_run:
        print(f"[DRY RUN] Would create: {transcripts_path}")
        print(f"[DRY RUN] Would create: {artifacts_path}")
        print(f"[DRY RUN] Would create: {artifacts_path / '.gitkeep'}")
        print(f"[DRY RUN] Would create: {session_notes_path}")
        print(f"[DRY RUN] Would create: {session_notes_path / '.gitkeep'}")
        print(f"[DRY RUN] Would create: {session_handoff_path}")
        print(f"[DRY RUN] Would create: {session_handoff_path / '.gitkeep'}")
    else:
        transcripts_path.mkdir(parents=True, exist_ok=True)
        artifacts_path.mkdir(parents=True, exist_ok=True)
        session_notes_path.mkdir(parents=True, exist_ok=True)
        session_handoff_path.mkdir(parents=True, exist_ok=True)

        # Create .gitkeep for empty archive subdirectories
        (artifacts_path / ".gitkeep").touch()
        (session_notes_path / ".gitkeep").touch()
        (session_handoff_path / ".gitkeep").touch()

        print(f"Created: .archive/transcripts/")
        print(f"Created: .archive/artifacts/")
        print(f"Created: .archive/artifacts/.gitkeep")
        print(f"Created: .archive/session-notes/")
        print(f"Created: .archive/session-notes/.gitkeep")
        print(f"Created: .archive/session-handoff/")
        print(f"Created: .archive/session-handoff/.gitkeep")

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
    print(f"      session-notes/")
    print(f"      session-handoff/")
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


def _summary_container(info: dict) -> None:
    """Print a summary for the bare-repo container layout."""
    project_path = info['project_path']
    print("=== Summary ===\n")
    print(f"Container project created at: {project_path}")
    print("\nStructure:")
    print(f"  {info['project_name']}/")
    print(f"    .bare/            (git database)")
    print(f"    streams/main/     (product worktree, branch main)")
    print(f"    .archive/         (session records, branch llm-dev-archive)")
    print("\nNext steps:")
    print(f"  1. cd {project_path / 'streams' / 'main'}")
    print(f"  2. Review and customize CLAUDE.md")
    print(f"  3. Run /llm-dev:init-session to start tracking conversations")
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
    parser.add_argument('--from-clone', metavar='URL',
                        help="Clone an existing remote into a container at <project-name> (uses the same name/--path args)")
    parser.add_argument('--in-place', action='store_true',
                        help="Force the legacy in-place layout instead of the container layout")

    args = parser.parse_args()

    if args.from_clone and args.in_place:
        print("Error: --from-clone and --in-place are mutually exclusive", file=sys.stderr)
        return 1

    # Get plugin root
    plugin_root = get_plugin_root()

    # Execute phases
    try:
        info = phase1_gather_information(args)
        template_path = phase2_locate_template(plugin_root)
        project_path = info['project_path']

        if args.from_clone:
            layout = "container"
            clone_container_project(project_path, args.from_clone, args.dry_run)
        elif is_new_project(project_path) and not args.in_place:
            layout = "container"
            replacements = _replacements_for(info)
            build_container_project(project_path, template_path, replacements, args.dry_run)
        else:
            layout = "in-place"
            # Legacy in-place layout (existing non-empty dirs, or --in-place).
            phase3_create_project_structure(info, template_path, args.dry_run)
            phase4_replace_placeholders(info, args.dry_run)
            phase5_initialize_archive(info, args.dry_run)
            phase6_git_setup(info, args.dry_run)

        if args.dry_run:
            print("\n[DRY RUN COMPLETE - No changes were made]\n")
        elif layout == "in-place":
            phase7_summary(info)
        else:
            _summary_container(info)
        return 0

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        if args.dry_run:
            print("\n[DRY RUN FAILED]\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
