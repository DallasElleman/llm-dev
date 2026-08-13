"""Plugin-root resolution — shared by handlers that load bundled templates."""
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
