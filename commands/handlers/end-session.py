#!/usr/bin/env python3
"""end-session.py - Archive an LLM session

Converts the Claude Code JSONL transcript to llm-dev JSON format and commits
it alongside the per-session notes and handoff documents.

Usage: python end-session.py <session-num> "<title>" [options]

Automatically:
- Finds session ID from README placeholder or most recent JSONL
- Converts JSONL to llm-dev JSON format with auto-generated outcomes
- Updates README.md (replaces placeholder with actual entry)
- Updates CHANGELOG.md (adds new entry at top)
- Commits transcript + session-notes + session-handoff (if present)

Examples:
    python end-session.py 4 "Setup automation framework"
    python end-session.py 5 "Refactor parser logic" --topics "python, refactoring"
    python end-session.py 6 "Debug API issues" --session-id abc123 --dry-run
    python end-session.py 9 "Session Title" \
        --topics "topic1, topic2" \
        --files-modified "orchestrate.py, CLAUDE.md" \
        --decisions "Use llm-dev template structure, Investigate root cause" \
        --next-steps "Implement context propagation fix, Add SAC agent"
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Version:
    """Semantic version parser and bumper."""

    def __init__(self, major: int, minor: int, patch: int):
        self.major = major
        self.minor = minor
        self.patch = patch

    @classmethod
    def parse(cls, version_str: str) -> Optional['Version']:
        """Parse a semantic version string like '1.2.3'."""
        match = re.match(r'^(\d+)\.(\d+)\.(\d+)$', version_str)
        if not match:
            return None
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    def bump_major(self) -> 'Version':
        """Bump major version (e.g., 1.2.3 -> 2.0.0)."""
        return Version(self.major + 1, 0, 0)

    def bump_minor(self) -> 'Version':
        """Bump minor version (e.g., 1.2.3 -> 1.3.0)."""
        return Version(self.major, self.minor + 1, 0)

    def bump_patch(self) -> 'Version':
        """Bump patch version (e.g., 1.2.3 -> 1.2.4)."""
        return Version(self.major, self.minor, self.patch + 1)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class TranscriptGenerator:
    """Generates structured JSON transcripts from Claude Code JSONL sessions."""

    def __init__(self, session_num: int, title: str, **kwargs):
        self.session_num = session_num
        self.title = title
        self.session_id = kwargs.get('session_id')
        self.topics = kwargs.get('topics')
        self.dry_run = kwargs.get('dry_run', False)
        self.model = kwargs.get('model')
        self.user = kwargs.get('user')
        self.bump_type = kwargs.get('bump_type', 'patch')  # 'major', 'minor', or 'patch'

        self.sanitize = kwargs.get('sanitize', False)

        # Additional outcome fields
        self.provided_files_modified = kwargs.get('files_modified', '')
        self.provided_artifacts = kwargs.get('artifacts', '')
        self.provided_decisions = kwargs.get('decisions', '')
        self.provided_next_steps = kwargs.get('next_steps', '')

        # Find archive directory
        self.archive_dir = self._find_archive_dir()
        if not self.archive_dir:
            raise FileNotFoundError("No .archive/transcripts directory found")

        self.project_dir = self.archive_dir.parent
        self.project_id = self.project_dir.name
        self.index_path = self.archive_dir / "transcripts" / "_index.md"
        self.changelog_path = self.archive_dir / "CHANGELOG.md"

        # Pad session number
        self.session_num_padded = f"{session_num:03d}"

        # Auto-detect session ID if not provided
        if not self.session_id:
            self.session_id = self._find_session_id()

        if not self.session_id:
            raise ValueError(
                "Could not find session ID. "
                "Provide it with --session-id or ensure init-session was run"
            )

        # Find JSONL file
        self.jsonl_path = self._find_jsonl_file()
        if not self.jsonl_path:
            raise FileNotFoundError(f"Could not find session JSONL: {self.session_id}.jsonl")

        # Generate metadata
        now = datetime.now()
        self.date_yyyymmdd = now.strftime("%Y%m%d")
        from datetime import timezone
        self.date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.date_display = now.strftime("%B %-d, %Y") if os.name != 'nt' else now.strftime("%B %d, %Y").replace(' 0', ' ')
        self.date_changelog = now.strftime("%Y-%m-%d")

        self.title_kebab = self._to_kebab_case(title)
        self.conversation_id = f"{self.date_yyyymmdd}-{self.title_kebab}"
        self.output_file = self.archive_dir / "transcripts" / f"{self.conversation_id}.json"

        # Get user info
        self.user_name = self._get_user_name()
        self.user_github = self._get_user_github()

    def _find_archive_dir(self) -> Optional[Path]:
        """Find .archive/transcripts directory by traversing up from cwd.

        Only returns archive directories at or below the current working
        directory to prevent accidentally modifying a parent project's archive.
        """
        cwd = Path.cwd().resolve()
        current = cwd
        while current != current.parent:
            archive_path = current / ".archive" / "transcripts"
            if archive_path.is_dir():
                # Verify the archive is within the cwd (not a parent project)
                try:
                    current.relative_to(cwd)
                except ValueError:
                    current = current.parent
                    continue
                return current / ".archive"
            current = current.parent
        return None

    def _read_current_version(self) -> Version:
        """Read the latest semver version from CHANGELOG.md.

        Scans the CHANGELOG for the most recent semantic version entry,
        ignoring date-based entries like [2026-01-10].
        Falls back to 0.1.0 if no version is found.
        """
        if not self.changelog_path.exists():
            return Version(0, 1, 0)

        content = self.changelog_path.read_text(encoding='utf-8')

        # Find all version entries in the format ## [X.Y.Z]
        # Ignore date entries like [2026-01-10] and [Unreleased]
        pattern = r'## \[(\d+\.\d+\.\d+)\]'
        matches = re.findall(pattern, content)

        if matches:
            # Return the first (most recent) valid semver
            version = Version.parse(matches[0])
            if version:
                return version

        # Default to 0.1.0 if no version found
        return Version(0, 1, 0)

    def _find_session_id(self) -> Optional[str]:
        """Find session ID from index placeholder or most recent JSONL."""
        # Try to extract from index placeholder
        if self.index_path.exists():
            try:
                content = self.index_path.read_text(encoding='utf-8')
                # Look for placeholder entry
                pattern = rf"### {self.session_num_padded} - \[In Progress\].*?\*\*Session\*\*:\s*(\S+)"
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    session_id = match.group(1).strip()
                    if session_id and session_id != 'unknown':
                        return session_id
            except Exception:
                pass

        # Fall back to most recent JSONL (non-agent)
        return self._find_most_recent_jsonl()

    def _find_most_recent_jsonl(self) -> Optional[str]:
        """Find most recent non-agent JSONL file modified in last 60 minutes."""
        claude_projects = Path.home() / ".claude" / "projects"
        if not claude_projects.exists():
            return None

        recent_files = []
        cutoff_time = datetime.now().timestamp() - (60 * 60)  # 60 minutes ago

        for jsonl_file in claude_projects.rglob("*.jsonl"):
            # Skip agent files
            if jsonl_file.name.startswith("agent-"):
                continue
            # Check modification time
            if jsonl_file.stat().st_mtime >= cutoff_time:
                recent_files.append((jsonl_file.stat().st_mtime, jsonl_file))

        if recent_files:
            # Sort by modification time (most recent first)
            recent_files.sort(reverse=True)
            return recent_files[0][1].stem  # Return filename without extension

        return None

    def _find_jsonl_file(self) -> Optional[Path]:
        """Locate session JSONL file in ~/.claude/projects/."""
        claude_projects = Path.home() / ".claude" / "projects"
        if not claude_projects.exists():
            return None

        for project_dir in claude_projects.iterdir():
            if not project_dir.is_dir():
                continue
            jsonl_file = project_dir / f"{self.session_id}.jsonl"
            if jsonl_file.exists():
                return jsonl_file

        return None

    def _to_kebab_case(self, text: str) -> str:
        """Convert text to kebab-case."""
        return re.sub(r'[^a-z0-9-]', '', text.lower().replace(' ', '-'))

    def _get_user_name(self) -> str:
        """Get user name from git config or override."""
        if self.user:
            return self.user

        try:
            import subprocess
            result = subprocess.run(
                ['git', 'config', 'user.name'],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        return "User"

    def _get_user_github(self) -> Optional[str]:
        """Get GitHub username from git config."""
        try:
            import subprocess
            # Try github.user first
            result = subprocess.run(
                ['git', 'config', 'github.user'],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()

            # Try extracting from remote origin
            result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                # Extract username from github.com URL
                match = re.search(r'github\.com[:/]([^/]+)/', url)
                if match:
                    return match.group(1)
        except Exception:
            pass

        return None

    def _parse_comma_separated(self, value: str) -> List[str]:
        """Parse comma-separated string into list of strings."""
        if not value:
            return []
        return [item.strip() for item in value.split(',') if item.strip()]

    def parse_jsonl(self) -> Dict:
        """Parse JSONL file to structured JSON transcript format."""
        messages = []
        model_id = None
        model_name = None
        files_created = []
        files_modified = []
        tools_used = Counter()

        with open(self.jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = entry.get('type')
                if msg_type not in ('user', 'assistant'):
                    continue
                if entry.get('isMeta'):
                    continue

                timestamp = entry.get('timestamp', self.date_iso)
                message_obj = entry.get('message', {})
                content = message_obj.get('content', '')

                # Extract model info
                if msg_type == 'assistant' and 'model' in message_obj:
                    model_id = message_obj.get('model')
                    if 'opus' in model_id.lower():
                        model_name = 'Claude Opus 4.5'
                    elif 'sonnet' in model_id.lower():
                        model_name = 'Claude Sonnet 4.5'
                    elif 'haiku' in model_id.lower():
                        model_name = 'Claude Haiku'
                    else:
                        model_name = 'Claude'

                # Parse message content
                message_text, tool_calls = self._parse_message_content(
                    content, tools_used, files_created, files_modified
                )

                # Skip empty messages
                if not message_text.strip() and not tool_calls:
                    continue

                msg = {
                    'speaker': msg_type,
                    'timestamp': timestamp,
                    'message': message_text
                }
                if msg_type == 'assistant' and tool_calls:
                    msg['tool_calls'] = tool_calls

                messages.append(msg)

        # Override model if specified
        if self.model:
            model_name = self.model
            model_id = self.model

        # Group consecutive tool-only messages
        messages = self._group_consecutive_tool_calls(messages)

        # Generate outcomes and topics
        outcomes = self._generate_outcomes(files_created, files_modified, messages)
        topics = self._generate_topics(tools_used)

        # Parse provided outcome fields
        provided_files_modified_list = self._parse_comma_separated(self.provided_files_modified)
        provided_artifacts_list = self._parse_comma_separated(self.provided_artifacts)
        provided_decisions_list = self._parse_comma_separated(self.provided_decisions)
        provided_next_steps_list = self._parse_comma_separated(self.provided_next_steps)

        # Merge provided files_modified with auto-detected ones
        # Convert auto-detected to paths list for easier merging
        auto_detected_paths = {f['path'] for f in files_modified}
        merged_files_modified = list(files_modified)  # Start with auto-detected

        # Add provided files that aren't already auto-detected
        for path in provided_files_modified_list:
            if path not in auto_detected_paths:
                merged_files_modified.append({
                    'path': path,
                    'changes': 'Modified file'
                })

        # Build transcript
        transcript = {
            'project_id': self.project_id,
            'conversation_id': self.conversation_id,
            'conversation_number': self.session_num,
            'date': self.date_iso,
            'participants': [
                {
                    'name': self.user_name,
                    'github': self.user_github,
                    'role': 'user',
                    'model': None
                },
                {
                    'name': model_name or 'Claude',
                    'github': None,
                    'role': 'assistant',
                    'model': model_id
                }
            ],
            'summary': {
                'title': self.title,
                'topics': topics,
                'outcomes': outcomes
            },
            'dialogue': messages,
            'outcomes': {
                'files_created': files_created,
                'files_modified': merged_files_modified,
                'artifacts_archived': provided_artifacts_list,
                'decisions': provided_decisions_list,
                'next_steps': provided_next_steps_list
            }
        }

        return transcript

    def _parse_message_content(
        self,
        content,
        tools_used: Counter,
        files_created: List[Dict],
        files_modified: List[Dict]
    ) -> Tuple[str, List[Dict]]:
        """Parse message content and extract tool calls."""
        if isinstance(content, str):
            # Skip command-name tags
            if '<command-name>' in content or '<local-command' in content:
                return '', []
            return content, []

        elif isinstance(content, list):
            text_parts = []
            tool_calls = []

            for item in content:
                if not isinstance(item, dict):
                    continue

                if item.get('type') == 'text':
                    text_parts.append(item.get('text', ''))

                elif item.get('type') == 'tool_use':
                    tool_name = item.get('name', 'Unknown')
                    inp = item.get('input', {})
                    tools_used[tool_name] += 1

                    # Track file operations
                    if tool_name == 'Write':
                        path = inp.get('file_path', '')
                        if path and path not in [f['path'] for f in files_created]:
                            files_created.append({
                                'path': path,
                                'description': 'Created file'
                            })
                    elif tool_name == 'Edit':
                        path = inp.get('file_path', '')
                        if path and path not in [f['path'] for f in files_modified]:
                            files_modified.append({
                                'path': path,
                                'changes': 'Modified file'
                            })

                    # Format description
                    desc = self._format_tool_description(tool_name, inp)
                    tool_calls.append({'tool': tool_name, 'description': desc})

            message_text = '\n'.join(text_parts)
            return message_text, tool_calls

        return '', []

    def _format_tool_description(self, tool_name: str, inp: Dict) -> str:
        """Format tool description based on tool type."""
        if tool_name == 'Read':
            return f"Read {inp.get('file_path', 'file')}"
        elif tool_name == 'Write':
            return f"Write to {inp.get('file_path', 'file')}"
        elif tool_name == 'Edit':
            return f"Edit {inp.get('file_path', 'file')}"
        elif tool_name == 'Bash':
            cmd = inp.get('command', '')
            if len(cmd) > 80:
                return f"Run: {cmd[:80]}..."
            return f"Run: {cmd}"
        elif tool_name == 'Glob':
            return f"Search pattern: {inp.get('pattern', '')}"
        elif tool_name == 'Grep':
            return f"Search for: {inp.get('pattern', '')}"
        elif tool_name == 'Task':
            return f"Spawn agent: {inp.get('description', '')}"
        elif tool_name == 'TodoWrite':
            return "Update todo list"
        else:
            return str(inp)[:100]

    def _generate_outcomes(
        self,
        files_created: List[Dict],
        files_modified: List[Dict],
        messages: List[Dict]
    ) -> List[str]:
        """Auto-generate outcomes based on file operations."""
        outcomes = []

        if files_created:
            outcomes.append(f"Created {len(files_created)} file(s)")
        if files_modified:
            outcomes.append(f"Modified {len(files_modified)} file(s)")

        # Add specific outcomes based on common patterns
        for file_info in files_created:
            path = file_info['path']
            basename = os.path.basename(path)

            if basename.endswith('.sh'):
                outcomes.append(f"Created {basename} script")
            elif basename.endswith('.md') and 'command' in path.lower():
                outcomes.append(f"Created {basename} command")
            elif basename.endswith('.json') and 'transcript' in path.lower():
                outcomes.append(f"Created transcript {basename}")

        # Deduplicate and limit outcomes
        outcomes = list(dict.fromkeys(outcomes))[:5]

        if not outcomes:
            outcomes = [f"Completed conversation with {len(messages)} exchanges"]

        return outcomes

    def _generate_topics(self, tools_used: Counter) -> List[str]:
        """Auto-generate topics if not provided."""
        if self.topics:
            return [t.strip() for t in self.topics.split(',')]

        topics = []
        if tools_used.get('Write') or tools_used.get('Edit'):
            topics.append('code development')
        if tools_used.get('Bash'):
            topics.append('shell scripting')
        if tools_used.get('Task'):
            topics.append('agent tasks')

        if not topics:
            topics = ['development session']

        return topics

    def _group_consecutive_tool_calls(self, messages: List[Dict]) -> List[Dict]:
        """Group consecutive assistant messages that have only tool calls (no text).

        When multiple tool calls occur in rapid succession without accompanying
        text messages, they are merged into a single dialogue entry. The timestamp
        of the first message in the group is preserved.
        """
        if not messages:
            return messages

        grouped = []
        i = 0

        while i < len(messages):
            msg = messages[i]

            # Check if this is a tool-only assistant message
            if (msg.get('speaker') == 'assistant' and
                    not msg.get('message', '').strip() and
                    msg.get('tool_calls')):

                # Start a group - collect consecutive tool-only messages
                group_timestamp = msg['timestamp']
                group_tool_calls = list(msg['tool_calls'])

                j = i + 1
                while j < len(messages):
                    next_msg = messages[j]
                    # Continue grouping if next is also tool-only assistant
                    if (next_msg.get('speaker') == 'assistant' and
                            not next_msg.get('message', '').strip() and
                            next_msg.get('tool_calls')):
                        group_tool_calls.extend(next_msg['tool_calls'])
                        j += 1
                    else:
                        break

                # Create merged entry (only if we actually grouped multiple)
                grouped.append({
                    'speaker': 'assistant',
                    'timestamp': group_timestamp,
                    'message': '',
                    'tool_calls': group_tool_calls
                })
                i = j
            else:
                grouped.append(msg)
                i += 1

        return grouped

    def write_transcript(self, transcript: Dict, content_override: str = None) -> None:
        """Write transcript to JSON file.

        If content_override is provided (e.g., sanitized content), write that
        directly instead of serializing the transcript dict.
        """
        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_file, 'w', encoding='utf-8') as f:
            if content_override is not None:
                f.write(content_override)
            else:
                json.dump(transcript, f, indent=2, ensure_ascii=False)

    def update_index(self, transcript: Dict) -> None:
        """Update _index.md by replacing placeholder with actual entry."""
        if not self.index_path.exists():
            print(f"Warning: Index not found at {self.index_path}")
            return

        # Extract values from transcript
        topics = ', '.join(transcript['summary']['topics'])
        outcomes = '; '.join(transcript['summary']['outcomes'])
        assistant = [p for p in transcript['participants'] if p['role'] == 'assistant'][0]
        model_display = f"{assistant['name']} ({assistant['model']})"

        # Format user display (handle missing github username)
        if self.user_github:
            user_display = f"{self.user_name} (@{self.user_github})"
        else:
            user_display = self.user_name

        # Build README entry
        readme_entry = f"""### {self.session_num_padded} - {self.title}
