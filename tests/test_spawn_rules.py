"""Unit tests for the spawn_session rules (SPEC section 4.1 / decisions D3/D6/D7/D10/D12/D13).

Each acceptance criterion of Card 2 (AT2.x) plus the guard rules gets a test.
The gateway is faked via the ``fake_gateway`` fixture; the parent session is a
fixed Desktop context; HERMES_HOME points at a temp profile (``tmp_home``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pytest

from spawn_session import state as state_mod
from spawn_session import tools
from spawn_session.config import Settings
from spawn_session.handover import read
from tests.conftest import base_args, call_spawn, make_parent, mk_handover


def handover_dir_for(parent_cwd: str | None) -> Path:
    if not parent_cwd:
        raise AssertionError("test needs a parent cwd")
    return Path(parent_cwd) / ".hermes" / "handovers"


def seed_frames(gw) -> list[dict[str, Any]]:
    return [f for f in gw.frames if f["method"] == "prompt.submit"]


def create_frames(gw) -> list[dict[str, Any]]:
    return [f for f in gw.frames if f["method"] == "session.create"]


# --------------------------------------------------------------------------- AT2.1


class TestUserAskedHappyPath:
    def test_creates_running_handover_and_child_session(
        self, fake_gateway, desktop_parent, tmp_home, settings_override
    ):
        result = call_spawn(base_args())

        assert result["ok"] is True
        assert result["status"] == "running"
        assert result["child_session_id"] == "ses-child-001"

        # Handover file exists, parses, and carries the required frontmatter.
        h = read(result["handover_path"])
        assert h.status == "running"
        assert h.meta["parent_session_id"] == "ses-parent-1"
        assert h.meta["child_session_id"] == "ses-child-001"
        assert h.meta["initiation"] == "user_asked"
        assert h.meta["initiator"] == "agent"
        assert h.task == "Make the test deterministic."
        assert h.context == "It fails ~10% of runs."

        # session.create got the right parameters (title prefixed, parent linked).
        (create_frame,) = create_frames(fake_gateway)
        params = create_frame["params"]
        assert params["title"] == "\u21b3 Fix flaky test"
        assert params["parent_session_id"] == "ses-parent-1"
        assert params["source"] == "desktop"  # B inherits A's surface
        assert params["cwd"] == desktop_parent.cwd
        assert params["idempotency_key"] == h.handover_id

        # B's first prompt is the seed message (task + context + report-back).
        (seed_frame,) = seed_frames(fake_gateway)
        text = seed_frame["params"]["text"]
        assert "Make the test deterministic." in text
        assert "It fails ~10% of runs." in text
        assert "report_back" in text

    def test_state_index_registers_child_ids(self, fake_gateway, desktop_parent, tmp_home):
        result = call_spawn(base_args())
        index = state_mod.load_index()
        assert index.is_child("ses-child-001")  # durable id
        assert index.is_child("rt-001")  # runtime id
        entry = index.children["ses-child-001"]
        assert entry["parent_session_id"] == "ses-parent-1"
        assert entry["handover_path"] == result["handover_path"]

    def test_broadcasts_child_created(self, fake_gateway, desktop_parent, tmp_home):
        events: list[tuple[str, dict]] = []
        tools._broadcast_event = lambda event, payload: events.append((event, payload))
        call_spawn(base_args())
        assert ("child.created",) == (events[0][0],)
        assert events[0][1]["child_session_id"] == "ses-child-001"


# --------------------------------------------------------------------------- AT2.2


class TestModelDefaults:
    def test_default_model_is_parent_model(self, fake_gateway, desktop_parent, tmp_home):
        call_spawn(base_args())
        (create_frame,) = create_frames(fake_gateway)
        params = create_frame["params"]
        assert params["model"] == "claude-opus-5-5"
        assert params["provider"] == "custom:cpa"
        assert params["reasoning_effort"] == "low"  # parent's effort

    def test_explicit_model_and_effort_override(self, fake_gateway, desktop_parent, tmp_home):
        result = call_spawn(base_args(model="custom:cpa:qwen38vl-27b-kvu", effort="high"))
        assert result["ok"] is True
        (create_frame,) = create_frames(fake_gateway)
        params = create_frame["params"]
        assert params["model"] == "qwen38vl-27b-kvu"
        assert params["provider"] == "custom:cpa"
        assert params["reasoning_effort"] == "high"
        h = read(result["handover_path"])
        assert h.meta["model"] == "custom:cpa:qwen38vl-27b-kvu"


# --------------------------------------------------------------------------- AT2.3 / D6


class TestModelRules:
    def test_bare_model_name_rejected(self, fake_gateway, desktop_parent, tmp_home):
        result = call_spawn(base_args(model="claude-opus-5-5"))
        assert result["ok"] is False
        assert "provider:model" in result["error"]
        assert create_frames(fake_gateway) == []

    def test_more_expensive_model_requires_confirmation(self, fake_gateway, desktop_parent, tmp_home):
        tools.set_settings_override(
            Settings(cost_rank={"custom:cpa:claude-opus-5-5": 1, "anthropic:claude-opus-4": 2})
        )
        result = call_spawn(base_args(model="anthropic:claude-opus-4"))
        assert result["ok"] is True
        assert result["status"] == "proposed"
        assert result["child_session_id"] is None
        assert any("more expensive" in r for r in result["confirmation_required"])
        assert create_frames(fake_gateway) == []  # no session created yet

    def test_cheaper_model_starts_immediately(self, fake_gateway, desktop_parent, tmp_home):
        tools.set_settings_override(
            Settings(cost_rank={"custom:cpa:claude-opus-5-5": 2, "openai:gpt-4o-mini": 1})
        )
        result = call_spawn(base_args(model="openai:gpt-4o-mini"))
        assert result["status"] == "running"

    def test_unknown_child_model_counts_as_expensive(self, fake_gateway, desktop_parent, tmp_home):
        tools.set_settings_override(Settings(cost_rank={"custom:cpa:claude-opus-5-5": 1}))
        result = call_spawn(base_args(model="acme:unknown-model"))
        assert result["status"] == "proposed"
        assert any("more expensive" in r for r in result["confirmation_required"])

    def test_two_unknown_models_are_equal(self, fake_gateway, tmp_path, tmp_home):
        # Both ranks unknown (inf == inf) -> not strictly more expensive.
        cwd = tmp_path / "proj"
        cwd.mkdir()
        parent = make_parent(provider="acme", model="mystery", cwd=str(cwd), git_repo_root=str(cwd))
        tools._resolve_parent = lambda sid: parent
        result = call_spawn(base_args(model="acme:mystery"))
        assert result["status"] == "running"


# --------------------------------------------------------------------------- D3


class TestOwnInitiative:
    def test_own_initiative_always_proposed(self, fake_gateway, desktop_parent, tmp_home):
        result = call_spawn(base_args(initiation="own_initiative"))
        assert result["ok"] is True
        assert result["status"] == "proposed"
        assert result["child_session_id"] is None
        assert any("own initiative" in r for r in result["confirmation_required"])
        assert create_frames(fake_gateway) == []

    def test_proposal_broadcast(self, fake_gateway, desktop_parent, tmp_home):
        events: list[tuple[str, dict]] = []
        tools._broadcast_event = lambda event, payload: events.append((event, payload))
        call_spawn(base_args(initiation="own_initiative"))
        assert events[0][0] == "child.proposed"


# --------------------------------------------------------------------------- AT2.5 / D7


class TestWorktree:
    def test_worktree_true_creates_branch_and_sets_cwd(
        self, fake_gateway, desktop_parent, tmp_home, monkeypatch
    ):
        from spawn_session.worktree import Worktree

        created = {}

        def fake_create(repo_root, slug, **kwargs):
            created["repo_root"] = str(repo_root)
            created["slug"] = slug
            created["kwargs"] = kwargs
            return Worktree(path=f"{repo_root}/.worktrees/spawn-{slug}", branch=f"spawn/{slug}")

        tools._create_worktree = fake_create
        result = call_spawn(base_args(worktree=True))
        assert result["ok"] is True
        assert created["slug"] == "fix-flaky-test"
        assert created["kwargs"]["worktree_dir"] == ".worktrees"
        assert created["kwargs"]["branch_prefix"] == "spawn/"

        (create_frame,) = create_frames(fake_gateway)
        assert create_frame["params"]["cwd"].endswith("/.worktrees/spawn-fix-flaky-test")

        h = read(result["handover_path"])
        assert h.meta["worktree"] == {
            "path": f"{desktop_parent.cwd}/.worktrees/spawn-fix-flaky-test",
            "branch": "spawn/fix-flaky-test",
        }
        # Seed message mentions the worktree + branch.
        (seed_frame,) = seed_frames(fake_gateway)
        assert "spawn/fix-flaky-test" in seed_frame["params"]["text"]

    @pytest.mark.parametrize("variant", ["own_initiative", "expensive", "cap"])
    def test_no_worktree_for_proposed_handover(
        self, variant, fake_gateway, desktop_parent, tmp_home
    ):
        calls = []
        tools._create_worktree = lambda *a, **k: calls.append((a, k))
        args = base_args(worktree=True)
        if variant == "own_initiative":
            args["initiation"] = "own_initiative"
        elif variant == "expensive":
            tools.set_settings_override(Settings(cost_rank={"custom:cpa:claude-opus-5-5": 1}))
            args["model"] = "unknown:very-expensive"
        else:
            tools.set_settings_override(Settings(max_children=0))
        result = call_spawn(args)
        assert result["status"] == "proposed"
        assert calls == []
        h = read(result["handover_path"])
        assert h.meta["worktree"] is None
        assert h.meta["worktree_requested"] is True
        assert h.meta["cwd"] == desktop_parent.cwd

    def test_worktree_false_keeps_parent_cwd(self, fake_gateway, desktop_parent, tmp_home):
        result = call_spawn(base_args(worktree=False))
        (create_frame,) = create_frames(fake_gateway)
        assert create_frame["params"]["cwd"] == desktop_parent.cwd
        h = read(result["handover_path"])
        assert h.meta["worktree"] is None


# --------------------------------------------------------------------------- AT2.6 / D12


class TestAllowedToolsets:
    def test_narrowing_recorded_in_handover(self, fake_gateway, desktop_parent, tmp_home):
        result = call_spawn(base_args(allowed_toolsets=["file", "web"]))
        assert result["ok"] is True
        h = read(result["handover_path"])
        assert h.meta["allowed_toolsets"] == ["file", "web"]

    def test_spawn_session_toolset_never_granted(self, fake_gateway, desktop_parent, tmp_home):
        result = call_spawn(base_args(allowed_toolsets=["spawn-session", "file"]))
        h = read(result["handover_path"])
        assert h.meta["allowed_toolsets"] == ["file"]

    def test_unknown_toolset_rejected(self, fake_gateway, desktop_parent, tmp_home, fake_registry):
        fake_registry({"read_file": "file", "web_search": "web"})
        result = call_spawn(base_args(allowed_toolsets=["teleport"]))
        assert result["ok"] is False
        assert "unknown toolset" in result["error"]

    def test_missing_known_toolsets_is_permissive(self, fake_gateway, desktop_parent, tmp_home):
        # No registry available (e.g. tests without Hermes installed): cannot
        # validate names, so the list passes through unchanged.
        result = call_spawn(base_args(allowed_toolsets=["anything"]))
        assert result["ok"] is True


# --------------------------------------------------------------------------- D13


@pytest.mark.parametrize("source", ["cli", "kanban", "telegram", "tui", "cron"])
def test_non_desktop_surface_refused(source, fake_gateway, tmp_path, tmp_home, monkeypatch):
    cwd = tmp_path / "proj"
    cwd.mkdir()
    parent = make_parent(source=source, cwd=str(cwd), git_repo_root=str(cwd))
    tools._resolve_parent = lambda sid: parent
    result = call_spawn(base_args())
    assert result["ok"] is False
    assert "delegate_task" in result["error"]
    assert "Kanban card" in result["error"]
    assert gw_frames_len(fake_gateway) == 0
    # No handover file may be created on a refused surface.
    assert list(handover_dir_for(parent.cwd).glob("*.md")) == []


def gw_frames_len(gw) -> int:
    return len(gw.frames)


# --------------------------------------------------------------------------- D10


class TestNestingAndConcurrency:
    def test_spawn_inside_child_refused(self, fake_gateway, desktop_parent, tmp_home):
        # Register the calling session itself as a known child.
        index = state_mod.load_index()
        grandchild = mk_handover(
            handover_dir_for(desktop_parent.cwd),
            title="Grand", task="t", context="c",
            parent_session_id="ses-grandparent", model="custom:cpa:x", status="running",
        )
        assert grandchild.path is not None
        index.register_child(
            ["ses-parent-1"], handover_path=grandchild.path,
            parent_session_id="ses-grandparent", status="running",
        )
        result = call_spawn(base_args())
        assert result["ok"] is False
        assert "one level only" in result["error"]
        assert create_frames(fake_gateway) == []

    def _seed_running_children(self, desktop_parent, tmp_home, n: int, initiator="agent", status="running"):
        from spawn_session.handover import update_status

        index = state_mod.load_index()
        for i in range(n):
            h = mk_handover(
                handover_dir_for(desktop_parent.cwd),
                title=f"Child {i}", task="t", context="c",
                parent_session_id="ses-parent-1", model="custom:cpa:x",
                status="running", initiator=initiator,
            )
            assert h.path is not None
            if status != "running":
                # Walk the state machine to the requested non-initial status.
                update_status(h.path, "reported")
                if status == "delivered":
                    update_status(h.path, "delivered")
            # Real gateway children carry two distinct ids (durable + runtime).
            index.register_child(
                [f"ses-existing-{i}", f"rt-existing-{i}"], handover_path=h.path,
                parent_session_id="ses-parent-1", status=status,
            )

    def test_two_id_children_counted_once(self, fake_gateway, desktop_parent, tmp_home):
        # Regression (review round 1): 2 real children must count as 2, not 4,
        # so the 3rd agent-initiated spawn still starts with max_children=3.
        self._seed_running_children(desktop_parent, tmp_home, 2)
        assert state_mod.running_agent_children(state_mod.load_index(), "ses-parent-1") == 2
        result = call_spawn(base_args())
        assert result["status"] == "running"

    def test_cap_after_spawns_through_handler(self, fake_gateway, desktop_parent, tmp_home):
        # Three handler spawns (each indexed under rt-/ses- ids) -> 4th proposed.
        for i in range(3):
            assert call_spawn(base_args(title=f"Spawn {i}"))["status"] == "running"
        result = call_spawn(base_args(title="Spawn 3"))
        assert result["status"] == "proposed"
        assert any("limit reached: 3" in r for r in result["confirmation_required"])

    def test_spawn_in_compressed_continuation_of_child_refused(
        self, fake_gateway, desktop_parent, tmp_home
    ):
        # Lineage: continuation (the caller) -> child B -> A. B's row links to A
        # via parent_session_id too, so a root walk would land on A.
        index = state_mod.load_index()
        h = mk_handover(
            handover_dir_for(desktop_parent.cwd), title="B", task="t", context="c",
            parent_session_id="ses-a", model="custom:cpa:x", status="running",
        )
        assert h.path is not None
        index.register_child(["ses-b"], handover_path=h.path, parent_session_id="ses-a", status="running")
        tools._lineage_ids = lambda sid: [sid, "ses-b", "ses-a"]
        result = call_spawn(base_args())
        assert result["ok"] is False
        assert "one level only" in result["error"]
        assert create_frames(fake_gateway) == []

    def test_fourth_agent_child_is_proposed(self, fake_gateway, desktop_parent, tmp_home):
        self._seed_running_children(desktop_parent, tmp_home, 3)
        result = call_spawn(base_args())
        assert result["ok"] is True
        assert result["status"] == "proposed"
        assert any("limit reached" in r for r in result["confirmation_required"])
        assert create_frames(fake_gateway) == []

    def test_user_initiated_children_do_not_count(self, fake_gateway, desktop_parent, tmp_home):
        # 3 running children created by the user (initiator=user) don't hit the cap.
        self._seed_running_children(desktop_parent, tmp_home, 3, initiator="user")
        result = call_spawn(base_args())
        assert result["status"] == "running"

    def test_max_children_configurable(self, fake_gateway, desktop_parent, tmp_home):
        tools.set_settings_override(Settings(max_children=5))
        self._seed_running_children(desktop_parent, tmp_home, 3)
        result = call_spawn(base_args())
        assert result["status"] == "running"

    def test_non_running_children_do_not_count(self, fake_gateway, desktop_parent, tmp_home):
        self._seed_running_children(desktop_parent, tmp_home, 3, status="delivered")
        result = call_spawn(base_args())
        assert result["status"] == "running"


# --------------------------------------------------------------------------- validation


class TestArgumentValidation:
    @pytest.mark.parametrize(
        "overrides",
        [
            {"task": ""},
            {"initiation": "spontaneous"},
            {"effort": "extreme"},
            {"title": "x" * 81},
        ],
    )
    def test_invalid_args_rejected(self, fake_gateway, desktop_parent, tmp_home, overrides):
        args = base_args(**overrides)
        if "title" in overrides:
            args["title"] = overrides["title"]
        result = call_spawn(args)
        assert result["ok"] is False
        assert create_frames(fake_gateway) == []

    def test_missing_required_fields(self, fake_gateway, desktop_parent, tmp_home):
        for key in ("title", "task", "initiation"):
            args = base_args()
            del args[key]
            result = call_spawn(args)
            assert result["ok"] is False


# --------------------------------------------------------------------------- failure paths


class TestFailurePaths:
    def test_gateway_create_failure_abandons_handover(
        self, fake_gateway, desktop_parent, tmp_home
    ):
        fake_gateway.fail_methods.add("session.create")
        result = call_spawn(base_args())
        assert result["ok"] is False
        assert "gateway error" in result["error"]
        # The handover file must not be left 'running' without a child.
        files = list(handover_dir_for(desktop_parent.cwd).glob("*.md"))
        assert len(files) == 1
        h = read(files[0])
        assert h.status == "abandoned"
        assert any(
            e.get("to") == "abandoned" and "session.create failed" in (e.get("reason") or "")
            for e in h.meta["history"]
        )

    def test_parent_not_found(self, fake_gateway, tmp_home, monkeypatch):
        from spawn_session.parent import ParentNotFound

        def boom(sid):
            raise ParentNotFound(f"no session row for id {sid!r}")

        tools._resolve_parent = boom
        result = call_spawn(base_args())
        assert result["ok"] is False
        assert "cannot resolve parent session" in result["error"]


# --------------------------------------------------------------------------- kanban board (D7)


class TestKanbanBoard:
    def test_board_from_env_lands_in_frontmatter_and_seed(
        self, fake_gateway, desktop_parent, tmp_home, monkeypatch
    ):
        monkeypatch.setenv("HERMES_KANBAN_BOARD", "hermes-spawn-session")
        result = call_spawn(base_args())
        h = read(result["handover_path"])
        assert h.meta["kanban_board"] == "hermes-spawn-session"
        (seed_frame,) = seed_frames(fake_gateway)
        assert "`board=hermes-spawn-session`" in seed_frame["params"]["text"]

    def test_no_board_when_unset(self, fake_gateway, desktop_parent, tmp_home, monkeypatch):
        monkeypatch.delenv("HERMES_KANBAN_BOARD", raising=False)
        result = call_spawn(base_args())
        h = read(result["handover_path"])
        assert h.meta["kanban_board"] is None


# --------------------------------------------------------------------------- fallback dir


class TestHandoverDirFallback:
    def test_unwritable_cwd_falls_back_to_profile(
        self, fake_gateway, tmp_home, monkeypatch
    ):
        parent = make_parent(cwd=None)  # no resolvable cwd at all
        tools._resolve_parent = lambda sid: parent
        result = call_spawn(base_args())
        assert result["ok"] is True
        path = Path(result["handover_path"])
        assert tmp_home in path.parents
        assert path.parent == tmp_home / "spawn-session" / "handovers"


# --------------------------------------------------------------------------- pre_tool_call guard (D10/D12)


class TestToolsetGuard:
    def _register_child(self, desktop_parent, tmp_home, allowed=None):
        index = state_mod.load_index()
        h = mk_handover(
            handover_dir_for(desktop_parent.cwd),
            title="B", task="t", context="c",
            parent_session_id="ses-parent-1", model="custom:cpa:x", status="running",
            allowed_toolsets=allowed,
        )
        assert h.path is not None
        index.register_child(
            ["ses-b"], handover_path=h.path, parent_session_id="ses-parent-1", status="running"
        )
        return h

    def test_guard_enforced_in_compressed_continuation(self, desktop_parent, tmp_home, fake_registry):
        fake_registry({"read_file": "file", "terminal": "terminal"})
        self._register_child(desktop_parent, tmp_home, allowed=["file"])
        tools._lineage_ids = lambda sid: [sid, "ses-b", "ses-parent-1"]
        verdict = tools.toolset_guard(tool_name="spawn_session", session_id="ses-b-cont")
        assert verdict is not None and verdict["action"] == "block"
        verdict = tools.toolset_guard(tool_name="terminal", session_id="ses-b-cont")
        assert verdict is not None and "allowed_toolsets" in verdict["message"]
        assert tools.toolset_guard(tool_name="read_file", session_id="ses-b-cont") is None

    def test_non_child_session_untouched(self, desktop_parent, tmp_home):
        assert tools.toolset_guard(tool_name="terminal", session_id="ses-parent-1") is None

    def test_spawn_blocked_in_child(self, desktop_parent, tmp_home):
        self._register_child(desktop_parent, tmp_home)
        verdict = tools.toolset_guard(tool_name="spawn_session", session_id="ses-b")
        assert verdict is not None and verdict["action"] == "block"
        assert "one level only" in verdict["message"]

    def test_report_back_allowed_in_child(self, desktop_parent, tmp_home, fake_registry):
        # report_back is the child's own tool: never blocked, even when narrowed.
        fake_registry({"read_file": "file", "report_back": "spawn-session"})
        self._register_child(desktop_parent, tmp_home, allowed=["file"])
        assert tools.toolset_guard(tool_name="report_back", session_id="ses-b") is None

    def test_unrestricted_child_passes_other_tools(self, desktop_parent, tmp_home):
        self._register_child(desktop_parent, tmp_home)
        assert tools.toolset_guard(tool_name="read_file", session_id="ses-b") is None

    def test_narrowed_child_blocks_foreign_toolset(
        self, desktop_parent, tmp_home, fake_registry
    ):
        fake_registry({"read_file": "file", "terminal": "terminal"})
        self._register_child(desktop_parent, tmp_home, allowed=["file"])
        verdict = tools.toolset_guard(tool_name="terminal", session_id="ses-b")
        assert verdict is not None and verdict["action"] == "block"
        assert "allowed_toolsets" in verdict["message"]
        # Allowed toolset passes.
        assert tools.toolset_guard(tool_name="read_file", session_id="ses-b") is None

    def test_unknown_tool_passes(self, desktop_parent, tmp_home, fake_registry):
        fake_registry({"read_file": "file"})
        self._register_child(desktop_parent, tmp_home, allowed=["file"])
        # A tool with no registered toolset cannot be judged: fail open.
        assert tools.toolset_guard(tool_name="mystery_tool", session_id="ses-b") is None


# --------------------------------------------------------------------------- plugin registration


class TestRegistration:
    def test_register_wires_tool_and_hook(self):
        # The plugin entry point is the repository-root __init__.py (loaded by the
        # Hermes plugin loader as a directory plugin), not the inner package.
        import importlib.util

        init_path = Path(__file__).resolve().parent.parent / "__init__.py"
        import sys

        # Load as a package (like the Hermes directory-plugin loader) so the
        # relative ``from .spawn_session...`` import resolves.
        spec = importlib.util.spec_from_file_location(
            "spawn_session_plugin", init_path, submodule_search_locations=[str(init_path.parent)]
        )
        assert spec is not None and spec.loader is not None
        plugin = importlib.util.module_from_spec(spec)
        sys.modules["spawn_session_plugin"] = plugin
        try:
            spec.loader.exec_module(plugin)
        finally:
            for name in [m for m in sys.modules if m == "spawn_session_plugin" or m.startswith("spawn_session_plugin.")]:
                del sys.modules[name]

        class FakeCtx:
            def __init__(self):
                self.tools = {}
                self.hooks = {}
                self.commands = {}

            def register_tool(self, **kwargs):
                self.tools[kwargs["name"]] = kwargs

            def register_hook(self, event, fn):
                self.hooks.setdefault(event, []).append(fn)

            def register_command(self, name, handler, description="", args_hint=""):
                self.commands[name] = handler

        ctx = FakeCtx()
        plugin.register(ctx)
        assert "report_back" in ctx.tools
        assert ctx.tools["report_back"]["schema"]["parameters"]["required"] == ["result"]
        assert set(ctx.commands) == {"report", "abandon", "detach", "spawn-cleanup"}
        assert "spawn_session" in ctx.tools
        assert ctx.tools["spawn_session"]["toolset"] == "spawn-session"
        assert ctx.tools["spawn_session"]["schema"]["parameters"]["required"] == [
            "title",
            "task",
            "initiation",
        ]
        assert len(ctx.hooks.get("pre_tool_call", [])) == 1
