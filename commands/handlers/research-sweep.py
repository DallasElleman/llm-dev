#!/usr/bin/env python3
"""research-sweep.py - calibrate a repo and drive research-type selection

Discovery-then-single-dispatch, mirroring init-session.py's stream selection:

  python research-sweep.py                                  # discovery mode
  python research-sweep.py --types t1,t2 [--depth standard] [--publish]

Discovery mode gathers calibration facts (LOC, module/test counts, commit
activity, branch divergence, deploy config, live URL) and the available
research types, then prints `RESEARCH_TYPES_NEEDED: <JSON>` and exits without
dispatching anything. Dispatch mode (--types) prints `RESEARCH_SWEEP_PLAN:
<JSON>` — the selected types' sub-domains and prompt skeletons, plus the same
calibration facts, for Claude to actually fan out read-only subagents against.

This handler never writes to or mutates the target repository: it only reads
and prints. Stdlib only; Python 3.12+.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _plugin

# Bundled reference files, relative to the plugin root.
REFERENCE_SUBPATH = ("commands", "references", "research-sweep")

LANGUAGE_EXTENSIONS = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust",
    ".rb": "Ruby", ".java": "Java", ".c": "C", ".h": "C", ".cpp": "C++",
    ".hpp": "C++", ".cs": "C#", ".php": "PHP", ".swift": "Swift", ".kt": "Kotlin",
    ".sh": "Shell",
}

IGNORE_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "__pycache__",
    ".venv", "venv", ".tox", "target", ".next", ".archive", ".worktrees",
}

TEST_NAME_RE = re.compile(r"(^|[_.-])test(s)?([_.-]|$)|[_.-]spec[_.-]|\.spec\.", re.IGNORECASE)

DEPLOY_MARKERS = (
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "vercel.json",
    "netlify.toml", "Procfile", "fly.toml", "app.yaml", "render.yaml",
)

MANIFEST_FILES = (
    "package.json", "requirements.txt", "pyproject.toml", "Cargo.toml",
    "go.mod", "Gemfile", "composer.json",
)

URL_RE = re.compile(r"https?://[^\s)>\"']+")

# Sub-domain ids and labels mirror `commands/references/research-sweep/report-types.md`
# exactly — the handler emits them, and the agent prompts are built from the
# matching section of that file. If they drift, the dispatch plan names
# sub-domains whose prompt skeletons don't exist.
RESEARCH_TYPES = [
    {
        "slug": "code-quality-security",
        "name": "Code quality, security & efficiency",
        "group": "code-health",
        "ref": "1",
        "sub_domains": [
            "1a. Auth & authorization",
            "1b. Injection, XSS, SSRF, uploads, secrets, transport",
            "1c. Language-level code quality",
            "1d. Frontend code quality",
            "1e. Data-layer efficiency",
            "1f. Tests, CI/CD, deps, ops",
        ],
        "preview": "Bugs, vulns, N+1s, hot paths, dead code.",
    },
    {
        "slug": "dependency-supply-chain",
        "name": "Dependency & supply chain",
        "group": "code-health",
        "ref": "4",
        "sub_domains": [
            "4a. Resolution & reproducibility",
            "4b. Vulnerabilities & weight",
            "4c. Provenance & licensing",
        ],
        "preview": "CVEs, lockfile/repro risk, image weight, licences.",
    },
    {
        "slug": "accessibility",
        "name": "Accessibility & inclusive design",
        "group": "code-health",
        "ref": "7",
        "sub_domains": [
            "7a. Structure & semantics",
            "7b. Interaction",
            "7c. Perception",
        ],
        "preview": "Semantics, keyboard, focus, ARIA, contrast, SR flows.",
    },
    {
        "slug": "coherence-sweep",
        "name": "Coherence sweep",
        "group": "code-health",
        "ref": "3",
        "sub_domains": [
            "3a. Doc->code drift",
            "3b. Doc->doc contradiction",
            "3c. Superseded-as-current",
            "3d. Code-internal incoherence",
            "3e. Reference integrity",
            "3f. Vocabulary & decision-log integrity",
        ],
        "preview": "Contradictions, superseded-as-current, drift.",
    },
    {
        "slug": "architecture-product",
        "name": "Architecture & product",
        "group": "product-ops",
        "ref": "2",
        "sub_domains": [
            "2a. Product intent vs. implementation",
            "2b. Infrastructure fit",
            "2c. Data model & storage",
            "2d. Search / ML / heavyweight subsystems",
            "2e. Frontend architecture & UX",
            "2f. Counterfactual",
        ],
        "preview": "What it does vs. how it's built; alternatives.",
    },
    {
        "slug": "onboarding",
        "name": "Onboarding & contributor experience",
        "group": "product-ops",
        "ref": "5",
        "sub_domains": [
            "5a. Cold-start path",
            "5b. First contribution path",
            "5c. Knowledge architecture",
        ],
        "preview": "clone -> setup -> first change -> merged PR.",
    },
    {
        "slug": "pre-launch-readiness",
        "name": "Pre-launch / operational readiness",
        "group": "product-ops",
        "ref": "6",
        "sub_domains": [
            "6a. Data safety",
            "6b. Failure behavior",
            "6c. Day-one experience",
            "6d. Go/no-go",
        ],
        "preview": "Go-no-go: backups, rollback, observability, load.",
    },
]

RESEARCH_TYPES_BY_SLUG = {t["slug"]: t for t in RESEARCH_TYPES}

DEPTHS = ("quick", "standard", "deep")

# Hard cap on one dispatch wave; batch if the plan exceeds it.
MAX_CONCURRENT_AGENTS = 20


def _planned_agent_count(types: list[str], depth: str) -> dict:
    """Fan-out arithmetic, stated before dispatch so the user can approve it.

    quick merges each type into a single agent; standard and deep run one per
    sub-domain. Verifiers are one per type (the adversarial pass).
    """
    selected = [t for t in RESEARCH_TYPES if t["slug"] in types]
    if depth == "quick":
        sweepers = len(selected)
    else:
        sweepers = sum(len(t["sub_domains"]) for t in selected)
    verifiers = len(selected)
    return {
        "sweepers": sweepers,
        "verifiers": verifiers,
        "total": sweepers + verifiers,
        "exceeds_cap": sweepers > MAX_CONCURRENT_AGENTS,
    }


def _git(*args: str, cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def calibrate_loc(root: Path) -> dict:
    """LOC by language, plus module and test file counts.

    A "module" is any source file whose extension we recognize; a "test" is
    any source file whose name matches a common test-naming convention. Both
    counts are best-effort heuristics, not a build-system-aware analysis.
    """
    loc_by_language: dict[str, int] = {}
    module_count = 0
    test_count = 0

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.relative_to(root).parts):
            continue
        language = LANGUAGE_EXTENSIONS.get(path.suffix)
        if language is None:
            continue
        module_count += 1
        if TEST_NAME_RE.search(path.name):
            test_count += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        loc_by_language[language] = loc_by_language.get(language, 0) + lines

    return {
        "loc_by_language": loc_by_language,
        "module_count": module_count,
        "test_count": test_count,
    }


def calibrate_activity(root: Path, days: int = 90) -> dict:
    """Commits and distinct authors over the trailing `days`."""
    out = _git("log", f"--since={days}.days", "--pretty=%an", cwd=root)
    if out is None:
        return {"commits": None, "distinct_authors": None}
    authors = [line for line in out.splitlines() if line.strip()]
    return {"commits": len(authors), "distinct_authors": len(set(authors))}


def calibrate_branch_divergence(root: Path) -> dict:
    """Ahead/behind counts of HEAD vs. the default branch, best-effort.

    Tries `origin/main` then `origin/master` then local `main`/`master`.
    Returns Nones (not an error) when there's no remote or no divergence
    baseline to compare against — a shallow clone or a fresh repo, say.
    """
    candidates = ("origin/main", "origin/master", "main", "master")
    head = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
    for base in candidates:
        if head is not None and base.split("/")[-1] == head:
            continue
        counts = _git("rev-list", "--left-right", "--count", f"{base}...HEAD", cwd=root)
        if counts is None:
            continue
        parts = counts.split()
        if len(parts) != 2:
            continue
        behind_str, ahead_str = parts
        try:
            return {"base": base, "ahead": int(ahead_str), "behind": int(behind_str)}
        except ValueError:
            continue
    return {"base": None, "ahead": None, "behind": None}


def calibrate_deploy_config(root: Path) -> list[str]:
    """Deploy-config marker files found at the repo root, plus any workflow
    file whose name suggests it's a deploy pipeline."""
    found = [name for name in DEPLOY_MARKERS if (root / name).is_file()]
    workflows_dir = root / ".github" / "workflows"
    if workflows_dir.is_dir():
        for path in workflows_dir.glob("*.y*ml"):
            if "deploy" in path.name.lower():
                found.append(str(path.relative_to(root)))
    return found


