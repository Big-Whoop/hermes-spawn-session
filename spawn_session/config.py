"""Plugin settings for spawn-session (SPEC.md section 8).

All keys live under ``plugins.entries.spawn-session`` in the profile config and
are read through ``PluginContext.get_config`` (which already handles the
``settings``/legacy-``config`` subtrees). :func:`from_mapping` accepts any
mapping so unit tests can inject settings without a live plugin context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

DEFAULT_MAX_CHILDREN = 3
DEFAULT_HANDOVER_DIR = ".hermes/handovers"
DEFAULT_WORKTREE_DIR = ".worktrees"
DEFAULT_BRANCH_PREFIX = "spawn/"
DEFAULT_TITLE_PREFIX = "\u21b3 "  # ↳
DEFAULT_DETACHED_PREFIX = "Detached: "


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the plugin settings."""

    max_children: int = DEFAULT_MAX_CHILDREN
    handover_dir: str = DEFAULT_HANDOVER_DIR
    worktree_dir: str = DEFAULT_WORKTREE_DIR
    branch_prefix: str = DEFAULT_BRANCH_PREFIX
    title_prefix: str = DEFAULT_TITLE_PREFIX
    detached_prefix: str = DEFAULT_DETACHED_PREFIX
    cost_rank: Mapping[str, int] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "Settings":
        """Build settings from a ``plugins.entries.spawn-session`` mapping.

        Unknown keys are ignored; wrong types fall back to the default so a
        broken config can never take the tool down (fail open for settings,
        fail closed for decisions).
        """
        raw = dict(raw or {})
        max_children = raw.get("max_children", DEFAULT_MAX_CHILDREN)
        if not isinstance(max_children, int) or isinstance(max_children, bool) or max_children < 0:
            max_children = DEFAULT_MAX_CHILDREN
        cost_rank = raw.get("cost_rank", {})
        if not isinstance(cost_rank, Mapping):
            cost_rank = {}
        cost_rank = {str(k): int(v) for k, v in cost_rank.items() if _is_int(v)}
        values = {
            "max_children": max_children,
            "handover_dir": _str(raw.get("handover_dir"), DEFAULT_HANDOVER_DIR),
            "worktree_dir": _str(raw.get("worktree_dir"), DEFAULT_WORKTREE_DIR),
            "branch_prefix": _str(raw.get("branch_prefix"), DEFAULT_BRANCH_PREFIX),
            "title_prefix": _str(raw.get("title_prefix"), DEFAULT_TITLE_PREFIX),
            "detached_prefix": _str(raw.get("detached_prefix"), DEFAULT_DETACHED_PREFIX),
            "cost_rank": cost_rank,
        }
        return cls(**values)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _str(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default
