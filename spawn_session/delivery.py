"""Report / notice delivery into the parent session A (SPEC Q4, decisions D4/D8/D11).

Delivery uses the documented plugin host API ``ctx.inject_message(text,
session_key=<A durable id>)``. On the Desktop/TUI host Hermes queues the text
on A's prompt queue: a busy A keeps it for the next turn, an idle A starts a
turn (docs: user-guide/features/plugins#injecting-messages). ``True`` only
means "accepted", so the handover moves to ``delivered`` only after the
injected text is visible in A's persisted history (polled in ``state.db``).

When A is not live (closed tab, process gone) ``inject_message`` returns
``False``; the handover then simply stays ``reported`` and
:func:`deliver_pending` (desktop "N open report(s)" -> Deliver, card 6)
retries later. Abort / detach notices that could not be delivered are kept in
the frontmatter under ``pending_notices`` and retried the same way.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import gateway
from . import parent as parent_mod
from .handover import Handover, HandoverError, read as handover_read, update_status, write as handover_write

logger = logging.getLogger("hermes.spawn-session")

# Seam: retitle a session (detach writes ``pending_title`` when it failed).
_set_title: Callable[[str, str], dict] = gateway.set_session_title

# --------------------------------------------------------------------------- seams

_plugin_ctx: Any = None


def set_plugin_context(ctx: Any) -> None:
    """Remember the PluginContext from ``register(ctx)`` (needed for inject_message)."""
    global _plugin_ctx
    _plugin_ctx = ctx


def _registered_context() -> Any:
    """The PluginContext, also when this module is a second copy.

    Hermes imports the plugin as ``hermes_plugins.<slug>`` and calls
    ``register(ctx)`` there, but ``dashboard/plugin_api.py`` is imported by
    path and reaches this package as top-level ``spawn_session``. Both copies
    live in the same process, so the REST routes look the context up on the
    copy that ``register`` filled in.
    """
    if _plugin_ctx is not None:
        return _plugin_ctx
    import sys

    for name, mod in list(sys.modules.items()):
        if mod is None or mod is sys.modules.get(__name__) or not name.endswith(".spawn_session.delivery"):
            continue
        ctx = getattr(mod, "_plugin_ctx", None)
        if ctx is not None:
            return ctx
    return None


def _default_inject(text: str, session_key: str) -> bool:
    ctx = _registered_context()
    if ctx is None or not hasattr(ctx, "inject_message"):
        logger.warning("inject_message unavailable (plugin context not registered)")
        return False
    try:
        return bool(ctx.inject_message(text, role="user", session_key=session_key))
    except Exception:
        logger.exception("inject_message failed for session %s", session_key)
        return False


def _default_history_contains(session_id: str, marker: str) -> bool:
    """True when a user message starting with ``marker`` is persisted.

    Searches A and its compression continuations (sessions whose
    ``parent_session_id`` chain leads to A): compression may rotate A's id
    while the report waits in the queue.
    """
    path = parent_mod.state_db_path()
    if not path.exists():
        return False
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return False
    try:
        ids = {session_id}
        frontier = [session_id]
        for _ in range(5):
            if not frontier:
                break
            q = ",".join("?" * len(frontier))
            rows = conn.execute(
                f"SELECT id FROM sessions WHERE parent_session_id IN ({q})", frontier
            ).fetchall()
            frontier = [str(r[0]) for r in rows if str(r[0]) not in ids]
            ids.update(frontier)
        q = ",".join("?" * len(ids))
        row = conn.execute(
            f"SELECT 1 FROM messages WHERE role = 'user' AND session_id IN ({q}) "
            "AND content LIKE ? LIMIT 1",
            [*ids, marker.replace("%", r"\%") + "%"],
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def _default_start_thread(target: Callable[..., None], *args: Any) -> None:
    threading.Thread(target=target, args=args, daemon=True, name="spawn-session-deliver").start()


_inject: Callable[[str, str], bool] = _default_inject
_history_contains: Callable[[str, str], bool] = _default_history_contains
_start_thread: Callable[..., None] = _default_start_thread
_sleep: Callable[[float], None] = time.sleep
_POLL_INTERVAL_S = 2.0


# --------------------------------------------------------------------------- formatting


def report_marker(h: Handover, index: Optional[int] = None) -> str:
    """Unique first line of a report message in A (SPEC section 5)."""
    i = index or len(h.reports)
    suffix = "" if i <= 1 else f", report {i}"
    return f"[spawn-session report: {h.title} ({h.handover_id}{suffix})]"


def report_message(h: Handover, index: Optional[int] = None) -> str:
    """Message injected into A for report ``index`` (1-based, default latest)."""
    i = index or len(h.reports)
    body = h.reports[i - 1].strip() if h.reports else "-"
    footer = (
        f"\n\n(Child session {h.meta.get('child_session_id') or '?'}; handover file "
        f"{h.path}. Review the report and continue the parent task.)"
    )
    return f"{report_marker(h, i)}\n{body}{footer}"


# --------------------------------------------------------------------------- reports


def deliver_report(path: Path | str, *, settings_timeout_s: int = 120) -> dict[str, Any]:
    """Inject the latest report of handover ``path`` into its parent A.

    Returns ``{"queued": bool, "parent_session_id": ..., "marker": ...}``.
    ``queued=False`` means A is not live: status stays ``reported`` (D8).
    On acceptance a background watcher flips the status to ``delivered`` once
    the message is in A's history (or leaves it ``reported`` after the timeout).
    """
    h = handover_read(path)
    parent_id = str(h.meta.get("parent_session_id") or "")
    if h.status != "reported" or not parent_id or not h.reports:
        return {"queued": False, "parent_session_id": parent_id, "reason": f"status {h.status}"}
    report_index = len(h.reports)
    marker = report_marker(h, report_index)
    if _history_contains(parent_id, marker):
        _mark_delivered(Path(path), report_index)  # already there (earlier attempt)
        return {"queued": True, "parent_session_id": parent_id, "marker": marker, "confirmed": True}
    ok = _inject(report_message(h, report_index), parent_id)
    if not ok:
        logger.info("parent %s not live; report %s stays 'reported'", parent_id, h.handover_id)
        return {"queued": False, "parent_session_id": parent_id, "marker": marker,
                "reason": "parent session not live; report kept for later delivery"}
    _start_thread(_confirm_delivery, Path(path), parent_id, marker, report_index, settings_timeout_s)
    return {"queued": True, "parent_session_id": parent_id, "marker": marker}


def _confirm_delivery(path: Path, parent_id: str, marker: str, report_index: int, timeout_s: int) -> None:
    polls = max(1, int(timeout_s / _POLL_INTERVAL_S))
    for attempt in range(polls + 1):
        if _history_contains(parent_id, marker):
            _mark_delivered(path, report_index)
            return
        if attempt < polls:
            _sleep(_POLL_INTERVAL_S)
    logger.warning("report %s not confirmed in parent %s within %ss; stays 'reported'",
                   path, parent_id, timeout_s)


def _mark_delivered(path: Path, report_index: int) -> None:
    try:
        h = handover_read(path)
        # A newer follow-up report may have been appended meanwhile; only the
        # latest one being visible means everything was delivered.
        if h.status != "reported" or len(h.reports) != report_index:
            return
        update_status(path, "delivered", by="plugin")
        _sync_index_status(path, "delivered")
    except HandoverError:
        logger.exception("could not mark %s delivered", path)


def _sync_index_status(path: Path, status: str) -> None:
    try:
        from .state import load_index

        load_index().set_status(path, status)
    except Exception:
        logger.debug("state index status sync skipped for %s", path)


# --------------------------------------------------------------------------- notices


def send_notice(path: Path | str, text: str) -> bool:
    """Inject a one-off notice (abort report / detach line) into A.

    Undeliverable notices are persisted in ``pending_notices`` for
    :func:`deliver_pending`.
    """
    h = handover_read(path)
    parent_id = str(h.meta.get("parent_session_id") or "")
    if parent_id and _inject(text, parent_id):
        return True
    h.meta.setdefault("pending_notices", []).append(text)
    handover_write(h)
    return False


def deliver_pending(handover_paths: list[Path], parent_session_id: str, *, timeout_s: int = 120) -> dict[str, Any]:
    """Retry delivery of everything still open for ``parent_session_id``.

    Backend action behind the desktop "N open report(s) -> Deliver" banner.
    """
    out: dict[str, Any] = {"reports": [], "notices": 0, "titles": 0}
    for p in handover_paths:
        try:
            h = handover_read(p)
        except HandoverError:
            continue
        if h.meta.get("parent_session_id") != parent_session_id:
            continue
        notices = list(h.meta.get("pending_notices") or [])
        if notices:
            remaining = [n for n in notices if not _inject(n, parent_session_id)]
            out["notices"] += len(notices) - len(remaining)
            h.meta["pending_notices"] = remaining or None
            if not remaining:
                h.meta.pop("pending_notices", None)
            handover_write(h)
        pending_title = h.meta.get("pending_title")
        child = h.meta.get("child_session_id")
        if pending_title and child:
            # D11: a detach whose retitle failed (B not live) is retried here.
            try:
                _set_title(str(child), str(pending_title))
            except gateway.GatewayError as exc:
                logger.info("pending title for %s still not applied: %s", child, exc)
            else:
                h.meta.pop("pending_title", None)
                handover_write(h)
                out["titles"] += 1
        if h.status == "reported":
            res = deliver_report(p, settings_timeout_s=timeout_s)
            out["reports"].append({"handover_id": h.handover_id, **res})
    return out