def calibrate_live_url(root: Path) -> str | None:
    """Best-effort scan of README.md for a live URL (excludes github.com)."""
    readme = root / "README.md"
    if not readme.is_file():
        return None
    try:
        text = readme.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    for match in URL_RE.findall(text):
        if "github.com" not in match and "anthropic.com" not in match:
            return match.rstrip(").,")
    return None


def calibrate_manifests_changed(root: Path, days: int = 90) -> bool:
    """Whether any dependency manifest changed in the trailing `days`."""
    out = _git("log", f"--since={days}.days", "--name-only", "--pretty=format:", cwd=root)
    if out is None:
        return False
    changed = {Path(line).name for line in out.splitlines() if line.strip()}
    return any(name in changed for name in MANIFEST_FILES)


def calibrate_readme_entry_point(root: Path) -> bool:
    """Whether README.md exists and looks like more than a stub."""
    readme = root / "README.md"
    if not readme.is_file():
        return False
    try:
        return len(readme.read_text(encoding="utf-8", errors="ignore").strip()) > 200
    except OSError:
        return False


def run_calibration(root: Path) -> dict:
    calibration = {
        **calibrate_loc(root),
        "activity_90d": calibrate_activity(root),
        "branch_divergence": calibrate_branch_divergence(root),
        "deploy_config": calibrate_deploy_config(root),
        "live_url": calibrate_live_url(root),
        "manifests_changed_90d": calibrate_manifests_changed(root),
        "readme_entry_point": calibrate_readme_entry_point(root),
    }
    return calibration


