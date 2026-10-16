"""REST backend for the spawn-session desktop half (SPEC section 3/7).

Mounted by Hermes under ``/api/plugins/spawn-session/`` when ``spawn-session``
is in ``plugins.enabled`` (desktop-plugin-sdk docs, "A backend for your
plugin"). The desktop half reaches it with ``ctx.rest('/…')``.

Routes (this card, t_8fdde1ac):
- ``GET  /defaults?session_id=``  — picker defaults (A's model/effort), child flag
- ``POST /spawn``                 — ⌘K user spawn (immediate start)
- ``GET  /proposals?session_id=`` — ``proposed`` handovers of A (cards)
- ``POST /confirm``               — Start a proposal (with optional edits)
- ``POST /dismiss``               — Dismiss a proposal

Routes (card t_1f857d7f, D8/D9/D11):
- ``GET  /children?session_id=``  — status cards in A + open-report count
- ``GET  /child?session_id=``     — B's header (parent link, Task, Context)
- ``GET  /tree``                  — child -> parent map for sidebar badges
- ``POST /abort``                 — Abort a child from A's card
- ``POST /detach``                — Detach a child (``confirm: true`` required)
- ``POST /deliver``               — deliver open reports/notices to A

The file is imported by path (not as part of the plugin package), so the
plugin root is put on ``sys.path`` to import the ``spawn_session`` package.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import APIRouter, Body, HTTPException  # noqa: E402

from spawn_session import desktop, gateway, parent as parent_mod, tools  # noqa: E402
from spawn_session.handover import HandoverError  # noqa: E402
from spawn_session.worktree import WorktreeError  # noqa: E402

router = APIRouter()


def _call(fn, *args: Any) -> Any:
    try:
        return fn(*args)
    except desktop.NotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (desktop.DesktopError, tools.SpawnError, HandoverError, WorktreeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except parent_mod.ParentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except gateway.GatewayError as exc:
        raise HTTPException(status_code=502, detail=f"gateway error: {exc}") from exc


# Sync handlers: FastAPI runs them in a worker thread, so blocking file I/O and
# the in-process gateway RPC never stall the event loop.


@router.get("/defaults")
def defaults(session_id: str) -> dict[str, Any]:
    return _call(desktop.spawn_defaults, session_id)


@router.post("/spawn")
def spawn(body: dict = Body(...)) -> dict[str, Any]:
    return _call(desktop.user_spawn, body)


@router.get("/proposals")
def proposals(session_id: str) -> dict[str, Any]:
    return {"proposals": _call(desktop.list_proposals, session_id)}


@router.post("/confirm")
def confirm(body: dict = Body(...)) -> dict[str, Any]:
    return _call(desktop.confirm_proposal, body)


@router.post("/dismiss")
def dismiss(body: dict = Body(...)) -> dict[str, Any]:
    return _call(desktop.dismiss_proposal, body)


@router.get("/children")
def children(session_id: str) -> dict[str, Any]:
    return _call(desktop.list_children, session_id)


@router.get("/child")
def child(session_id: str) -> dict[str, Any]:
    return _call(desktop.child_info, session_id)


@router.get("/tree")
def tree() -> dict[str, Any]:
    return _call(desktop.session_tree)


@router.post("/abort")
def abort(body: dict = Body(...)) -> dict[str, Any]:
    return _call(desktop.abort_child, body)


@router.post("/detach")
def detach(body: dict = Body(...)) -> dict[str, Any]:
    return _call(desktop.detach_child, body)


@router.post("/deliver")
def deliver(body: dict = Body(...)) -> dict[str, Any]:
    return _call(desktop.deliver_open_reports, body)
