"""Tests for the desktop UI backend (card t_1f857d7f: D8, D9, D11).

B header (child_info), A's status cards + open-report count (list_children),
sidebar child map (session_tree), Abort / Detach from A's card and
deliver-on-click of open reports, plus the REST routes.
"""

from __future__ import annotations

import threading

import pytest

from spawn_session import delivery, desktop, lifecycle, tools
from spawn_session.handover import read
from tests.conftest import base_args, call_spawn
from tests.test_desktop import _REAL_THREAD, _load_plugin_api, _propose


@pytest.fixture
def parent_live(monkeypatch):
    """A's injection seam: ``state['live']`` toggles acceptance; accepted text lands in history."""
    state = {"live": True, "history": []}

    def inject(text, key):
        if not state["live"]:
            return False
        state["history"].append((key, text))
        return True

    monkeypatch.setattr(delivery, "_inject", inject)
    monkeypatch.setattr(delivery, "_history_contains",
                        lambda sid, marker: any(t.startswith(marker) for _, t in state["history"]))
    monkeypatch.setattr(delivery, "_start_thread", lambda target, *a: target(*a))
    monkeypatch.setattr(delivery, "_sleep", lambda s: None)
    monkeypatch.setattr(lifecycle, "_archive_session", lambda sid: {})
    return state


@pytest.fixture
def spawned(fake_gateway, desktop_parent, tmp_home, settings_override, parent_live):
    tools._lineage_ids = lambda sid: [sid]
    return call_spawn(base_args())


def _report(child_id: str) -> None:
    import json

    res = json.loads(tools.report_back_handler({"result": "done"}, session_id=child_id))
    assert res.get("ok") is True, res


class TestChildHeader:
    def test_child_gets_parent_link_task_and_context(self, spawned):
        info = desktop.child_info(spawned["child_session_id"])
        assert info["is_child"] is True
        assert info["parent_session_id"] == "ses-parent-1"
        assert info["parent_title"] == "Parent session"
        assert info["task"] == "Make the test deterministic."
        assert info["context"] == "It fails ~10% of runs."
        assert info["detached"] is False

    def test_non_child_has_no_header(self, spawned):
        assert desktop.child_info("ses-parent-1") == {"is_child": False}

    def test_detached_child_keeps_header_and_flag(self, spawned):
        desktop.detach_child({"handover_id": spawned["handover_id"], "confirm": True})
        info = desktop.child_info(spawned["child_session_id"])
        assert info["is_child"] is True and info["detached"] is True


class TestStatusCards:
    def test_running_child_listed_proposals_excluded(self, spawned):
        _propose()
        out = desktop.list_children("ses-parent-1")
        assert [c["handover_id"] for c in out["children"]] == [spawned["handover_id"]]
        assert out["children"][0]["status"] == "running"
        assert out["open_reports"] == 0

    def test_reported_while_parent_closed_counts_as_open(self, spawned, parent_live):
        parent_live["live"] = False
        _report(spawned["child_session_id"])
        out = desktop.list_children("ses-parent-1")
        assert out["children"][0]["status"] == "reported"
        assert out["open_reports"] == 1

    def test_child_does_not_list_its_parents_children(self, spawned, monkeypatch):
        # Hermes links B to A via parent_session_id, so B's lineage is [B, A];
        # B must not count as A (no status card for B inside B).
        child = spawned["child_session_id"]
        lineages = {child: [child, "ses-parent-1"], f"{child}-cont": [f"{child}-cont", child, "ses-parent-1"]}
        monkeypatch.setattr(tools, "_lineage_ids", lambda sid: lineages.get(sid, [sid]))
        _propose()
        for sid in (child, f"{child}-cont"):
            assert desktop.list_children(sid) == {"children": [], "open_reports": 0}
            assert desktop.list_proposals(sid) == []
        assert [c["handover_id"] for c in desktop.list_children("ses-parent-1")["children"]] == [spawned["handover_id"]]

    def test_delivered_after_report(self, spawned):
        _report(spawned["child_session_id"])
        c = desktop.list_children("ses-parent-1")["children"][0]
        assert c["status"] == "delivered" and c["reports"] == 1 and c["open_reports"] == 0


