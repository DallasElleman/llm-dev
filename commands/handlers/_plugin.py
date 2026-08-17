"""Plugin-root resolution — shared by handlers that load bundled templates."""
import json
import os
from pathlib import Path


def _looks_like_plugin(root: Path) -> bool:
    return (
        (root / ".claude-plugin" / "plugin.json").exists()
        or (root / ".grok-plugin" / "plugin.json").exists()
    )


def plugin_root() -> Path:
    """Resolve the llm-dev plugin root.

    Prefer an explicit env override (`GROK_PLUGIN_ROOT`, then
    `CLAUDE_PLUGIN_ROOT`) when it actually points at a plugin tree. Those
    variables are documented for hook children and are often unset in a
    tool-child shell, so fall back to this file's location
    (`commands/handlers/` → plugin root).
    """
    for key in ("GROK_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"):
        raw = os.environ.get(key)
        if not raw:
            continue
        root = Path(raw).resolve()
        if _looks_like_plugin(root):
            return root

    root = Path(__file__).resolve().parent.parent.parent
    if not _looks_like_plugin(root):
        raise ValueError(
            f"Plugin root does not contain .claude-plugin/plugin.json "
            f"or .grok-plugin/plugin.json: {root}"
        )
    return root


def _version_at(root: Path) -> str | None:
    """Read `version` from either manifest under `root`, or None. Never raises —
    a plugin manifest on disk is untrusted input."""
    for sub in (".claude-plugin", ".grok-plugin"):
        try:
            data = json.loads((root / sub / "plugin.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        version = data.get("version") if isinstance(data, dict) else None
        if isinstance(version, str) and version.strip():
            return version.strip()
    return None


def plugin_version() -> str | None:
    """The version of the plugin install these handlers are running from.

    Used as the manifest's provenance stamp: a session can init against one
    install and end against another (marketplace checkout vs. a versioned
    cache dir) with nothing noticing. Resolution follows the same
    verify-before-trusting discipline as research-sweep's `reference_dir()`:
    prefer the resolved plugin root, but only trust a root that actually
    yields a version, then fall back to this file's own tree.

    Returns None when no manifest is readable — callers stamp null and carry
    on rather than failing the run.
    """
    roots: list[Path] = []
    try:
        roots.append(plugin_root())
    except ValueError:
        pass
    own = Path(__file__).resolve().parent.parent.parent
    if own not in roots:
        roots.append(own)
    for root in roots:
        version = _version_at(root)
        if version:
            return version
    return None
