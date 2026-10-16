"""Tests for spawn_session.seed (child first message)."""

from __future__ import annotations

from pathlib import Path

from spawn_session.handover import create as handover_create
from spawn_session.seed import build_seed_message


def _h(base: Path, **extra):
    return handover_create(
        base, title="T", task="Do the thing.", context="Background here.",
        parent_session_id="ses-p", model="prov:m", status="running", **extra,
    )


def test_seed_contains_task_context_and_report_obligation(tmp_path: Path):
    h = _h(tmp_path)
    text = build_seed_message(h)
    assert "# Task" in text
    assert "Do the thing." in text
    assert "# Context" in text
    assert "Background here." in text
    assert "report_back" in text
    # No frontmatter leaks into the seed.
    assert "handover_id" not in text
    assert "---" not in text.split("# Task")[0]


def test_seed_includes_worktree_hint(tmp_path: Path):
    h = _h(tmp_path, worktree={"path": "/w/.worktrees/spawn-x", "branch": "spawn/x"})
    text = build_seed_message(h)
    assert "/w/.worktrees/spawn-x" in text
    assert "spawn/x" in text


def test_seed_includes_kanban_board_from_meta(tmp_path: Path):
    h = _h(tmp_path, kanban_board="my-board")
    text = build_seed_message(h)
    assert "`board=my-board`" in text


def test_explicit_board_overrides_meta(tmp_path: Path):
    h = _h(tmp_path, kanban_board="meta-board")
    text = build_seed_message(h, kanban_board="explicit-board")
    assert "explicit-board" in text
    assert "meta-board" not in text


def test_no_hints_when_absent(tmp_path: Path):
    h = _h(tmp_path)
    text = build_seed_message(h)
    assert "Kanban board for this task" not in text
    assert "git worktree" not in text
