"""Tests for spawn_session.state (state index)."""

from __future__ import annotations

import json
from pathlib import Path

from spawn_session import state as state_mod
from tests.conftest import mk_handover


def _index(tmp_path: Path) -> state_mod.StateIndex:
    return state_mod.StateIndex(tmp_path / "state.json")


def test_register_and_lookup(tmp_path: Path):
    idx = _index(tmp_path)
    hp = tmp_path / "h.md"
    hp.write_text("placeholder", encoding="utf-8")
    idx.register_child(
        ["ses-a", "rt-a"], handover_path=hp, parent_session_id="ses-p", status="running"
    )
    assert idx.is_child("ses-a")
    assert idx.is_child("rt-a")
    assert not idx.is_child("ses-b")
    assert idx.handover_for("ses-a") == hp
    entry = idx.children["ses-a"]
    assert entry["parent_session_id"] == "ses-p"


def test_missing_handover_file_is_dropped(tmp_path: Path):
    idx = _index(tmp_path)
    gone = tmp_path / "gone.md"
    gone.write_text("x", encoding="utf-8")
    idx.register_child(["ses-a"], handover_path=gone, parent_session_id="p", status="running")
    gone.unlink()
    assert not idx.is_child("ses-a")
    assert idx.handover_for("ses-a") is None


def test_corrupt_index_treated_as_empty(tmp_path: Path):
    idx = _index(tmp_path)
    idx.path.write_text("{not json", encoding="utf-8")
    assert idx.children == {}


def test_remove_child(tmp_path: Path):
    idx = _index(tmp_path)
    hp = tmp_path / "h.md"
    hp.write_text("x", encoding="utf-8")
    idx.register_child(["ses-a", "rt-a"], handover_path=hp, parent_session_id="p", status="running")
    idx.remove_child("ses-a", "rt-a")
    assert not idx.is_child("ses-a") and not idx.is_child("rt-a")


def test_rebuild_from_handover_files(tmp_path: Path):
    base = tmp_path / "handovers"
    mk_handover(
        base, title="One", task="t", context="c",
        parent_session_id="ses-p", model="prov:m", status="running", child_session_id="ses-child-1",
    )
    idx = _index(tmp_path)
    n = idx.rebuild(sorted(base.glob("*.md")))
    assert n == 1
    assert idx.is_child("ses-child-1")


def test_running_agent_children_counts_files(tmp_path: Path):
    from spawn_session.handover import update_status

    base = tmp_path / "handovers"
    idx = _index(tmp_path)
    for i, (status, initiator) in enumerate(
        [("running", "agent"), ("running", "user"), ("delivered", "agent")]
    ):
        h = mk_handover(
            base, title=f"C{i}", task="t", context="c",
            parent_session_id="ses-p", model="prov:m", status="running", initiator=initiator,
        )
        assert h.path is not None
        if status != "running":
            update_status(h.path, "reported")
            if status == "delivered":
                update_status(h.path, "delivered")
        idx.register_child(
            [f"ses-{i}"], handover_path=h.path, parent_session_id="ses-p", status=status
        )
    # Only running + agent counts: exactly 1.
    assert state_mod.running_agent_children(idx, "ses-p") == 1
    # Other parents are not counted.
    assert state_mod.running_agent_children(idx, "ses-other") == 0


def test_load_index_rebuilds_when_empty(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HERMES_HOME", str(home))
    fallback = home / "spawn-session" / "handovers"
    h = mk_handover(
        fallback, title="F", task="t", context="c",
        parent_session_id="ses-p", model="prov:m", status="running", child_session_id="ses-f",
    )
    idx = state_mod.load_index()
    assert idx.is_child("ses-f")
    # The index file now exists on disk.
    assert idx.path.exists()
    data = json.loads(idx.path.read_text(encoding="utf-8"))
    assert "ses-f" in data["children"]
