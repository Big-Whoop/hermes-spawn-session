"""Seed message for a child session (SPEC.md section 5).

B's first message is the handover body (Task + Context, without frontmatter)
plus the environment hints (Kanban board, worktree) and the report-back
obligation. The parent scope note from card t_6faaefc5: ``child_first_message()``
in :mod:`spawn_session.handover` returns Task + Context only; this module
assembles the full seed message.
"""

from __future__ import annotations

from .handover import Handover, child_first_message


def build_seed_message(
    h: Handover,
    *,
    kanban_board: str | None = None,
) -> str:
    """Full first message for the child session.

    ``kanban_board`` defaults to the handover frontmatter value (SPEC Q1: the
    board is passed by name, never mutated globally).
    """
    parts = [child_first_message(h)]
    worktree = h.meta.get("worktree")
    if isinstance(worktree, dict) and worktree.get("path"):
        parts.append(
            f"Working directory: git worktree {worktree['path']} (branch "
            f"{worktree.get('branch', '?')}). Commit your changes on that branch and list the "
            "branch and commits in your report."
        )
    board = kanban_board or h.meta.get("kanban_board")
    if isinstance(board, str) and board:
        parts.append(f"Kanban board for this task: `{board}` — pass `board={board}` to kanban tools.")
    parts.append(
        "When you are done, call the `report_back` tool with a structured result "
        "(result, changes, open items, artifacts) so it is delivered back to the parent session."
    )
    return "\n\n".join(parts)
