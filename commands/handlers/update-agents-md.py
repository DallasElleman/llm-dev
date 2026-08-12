#!/usr/bin/env python3
"""update-agents-md.py - Maintain a project's AGENTS.md / CLAUDE.md.

Usage: python update-agents-md.py [--project-path PATH] [--file NAME]
                                   [--mode refresh|verify-refs|targeted|audit]
                                   [--sections "<heading>, <heading>"]
                                   [--restamp] [--list] [--dry-run]

Run with no --mode/--list/--restamp and the handler does not act: it prints
the calibration facts as `AUDIT_SCOPE_NEEDED: <JSON>` and exits, so Claude can
present a scope menu (AskUserQuestion) and re-invoke exactly once with a
chosen --mode. This mirrors init-session's STREAM_SELECTION_NEEDED pattern.

The handler owns the arithmetic (line/char counts, reference resolution,
staleness) because agent self-counts are unreliable even when their quotes
are exact. It does not judge content — the audit protocol and editing rules
that require judgment live in commands/update-agents-md.md, applied by Claude
and dispatched subagents, not this script.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

CANDIDATE_NAMES = ("CLAUDE.md", "AGENTS.md")

META_DATE_RE = re.compile(
    r"^(\*\*Last (?:[Ee]dited|[Uu]pdated)\*\*):\s*(\d{4}-\d{2}-\d{2})",
    re.MULTILINE,
)
HEADING_RE = re.compile(r"^#{1,6}\s")
SECTION_HEADING_RE = re.compile(r"^##\s+.*$", re.MULTILINE)
HR_RE = re.compile(r"^(-{3,}|\*{3,}|_{3,})\s*$")
METADATA_LINE_RE = re.compile(r"^\*\*[^*]+\*\*:")
FENCE_RE = re.compile(r"^```")
PATH_IN_BACKTICKS_RE = re.compile(r"`([^`\n]+)`")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
ANCHOR_RE = re.compile(r"\xa7\s*(\d+)")
# A deploy-branch claim is a backticked token on a line that mentions deploying,
# introduced by a preposition that makes it a *target* ("deploys from `main`",
# "the deploy branch is `release`"). Matching any backticked token near the word
# "deploy" instead picks up directory paths and script names from ordinary prose.
DEPLOY_TARGET_RE = re.compile(
    r"\b(?:branch|from|to|onto|against|on)\b[^\n`]{0,30}`([^`\n]+)`",
    re.IGNORECASE,
)
VERSION_NUM_RE = re.compile(r"^\d+(\.\d+){1,3}$")
PLACEHOLDER_CHARS = set("$<>{}*")

SESSION_BOUNDARY_WARNING = (
    "Session-boundary check: an agent's copy of this file is a session-start "
    "snapshot -- it does not refresh on edit and does not disappear on "
    "delete, and subagents inherit the parent's snapshot either way. If this "
    "file's content is already in the current session's context (injected as "
    "project instructions, or read earlier in this conversation), a Full "
    "audit run from here is biased. Hold the file aside and start a new "
    "session before running the Full audit -- every dispatched agent then "
    "gets a clean context for free."
)


def resolve_target(project_root: Path, explicit: str | None) -> tuple[Path | None, Path | None]:
    """Return (target, other_candidate_if_also_present)."""
    if explicit:
        return (project_root / explicit).resolve(), None
    found = None
    other = None
    for name in CANDIDATE_NAMES:
        p = project_root / name
        if p.exists():
            if found is None:
                found = p
            else:
                other = p
    return found, other


def find_metadata_date(text: str) -> tuple[date | None, str | None]:
    m = META_DATE_RE.search(text)
    if not m:
        return None, None
    try:
        return datetime.strptime(m.group(2), "%Y-%m-%d").date(), m.group(1)
    except ValueError:
        return None, None


def git_last_modified(path: Path, cwd: Path) -> date | None:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=short", "--", str(path)],
            cwd=str(cwd), capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    if not out:
        return None
    try:
        return datetime.strptime(out, "%Y-%m-%d").date()
    except ValueError:
        return None


def current_branch(cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(cwd), capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return out or None


def instruction_lines(text: str) -> int:
    """Heuristic count of prose/instruction lines: excludes blanks, headings,
    horizontal rules, metadata-label lines, and fenced code block contents."""
    count = 0
    in_fence = False
    for line in text.splitlines():
        s = line.strip()
        if FENCE_RE.match(s):
            in_fence = not in_fence
            continue
        if in_fence or not s:
            continue
        if HEADING_RE.match(s) or HR_RE.match(s) or METADATA_LINE_RE.match(s):
            continue
        count += 1
    return count


def split_sections(text: str) -> list[dict]:
    """Split on level-2 (##) headings; each entry covers heading through the
    line before the next ## heading (or EOF)."""
    lines = text.splitlines()
    sections: list[dict] = []
    current = None
    for line in lines:
        if re.match(r"^##\s+", line):
            if current is not None:
                sections.append(current)
            current = {"heading": line.strip(), "body": []}
        elif current is not None:
            current["body"].append(line)
    if current is not None:
        sections.append(current)

    result = []
    for s in sections:
        body_text = "\n".join(s["body"])
        result.append({
            "heading": s["heading"],
            "lines": len(s["body"]) + 1,
            "chars": len(body_text) + len(s["heading"]),
            "instruction_bearing_lines": instruction_lines(body_text),
        })
    return result


def looks_like_path(token: str) -> bool:
    if not token or " " in token:
        return False
    if any(c in PLACEHOLDER_CHARS for c in token):
        return False
    if VERSION_NUM_RE.match(token):
        return False
    if token.startswith("-"):
        return False
    if "/" in token:
        return True
    return bool(re.search(r"\.[A-Za-z]{1,6}$", token))


def extract_references(text: str) -> list[dict]:
    refs = []
    for m in PATH_IN_BACKTICKS_RE.finditer(text):
        tok = m.group(1)
        if looks_like_path(tok):
            refs.append({"ref": tok, "kind": "path",
                         "line": text.count("\n", 0, m.start()) + 1})
    for m in MD_LINK_RE.finditer(text):
        target = m.group(1)
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        refs.append({"ref": target, "kind": "path",
                     "line": text.count("\n", 0, m.start()) + 1})
    for m in ANCHOR_RE.finditer(text):
        refs.append({"ref": "\xa7" + m.group(1), "kind": "anchor",
                     "line": text.count("\n", 0, m.start()) + 1})
    return refs


def check_references(text: str, project_root: Path) -> tuple[list[dict], list[dict]]:
    headings = [h.lstrip("#").strip() for h in SECTION_HEADING_RE.findall(text)]
    refs = extract_references(text)
    checked = []
    dangling = []
    seen = set()
    for r in refs:
        key = (r["kind"], r["ref"])
        if key in seen:
            continue
        seen.add(key)
        if r["kind"] == "path":
            candidate = r["ref"].split("#")[0].lstrip("/")
            ok = (project_root / candidate).exists()
        else:
            idx = int(r["ref"][1:])
            ok = 1 <= idx <= len(headings)
        entry = {**r, "resolved": ok}
        checked.append(entry)
        if not ok:
            dangling.append(entry)
    return checked, dangling


def looks_like_branch(token: str) -> bool:
    """Reject tokens that are clearly paths, filenames, flags, or placeholders.
    Branch names may contain '/' (`deploy/v1.2.3`), so '/' alone isn't
    disqualifying — but a leading '.', '/', or '-' and a trailing file
    extension are."""
    if not token or " " in token:
        return False
    if token.startswith((".", "/", "-")):
        return False
    if any(c in token for c in PLACEHOLDER_CHARS):
        return False
    return not re.search(r"\.[A-Za-z]{1,6}$", token)


def find_deploy_claim(text: str) -> str | None:
    """Best-effort extraction of the branch the file claims deploys happen from.

    Scoped to lines that mention deploying, and to backticked tokens that both
    follow a target-introducing preposition and look like a branch name.
    """
    for line in text.splitlines():
        if "deploy" not in line.lower():
            continue
        for m in DEPLOY_TARGET_RE.finditer(line):
            if looks_like_branch(m.group(1)):
                return m.group(1)
    return None


def build_calibration(project_root: Path, target: Path, other: Path | None) -> dict:
    text = target.read_text(encoding="utf-8")

    meta_date, meta_label = find_metadata_date(text)
    date_source = "metadata" if meta_date else None
    if meta_date is None:
        meta_date = git_last_modified(target, project_root)
        date_source = "git" if meta_date else None
    days_stale = (date.today() - meta_date).days if meta_date else None

    checked, dangling = check_references(text, project_root)

    deploy_claim = find_deploy_claim(text)
    branch = current_branch(project_root)
    branch_matches = deploy_claim == branch if (deploy_claim and branch) else None

    return {
        "file": target.name,
        "path": str(target),
        "other_file_present": other.name if other else None,
        "metadata": {
            "last_edited": meta_date.isoformat() if meta_date else None,
            "last_edited_source": date_source,
            "last_edited_label": meta_label,
            "days_stale": days_stale,
        },
        "size": {
            "lines": len(text.splitlines()),
            "chars": len(text),
            "instruction_bearing_lines": instruction_lines(text),
        },
        "sections": split_sections(text),
        "references": {
            "checked_count": len(checked),
            "dangling_count": len(dangling),
            "dangling": dangling,
        },
        "git": {
            "current_branch": branch,
            "deploy_branch_claim": deploy_claim,
            "branch_matches_claim": branch_matches,
        },
    }


def recommend_mode(calibration: dict) -> tuple[str, str]:
    dangling = calibration["references"]["dangling_count"]
    instr = calibration["size"]["instruction_bearing_lines"]
    days_stale = calibration["metadata"]["days_stale"]

    # A branch mismatch is deliberately NOT an escalation trigger: you are on a
    # feature branch for most of a project's life, so it fires constantly and
    # would recommend the most expensive mode (a full audit dispatching one
    # subagent per angle) as the steady state. It stays in the calibration JSON
    # as an informational field for Claude to weigh.
    reasons = []
    if dangling:
        reasons.append(f"{dangling} dangling reference(s)")
    if instr > 200:
        reasons.append(f"{instr} instruction-bearing lines (budget ~150-200)")

    if reasons:
        return "audit", "Structural drift detected: " + ", ".join(reasons) + "."
    if days_stale is not None and days_stale > 0:
        return "refresh", (
            f"Only the date looks stale ({days_stale} day(s) since last edit); "
            "no structural drift found."
        )
    return "refresh", "No metadata date found; a refresh pass would establish one."


def restamp_last_edited(target: Path) -> bool:
    text = target.read_text(encoding="utf-8")
    today = date.today().isoformat()
    new_text, n = META_DATE_RE.subn(lambda m: f"{m.group(1)}: {today}", text, count=1)
    if n == 0:
        return False
    target.write_text(new_text, encoding="utf-8")
    return True


def _calibration_line(calibration: dict) -> str:
    return "CALIBRATION: " + json.dumps(calibration)


def print_verify_refs_report(calibration: dict) -> None:
    refs = calibration["references"]
    print(f"Reference check for {calibration['file']}: {refs['checked_count']} "
          f"reference(s) found, {refs['dangling_count']} dangling.")
    if refs["dangling"]:
        print()
        print("Dangling references:")
        for d in refs["dangling"]:
            print(f"  line {d['line']}: {d['kind']} `{d['ref']}` does not resolve")
    else:
        print("All references resolve cleanly.")
    print()
    print("Note: only paths, markdown links, and numeric \xa7N anchors are "
          "checked automatically. Module/symbol references and text-form "
          "anchors still need manual verification.")
    print()
    print(_calibration_line(calibration))


def print_refresh_worksheet(calibration: dict) -> None:
    meta = calibration["metadata"]
    git = calibration["git"]
    print(f"Refresh worksheet for {calibration['file']}:")
    stale = f"  ({meta['days_stale']} day(s) ago)" if meta["days_stale"] is not None else ""
    print(f"  Last edited: {meta['last_edited'] or '(none found)'}{stale}")
    print(f"  Current branch: {git['current_branch'] or '(unknown)'}")
    mismatch = "  -- MISMATCH" if git["branch_matches_claim"] is False else ""
    print(f"  File's deploy-branch claim: {git['deploy_branch_claim'] or '(none found)'}{mismatch}")
    print()
    print("Re-verify each volatile assertion (objective, deploy branch, key module")
    print("roles) against the current repo state and fix drift directly in the file.")
    print("When done, re-run this handler with `--mode refresh --restamp` to update")
    print("the Last edited date before committing.")
    print()
    print(_calibration_line(calibration))


def print_targeted_report(calibration: dict, sections_arg: str) -> None:
    wanted = [s.strip() for s in sections_arg.split(",") if s.strip()]
    matched = []
    missing = []
    for w in wanted:
        hit = next((s for s in calibration["sections"] if w.lower() in s["heading"].lower()), None)
        (matched if hit else missing).append(hit or w)
    print(f"Targeted audit scope for {calibration['file']}: "
          f"{len(matched)}/{len(wanted)} section(s) matched.")
    for s in matched:
        print(f"  {s['heading']}  ({s['lines']} lines, "
              f"{s['instruction_bearing_lines']} instruction-bearing)")
    if missing:
        print(f"  Not found: {', '.join(missing)}")
    print()
    print("Apply the audit protocol (falsifier-before-search, UNVERIFIABLE-here,")
    print("removal needs evidence) to only the matched section(s) above.")
    print()
    print(_calibration_line(calibration))


def print_audit_briefing(calibration: dict) -> None:
    print(f"Full audit briefing for {calibration['file']}:")
    print()
    print(SESSION_BOUNDARY_WARNING)
    print()
    size = calibration["size"]
    print(f"  Lines: {size['lines']}  Chars: {size['chars']}  "
          f"Instruction-bearing: {size['instruction_bearing_lines']}")
    print(f"  Sections: {len(calibration['sections'])}")
    print(f"  Dangling references: {calibration['references']['dangling_count']}")
    print()
    print("Dispatch one read-only agent per angle (run/test, module map, each")
    print("gotcha cluster, conventions, plus an omissions sweep over archived")
    print("session notes) per the Audit Protocol. Each agent states its falsifier")
    print("before searching; a verdict with no falsifier is rejected.")
    print()
    print(_calibration_line(calibration))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Maintain a project's AGENTS.md / CLAUDE.md"
    )
    parser.add_argument("--project-path", default=None, metavar="PATH",
                        help="Explicit project root to search from (default: cwd)")
    parser.add_argument("--file", default=None, metavar="NAME",
                        help="Explicit filename to target, relative to project root "
                             "(default: auto-detect CLAUDE.md, then AGENTS.md)")
    parser.add_argument("--mode", choices=["refresh", "verify-refs", "targeted", "audit"],
                        default=None)
    parser.add_argument("--sections", default=None, metavar="LIST",
                        help='Comma-separated section headings for --mode targeted, '
                             'e.g. "Deploy Workflow, Known Risks"')
    parser.add_argument("--restamp", action="store_true",
                        help="Update the Last edited metadata date to today "
                             "(mechanical; run after making edits)")
    parser.add_argument("--list", action="store_true",
                        help="Print calibration JSON and exit (no AUDIT_SCOPE_NEEDED "
                             "prefix); an alternative discovery source")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    project_root = Path(args.project_path).resolve() if args.project_path else Path.cwd()
    target, other = resolve_target(project_root, args.file)

    if target is None or not target.exists():
        print(json.dumps({
            "error": "no_target_file",
            "message": (
                f"No CLAUDE.md or AGENTS.md found at {project_root}. Create one "
                "(see /llm-dev:init-project) before running update-agents-md."
            ),
        }))
        return 1

    if args.restamp:
        if args.dry_run:
            print(f"[DRY RUN] Would restamp Last edited date in {target}")
        elif restamp_last_edited(target):
            print(f"Restamped Last edited date in {target}")
        else:
            print(f"No 'Last edited'/'Last Updated' metadata line found in {target}; "
                  "nothing to restamp.")

    calibration = build_calibration(project_root, target, other)

    if args.list:
        print(json.dumps(calibration, indent=2))
        return 0

    if args.mode is None:
        rec_mode, rec_reason = recommend_mode(calibration)
        payload = dict(calibration)
        payload["recommended_mode"] = rec_mode
        payload["recommendation_reason"] = rec_reason
        payload["session_boundary_warning"] = SESSION_BOUNDARY_WARNING
        payload["instruction"] = (
            "Present these to the user with the AskUserQuestion tool: one option per "
            "mode (Refresh, Verify references, Targeted audit, Full audit), marking "
            f"'{rec_mode}' as (Recommended) using recommendation_reason as its "
            "description. The automatic 'Other' free-text box covers anything beyond "
            "the four options. Before offering Full audit, weigh session_boundary_"
            "warning against this session's own context -- if this file's content is "
            "already loaded, hold it aside and recommend starting a new session "
            "instead of proceeding. Then re-invoke update-agents-md.py exactly once "
            "with --mode <chosen> (add --sections \"<list>\" for targeted)."
        )
        print("AUDIT_SCOPE_NEEDED: " + json.dumps(payload))
        return 0

    if args.mode == "verify-refs":
        print_verify_refs_report(calibration)
        return 0

    if args.mode == "refresh":
        print_refresh_worksheet(calibration)
        return 0

    if args.mode == "targeted":
        if not args.sections:
            print('Error: --mode targeted requires --sections "<comma-separated headings>"',
                  file=sys.stderr)
            return 1
        print_targeted_report(calibration, args.sections)
        return 0

    if args.mode == "audit":
        print_audit_briefing(calibration)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
