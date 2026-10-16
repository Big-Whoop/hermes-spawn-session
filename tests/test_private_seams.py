"""Guarded fallbacks for the two private Hermes seams (SPEC 3.1, catalog rule 9)."""

from __future__ import annotations

import json
import sys
import types

import pytest

from spawn_session import commands, gateway, tools


def _fake_session_context(monkeypatch, values):
    mod = types.ModuleType("gateway.session_context")
    mod.get_session_env = lambda name, default="": values.get(name, default)
    pkg = types.ModuleType("gateway")
    pkg.session_context = mod
    monkeypatch.setitem(sys.modules, "gateway", pkg)
    monkeypatch.setitem(sys.modules, "gateway.session_context", mod)


def test_current_session_prefers_session_context(monkeypatch):
    _fake_session_context(monkeypatch, {"HERMES_SESSION_KEY": "ses-ctx"})
    monkeypatch.setenv("HERMES_SESSION_KEY", "ses-env")
    assert commands._default_current_session() == "ses-ctx"


def test_current_session_context_falls_back_to_session_id(monkeypatch):
    _fake_session_context(monkeypatch, {"HERMES_SESSION_ID": "ses-id"})
    assert commands._default_current_session() == "ses-id"


def test_current_session_env_fallback_when_seam_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "gateway.session_context", None)
    monkeypatch.delenv("HERMES_SESSION_KEY", raising=False)
    monkeypatch.setenv("HERMES_SESSION_ID", "ses-env")
    assert commands._default_current_session() == "ses-env"


def test_current_session_empty_when_nothing_available(monkeypatch):
    monkeypatch.setitem(sys.modules, "gateway.session_context", None)
    monkeypatch.delenv("HERMES_SESSION_KEY", raising=False)
    monkeypatch.delenv("HERMES_SESSION_ID", raising=False)
    assert commands._default_current_session() == ""


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
