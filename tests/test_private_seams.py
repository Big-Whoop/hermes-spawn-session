"""Calling-session context for slash commands, and the guarded fallback for the
remaining private Hermes seam (SPEC 3.1, catalog rule 9)."""

from __future__ import annotations

import inspect
import json
import sys

import pytest

from spawn_session import commands, gateway, tools


def _dispatch(handler, raw_args, **context):
    # What hermes_cli.plugin_command_dispatch.invoke_plugin_command (>= v0.22.5)
    # does: pass only the context keywords the handler declares.
    params = inspect.signature(handler).parameters
    return handler(raw_args, **{k: v for k, v in context.items() if k in params})


@pytest.mark.parametrize("name", sorted(commands.COMMANDS))
def test_command_handlers_declare_session_context(name):
    params = inspect.signature(commands.COMMANDS[name][0]).parameters
    assert {"session_key", "session_id"} <= set(params)


def test_current_session_from_session_key(monkeypatch):
    seen = []
    monkeypatch.setattr(commands, "_child_handover", lambda: seen.append(commands._current_session()) or None)
    monkeypatch.setattr(commands.lifecycle, "abandon", lambda *a, **k: {"handover_id": "h"})
    _dispatch(commands.COMMANDS["abandon"][0], "", session_key="ses-key", session_id="ses-id",
              platform="desktop", source=None)
    assert seen == ["ses-key"]
    assert commands._default_current_session() == ""  # unbound after the call


def test_current_session_falls_back_to_session_id(monkeypatch):
    seen = []
    monkeypatch.setattr(commands, "_child_handover", lambda: seen.append(commands._current_session()) or None)
    monkeypatch.setattr(commands.lifecycle, "abandon", lambda *a, **k: {"handover_id": "h"})
    _dispatch(commands.COMMANDS["abandon"][0], "", session_key="", session_id="ses-id")
    assert seen == ["ses-id"]


def test_no_session_context_is_a_clean_error():
    out = _dispatch(commands.COMMANDS["detach"][0], "confirm")
    assert out == "spawn-session: cannot determine the current session"


def test_gateway_unavailable_message_names_host(monkeypatch):
    gateway.set_handle_request_override(None)
    monkeypatch.setitem(sys.modules, "tui_gateway.server", None)
    with pytest.raises(gateway.GatewayUnavailable, match="Desktop/TUI gateway"):
        gateway.create_session(title="x")


def test_spawn_tool_returns_json_when_gateway_seam_missing(monkeypatch):
    # Tool handlers never raise; a missing RPC door must surface as JSON.
    gateway.set_handle_request_override(None)
    monkeypatch.setitem(sys.modules, "tui_gateway.server", None)
    out = tools.spawn_session_handler({"task": "t"}, session_id="ses-a")
    assert isinstance(json.loads(out), dict)
