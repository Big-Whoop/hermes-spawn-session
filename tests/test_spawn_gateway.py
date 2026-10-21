"""Tests for spawn_session.gateway (RPC wrapper)."""

from __future__ import annotations

import pytest

from spawn_session import gateway


class RecordingHandle:
    def __init__(self, result=None, error=None, exc=None):
        self.result = result
        self.error = error
        self.exc = exc
        self.frames = []

    def __call__(self, frame):
        self.frames.append(frame)
        if self.exc is not None:
            raise self.exc
        if self.error is not None:
            return {"id": frame.get("id"), "error": self.error}
        return {"id": frame.get("id"), "result": self.result or {}}


def test_rpc_success(monkeypatch):
    rec = RecordingHandle(result={"hello": "world"})
    gateway.set_handle_request_override(rec)
    try:
        assert gateway.rpc("ping", {}) == {"hello": "world"}
        assert rec.frames[0]["method"] == "ping"
    finally:
        gateway.set_handle_request_override(None)


def test_rpc_error_frame_raises(monkeypatch):
    rec = RecordingHandle(error={"code": -32601, "message": "nope"})
    gateway.set_handle_request_override(rec)
    try:
        with pytest.raises(gateway.GatewayError, match="nope"):
            gateway.rpc("ping", {})
    finally:
        gateway.set_handle_request_override(None)


def test_rpc_exception_raises_gateway_error(monkeypatch):
    rec = RecordingHandle(exc=RuntimeError("boom"))
    gateway.set_handle_request_override(rec)
    try:
        with pytest.raises(gateway.GatewayError, match="boom"):
            gateway.rpc("ping", {})
    finally:
        gateway.set_handle_request_override(None)


def test_create_session_param_mapping(monkeypatch):
    rec = RecordingHandle(
        result={"session_id": "rt-1", "stored_session_id": "ses-1", "message_count": 0}
    )
    gateway.set_handle_request_override(rec)
    try:
        res = gateway.create_session(
            title="T", cwd="/x", model="m", provider="p", reasoning_effort="high",
            parent_session_id="ses-p", idempotency_key="hs_1", source="desktop",
        )
        assert res["stored_session_id"] == "ses-1"
        params = rec.frames[0]["params"]
        assert params["title"] == "T"
        assert params["cwd"] == "/x"
        assert params["cwd_explicit"] is True
        assert params["model"] == "m"
        assert params["provider"] == "p"
        assert params["reasoning_effort"] == "high"
        assert params["parent_session_id"] == "ses-p"
        assert params["idempotency_key"] == "hs_1"
        assert params["source"] == "desktop"
    finally:
        gateway.set_handle_request_override(None)


def test_create_session_minimal(monkeypatch):
    rec = RecordingHandle(result={"session_id": "rt-1", "stored_session_id": "ses-1"})
    gateway.set_handle_request_override(rec)
    try:
        res = gateway.create_session()
        assert res["session_id"] == "rt-1"
        assert rec.frames[0]["params"] == {}
    finally:
        gateway.set_handle_request_override(None)


def test_create_session_no_ids_raises(monkeypatch):
    rec = RecordingHandle(result={"foo": "bar"})
    gateway.set_handle_request_override(rec)
    try:
        with pytest.raises(gateway.GatewayError, match="no ids"):
            gateway.create_session()
    finally:
        gateway.set_handle_request_override(None)


def test_submit_prompt(monkeypatch):
    rec = RecordingHandle(result={"ok": True})
    gateway.set_handle_request_override(rec)
    try:
        gateway.submit_prompt("rt-1", "hello")
        assert rec.frames[0]["params"] == {"session_id": "rt-1", "text": "hello"}
    finally:
        gateway.set_handle_request_override(None)


def test_unavailable_raises(monkeypatch):
    # No override and a broken import path -> GatewayUnavailable.
    gateway.set_handle_request_override(None)
    monkeypatch.setitem(__import__("sys").modules, "tui_gateway.server", None)
    with pytest.raises(gateway.GatewayUnavailable):
        gateway.rpc("ping", {})


def test_set_session_title_maps_stored_id_to_live_runtime_id():
    """``session.title`` needs the live runtime id; the plugin keeps the stored id (AT7.3)."""
    frames = []

    def handle(frame):
        frames.append(frame)
        if frame["method"] == "session.active_list":
            return {"id": frame["id"], "result": {"sessions": [
                {"id": "rt-other", "session_key": "ses-other"},
                {"id": "rt-b", "session_key": "ses-b"},
            ]}}
        return {"id": frame["id"], "result": {"title": frame["params"]["title"]}}

    gateway.set_handle_request_override(handle)
    try:
        gateway.set_session_title("ses-b", "\u21b3 Detached: x")
        assert frames[-1]["method"] == "session.title"
        assert frames[-1]["params"] == {"session_id": "rt-b", "title": "\u21b3 Detached: x"}
    finally:
        gateway.set_handle_request_override(None)


def test_set_session_title_falls_back_to_given_id():
    frames = []

    def handle(frame):
        frames.append(frame)
        if frame["method"] == "session.active_list":
            return {"id": frame["id"], "error": {"code": 5000, "message": "no sessions"}}
        return {"id": frame["id"], "result": {}}

    gateway.set_handle_request_override(handle)
    try:
        gateway.set_session_title("rt-live", "t")
        assert frames[-1]["params"]["session_id"] == "rt-live"
    finally:
        gateway.set_handle_request_override(None)
