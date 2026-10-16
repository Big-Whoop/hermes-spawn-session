"""Desktop-facing service layer (SPEC section 7, decisions D2/D3/D6/D10).

The desktop half (``desktop/plugin.js``) talks to these functions through the
REST backend in ``dashboard/plugin_api.py``. They are plain functions so they
can be unit-tested without FastAPI or a running gateway.

- :func:`user_spawn` — ⌘K "Spawn session with report": user-initiated, starts
  immediately (no cost/cap confirmation: the user is the confirmer, D6/D10 —
  user spawns are unlimited), refused when the focused session is a child (D10).
- :func:`list_proposals` — ``proposed`` handovers of a parent session (the
  confirmation cards for agent ``own_initiative`` proposals, D3).
- :func:`confirm_proposal` — Start (optionally with the user's edits of title,
  task, context, model, effort): ``proposed`` -> ``running`` and B is created.
- :func:`dismiss_proposal` — Dismiss: ``proposed`` -> ``abandoned``.
- :func:`spawn_defaults` — A's model/effort (picker default, D6) and whether
  the session is a spawned child (⌘K blocked, AT5.5).
- :func:`list_children` — status cards in A + "N open report(s)" count (D8/D9).
- :func:`child_info` — B's header: parent link, Task, Context (D9).
- :func:`session_tree` — child -> parent map for sidebar row badges (D9/Q3).
- :func:`abort_child` / :func:`detach_child` — status-card buttons (D11).
- :func:`deliver_open_reports` — deliver-on-click of undelivered reports (D8).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from . import parent as parent_mod, state as state_mod, tools
from .handover import HandoverError, create as handover_create, read as handover_read, slugify
from .handover import update_status, write as handover_write

logger = logging.getLogger("hermes.spawn-session")

EFFORTS = ("low", "medium", "high", "xhigh")


class DesktopError(ValueError):
    """Invalid desktop request (maps to HTTP 400)."""


class NotFound(LookupError):
    """Unknown handover (maps to HTTP 404)."""


# --------------------------------------------------------------------------- helpers


def _lineage(session_id: str) -> list[str]:
    try:
        ids = tools._lineage_ids(session_id)
    except Exception:
        ids = [session_id]
    return ids or [session_id]


def _parent_ids(session_id: str) -> set[str]:
    """Ids that identify the same parent conversation as ``session_id``.

    The Desktop hands us the durable (lineage-root) id; the agent tool records
    the id of the live segment. Both are ancestors-or-self of each other, so a
    proposal matches when its parent id is in the lineage of ``session_id`` or
    ``session_id`` is in the lineage of its parent id.
    """
    return set(_lineage(session_id))


def _matches_parent(meta_parent: Any, session_id: str, own_lineage: set[str]) -> bool:
    if not isinstance(meta_parent, str) or not meta_parent:
        return False
    if meta_parent in own_lineage:
        return True
    return session_id in set(_lineage(meta_parent))


def _all_handover_files() -> list[Path]:
    index = tools._load_index()
    return state_mod._find_handover_files(index.path)


def _find_handover(handover_id: str) -> Path:
    if not isinstance(handover_id, str) or not handover_id.startswith("hs_"):
        raise DesktopError("invalid handover_id")
    for path in _all_handover_files():
        try:
            h = handover_read(path)
        except Exception:
            continue
        if h.meta.get("handover_id") == handover_id:
            return path
    raise NotFound(f"no handover {handover_id}")


def _clean_str(value: Any, name: str, *, required: bool, max_len: Optional[int] = None) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise DesktopError(f"{name} must be a string")
    value = value.strip()
    if required and not value:
        raise DesktopError(f"{name} is required")
    if max_len is not None and len(value) > max_len:
        raise DesktopError(f"{name} must be at most {max_len} characters")
    return value


def _clean_effort(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if value not in EFFORTS:
        raise DesktopError(f"effort must be one of {', '.join(EFFORTS)}")
    return str(value)


def _clean_model(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise DesktopError("model must be a 'provider:model' string")
    try:
        tools.split_model_ref(value)
    except tools.SpawnError as exc:
        raise DesktopError(str(exc)) from exc
    return value.strip()


def _proposal_view(h: Any) -> dict[str, Any]:
    meta = h.meta
    return {
        "handover_id": meta.get("handover_id"),
        "parent_session_id": meta.get("parent_session_id"),
        "title": meta.get("title"),
        "task": h.task,
        "context": h.context,
        "model": meta.get("model"),
        "effort": meta.get("effort"),
        "initiation": meta.get("initiation"),
        "initiator": meta.get("initiator"),
        "worktree_requested": bool(meta.get("worktree_requested")),
        "reasons": list(meta.get("proposal_reasons") or []),
        "created_at": meta.get("created_at"),
        "handover_path": str(h.path) if h.path else None,
    }


def _is_child(index: state_mod.StateIndex, *session_ids: str) -> bool:
    """D10: any of the given ids (requested id, resolved row id) is a spawned child."""
    return any(sid and tools._child_in_lineage(index, sid) is not None for sid in session_ids)


def _resolve_desktop_parent(session_id: str) -> parent_mod.ParentContext:
    if not isinstance(session_id, str) or not session_id.strip():
        raise DesktopError("session_id is required")
    try:
        return tools._resolve_parent(session_id.strip())
    except parent_mod.ParentNotFound as exc:
        raise NotFound(f"cannot resolve session: {exc}") from exc


# --------------------------------------------------------------------------- API


def spawn_defaults(session_id: str) -> dict[str, Any]:
    """Picker defaults for the ⌘K dialog: A's model/effort + child flag."""
    a = _resolve_desktop_parent(session_id)
    index = tools._load_index()
    is_child = _is_child(index, session_id.strip(), a.session_id)
    return {
        "session_id": a.session_id,
        "title": a.title,
        "model": a.model_ref if ":" in a.model_ref else None,
        "effort": a.effort,
        "cwd": a.cwd,
        "source": a.source,
        "is_child": is_child,
        "can_spawn": (not is_child) and a.source in tools.DESKTOP_SOURCES,
    }


