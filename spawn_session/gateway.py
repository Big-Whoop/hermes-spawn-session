"""In-process TUI-gateway JSON-RPC access for the spawn-session backend.

The Python half of this plugin runs inside the gateway process (Desktop/TUI
host), so it can drive the same JSON-RPC methods a desktop client uses:
``session.create``, ``prompt.submit``, ``session.title``. Hermes core itself
calls these handlers in-process (see ``tui_gateway/methods_onboarding.py``);
this module wraps that pattern with fail-closed error handling.

Docs-first note: the method catalog and per-session model/provider overrides
are documented at
https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration
; the parameter contract is validated by the gateway's own pydantic contracts
(``tui_gateway/contracts``), so typos surface as JSON-RPC errors here.
"""

from __future__ import annotations

import itertools
import uuid
from typing import Any, Callable, Mapping, Optional

# Indirection seam for unit tests: set to a fake ``handle_request`` replacement.
_handle_request_override: Optional[Callable[[dict], dict | None]] = None


class GatewayError(RuntimeError):
    """The gateway answered with an error frame."""


class GatewayUnavailable(GatewayError):
    """No usable in-process gateway (e.g. not running inside the gateway host)."""


def set_handle_request_override(fn: Callable[[dict], dict | None] | None) -> None:
    """Test seam: replace (or restore, with ``None``) the RPC entry point."""
    global _handle_request_override
    _handle_request_override = fn


def _resolve_handle_request() -> Callable[[dict], dict | None]:
    if _handle_request_override is not None:
        return _handle_request_override
    try:
        # server.py rebinds split-module handlers onto its own namespace; the
        # raw tui_gateway.rpc_dispatch.handle_request lacks those globals.
        from tui_gateway.server import handle_request
    except Exception as exc:  # ImportError or a broken gateway build
        raise GatewayUnavailable(
            "no in-process TUI gateway available; spawn_session can only run inside the "
            f"Desktop/TUI gateway process ({exc.__class__.__name__})"
        ) from exc
    return handle_request


def rpc(method: str, params: Mapping[str, Any] | None = None) -> dict:
    """Send one JSON-RPC request to the in-process gateway and return the result.

    Raises :class:`GatewayUnavailable` when no gateway is importable and
    :class:`GatewayError` when the gateway answers with an error frame.
    """
    handle_request = _resolve_handle_request()
    frame = {"id": str(uuid.uuid4()), "method": method, "params": dict(params or {})}
    try:
        response = handle_request(frame)
    except Exception as exc:
        raise GatewayError(f"gateway call {method!r} failed: {exc}") from exc
    if not isinstance(response, dict):
        raise GatewayError(f"gateway call {method!r} returned no response frame")
    if "error" in response:
        err = response["error"] or {}
        detail = err.get("message") or str(err)
        raise GatewayError(f"{method}: {detail}")
    return dict(response.get("result") or {})


_create_counter = itertools.count(1)


def create_session(
    *,
    title: str | None = None,
    cwd: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    reasoning_effort: str | None = None,
    parent_session_id: str | None = None,
    idempotency_key: str | None = None,
    source: str | None = None,
) -> dict:
    """Create a visible top-level session (``session.create``).

    Returns the result mapping with at least ``session_id`` (runtime id),
    ``stored_session_id`` (durable key) and ``message_count``.
    """
    params: dict[str, Any] = {}
    if title is not None:
        params["title"] = title
    if cwd is not None:
        params["cwd"] = cwd
        # A deliberate workspace pick: the child must keep this cwd even when a
        # named profile defines its own terminal.cwd (SPEC D7).
        params["cwd_explicit"] = True
    if model is not None:
        params["model"] = model
    if provider is not None:
        params["provider"] = provider
    if reasoning_effort is not None:
        params["reasoning_effort"] = reasoning_effort
    if parent_session_id is not None:
        params["parent_session_id"] = parent_session_id
    if idempotency_key is not None:
        params["idempotency_key"] = idempotency_key
    if source is not None:
        # Without an explicit source the gateway falls back to the process
        # platform (HERMES_DESKTOP env), which can tag the child 'tui'.
        params["source"] = source
    result = rpc("session.create", params)
    if "stored_session_id" not in result and "session_id" not in result:
        raise GatewayError(f"session.create returned no ids: {result!r}")
    return result


def submit_prompt(session_id: str, text: str, *, display_kind: str | None = None) -> dict:
    """Submit a prompt to a live session (``prompt.submit``).

    The gateway runs the turn asynchronously; this returns once the submission
    was accepted. Used to start the child's first turn with the seed message.
    """
    params: dict[str, Any] = {"session_id": session_id, "text": text}
    if display_kind is not None:
        params["display_kind"] = display_kind
    return rpc("prompt.submit", params)


def set_session_title(session_id: str, title: str) -> dict:
    """Set a session's stored title (``session.title``)."""
    return rpc("session.title", {"session_id": session_id, "title": title})


def archive_session(session_id: str) -> dict:
    """Archive (soft-hide, messages kept) a session + lineage (``session.archive``).

    Accepts a live runtime id or a stored id; never deletes (D11).
    """
    return rpc("session.archive", {"session_id": session_id, "archived": True})
