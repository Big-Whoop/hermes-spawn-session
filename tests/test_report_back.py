"""Unit tests for report-back, delivery queueing/persistence, abort and detach
(SPEC 4.2/4.3/6, decisions D4/D8/D11; acceptance tests AT4.x / AT7.x).

Injection into the parent and the parent's history are faked through the
``delivery`` seams; gateway RPCs (archive/title) through the lifecycle seams.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from spawn_session import commands, delivery, lifecycle, state as state_mod, tools
from spawn_session import worktree as wt_mod
from spawn_session.handover import read
from tests.conftest import mk_handover


class FakeParent:
    """Parent A: records injected messages; ``live`` toggles acceptance;
    ``persist`` controls whether accepted messages reach A's history."""

    def __init__(self) -> None:
        self.live = True
        self.persist = True
        self.injected: list[tuple[str, str]] = []
        self.history: dict[str, list[str]] = {}
        self.threads: list[tuple] = []

    def inject(self, text: str, session_key: str) -> bool:
        if not self.live:
            return False
        self.injected.append((session_key, text))
        if self.persist:
            self.history.setdefault(session_key, []).append(text)
        return True

    def history_contains(self, session_id: str, marker: str) -> bool:
        return any(m.startswith(marker) for m in self.history.get(session_id, []))

    def start_thread(self, target, *args) -> None:
        self.threads.append((target, args))
        target(*args)  # inline: deterministic


@pytest.fixture
def parent(monkeypatch):
    fp = FakeParent()
    monkeypatch.setattr(delivery, "_inject", fp.inject)
    monkeypatch.setattr(delivery, "_history_contains", fp.history_contains)
    monkeypatch.setattr(delivery, "_start_thread", fp.start_thread)
    monkeypatch.setattr(delivery, "_sleep", lambda s: None)
    return fp


@pytest.fixture
def gw_calls(monkeypatch):
    calls: dict[str, list] = {"archive": [], "title": []}
    monkeypatch.setattr(lifecycle, "_archive_session", lambda sid: calls["archive"].append(sid) or {})
    monkeypatch.setattr(lifecycle, "_set_title", lambda sid, t: calls["title"].append((sid, t)) or {})
    return calls


@pytest.fixture
def child(tmp_path, tmp_home):
    """A running child B ('ses-b') of parent 'ses-a', registered in the index."""
    base = tmp_path / "proj" / ".hermes" / "handovers"
    h = mk_handover(base, title="Fix flaky test", task="t", context="c",
                    parent_session_id="ses-a", child_session_id="ses-b",
                    model="custom:cpa:x", status="running")
    state_mod.load_index().register_child(["ses-b", "rt-b"], handover_path=h.path,
                                          parent_session_id="ses-a", status="running")
    tools._lineage_ids = lambda sid: [sid]
    return h


def call_report(args: dict[str, Any], session_id: str = "ses-b") -> dict[str, Any]:
    return json.loads(tools.report_back_handler(args, session_id=session_id))


FULL = {
    "result": "Test is deterministic now.",
    "changes": ["seeded RNG in conftest"],
    "open_items": ["CI matrix not rerun"],
    "artifacts": [{"kind": "commit", "value": "abc123"}, {"kind": "path", "value": "tests/x.py"}],
}


# --------------------------------------------------------------------------- report generation (AT4.1)


class TestReportGeneration:
    def test_structured_sections(self, child):
        body = lifecycle.build_report(FULL)
        assert body.startswith("## Result\nTest is deterministic now.")
        assert "## Changes\n- seeded RNG in conftest" in body
        assert "## Open items\n- CI matrix not rerun" in body
        assert "## Artifacts\n- commit: abc123\n- path: tests/x.py" in body

    def test_minimal_report_fills_dashes(self):
        body = lifecycle.build_report({"result": "done"})
        assert "## Changes\n-" in body and "## Artifacts\n-" in body

    def test_worktree_branch_added_as_artifact(self, child):
        h = read(child.path)
        h.meta["worktree"] = {"path": "/x/.worktrees/spawn-a", "branch": "spawn/a"}
        assert "- branch: spawn/a" in lifecycle.build_report({"result": "r"}, h)

    @pytest.mark.parametrize("bad", [
        {"result": ""},
        {"result": "r", "changes": "not a list"},
        {"result": "r", "artifacts": [{"kind": "file", "value": "x"}]},
        {"result": "r", "artifacts": [{"kind": "path", "value": ""}]},
    ])
    def test_invalid_arguments(self, bad):
        with pytest.raises(lifecycle.LifecycleError):
            lifecycle.build_report(bad)


# --------------------------------------------------------------------------- report_back tool + delivery