def user_spawn(body: dict[str, Any]) -> dict[str, Any]:
    """⌘K spawn: create a user-initiated, immediately running child of A."""
    session_id = body.get("session_id")
    a = _resolve_desktop_parent(session_id)  # type: ignore[arg-type]
    if a.source not in tools.DESKTOP_SOURCES:
        raise DesktopError(tools.D13_MESSAGE)
    index = tools._load_index()
    if _is_child(index, str(session_id).strip(), a.session_id):
        raise DesktopError(tools.D10_MESSAGE)

    title = _clean_str(body.get("title"), "title", required=True, max_len=80)
    task = _clean_str(body.get("task"), "task", required=True)
    context = _clean_str(body.get("context"), "context", required=False)
    model_ref = _clean_model(body.get("model"))
    if model_ref is None:
        if ":" not in a.model_ref:
            raise DesktopError(
                "the parent session's provider could not be resolved; pick a model explicitly"
            )
        model_ref = a.model_ref
    effort = _clean_effort(body.get("effort"))
    if effort is None:
        effort = a.effort
    provider, _ = tools.split_model_ref(model_ref)

    settings = tools._settings()
    base_cwd = a.cwd or None
    child_cwd = base_cwd
    wt_info: Optional[dict[str, str]] = None
    if bool(body.get("worktree", False)):
        repo_root = a.git_repo_root or (str(tools._find_repo_root(base_cwd)) if base_cwd else None)
        if not repo_root:
            raise DesktopError("worktree requested but the parent session has no git repository")
        wt = tools._create_worktree(
            repo_root, slugify(title),
            worktree_dir=settings.worktree_dir, branch_prefix=settings.branch_prefix,
        )
        wt_info = {"path": wt.path, "branch": wt.branch}
        child_cwd = wt.path

    project_meta, _, kanban_board = tools.plan_project(base_cwd, child_cwd, None)
    h = handover_create(
        tools._handover_base_dir(a.cwd),
        title=title,
        task=task,
        context=context,
        parent_session_id=a.session_id,
        model=model_ref,
        provider=provider,
        effort=effort,
        cwd=child_cwd,
        status="running",
        initiation="user_asked",
        initiator="user",
        worktree=wt_info,
        kanban_board=kanban_board,
        project=project_meta,
    )
    assert h.path is not None
    try:
        index.register_handover_root(Path(h.path).parent)
    except OSError:
        logger.warning("could not record handover root %s", Path(h.path).parent)
    return tools.start_child(h, index=index, settings=settings, parent_source=a.source, by="user")


def list_proposals(session_id: str) -> list[dict[str, Any]]:
    """``proposed`` handovers whose parent is ``session_id`` (newest first)."""
    if not isinstance(session_id, str) or not session_id.strip():
        raise DesktopError("session_id is required")
    session_id = session_id.strip()
    own = _parent_ids(session_id)
    out: list[dict[str, Any]] = []
    for path in _all_handover_files():
        try:
            h = handover_read(path)
        except Exception:
            continue
        if h.meta.get("status") != "proposed":
            continue
        if _matches_parent(h.meta.get("parent_session_id"), session_id, own):
            out.append(_proposal_view(h))
    out.sort(key=lambda p: str(p.get("created_at") or ""), reverse=True)
    return out