def derive_recommended(calibration: dict) -> set[str]:
    """Recommend research types based on calibration facts.

    - pre-launch-readiness: branch is far ahead of the deployed default AND
      a deploy config exists (nothing to launch-check without one).
    - dependency-supply-chain: a manifest changed in the last 90 days.
    - onboarding: no substantive README entry point.
    """
    recommended: set[str] = set()

    divergence = calibration.get("branch_divergence", {})
    ahead = divergence.get("ahead")
    if ahead is not None and ahead >= 10 and calibration.get("deploy_config"):
        recommended.add("pre-launch-readiness")

    if calibration.get("manifests_changed_90d"):
        recommended.add("dependency-supply-chain")

    if not calibration.get("readme_entry_point"):
        recommended.add("onboarding")

    return recommended


def _types_needed_payload(calibration: dict) -> dict:
    recommended = derive_recommended(calibration)
    return {
        "calibration": calibration,
        "research_types": [
            {
                "slug": t["slug"],
                "name": t["name"],
                "group": t["group"],
                "sub_domain_count": len(t["sub_domains"]),
                "preview": t["preview"],
                "recommended": t["slug"] in recommended,
            }
            for t in RESEARCH_TYPES
        ],
        "depths": list(DEPTHS),
        "instruction": (
            "Report the calibration facts to the user in a few lines (call out "
            "anything surprising, e.g. large branch divergence or a missing "
            "README, before the menu). Then present the research types with "
            "AskUserQuestion, multiSelect: true, split into two questions by "
            "`group` (code-health, then product-ops) so both stay within the "
            "4-option-per-question limit without truncating the menu. Add a "
            "third question for depth (quick/standard/deep) and a fourth for "
            "whether to publish the report anywhere durable (default: no, "
            "scratchpad only). Then re-invoke this handler exactly once with "
            "--types <comma-separated slugs> --depth <depth> [--publish]."
        ),
    }