class TestOpenReports:
    def test_deliver_on_click(self, spawned, parent_live):
        parent_live["live"] = False
        _report(spawned["child_session_id"])
        parent_live["live"] = True  # A reopened
        res = desktop.deliver_open_reports({"session_id": "ses-parent-1"})
        assert res["queued"] == 1
        assert read(spawned["handover_path"]).status == "delivered"
        assert desktop.list_children("ses-parent-1")["open_reports"] == 0

    def test_pending_notice_counted_and_delivered(self, spawned, parent_live):
        parent_live["live"] = False
        desktop.detach_child({"handover_id": spawned["handover_id"], "confirm": True})
        assert desktop.list_children("ses-parent-1")["open_reports"] == 1
        parent_live["live"] = True
        res = desktop.deliver_open_reports({"session_id": "ses-parent-1"})
        assert res["notices"] == 1
        assert desktop.list_children("ses-parent-1")["open_reports"] == 0

    def test_parent_still_closed_keeps_report(self, spawned, parent_live):
        parent_live["live"] = False
        _report(spawned["child_session_id"])
        res = desktop.deliver_open_reports({"session_id": "ses-parent-1"})
        assert res["queued"] == 0
        assert read(spawned["handover_path"]).status == "reported"


class TestAbortDetach:
    def test_abort_from_card(self, spawned, events):
        res = desktop.abort_child({"handover_id": spawned["handover_id"]})
        assert res["status"] == "abandoned"
        h = read(spawned["handover_path"])
        assert h.status == "abandoned"
        assert ("child.status", {"handover_id": spawned["handover_id"], "status": "abandoned"}) in events

    def test_abort_after_report_refused(self, spawned):
        _report(spawned["child_session_id"])
        with pytest.raises(desktop.DesktopError):
            desktop.abort_child({"handover_id": spawned["handover_id"]})

    def test_detach_requires_confirm(self, spawned):
        with pytest.raises(desktop.DesktopError):
            desktop.detach_child({"handover_id": spawned["handover_id"]})
        assert read(spawned["handover_path"]).status == "running"

    def test_detach_retitles_and_keeps_nesting(self, spawned, fake_gateway):
        res = desktop.detach_child({"handover_id": spawned["handover_id"], "confirm": True})
        assert res["status"] == "detached"
        titles = [f["params"]["title"] for f in fake_gateway.frames if f["method"] == "session.title"]
        assert titles == ["↳ Detached: Fix flaky test"]
        tree = desktop.session_tree()["children"]
        assert tree[spawned["child_session_id"]]["parent_session_id"] == "ses-parent-1"
        assert tree[spawned["child_session_id"]]["status"] == "detached"
        with pytest.raises(desktop.DesktopError):  # irreversible
            desktop.detach_child({"handover_id": spawned["handover_id"], "confirm": True})


@pytest.fixture
def events():
    got: list = []
    tools._broadcast_event = lambda event, payload: got.append((event, payload))
    return got


class TestSidebarTree:
    def test_child_title_has_arrow_prefix(self, spawned, fake_gateway):
        create = [f for f in fake_gateway.frames if f["method"] == "session.create"][0]
        assert create["params"]["title"] == "↳ Fix flaky test"

    def test_tree_maps_both_child_ids_to_parent(self, spawned):
        tree = desktop.session_tree()["children"]
        assert set(tree) == {"ses-child-001", "rt-001"}
        assert {e["parent_session_id"] for e in tree.values()} == {"ses-parent-1"}


class TestRestUi:
    def test_routes(self, spawned, monkeypatch, parent_live):
        monkeypatch.setattr(threading, "Thread", _REAL_THREAD)
        api = _load_plugin_api()
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(api.router, prefix="/p")
        c = TestClient(app)
        hid, cid = spawned["handover_id"], spawned["child_session_id"]

        assert c.get("/p/child", params={"session_id": cid}).json()["is_child"] is True
        assert c.get("/p/children", params={"session_id": "ses-parent-1"}).json()["children"][0]["handover_id"] == hid
        assert cid in c.get("/p/tree").json()["children"]
        assert c.post("/p/detach", json={"handover_id": hid}).status_code == 400
        assert c.post("/p/abort", json={"handover_id": "hs_20990101_000000"}).status_code == 404
        assert c.post("/p/deliver", json={"session_id": "ses-parent-1"}).status_code == 200
        assert c.post("/p/abort", json={"handover_id": hid}).json()["status"] == "abandoned"
