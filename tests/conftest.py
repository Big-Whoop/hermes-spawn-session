"""Shared fixtures for spawn-session backend tests."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any, Iterator, Optional

import pytest

from spawn_session import gateway, tools
from spawn_session import parent as parent_mod
from spawn_session import project as project_mod
from spawn_session import state as state_mod
from spawn_session import worktree as worktree_mod
from spawn_session.config import Settings
from spawn_session.parent import ParentContext


class FakeGateway:
    """Stands in for the in-process TUI gateway (gateway.rpc seam)."""

    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []
        self.fail_methods: set[str] = set()
        self.create_count = 0
        # tools.list answer for the parent (D12 superset check):
        # name -> (enabled, resolved tools). Default: everything enabled.
        self.toolsets: dict[str, tuple[bool, list[str]]] = {
            name: (True, [f"{name}_tool"])
            for name in ("file", "web", "terminal", "project", "spawn-session", "anything")
        }

    def __call__(self, frame: dict[str, Any]) -> Optional[dict]:
        self.frames.append(frame)
        method = frame["method"]
        if method in self.fail_methods:
            return {"id": frame.get("id"), "error": {"code": -32000, "message": f"{method} failed (fake)"}}
        if method == "session.create":
            self.create_count += 1
            n = self.create_count
            return {
                "id": frame.get("id"),
                "result": {
                    "session_id": f"rt-{n:03d}",
                    "stored_session_id": f"ses-child-{n:03d}",
                    "message_count": 0,
                },
            }
        if method == "prompt.submit":
            return {"id": frame.get("id"), "result": {"ok": True}}
        if method == "tools.list":
            return {"id": frame.get("id"), "result": {"toolsets": [
                {"name": n, "enabled": en, "tools": list(t)} for n, (en, t) in self.toolsets.items()
            ]}}
        if method == "session.title":
            return {"id": frame.get("id"), "result": {"title": frame["params"].get("title", "")}}
        return {"id": frame.get("id"), "error": {"code": -32601, "message": f"unknown {method}"}}


@pytest.fixture
def fake_gateway(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeGateway]:
    gw = FakeGateway()
    gateway.set_handle_request_override(gw)
    # The handler schedules the seed prompt on a daemon thread; run it inline in
    # tests so assertions see the submitted frame deterministically.
    class InlineThread:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def start(self) -> None:
            self.kwargs["target"](*self.kwargs.get("args", ()), **self.kwargs.get("kwargs", {}))

    monkeypatch.setattr(tools.threading, "Thread", InlineThread)
    yield gw
    gateway.set_handle_request_override(None)


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HERMES_HOME at an empty temp profile."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


@pytest.fixture
def settings_override(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    s = Settings()
    tools.set_settings_override(s)
    yield s
    tools.set_settings_override(None)


def make_parent(
    session_id: str = "ses-parent-1",
    source: str = "desktop",
    model: str = "claude-opus-5-5",
    provider: str = "custom:cpa",
    cwd: Optional[str] = "/workspace/project",
    git_repo_root: Optional[str] = None,
    effort: Optional[str] = "low",
    title: str = "Parent session",
) -> ParentContext:
    return ParentContext(
        session_id=session_id,
        source=source,
        title=title,
        model=model,
        provider=provider,
        cwd=cwd,
        git_repo_root=git_repo_root or cwd,
        effort=effort,
    )


@pytest.fixture
def desktop_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ParentContext:
    """Desktop parent whose cwd is a writable temp project dir (never real paths)."""
    cwd = tmp_path / "proj"
    cwd.mkdir()
    parent = make_parent(cwd=str(cwd), git_repo_root=str(cwd))
    monkeypatch.setattr(tools, "_resolve_parent", lambda sid: parent)
    return parent


@pytest.fixture(autouse=True)
def _reset_tools_seams():
    """Keep handler seams at their real defaults between tests."""
    yield
    tools._resolve_parent = parent_mod.resolve_parent_context
    tools._load_index = state_mod.load_index
    tools._gateway_create = gateway.create_session
    tools._find_repo_root = worktree_mod.find_repo_root
    tools._create_worktree = worktree_mod.create_worktree
    tools._broadcast_event = tools._default_broadcast
    tools._lineage_ids = parent_mod.lineage_ids
    tools._project_for_path = project_mod.project_for_path
    tools._parent_toolsets = gateway.session_toolsets
    tools.set_settings_override(None)
    _guard_cache_clear()


def _guard_cache_clear() -> None:
    tools._guard_cache.clear()


@pytest.fixture
def fake_registry(monkeypatch: pytest.MonkeyPatch):
    """Install a stub ``tools.registry`` module with a given tool->toolset map."""

    def _install(tool_map: dict[str, str]) -> types.ModuleType:
        reg = types.SimpleNamespace(
            get_tool_to_toolset_map=lambda: dict(tool_map),
            get_toolset_for_tool=lambda name: tool_map.get(name),
        )
        tools_mod = types.ModuleType("tools")
        registry_mod = types.ModuleType("tools.registry")
        setattr(registry_mod, "registry", reg)
        setattr(tools_mod, "registry", registry_mod)
        monkeypatch.setitem(sys.modules, "tools", tools_mod)
        monkeypatch.setitem(sys.modules, "tools.registry", registry_mod)
        return registry_mod

    yield _install


def call_spawn(args: dict[str, Any], session_id: str = "ses-parent-1") -> dict[str, Any]:
    """Invoke the tool handler and parse its JSON result."""
    raw = tools.spawn_session_handler(dict(args), session_id=session_id)
    return json.loads(raw)


def mk_handover(base_dir: Path | str, **kwargs: Any):
    """Create a handover file and assert its path is set (always true in practice)."""
    from spawn_session.handover import create as _create

    h = _create(base_dir, **kwargs)
    assert h.path is not None
    return h


def base_args(**overrides: Any) -> dict[str, Any]:
    args = {
        "title": "Fix flaky test",
        "task": "Make the test deterministic.",
        "context": "It fails ~10% of runs.",
        "initiation": "user_asked",
    }
    args.update(overrides)
    return args