def reference_dir() -> Path:
    """Absolute path to the bundled research-sweep reference files.

    The dispatch plan is consumed by an agent whose cwd is the *user's*
    project, so a project-relative reference path never resolves and the
    quality contract silently drops out of the sweep. Resolve against the
    installed plugin root instead, falling back to this file's own location
    (dev checkout, or a plugin root that doesn't carry the references) so the
    emitted path is always absolute and points at real files when they exist.
    """
    roots = []
    try:
        roots.append(_plugin.plugin_root())
    except ValueError:
        pass
    roots.append(Path(__file__).resolve().parent.parent.parent)
    for root in roots:
        candidate = root.joinpath(*REFERENCE_SUBPATH)
        if candidate.is_dir():
            return candidate
    return roots[-1].joinpath(*REFERENCE_SUBPATH)


def _sweep_plan_payload(calibration: dict, types: list[str], depth: str, publish: bool) -> dict:
    references = reference_dir()
    report_craft = references / "report-craft.md"
    report_types = references / "report-types.md"
    return {
        "calibration": calibration,
        "depth": depth,
        "publish": publish,
        "selected_types": [
            {
                "slug": t["slug"],
                "name": t["name"],
                "report_types_section": t["ref"],
                "sub_domains": t["sub_domains"],
                "preview": t["preview"],
            }
            for t in RESEARCH_TYPES
            if t["slug"] in types
        ],
        "agent_count": _planned_agent_count(types, depth),
        "max_concurrent_agents": MAX_CONCURRENT_AGENTS,
        "reference_paths": {
            "report_craft": str(report_craft),
            "report_types": str(report_types),
        },
        "instruction": (
            "For each sub-domain across the selected types, fan out one "
            "read-only subagent carrying the quality contract from "
            f"{report_craft} and the "
            "matching prompt skeleton from "
            f"{report_types}, filled in "
            "with these calibration facts. At 'quick' depth, run only the top "
            "2 sub-domains per type by relevance to the calibration facts; at "
            "'deep' depth, add a second adversarial verification pass on "
            "every finding (not just high-severity ones). Verify adversarially "
            f"per {report_craft}, then synthesize one report per its "
            "synthesis rules. Never write files, run mutating git commands, or "
            "deploy anything. The report goes to the scratchpad; ask "
            "explicitly before publishing it anywhere durable, even if "
            "--publish was passed — that flag only records the user's stated "
            "intent from the menu, it is not itself permission to skip the "
            "final confirmation."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Calibrate a repo and drive research-sweep type selection"
    )
    parser.add_argument(
        "--types", default=None,
        help="Comma-separated research type slugs to dispatch (dispatch mode)",
    )
    parser.add_argument(
        "--depth", default="standard", choices=DEPTHS,
        help="Sweep depth (default: standard)",
    )
    parser.add_argument(
        "--publish", action="store_true",
        help="Record that the user opted into publishing the report "
             "(final publish still requires explicit confirmation)",
    )
    parser.add_argument(
        "--project-path", default=None, metavar="PATH",
        help="Explicit project root to calibrate (default: cwd)",
    )
    args = parser.parse_args(argv)

    root = Path(args.project_path).resolve() if args.project_path else Path.cwd()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    calibration = run_calibration(root)

    if not args.types:
        print("RESEARCH_TYPES_NEEDED: " + json.dumps(_types_needed_payload(calibration)))
        return 0

    requested = [slug.strip() for slug in args.types.split(",") if slug.strip()]
    unknown = [slug for slug in requested if slug not in RESEARCH_TYPES_BY_SLUG]
    if unknown:
        print(f"Error: unknown research type slug(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Valid slugs: {', '.join(RESEARCH_TYPES_BY_SLUG)}", file=sys.stderr)
        return 1

    print("RESEARCH_SWEEP_PLAN: " + json.dumps(
        _sweep_plan_payload(calibration, requested, args.depth, args.publish)
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
