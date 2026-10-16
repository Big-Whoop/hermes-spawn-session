"""Tests for the desktop service layer (card t_8fdde1ac: ⌘K spawn + confirmation card).

Covers D2 (user spawn via ⌘K), D3 (proposal card Start/Edit/Dismiss), D6
(default = A's model/effort; edits honoured), D7 (worktree only on Start),
D10 (no spawn from a child session) and the REST mapping in
``dashboard/plugin_api.py``.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from spawn_session import desktop, tools
from spawn_session import worktree as wt_mod
from spawn_session.handover import read
from tests.conftest import base_args, call_spawn


_REAL_THREAD = threading.Thread


def create_frames(gw) -> list[dict[str, Any]]:
    return [f for f in gw.frames if f["method"] == "session.create"]


@pytest.fixture
def events():
    got: list[tuple[str, dict]] = []
    tools._broadcast_event = lambda event, payload: got.append((event, payload))
    return got


def _propose(**overrides: Any) -> dict[str, Any]:
    result = call_spawn(base_args(initiation="own_initiative", **overrides))
    assert result["ok"] is True and result["status"] == "proposed"
    return result


# --------------------------------------------------------------------------- defaults


class TestDefaults:
    def test_returns_parent_model_and_effort(self, desktop_parent, tmp_home):
        d = desktop.spawn_defaults("ses-parent-1")
        assert d["model"] == "custom:cpa:claude-opus-5-5"
        assert d["effort"] == "low"
        assert d["is_child"] is False
        assert d["can_spawn"] is True

    def test_child_session_cannot_spawn(self, fake_gateway, desktop_parent, tmp_home, settings_override):
        child = call_spawn(base_args())["child_session_id"]
        d = desktop.spawn_defaults(child)
        assert d["is_child"] is True
        assert d["can_spawn"] is False

    def test_missing_session_id_rejected(self, desktop_parent, tmp_home):
        with pytest.raises(desktop.DesktopError):
            desktop.spawn_defaults("")


# --------------------------------------------------------------------------- ⌘K user spawn


class TestUserSpawn:
    def test_spawn_uses_parent_model_by_default(
        self, fake_gateway, desktop_parent, tmp_home, settings_override, events
    ):
        res = desktop.user_spawn({"session_id": "ses-parent-1", "title": "Research X", "task": "Find Y"})
        assert res["ok"] is True and res["status"] == "running"
        h = read(res["handover_path"])
        assert h.meta["initiator"] == "user"
        assert h.meta["initiation"] == "user_asked"
        assert h.meta["model"] == "custom:cpa:claude-opus-5-5"
        assert h.meta["effort"] == "low"
        frame = create_frames(fake_gateway)[0]["params"]
        assert frame["model"] == "claude-opus-5-5"
        assert frame["provider"] == "custom:cpa"
        assert frame["parent_session_id"] == "ses-parent-1"
        assert frame["title"].endswith("Research X")
        created = [p for e, p in events if e == "child.created"]
        assert created and created[0]["initiator"] == "user"

    def test_model_and_effort_override(self, fake_gateway, desktop_parent, tmp_home, settings_override):
        res = desktop.user_spawn({
            "session_id": "ses-parent-1", "title": "T", "task": "do",
            "model": "openrouter:anthropic/claude-sonnet-4.6", "effort": "high",
        })
        frame = create_frames(fake_gateway)[0]["params"]
        assert frame["provider"] == "openrouter"
        assert frame["model"] == "anthropic/claude-sonnet-4.6"
        assert frame["reasoning_effort"] == "high"
        assert read(res["handover_path"]).meta["effort"] == "high"

    def test_more_expensive_model_starts_without_proposal(
        self, fake_gateway, desktop_parent, tmp_home, settings_override
    ):
        # D6: the confirmation rule targets the AGENT; the user is the confirmer.
        res = desktop.user_spawn({"session_id": "ses-parent-1", "title": "T", "task": "do", "model": "x:unknown"})
        assert res["status"] == "running"

    def test_user_spawns_are_not_capped(self, fake_gateway, desktop_parent, tmp_home, settings_override):
        for i in range(settings_override.max_children + 2):
            res = desktop.user_spawn({"session_id": "ses-parent-1", "title": f"T{i}", "task": "do"})
            assert res["status"] == "running"
        assert len(create_frames(fake_gateway)) == settings_override.max_children + 2

    def test_bare_model_rejected(self, fake_gateway, desktop_parent, tmp_home, settings_override):
        with pytest.raises(desktop.DesktopError):
            desktop.user_spawn({"session_id": "ses-parent-1", "title": "T", "task": "do", "model": "gpt-5"})
        assert create_frames(fake_gateway) == []

    @pytest.mark.parametrize("missing", ["title", "task"])
    def test_required_fields(self, fake_gateway, desktop_parent, tmp_home, settings_override, missing):
        body = {"session_id": "ses-parent-1", "title": "T", "task": "do"}
        body[missing] = "  "
        with pytest.raises(desktop.DesktopError):
            desktop.user_spawn(body)

    def test_bad_effort_rejected(self, fake_gateway, desktop_parent, tmp_home, settings_override):
        with pytest.raises(desktop.DesktopError):
            desktop.user_spawn({"session_id": "ses-parent-1", "title": "T", "task": "do", "effort": "max"})

    def test_refused_inside_child(self, fake_gateway, desktop_parent, tmp_home, settings_override):
        child = call_spawn(base_args())["child_session_id"]
        with pytest.raises(desktop.DesktopError, match="one level only"):
            desktop.user_spawn({"session_id": child, "title": "T", "task": "do"})

    def test_refused_on_non_desktop(self, fake_gateway, tmp_path, tmp_home, settings_override, monkeypatch):
        from tests.conftest import make_parent

        p = make_parent(source="cli", cwd=str(tmp_path))
        monkeypatch.setattr(tools, "_resolve_parent", lambda sid: p)
        with pytest.raises(desktop.DesktopError, match="only available in Hermes Desktop"):
            desktop.user_spawn({"session_id": "ses-parent-1", "title": "T", "task": "do"})


# --------------------------------------------------------------------------- proposal cards


class TestProposals:
    def test_proposal_listed_with_card_fields(
        self, fake_gateway, desktop_parent, tmp_home, settings_override, events
    ):
        r = _propose()
        props = desktop.list_proposals("ses-parent-1")
        assert [p["handover_id"] for p in props] == [r["handover_id"]]
        p = props[0]
        assert p["title"] == "Fix flaky test"
        assert p["task"] == "Make the test deterministic."
        assert p["context"] == "It fails ~10% of runs."
        assert p["model"] == "custom:cpa:claude-opus-5-5"
        assert any("own initiative" in reason for reason in p["reasons"])
        # The broadcast carries the card fields too.
        proposed = [pl for e, pl in events if e == "child.proposed"][0]
        assert proposed["task"] == "Make the test deterministic."
        assert proposed["model"] == "custom:cpa:claude-opus-5-5"

    def test_other_parents_proposals_not_listed(self, fake_gateway, desktop_parent, tmp_home, settings_override):
        _propose()
        assert desktop.list_proposals("ses-someone-else") == []

    def test_start_creates_child(self, fake_gateway, desktop_parent, tmp_home, settings_override):
        r = _propose()
        res = desktop.confirm_proposal({"handover_id": r["handover_id"]})
        assert res["status"] == "running"
        assert res["child_session_id"] == "ses-child-001"
        h = read(r["handover_path"])
        assert h.status == "running"
        assert h.meta["child_session_id"] == "ses-child-001"
        assert h.meta["history"][-1]["by"] == "user"
        assert desktop.list_proposals("ses-parent-1") == []

    def test_edit_then_start_applies_edits(self, fake_gateway, desktop_parent, tmp_home, settings_override):
        r = _propose()
        desktop.confirm_proposal({
            "handover_id": r["handover_id"], "title": "Renamed", "task": "New task",
            "context": "New ctx", "model": "openrouter:m1", "effort": "xhigh",
        })
        h = read(r["handover_path"])
        assert (h.title, h.task, h.context) == ("Renamed", "New task", "New ctx")
        assert h.meta["model"] == "openrouter:m1" and h.meta["provider"] == "openrouter"
        frame = create_frames(fake_gateway)[0]["params"]
        assert frame["title"].endswith("Renamed")
        assert (frame["provider"], frame["model"], frame["reasoning_effort"]) == ("openrouter", "m1", "xhigh")

    def test_dismiss_abandons_without_session(self, fake_gateway, desktop_parent, tmp_home, settings_override, events):
        r = _propose()
        res = desktop.dismiss_proposal({"handover_id": r["handover_id"]})
        assert res["status"] == "abandoned"
        assert read(r["handover_path"]).status == "abandoned"
        assert create_frames(fake_gateway) == []
        assert any(e == "child.dismissed" for e, _ in events)
        assert desktop.list_proposals("ses-parent-1") == []

    def test_start_twice_refused(self, fake_gateway, desktop_parent, tmp_home, settings_override):
        r = _propose()
        desktop.confirm_proposal({"handover_id": r["handover_id"]})
        with pytest.raises(desktop.DesktopError, match="not proposed"):
            desktop.confirm_proposal({"handover_id": r["handover_id"]})
        assert len(create_frames(fake_gateway)) == 1

    def test_dismiss_after_start_refused(self, fake_gateway, desktop_parent, tmp_home, settings_override):
        r = _propose()
        desktop.confirm_proposal({"handover_id": r["handover_id"]})
        with pytest.raises(desktop.DesktopError):
            desktop.dismiss_proposal({"handover_id": r["handover_id"]})

    def test_unknown_handover(self, desktop_parent, tmp_home):
        with pytest.raises(desktop.NotFound):
            desktop.confirm_proposal({"handover_id": "hs_20990101_000000"})
        with pytest.raises(desktop.DesktopError):
            desktop.dismiss_proposal({"handover_id": "../etc/passwd"})

    def test_worktree_created_only_on_start(
        self, fake_gateway, desktop_parent, tmp_home, settings_override, monkeypatch
    ):
        calls: list[tuple] = []

        def fake_wt(repo_root, slug, **kw):
            calls.append((str(repo_root), slug))
            return wt_mod.Worktree(path=f"{repo_root}/.worktrees/spawn-{slug}", branch=f"spawn/{slug}")

        monkeypatch.setattr(tools, "_create_worktree", fake_wt)
        r = _propose(worktree=True)
        assert calls == []
        desktop.confirm_proposal({"handover_id": r["handover_id"]})
        assert len(calls) == 1
        h = read(r["handover_path"])
        assert h.meta["worktree"]["branch"] == "spawn/fix-flaky-test"
        assert create_frames(fake_gateway)[0]["params"]["cwd"].endswith("spawn-fix-flaky-test")

    def test_gateway_failure_on_start_abandons(self, fake_gateway, desktop_parent, tmp_home, settings_override):
        from spawn_session import gateway

        r = _propose()
        fake_gateway.fail_methods.add("session.create")
        with pytest.raises(gateway.GatewayError):
            desktop.confirm_proposal({"handover_id": r["handover_id"]})
        assert read(r["handover_path"]).status == "abandoned"


# --------------------------------------------------------------------------- REST mapping


def _load_plugin_api():
    pytest.importorskip("fastapi")
    path = Path(__file__).resolve().parent.parent / "dashboard" / "plugin_api.py"
    spec = importlib.util.spec_from_file_location("spawn_session_plugin_api_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestRest:
    def test_routes_and_status_codes(
        self, fake_gateway, desktop_parent, tmp_home, settings_override, monkeypatch
    ):
        # fake_gateway swaps threading.Thread globally for an inline runner;
        # TestClient/anyio need real threads, so restore the original class.
        monkeypatch.setattr(threading, "Thread", _REAL_THREAD)
        api = _load_plugin_api()
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.include_router(api.router, prefix="/api/plugins/spawn-session")
        c = TestClient(app)
        base = "/api/plugins/spawn-session"

        assert c.get(f"{base}/defaults", params={"session_id": "ses-parent-1"}).json()["can_spawn"] is True
        ok = c.post(f"{base}/spawn", json={"session_id": "ses-parent-1", "title": "T", "task": "do"})
        assert ok.status_code == 200 and ok.json()["status"] == "running"
        bad = c.post(f"{base}/spawn", json={"session_id": "ses-parent-1", "title": "", "task": "do"})
        assert bad.status_code == 400

        r = _propose()
        props = c.get(f"{base}/proposals", params={"session_id": "ses-parent-1"}).json()["proposals"]
        assert [p["handover_id"] for p in props] == [r["handover_id"]]
        assert c.post(f"{base}/confirm", json={"handover_id": "hs_20990101_000000"}).status_code == 404
        assert c.post(f"{base}/dismiss", json={"handover_id": r["handover_id"]}).json()["status"] == "abandoned"