**File**: {self.conversation_id}.json
**Date**: {self.date_display}
**Participants**: {user_display}, {model_display}
**Topics**: {topics}
**Outcomes**: {outcomes}"""

        # Read current content
        content = self.index_path.read_text(encoding='utf-8')

        # Pattern to match the placeholder entry (including Session line)
        pattern = rf'### {self.session_num_padded} - \[In Progress\]\n\*\*File\*\*:.*?\n\*\*Date\*\*:.*?\n\*\*Participants\*\*:.*?\n(\*\*Session\*\*:.*?\n)?\*\*Topics\*\*:.*?\n\*\*Outcomes\*\*:.*?(?=\n\n|\n##|\Z)'

        # Replace placeholder
        new_content = re.sub(pattern, readme_entry, content, flags=re.DOTALL)

        # Write back
        self.index_path.write_text(new_content, encoding='utf-8')

    def _format_changelog_entry(self, transcript: Dict) -> str:
        """Format changelog entry using proper Types of Changes categories.

        Categories: Added, Changed, Deprecated, Removed, Fixed, Security
        """
        # Read current version and bump it
        current_version = self._read_current_version()
        if self.bump_type == 'major':
            new_version = current_version.bump_major()
        elif self.bump_type == 'minor':
            new_version = current_version.bump_minor()
        else:  # patch
            new_version = current_version.bump_patch()

        files_created = transcript['outcomes'].get('files_created', [])
        files_modified = transcript['outcomes'].get('files_modified', [])
        title_lower = self.title.lower()
        topics = [t.lower() for t in transcript['summary'].get('topics', [])]

        lines = []
        lines.append(f"## [{new_version}] - {self.date_changelog}")
        lines.append(f"**Conversation**: {self.session_num_padded} - {self.title}")
        lines.append(f"**Transcript**: [{self.conversation_id}.json](transcripts/{self.conversation_id}.json)")

        # Detect if this is a fix (from title or topics)
        is_fix = 'fix' in title_lower or 'bug' in title_lower or any('fix' in t for t in topics)
        is_security = 'security' in title_lower or any('security' in t for t in topics)

        # Group changes by category
        added_items = []
        changed_items = []
        fixed_items = []
        security_items = []

        # Categorize file operations
        for f in files_created:
            path = f.get('path', '')
            basename = os.path.basename(path)
            added_items.append(basename)

        for f in files_modified:
            path = f.get('path', '')
            basename = os.path.basename(path)
            if is_security:
                security_items.append(f"Updated {basename}")
            elif is_fix:
                fixed_items.append(f"Fixed issues in {basename}")
            else:
                changed_items.append(f"Updated {basename}")

        # Build categorized output
        if added_items:
            lines.append("### Added")
            for item in added_items:
                lines.append(f"- {item}")

        if changed_items:
            lines.append("### Changed")
            for item in changed_items:
                lines.append(f"- {item}")

        if fixed_items:
            lines.append("### Fixed")
            for item in fixed_items:
                lines.append(f"- {item}")

        if security_items:
            lines.append("### Security")
            for item in security_items:
                lines.append(f"- {item}")

        # Fallback if no file operations detected
        if not (added_items or changed_items or fixed_items or security_items):
            lines.append("### Changed")
            lines.append(f"- Development session: {self.title}")

        return '\n'.join(lines)

    def update_changelog(self, transcript: Dict) -> None:
        """Update CHANGELOG.md with new entry at top."""
        changelog_entry = self._format_changelog_entry(transcript)

        if self.changelog_path.exists():
            content = self.changelog_path.read_text(encoding='utf-8')

            # Insert after ## [Unreleased] section (before next ## [)
            if '## [Unreleased]' in content:
                pattern = r'(## \[Unreleased\].*?\n)(\n*)(## \[)'
                replacement = r'\1\n' + changelog_entry + r'\n\n\3'
                new_content = re.sub(pattern, replacement, content, count=1)
            else:
                # Insert after header (before first ## [ entry)
                lines = content.split('\n')
                insert_idx = len(lines)
                for i, line in enumerate(lines):
                    if line.startswith('## ['):
                        insert_idx = i
                        break
                lines.insert(insert_idx, '\n' + changelog_entry + '\n')
                new_content = '\n'.join(lines)

            self.changelog_path.write_text(new_content, encoding='utf-8')
        else:
            # Create new changelog
            changelog_content = f"""# Changelog