def confirm_proposal(body: dict[str, Any]) -> dict[str, Any]:
    """Start: apply the user's edits, ``proposed`` -> ``running``, create B."""
    path = _find_handover(body.get("handover_id"))  # type: ignore[arg-type]
    h = handover_read(path)
    if h.status != "proposed":
        raise DesktopError(f"handover is {h.status}, not proposed")

    edits: dict[str, Any] = {}
    if body.get("title") is not None:
        edits["title"] = _clean_str(body.get("title"), "title", required=True, max_len=80)
    if body.get("task") is not None:
        edits["task"] = _clean_str(body.get("task"), "task", required=True)
    if body.get("context") is not None:
        edits["context"] = _clean_str(body.get("context"), "context", required=False)
    model_ref = _clean_model(body.get("model"))
    effort = _clean_effort(body.get("effort"))

    try:
        a = tools._resolve_parent(h.meta["parent_session_id"])
        parent_source = a.source
        git_root = a.git_repo_root
    except parent_mod.ParentNotFound:
        parent_source, git_root = "desktop", None

    settings = tools._settings()
    if "title" in edits:
        h.meta["title"] = edits["title"]
    if "task" in edits:
        h.task = edits["task"]
    if "context" in edits:
        h.context = edits["context"]
    if model_ref is not None:
        h.meta["model"] = model_ref
        h.meta["provider"] = tools.split_model_ref(model_ref)[0]
    if effort is not None:
        h.meta["effort"] = effort

    # D7: a proposal never touched the repo; the worktree is created on Start.
    if h.meta.get("worktree_requested") and not h.meta.get("worktree"):
        base_cwd = h.meta.get("cwd")
        if not git_root and not base_cwd:
            raise DesktopError("worktree requested but the handover has no working directory")
        repo_root = git_root or str(tools._find_repo_root(str(base_cwd)))
        wt = tools._create_worktree(
            repo_root, slugify(h.title),
            worktree_dir=settings.worktree_dir, branch_prefix=settings.branch_prefix,
        )
        h.meta["worktree"] = {"path": wt.path, "branch": wt.branch}
        h.meta["cwd"] = wt.path
        # D7: the project assignment was planned for A's cwd; re-plan for the
        # worktree (the board stays as recorded in the proposal).
        if h.meta.get("project"):
            project_meta, toolsets, _ = tools.plan_project(
                str(base_cwd) if base_cwd else None, wt.path, h.meta.get("allowed_toolsets"))
            h.meta["project"] = project_meta
            h.meta["allowed_toolsets"] = toolsets
    handover_write(h)
    update_status(path, "running", by="user", reason="confirmed in desktop card")
    h = handover_read(path)
    index = tools._load_index()
    return tools.start_child(h, index=index, settings=settings, parent_source=parent_source, by="user")


def _parent_title(parent_session_id: Any) -> Optional[str]:
    if not isinstance(parent_session_id, str) or not parent_session_id:
        return None
    try:
        return tools._resolve_parent(parent_session_id).title or None
    except Exception:
        return None


def _open_report_count(h: Any) -> int:
    """Undelivered items for A: a ``reported`` report plus kept notices (D8)."""
    n = 1 if h.status == "reported" else 0
    return n + len(h.meta.get("pending_notices") or [])


def _child_view(h: Any) -> dict[str, Any]:
    meta = h.meta
    wt = meta.get("worktree") if isinstance(meta.get("worktree"), dict) else None
    return {
        "handover_id": meta.get("handover_id"),
        "parent_session_id": meta.get("parent_session_id"),
        "child_session_id": meta.get("child_session_id"),
        "title": meta.get("title"),
        "status": h.status,
        "initiator": meta.get("initiator"),
        "model": meta.get("model"),
        "effort": meta.get("effort"),
        "reports": len(h.reports),
        "open_reports": _open_report_count(h),
        "worktree": {"path": wt.get("path"), "branch": wt.get("branch")} if wt else None,
        "worktree_cleanup": meta.get("worktree_cleanup"),
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
        "handover_path": str(h.path) if h.path else None,
    }


def _handovers_of_parent(session_id: str) -> list[tuple[Path, Any]]:
    if not isinstance(session_id, str) or not session_id.strip():
        raise DesktopError("session_id is required")
    session_id = session_id.strip()
    own = _parent_ids(session_id)
    out: list[tuple[Path, Any]] = []
    for path in _all_handover_files():
        try:
            h = handover_read(path)
        except Exception:
            continue
        if _matches_parent(h.meta.get("parent_session_id"), session_id, own):
            out.append((path, h))
    return out


def list_children(session_id: str) -> dict[str, Any]:
    """Status cards in A (D9): every started child of ``session_id``.

    ``proposed`` handovers are excluded (they are the confirmation cards).
    ``open_reports`` is the total for the "N open report(s)" notice (D8).
    """
    children = [_child_view(h) for _, h in _handovers_of_parent(session_id)
                if h.status != "proposed"]
    children.sort(key=lambda c: str(c.get("created_at") or ""), reverse=True)
    return {"children": children, "open_reports": sum(c["open_reports"] for c in children)}