class TestReportBack:
    def test_appends_report_and_delivers(self, child, parent):
        res = call_report(FULL)
        assert res["ok"] is True and res["delivery"] == "queued"
        h = read(child.path)
        assert len(h.reports) == 1 and "Test is deterministic now." in h.reports[0]
        # AT4.2: injected into A (durable id), marker first, then confirmed -> delivered.
        ((key, text),) = parent.injected
        assert key == "ses-a"
        assert text.startswith(f"[spawn-session report: Fix flaky test ({h.handover_id})]")
        assert h.status == "delivered"
        assert [e["to"] for e in h.meta["history"]] == ["reported", "delivered"]
        assert state_mod.load_index().children["ses-b"]["status"] == "delivered"

    def test_parent_not_live_keeps_reported(self, child, parent):
        # AT4.4 / D8: A closed -> status stays reported (persisted for later).
        parent.live = False
        res = call_report(FULL)
        assert res["ok"] is True and res["delivery"] == "pending"
        assert read(child.path).status == "reported"
        assert parent.injected == []

    def test_accepted_but_unconfirmed_stays_reported(self, child, parent):
        # AT4.3: A mid-turn -> accepted to the queue, not yet in history.
        parent.persist = False
        call_report(FULL)
        assert len(parent.injected) == 1
        assert read(child.path).status == "reported"  # 'delivered' only once visible

    def test_deliver_pending_after_reopen(self, child, parent):
        parent.live = False
        call_report(FULL)
        parent.live = True
        out = commands.action_deliver_pending("ses-a")
        assert out["reports"][0]["queued"] is True
        assert read(child.path).status == "delivered"

    def test_redelivery_is_idempotent(self, child, parent):
        parent.persist = False
        call_report(FULL)
        parent.history["ses-a"] = [parent.injected[0][1]]  # turn finished later
        commands.action_deliver_pending("ses-a")
        assert len(parent.injected) == 1  # not injected twice
        assert read(child.path).status == "delivered"

    def test_follow_up_report(self, child, parent):
        # AT4.6
        call_report(FULL)
        res = call_report({"result": "Also fixed the second flake."})
        assert res["report_number"] == 2
        h = read(child.path)
        assert len(h.reports) == 2 and h.status == "delivered"
        assert parent.injected[1][1].startswith(f"[spawn-session report: Fix flaky test ({h.handover_id}, report 2)]")
        assert "# Report (2)" in Path(child.path).read_text()

    def test_follow_up_while_still_reported(self, child, parent):
        parent.live = False
        call_report(FULL)
        res = call_report({"result": "more"})
        assert res["ok"] and read(child.path).status == "reported"

    def test_refused_outside_child(self, child, parent):
        res = call_report(FULL, session_id="ses-a")
        assert res["ok"] is False and "only available in a session spawned" in res["error"]

    def test_works_from_compression_continuation(self, child, parent):
        tools._lineage_ids = lambda sid: [sid, "ses-b", "ses-a"]
        assert call_report(FULL, session_id="ses-b-cont")["ok"] is True

    def test_refused_after_detach(self, child, parent, gw_calls):
        lifecycle.detach(Path(child.path))
        res = call_report(FULL)
        assert res["ok"] is False and "detached" in res["error"]


# --------------------------------------------------------------------------- history check (real sqlite)


def test_history_contains_follows_continuations(tmp_home):
    import sqlite3

    db = tmp_home / "state.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE sessions (id TEXT, parent_session_id TEXT)")
    conn.execute("CREATE TABLE messages (session_id TEXT, role TEXT, content TEXT)")
    conn.executemany("INSERT INTO sessions VALUES (?, ?)", [("a", None), ("a2", "a")])
    conn.execute("INSERT INTO messages VALUES ('a2', 'user', '[spawn-session report: X (hs_1)]\nbody')")
    conn.commit()
    conn.close()
    assert delivery._default_history_contains("a", "[spawn-session report: X (hs_1)]")
    assert not delivery._default_history_contains("a", "[spawn-session report: X (hs_2)]")


# --------------------------------------------------------------------------- abandon (AT7.1 / AT7.2)


def _git(cwd: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True, text=True,
                          env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                               "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin"}).stdout.strip()