{changelog_entry}
"""
            self.changelog_path.write_text(changelog_content, encoding='utf-8')

    def _scan_pii(self, content: str) -> List[Dict]:
        """Scan transcript content for PII patterns.

        Returns a list of findings, each with 'type', 'count', and 'example'.
        """
        findings = []

        # Home directory paths (extract username from pattern)
        home_patterns = [
            (r'/Users/([^/\s"]+)/', 'macOS home path'),
            (r'/home/([^/\s"]+)/', 'Linux home path'),
            (r'C:\\\\Users\\\\([^\\\\"\s]+)\\\\', 'Windows home path'),
        ]
        for pattern, label in home_patterns:
            matches = re.findall(pattern, content)
            if matches:
                username = matches[0]
                count = len(matches)
                findings.append({
                    'type': f'{label} (username: {username})',
                    'count': count,
                    'pattern': pattern,
                    'username': username,
                })

        # Email addresses
        email_matches = re.findall(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            content
        )
        # Filter out known safe emails (Co-Authored-By, noreply)
        email_matches = [e for e in email_matches if 'noreply@' not in e]
        if email_matches:
            findings.append({
                'type': 'email address',
                'count': len(email_matches),
                'example': email_matches[0],
            })

        # API keys / tokens (high-entropy strings near keywords, handles JSON escaping)
        secret_pattern = r'(?:key|token|secret|password|api_key|apikey|auth)["\s:=\\]+["\']?([a-zA-Z0-9_\-]{20,})'
        secret_matches = re.findall(secret_pattern, content, re.IGNORECASE)
        if secret_matches:
            findings.append({
                'type': 'potential secret/token',
                'count': len(secret_matches),
                'example': secret_matches[0][:8] + '...',
            })

        # Participant name (from self.user_name if not generic)
        if self.user_name and self.user_name != 'User':
            name_count = content.count(self.user_name)
            if name_count > 0:
                findings.append({
                    'type': f'participant name ("{self.user_name}")',
                    'count': name_count,
                })

        return findings

    def _sanitize_content(self, content: str, findings: List[Dict]) -> str:
        """Apply redactions to transcript content based on scan findings."""
        sanitized = content

        # Replace home directory paths
        for finding in findings:
            if 'username' in finding:
                username = finding['username']
                sanitized = sanitized.replace(f'/Users/{username}/', '/Users/<user>/')
                sanitized = sanitized.replace(f'/home/{username}/', '/home/<user>/')
                sanitized = sanitized.replace(
                    f'C:\\\\Users\\\\{username}\\\\',
                    'C:\\\\Users\\\\<user>\\\\'
                )

        # Replace participant name
        if self.user_name and self.user_name != 'User':
            sanitized = sanitized.replace(self.user_name, '<user>')

        return sanitized

    def _report_findings(self, findings: List[Dict]) -> None:
        """Print PII scan results."""
        print(f"\n{'='*50}")
        print(f"PII SCAN: {len(findings)} type(s) of sensitive data found")
        print(f"{'='*50}")
        for f in findings:
            line = f"  - {f['type']}: {f['count']} occurrence(s)"
            if 'example' in f:
                line += f" (e.g., {f['example']})"
            print(line)
        print()

    def _is_git_repo(self) -> bool:
        """Check if project directory is a git repository."""
        git_dir = self.project_dir / ".git"
        return git_dir.exists() and git_dir.is_dir()

    def _git_commit_transcripts(self) -> None:
        """Auto-commit transcript, index, changelog, session-notes, and handoff."""
        if not self._is_git_repo():
            return

        try:
            # Build list of files to commit (relative to project_dir)
            files_to_commit = []

            # Transcript file (relative path)
            transcript_rel = self.output_file.relative_to(self.project_dir)
            files_to_commit.append(str(transcript_rel))

            # Index file
            index_rel = self.index_path.relative_to(self.project_dir)
            files_to_commit.append(str(index_rel))

            # Changelog file
            changelog_rel = self.changelog_path.relative_to(self.project_dir)
            files_to_commit.append(str(changelog_rel))

            # Session notes file (created by /init-session). Include if present
            # so cross-session learnings travel with the transcript commit.
            session_notes_path = (
                self.archive_dir
                / "session-notes"
                / f"{self.date_yyyymmdd}-{self.session_num_padded}-session-notes.md"
            )
            if session_notes_path.exists():
                files_to_commit.append(
                    str(session_notes_path.relative_to(self.project_dir))
                )

            # Session handoff file (written by Claude during /end-session before
            # the handler runs). Without it, the next session has no high-signal
            # re-entry point — emit a warning but don't block the archive.
            session_handoff_path = (
                self.archive_dir
                / "session-handoff"
                / f"{self.date_yyyymmdd}-{self.session_num_padded}-session-handoff.md"
            )
            if session_handoff_path.exists():
                files_to_commit.append(
                    str(session_handoff_path.relative_to(self.project_dir))
                )
            else:
                print(
                    f"\nWarning: no session-handoff file found at "
                    f"{session_handoff_path.relative_to(self.project_dir)} — "
                    f"the next session will have no re-entry point.",
                    file=sys.stderr,
                )

            # Build commit message with date
            commit_message = f"Add transcript for session {self.date_display}"

            # Stage files
            subprocess.run(
                ['git', 'add'] + files_to_commit,
                cwd=str(self.project_dir),
                check=True,
                capture_output=True
            )

            # Commit
            subprocess.run(
                ['git', 'commit', '-m', commit_message],
                cwd=str(self.project_dir),
                check=True,
                capture_output=True
            )

            print(f"\nGit commit successful: {commit_message}")

        except subprocess.CalledProcessError as e:
            # Don't fail if git commit fails - just report it
            print(f"\nWarning: Git commit failed: {e}")
        except Exception as e:
            print(f"\nWarning: Could not commit to git: {e}")

    def run(self) -> None:
        """Main execution flow."""
        print(f"Creating transcript for conversation {self.session_num_padded}: {self.title}")
        print(f"Session: {self.session_id}")
        print(f"Output: {self.output_file}")

        # Calculate new version
        current_version = self._read_current_version()
        if self.bump_type == 'major':
            new_version = current_version.bump_major()
        elif self.bump_type == 'minor':
            new_version = current_version.bump_minor()
        else:  # patch
            new_version = current_version.bump_patch()

        print(f"\nVersion: {current_version} -> {new_version} ({self.bump_type} bump)")

        # Prompt for confirmation (unless in dry-run mode)
        if not self.dry_run:
            try:
                response = input("Continue with this version? [Y/n]: ").strip().lower()
                if response and response not in ('y', 'yes'):
                    print("Aborted by user.")
                    sys.exit(0)
            except (KeyboardInterrupt, EOFError):
                print("\nAborted by user.")
                sys.exit(0)

        if self.dry_run:
            print("\n[DRY RUN MODE]")

        # Parse JSONL and generate transcript
        transcript = self.parse_jsonl()

        # Extract metadata for display
        message_count = len(transcript['dialogue'])
        topics = ', '.join(transcript['summary']['topics'])
        outcomes = '; '.join(transcript['summary']['outcomes'])

        print(f"Messages: {message_count}")
        print(f"Topics: {topics}")
        print(f"Outcomes: {outcomes}")

        if self.dry_run:
            print(f"\nWould write: {self.output_file}")
            print(f"Would update: {self.index_path} (replace placeholder)")
            print(f"Would update: {self.changelog_path} (add entry at top with version {new_version})")
            print("\n[DRY RUN COMPLETE]")
            return

        # Serialize and scan for PII
        content = json.dumps(transcript, indent=2, ensure_ascii=False)
        findings = self._scan_pii(content)

        if findings and not self.sanitize:
            self._report_findings(findings)
            try:
                response = input(
                    "Options: [c]ommit anyway / [s]anitize and commit / [a]bort: "
                ).strip().lower()
                if response in ('a', 'abort'):
                    print("Aborted by user.")
                    sys.exit(0)
                elif response in ('s', 'sanitize'):
                    content = self._sanitize_content(content, findings)
                    print("Sanitized.")
                # 'c' or 'commit' or empty: proceed as-is
            except (KeyboardInterrupt, EOFError):
                print("\nAborted by user.")
                sys.exit(0)
        elif findings and self.sanitize:
            self._report_findings(findings)
            content = self._sanitize_content(content, findings)
            print("Auto-sanitized (--sanitize flag).")

        # Write files
        self.write_transcript(transcript, content_override=content)
        print(f"\nTranscript created: {self.output_file}")

        self.update_index(transcript)
        print(f"Index updated: {self.index_path}")

        self.update_changelog(transcript)
        print(f"CHANGELOG updated: {self.changelog_path}")

        # Auto-commit if in git repo
        self._git_commit_transcripts()

        print(f"\nDone! Conversation {self.session_num_padded} archived successfully.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='End an LLM session: archive transcript, commit notes + handoff bundle',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 4 "Setup automation framework"
  %(prog)s 5 "Refactor parser logic" --topics "python, refactoring"
  %(prog)s 6 "Debug API issues" --session-id abc123 --dry-run
        """
    )

    parser.add_argument(
        'session_num',
        type=int,
        help='The conversation number (e.g., 4)'
    )
    parser.add_argument(
        'title',
        type=str,
        help='Brief conversation title (3-7 words)'
    )
    parser.add_argument(
        '--topics',
        type=str,
        help='Comma-separated topic list'
    )
    parser.add_argument(
        '--session-id',
        type=str,
        help='Session UUID (auto-detected if not provided)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview without writing files'
    )
    parser.add_argument(
        '--model',
        type=str,
        help='Override model name'
    )
    parser.add_argument(
        '--user',
        type=str,
        help='Override user name'
    )
    parser.add_argument(
        '--minor',
        action='store_true',
        help='Bump minor version (X.Y.Z -> X.Y+1.0)'
    )
    parser.add_argument(
        '--major',
        action='store_true',
        help='Bump major version (X.Y.Z -> X+1.0.0)'
    )
    parser.add_argument(
        '--sanitize',
        action='store_true',
        help='Automatically redact PII (home paths, names) without prompting'
    )
    parser.add_argument(
        '--files-modified',
        type=str,
        help='Comma-separated list of modified files (e.g., "file1.py, file2.md")'
    )
    parser.add_argument(
        '--artifacts',
        type=str,
        help='Comma-separated list of archived artifacts (e.g., "artifact1.md, artifact2.md")'
    )
    parser.add_argument(
        '--decisions',
        type=str,
        help='Comma-separated list of decisions made (e.g., "decision1, decision2")'
    )
    parser.add_argument(
        '--next-steps',
        type=str,
        help='Comma-separated list of next steps (e.g., "step1, step2")'
    )

    args = parser.parse_args()

    # Determine bump type
    bump_type = 'patch'
    if args.major:
        bump_type = 'major'
    elif args.minor:
        bump_type = 'minor'

    try:
        generator = TranscriptGenerator(
            session_num=args.session_num,
            title=args.title,
            session_id=args.session_id,
            topics=args.topics,
            dry_run=args.dry_run,
            sanitize=args.sanitize,
            model=args.model,
            user=args.user,
            bump_type=bump_type,
            files_modified=getattr(args, 'files_modified', ''),
            artifacts=getattr(args, 'artifacts', ''),
            decisions=getattr(args, 'decisions', ''),
            next_steps=getattr(args, 'next_steps', '')
        )
        generator.run()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
