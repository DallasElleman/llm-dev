"""Read-time trust resolution for prior-session archive content.

The Phase 3 keystone (unified-git-state §4): `init-session` reads prior records
(handoff / notes / transcript) back into the next session's context, so a
trusted-but-compromised contributor could plant prompt-injection. This module
decides, per record, whether its author is trusted to **auto-load** — by `own`
identity or an explicit **allowlist** — so untrusted records are listed, not
injected.

The allowlist lives on the protected `main` branch (`.llm-dev/allowlist.json`),
NOT on the synced archive branch, so a contributor with archive-write cannot add
themselves. It is read via `git show origin/main:…` (the authoritative,
branch-protection-gated ref), falling back to local `main`, then to empty.

Caveat (documented, not hidden): identity is `git config user.name`, which is
self-asserted and spoofable. So this gate is a **soft, defense-in-depth control**
today; the always-on structural protection is that `init-session` lists
untrusted records instead of injecting them. Binding the name to a verified
signing key (signature verification) is the future hardening — the `signature`
field is the slot it plugs into.

Stdlib only; Python 3.12+. JSON and git output are untrusted input — every
function is fail-closed (any error → least trust) and never raises.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ALLOWLIST_PATH = ".llm-dev/allowlist.json"
ALLOWLIST_REF = "origin/main"
ALLOWLIST_FALLBACK_REF = "main"


def parse_allowlist(text: str) -> set[str]:
    """Parse allowlist JSON → set of trusted contributor names.

    Tolerant of unknown keys (schema can grow). Any malformed input — bad JSON,
    non-object root, missing/!list `contributors`, non-string items — yields an
    empty set. Never raises.
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return set()
    if not isinstance(data, dict):
        return set()
    contributors = data.get("contributors")
    if not isinstance(contributors, list):
        return set()
    # Drop empties/whitespace: an empty name would otherwise trust every record
    # with a missing/blank `contributor` (fail-open). Fail closed instead.
    return {c for c in contributors if isinstance(c, str) and c.strip()}


def decide(contributor: str, own: str, allowlist: set[str]) -> dict:
    """Classify a record's author. `own` always wins over the allowlist.

    Returns {author, trusted, basis: own|allowlist|untrusted, signature}. The
    `signature` slot is honest about the current state ("unverified") and is
    where future signature verification reports verified/unsigned/etc.
    """
    if contributor and contributor == own:
        basis = "own"
    elif contributor and contributor in allowlist:
        basis = "allowlist"
    else:
        basis = "untrusted"
    return {
        "author": contributor,
        "trusted": basis != "untrusted",
        "basis": basis,
        "signature": "unverified",
    }


def _git_show(ref_path: str, cwd: Path) -> str | None:
    """`git show <ref>:<path>` → content, or None on any failure (missing ref/
    path, not a repo, git absent). Never raises."""
    try:
        r = subprocess.run(
            ["git", "show", ref_path],
            cwd=str(cwd), capture_output=True, text=True,
        )
    except (OSError, ValueError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout


def load_allowlist(cwd: Path, *, ref: str = ALLOWLIST_REF,
                   path: str = ALLOWLIST_PATH,
                   fallback_ref: str = ALLOWLIST_FALLBACK_REF) -> set[str]:
    """Trusted contributors from the protected-`main` allowlist.

    Prefers the authoritative `origin/main` (what branch protection gated), then
    local `main`, then empty. No network fetch is forced — the local `origin/main`
    ref reflects the last fetch, and staleness fails safe (a newly-trusted author
    is merely listed-not-injected until the next fetch). Fail-closed: any failure
    → empty set → only `own` records auto-load.
    """
    text = _git_show(f"{ref}:{path}", cwd)
    if text is None and fallback_ref:
        text = _git_show(f"{fallback_ref}:{path}", cwd)
    if text is None:
        return set()
    return parse_allowlist(text)


def current_contributor(cwd: Path) -> str:
    """`git config user.name`, or "User" if unset/unavailable. The `own`
    identity. (Mirrors init-session.get_git_username; kept here so the trust
    logic is self-contained and unit-testable.)"""
    try:
        r = subprocess.run(
            ["git", "config", "user.name"],
            cwd=str(cwd), capture_output=True, text=True,
        )
    except (OSError, ValueError):
        return "User"
    name = r.stdout.strip()
    return name if (r.returncode == 0 and name) else "User"