@pytest.fixture
def repo_with_worktree(tmp_path):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", str(remote))
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    (repo / "a.txt").write_text("a\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "init")
    _git(repo, "remote", "add", "origin", str(remote))
    wt = wt_mod.create_worktree(repo, "fix-flaky-test")
    return repo, remote, wt


class TestAbandon:
    def test_abandon_notifies_and_archives(self, child, parent, gw_calls):
        res = lifecycle.abandon(Path(child.path), reason="wrong approach")
        assert res["status"] == "abandoned" and res["parent_notified"] is True
        assert gw_calls["archive"] == ["ses-b"]  # archived, never deleted
        (_, text), = parent.injected
        assert text.startswith("[spawn-session aborted: Fix flaky test")
        assert "Reason: wrong approach" in text
        assert read(child.path).status == "abandoned"
        # Still indexed: the D10 ban keeps applying.
        assert state_mod.load_index().is_child("ses-b")

    def test_abort_notice_persisted_when_parent_closed(self, child, parent, gw_calls):
        parent.live = False
        res = lifecycle.abandon(Path(child.path))
        assert res["parent_notified"] is False
        assert read(child.path).meta["pending_notices"]
        parent.live = True
        out = commands.action_deliver_pending("ses-a")
        assert out["notices"] == 1
        assert "pending_notices" not in read(child.path).meta

    def test_dirty_worktree_banked_and_kept(self, child, parent, gw_calls, repo_with_worktree):
        repo, remote, wt = repo_with_worktree
        h = read(child.path)
        h.meta["worktree"] = {"path": wt.path, "branch": wt.branch}
        from spawn_session.handover import write

        write(h)
        (Path(wt.path) / "wip.txt").write_text("unsaved work\n")
        res = lifecycle.abandon(Path(child.path), reason="stop")
        bank = res["worktree"]["bank"]
        assert bank["commit"] and bank["pushed"] is True
        assert _git(remote, "rev-parse", wt.branch) == bank["commit"]
        assert Path(wt.path).is_dir()  # never auto-deleted
        assert "Remove worktree + branch?" in res["question"]
        assert read(child.path).meta["worktree_cleanup"] == "awaiting_user"

        # User answers "no": kept. A second answer is refused.
        assert lifecycle.cleanup_worktree(Path(child.path), confirm=False)["removed"] is False
        with pytest.raises(lifecycle.LifecycleError):
            lifecycle.cleanup_worktree(Path(child.path), confirm=True)
        assert Path(wt.path).is_dir()

    def test_cleanup_yes_removes(self, child, parent, gw_calls, repo_with_worktree):
        repo, remote, wt = repo_with_worktree
        h = read(child.path)
        h.meta["worktree"] = {"path": wt.path, "branch": wt.branch}
        from spawn_session.handover import write

        write(h)
        lifecycle.abandon(Path(child.path))
        out = commands.cmd_spawn_cleanup(f"{h.handover_id} yes")
        assert "Removed worktree" in out
        assert not Path(wt.path).exists()
        assert wt.branch not in _git(repo, "branch", "--list")

    def test_cannot_abandon_reported(self, child, parent, gw_calls):
        call_report(FULL)
        with pytest.raises(lifecycle.LifecycleError):
            lifecycle.abandon(Path(child.path))

    def test_decline_proposal(self, tmp_path, tmp_home, parent, gw_calls):
        h = mk_handover(tmp_path / "h", title="P", task="t", context="c", parent_session_id="ses-a",
                        model="custom:cpa:x", status="proposed")
        assert lifecycle.abandon(Path(h.path))["status"] == "abandoned"
        assert parent.injected == [] and gw_calls["archive"] == []


# --------------------------------------------------------------------------- detach (AT7.3)


class TestDetach:
    def test_detach(self, child, parent, gw_calls):
        res = lifecycle.detach(Path(child.path))
        assert res["status"] == "detached"
        assert gw_calls["title"] == [("ses-b", "\u21b3 Detached: Fix flaky test")]
        (_, text), = parent.injected
        assert "[spawn-session detached: Fix flaky test" in text and "\n" not in text
        assert state_mod.load_index().is_child("ses-b")  # D10 ban still applies

    def test_irreversible(self, child, parent, gw_calls):
        lifecycle.detach(Path(child.path))
        with pytest.raises(lifecycle.LifecycleError):
            lifecycle.detach(Path(child.path))
        with pytest.raises(lifecycle.LifecycleError):
            lifecycle.abandon(Path(child.path))

    def test_detach_after_delivered(self, child, parent, gw_calls):
        call_report(FULL)
        assert lifecycle.detach(Path(child.path))["status"] == "detached"


# --------------------------------------------------------------------------- slash commands (AT4.5)


@pytest.fixture
def in_child(monkeypatch):
    monkeypatch.setattr(commands, "_current_session", lambda: "ses-b")
    monkeypatch.setattr(commands, "_lineage_ids", lambda sid: [sid])


class TestCommands:
    def test_report_command_injects_prompt_into_b(self, child, parent, in_child):
        out = commands.cmd_report("mention the CI run")
        assert "Report requested" in out
        ((key, text),) = parent.injected
        assert key == "ses-b" and "report_back" in text and "mention the CI run" in text

    def test_commands_refused_outside_child(self, child, parent, monkeypatch):
        monkeypatch.setattr(commands, "_current_session", lambda: "ses-a")
        monkeypatch.setattr(commands, "_lineage_ids", lambda sid: [sid])
        assert "only available in a session spawned" in commands.cmd_report("")
        assert "only available in a session spawned" in commands.cmd_abandon("")

    def test_abandon_command(self, child, parent, gw_calls, in_child):
        out = commands.cmd_abandon("not needed")
        assert "Abandoned" in out and read(child.path).status == "abandoned"

    def test_detach_requires_confirm(self, child, parent, gw_calls, in_child):
        assert "irreversible" in commands.cmd_detach("")
        assert read(child.path).status == "running"
        assert "Detached" in commands.cmd_detach("confirm")
        assert read(child.path).status == "detached"

    def test_backend_actions_by_handover_id(self, child, parent, gw_calls):
        assert commands.action_detach(child.handover_id)["status"] == "detached"
        assert json.loads(commands.as_json(commands.action_abandon, child.handover_id))["ok"] is False
