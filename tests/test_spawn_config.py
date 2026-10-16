"""Tests for spawn_session.config."""

from __future__ import annotations

from spawn_session.config import Settings


def test_defaults():
    s = Settings.from_mapping(None)
    assert s.max_children == 3
    assert s.handover_dir == ".hermes/handovers"
    assert s.worktree_dir == ".worktrees"
    assert s.branch_prefix == "spawn/"
    assert s.title_prefix == "\u21b3 "
    assert s.cost_rank == {}


def test_explicit_values():
    s = Settings.from_mapping(
        {
            "max_children": 5,
            "handover_dir": "custom/handovers",
            "worktree_dir": "wt",
            "branch_prefix": "sp/",
            "cost_rank": {"a:b": 1, "c:d": 2},
        }
    )
    assert s.max_children == 5
    assert s.handover_dir == "custom/handovers"
    assert s.branch_prefix == "sp/"
    assert s.cost_rank == {"a:b": 1, "c:d": 2}


def test_bad_types_fall_back_to_defaults():
    s = Settings.from_mapping({"max_children": "many", "cost_rank": "nope"})
    assert s.max_children == 3
    assert s.cost_rank == {}


def test_bool_is_not_a_valid_int():
    s = Settings.from_mapping({"max_children": True})
    assert s.max_children == 3


def test_negative_max_children_rejected():
    s = Settings.from_mapping({"max_children": -1})
    assert s.max_children == 3


def test_unknown_keys_ignored():
    s = Settings.from_mapping({"bogus": 1, "max_children": 4})
    assert s.max_children == 4