def child_info(session_id: str) -> dict[str, Any]:
    """Header in B (D9): parent link, Task and Context; ``is_child`` False otherwise."""
    if not isinstance(session_id, str) or not session_id.strip():
        raise DesktopError("session_id is required")
    index = tools._load_index()
    child_id = tools._child_in_lineage(index, session_id.strip())
    path = index.handover_for(child_id) if child_id else None
    if path is None:
        return {"is_child": False}
    h = handover_read(path)
    parent_id = h.meta.get("parent_session_id")
    return {
        "is_child": True,
        "handover_id": h.handover_id,
        "status": h.status,
        "detached": h.status == "detached",
        "title": h.title,
        "parent_session_id": parent_id,
        "parent_title": _parent_title(parent_id),
        "task": h.task,
        "context": h.context,
        "model": h.meta.get("model"),
    }


def session_tree() -> dict[str, Any]:
    """Child session id -> parent link, for sidebar row decorations (D9 / Q3)."""
    index = tools._load_index()
    out: dict[str, dict[str, Any]] = {}
    seen: dict[str, Any] = {}
    for sid, entry in index.children.items():
        p = entry.get("handover_path")
        if not isinstance(p, str):
            continue
        if p not in seen:
            try:
                seen[p] = handover_read(p)
            except Exception:
                seen[p] = None
        h = seen[p]
        if h is None:
            continue
        out[sid] = {
            "parent_session_id": h.meta.get("parent_session_id"),
            "handover_id": h.handover_id,
            "status": h.status,
            "title": h.title,
        }
    return {"children": out}


def abort_child(body: dict[str, Any]) -> dict[str, Any]:
    """Abort button on A's status card (D11)."""
    from . import lifecycle

    path = _find_handover(body.get("handover_id"))  # type: ignore[arg-type]
    reason = body.get("reason")
    reason = reason.strip() if isinstance(reason, str) and reason.strip() else "aborted from the parent's status card"
    try:
        res = lifecycle.abandon(path, reason=reason, by="user", settings=tools._settings())
    except lifecycle.LifecycleError as exc:
        raise DesktopError(str(exc)) from exc
    tools._broadcast_event("child.status", {"handover_id": res["handover_id"], "status": res["status"]})
    return res


def detach_child(body: dict[str, Any]) -> dict[str, Any]:
    """Detach button on A's status card (D11, irreversible)."""
    from . import lifecycle

    if body.get("confirm") is not True:
        raise DesktopError("detach is irreversible; resend with confirm=true")
    path = _find_handover(body.get("handover_id"))  # type: ignore[arg-type]
    try:
        res = lifecycle.detach(path, by="user", settings=tools._settings())
    except lifecycle.LifecycleError as exc:
        raise DesktopError(str(exc)) from exc
    tools._broadcast_event("child.status", {"handover_id": res["handover_id"], "status": res["status"]})
    return res


def deliver_open_reports(body: dict[str, Any]) -> dict[str, Any]:
    """"N open report(s) -> Deliver" (D8): retry everything open for A."""
    from . import delivery

    session_id = body.get("session_id")
    groups: dict[str, list[Path]] = {}
    for path, h in _handovers_of_parent(session_id):  # type: ignore[arg-type]
        if _open_report_count(h):
            groups.setdefault(str(h.meta.get("parent_session_id")), []).append(path)
    out: dict[str, Any] = {"reports": [], "notices": 0}
    timeout = tools._settings().delivery_confirm_timeout_s
    for parent_id, paths in groups.items():
        res = delivery.deliver_pending(paths, parent_id, timeout_s=timeout)
        out["reports"].extend(res["reports"])
        out["notices"] += res["notices"]
    out["queued"] = sum(1 for r in out["reports"] if r.get("queued"))
    return out


def dismiss_proposal(body: dict[str, Any]) -> dict[str, Any]:
    """Dismiss: ``proposed`` -> ``abandoned`` (no session is ever created)."""
    path = _find_handover(body.get("handover_id"))  # type: ignore[arg-type]
    reason = body.get("reason")
    current = handover_read(path)
    if current.status != "proposed":
        raise DesktopError(f"handover is {current.status}, not proposed")
    try:
        h = update_status(
            path, "abandoned", by="user",
            reason=str(reason) if isinstance(reason, str) and reason.strip() else "dismissed in desktop card",
        )
    except HandoverError as exc:
        raise DesktopError(str(exc)) from exc
    tools._broadcast_event("child.dismissed", {
        "handover_id": h.handover_id,
        "parent_session_id": h.meta.get("parent_session_id"),
    })
    return {"ok": True, "handover_id": h.handover_id, "status": h.status}
