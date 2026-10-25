"""Slash commands in child session B and backend actions for A's buttons (SPEC 4.3, D4/D11).

The calling session comes from the context keywords Hermes (>= v0.22.5) passes
to plugin command handlers that declare them (``session_key``/``session_id``;
developer guide, "Calling-session context"). In the Desktop/TUI gateway
``session_key`` is the durable session id.

Commands:
- ``/report [note]`` — asks B's agent (injected user message) to call ``report_back``.
- ``/abandon [reason]`` — D11 abort.
- ``/detach confirm`` — D11 detach; irreversible, so a bare ``/detach`` only explains.
- ``/spawn-cleanup <handover_id> yes|no`` — answer the worktree-removal question.

Backend actions (for the desktop half's status-card buttons in A, later card):
:func:`action_abandon`, :func:`action_detach`, :func:`action_deliver_pending`.
"""

from __future__ import annotations

import json
import contextvars
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from . import delivery, lifecycle, parent as parent_mod, state as state_mod

logger = logging.getLogger("hermes.spawn-session")


# Calling-session context of the running command, bound by :func:`_guard`.
_caller: contextvars.ContextVar[tuple[str, str]] = contextvars.ContextVar(
    "spawn_session_caller", default=("", ""))


def _default_current_session() -> str:
    session_key, session_id = _caller.get()
    return session_key or session_id


# Seams (tests replace these).
_current_session: Callable[[], str] = _default_current_session
_load_index: Callable[..., state_mod.StateIndex] = state_mod.load_index
_lineage_ids: Callable[[str], list[str]] = parent_mod.lineage_ids


def _settings():
    from .tools import _settings as tools_settings

    return tools_settings()


def _child_handover() -> Path:
    sid = _current_session()
    if not sid:
        raise lifecycle.LifecycleError("cannot determine the current session")
    return lifecycle.handover_for_session(_load_index(), sid, _lineage_ids)


def _guard(fn: Callable[[str], str]) -> Callable[..., str]:
    # Declaring the keywords opts in to Hermes's calling-session context.
    def wrapped(raw_args: str = "", *, session_key: str = "", session_id: str = "") -> str:
        token = _caller.set((str(session_key or ""), str(session_id or "")))
        try:
            return fn((raw_args or "").strip())
        except lifecycle.LifecycleError as exc:
            return f"spawn-session: {exc}"
        except Exception as exc:  # a slash command must never crash the host
            logger.exception("spawn-session command failed")
            return f"spawn-session: internal error: {exc}"
        finally:
            _caller.reset(token)

    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped


REPORT_PROMPT = (
    "Please finish up and call the `report_back` tool now with a complete structured report: "
    "`result` (what was achieved), `changes` (list), `open_items` (list) and `artifacts` "
    "(paths, commits, branches, URLs, PRs as {kind, value})."
)


@_guard
def cmd_report(note: str) -> str:
    """/report [note] — ask B's agent to call report_back."""
    path = _child_handover()
    from .handover import read

    h = read(path)
    if h.status in ("abandoned", "detached"):
        raise lifecycle.LifecycleError(f"this session is {h.status}; report-back is cancelled")
    text = REPORT_PROMPT + (f"\n\nGuidance from the user: {note}" if note else "")
    sid = _current_session()
    if not delivery._inject(text, sid):
        raise lifecycle.LifecycleError("could not queue the report request in this session")
    return "Report requested: the agent will call report_back on its next turn."


@_guard
def cmd_abandon(reason: str) -> str:
    """/abandon [reason] — D11 abort."""
    res = lifecycle.abandon(_child_handover(), reason=reason or None, by="user", settings=_settings())
    lines = [f"Abandoned {res['handover_id']}; the parent was "
             + ("notified." if res.get("parent_notified") else "not live (notice kept for later).")]
    if res.get("question"):
        lines.append(res["question"])
    return "\n".join(lines)


@_guard
def cmd_detach(arg: str) -> str:
    """/detach confirm — D11 detach (irreversible)."""
    if arg.lower() not in ("confirm", "yes", "--yes"):
        return ("Detach is irreversible: this session continues independently, no report is "
                "sent back and it cannot be re-attached. Run `/detach confirm` to proceed.")
    res = lifecycle.detach(_child_handover(), by="user", settings=_settings())
    return f"Detached {res['handover_id']}; title is now {res['title']!r}."


@_guard
def cmd_spawn_cleanup(arg: str) -> str:
    """/spawn-cleanup <handover_id> yes|no — answer the worktree-removal question."""
    parts = arg.split()
    if len(parts) != 2 or parts[1].lower() not in ("yes", "no"):
        return "Usage: /spawn-cleanup <handover_id> yes|no"
    path = lifecycle.find_by_handover_id(_load_index(), parts[0])
    res = lifecycle.cleanup_worktree(path, confirm=parts[1].lower() == "yes")
    return (f"Removed worktree {res['worktree']} and its branch." if res["removed"]
            else f"Kept worktree {res['worktree']}.")


COMMANDS: dict[str, tuple[Callable[..., str], str, str]] = {
    "report": (cmd_report, "Spawned session: ask the agent to report back to the parent", "[note]"),
    "abandon": (cmd_abandon, "Spawned session: abort and notify the parent", "[reason]"),
    "detach": (cmd_detach, "Spawned session: detach from the parent (irreversible)", "confirm"),
    "spawn-cleanup": (cmd_spawn_cleanup, "Remove or keep an abandoned child's worktree",
                      "<handover_id> yes|no"),
}


# --------------------------------------------------------------------------- backend actions


def action_abandon(handover_id: str, reason: Optional[str] = None) -> dict[str, Any]:
    path = lifecycle.find_by_handover_id(_load_index(), handover_id)
    return lifecycle.abandon(path, reason=reason, by="user", settings=_settings())


def action_detach(handover_id: str) -> dict[str, Any]:
    path = lifecycle.find_by_handover_id(_load_index(), handover_id)
    return lifecycle.detach(path, by="user", settings=_settings())


def action_deliver_pending(parent_session_id: str) -> dict[str, Any]:
    index = _load_index()
    return delivery.deliver_pending(index.handovers_for_parent(parent_session_id), parent_session_id,
                                    timeout_s=_settings().delivery_confirm_timeout_s)


def as_json(fn: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> str:
    try:
        return json.dumps(fn(*args, **kwargs))
    except lifecycle.LifecycleError as exc:
        return json.dumps({"ok": False, "error": str(exc)})
