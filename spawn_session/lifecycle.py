"""Report-back, abort and detach lifecycle for spawned children (SPEC 4.2/4.3/6, D4/D8/D11).

Entry points shared by the ``report_back`` tool, the ``/report``,
``/abandon``, ``/detach`` slash commands in B and the backend actions behind
A's status-card buttons (desktop half, later card):

- :func:`report` — append a structured report, status ``reported``, deliver to A.
- :func:`abandon` — status ``abandoned``, bank worktree changes, abort report
  to A, archive B (never delete), leave worktree removal to the user.
- :func:`detach` — status ``detached`` (irreversible), title prefix, one-line
  notice to A; B stays indexed as a child so the D10 spawn ban still applies.
- :func:`cleanup_worktree` — remove worktree + branch, only on explicit
  user confirmation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from . import delivery, gateway, state as state_mod, worktree as wt_mod
from .config import Settings
from .handover import (
    Handover,
    HandoverError,
    append_report,
    format_report,
    read as handover_read,
    update_status,
    write as handover_write,
)

logger = logging.getLogger("hermes.spawn-session")

ARTIFACT_KINDS = ("path", "commit", "branch", "url", "pr")

# Seams (tests replace these).
_bank_changes: Callable[..., wt_mod.BankResult] = wt_mod.bank_changes
_remove_worktree: Callable[..., None] = wt_mod.remove_worktree
_find_repo_root: Callable[[str | Path], Path] = wt_mod.find_repo_root
_archive_session: Callable[[str], dict] = gateway.archive_session
_set_title: Callable[[str, str], dict] = gateway.set_session_title


class LifecycleError(ValueError):
    """Request refused (wrong session, wrong status, bad arguments)."""


# --------------------------------------------------------------------------- formatting


def _bullets(items: Any, field: str) -> Optional[str]:
    if items is None:
        return None
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        raise LifecycleError(f"{field} must be a list of strings")
    cleaned = [i.strip() for i in items if i.strip()]
    return "\n".join(f"- {i}" for i in cleaned) or None


def _artifact_lines(artifacts: Any) -> Optional[str]:
    if artifacts is None:
        return None
    if not isinstance(artifacts, list):
        raise LifecycleError("artifacts must be a list of {kind, value} objects")
    lines = []
    for a in artifacts:
        if not isinstance(a, dict) or not isinstance(a.get("value"), str) or not a["value"].strip():
            raise LifecycleError("each artifact needs a non-empty string 'value'")
        kind = a.get("kind")
        if kind not in ARTIFACT_KINDS:
            raise LifecycleError(f"artifact kind must be one of {', '.join(ARTIFACT_KINDS)}")
        lines.append(f"- {kind}: {a['value'].strip()}")
    return "\n".join(lines) or None


def build_report(args: dict[str, Any], h: Optional[Handover] = None) -> str:
    """Structured report body (Result / Changes / Open items / Artifacts).

    The child's worktree branch is added as an artifact when the child did not
    list it itself (D7: "report lists branch/commits").
    """
    result = args.get("result")
    if not isinstance(result, str) or not result.strip():
        raise LifecycleError("result is required (non-empty string)")
    raw_artifacts = args.get("artifacts")
    artifacts = list(raw_artifacts) if isinstance(raw_artifacts, list) else (
        [] if raw_artifacts is None else raw_artifacts)
    wt = (h.meta.get("worktree") if h is not None else None) or None
    if isinstance(wt, dict) and wt.get("branch") and isinstance(artifacts, list):
        if not any(isinstance(a, dict) and a.get("kind") == "branch" and a.get("value") == wt["branch"]
                   for a in artifacts):
            artifacts.append({"kind": "branch", "value": wt["branch"]})
    return format_report(
        result.strip(),
        _bullets(args.get("changes"), "changes"),
        _bullets(args.get("open_items"), "open_items"),
        _artifact_lines(artifacts if artifacts else None),
    )


# --------------------------------------------------------------------------- lookup


def handover_for_session(index: state_mod.StateIndex, session_id: str,
                         lineage: Callable[[str], list[str]]) -> Path:
    """Handover file of the spawned child ``session_id`` (or a continuation of it)."""
    try:
        ids = lineage(session_id) or [session_id]
    except Exception:
        ids = [session_id]
    for sid in ids:
        path = index.handover_for(sid)
        if path is not None:
            return path
    raise LifecycleError("this command is only available in a session spawned by spawn_session")


# --------------------------------------------------------------------------- report


def report(path: Path, args: dict[str, Any], *, by: str = "agent",
           settings: Optional[Settings] = None) -> dict[str, Any]:
    settings = settings or Settings()
    h = handover_read(path)
    if h.status in ("abandoned", "detached"):
        raise LifecycleError(
            f"report_back is not available: this session is {h.status} "
            "(report-back to the parent was cancelled)"
        )
    if h.status == "proposed":
        raise LifecycleError("handover is still proposed; nothing to report")
    body = build_report(args, h)
    h = append_report(path, body, by=by)
    _sync_index(path, "reported")
    res = delivery.deliver_report(path, settings_timeout_s=settings.delivery_confirm_timeout_s)
    n = len(h.reports)
    return {
        "ok": True,
        "handover_id": h.handover_id,
        "status": "reported",
        "report_number": n,
        "delivery": "queued" if res.get("queued") else "pending",
        "note": (
            "Report queued for the parent session; it runs a turn on it when idle "
            "(status becomes 'delivered' once it appears in the parent's history)."
            if res.get("queued") else
            "Parent session is not live; the report is kept as 'reported' and delivered when it is reopened."
        ),
        "handover_path": str(path),
    }


# --------------------------------------------------------------------------- abandon


def abandon(path: Path, *, reason: Optional[str] = None, by: str = "user",
            settings: Optional[Settings] = None) -> dict[str, Any]:
    """D11 abort. Never deletes the worktree or the session."""
    settings = settings or Settings()
    h = handover_read(path)
    if h.status == "proposed":
        # Declining a proposal: nothing was created, nothing to bank or notify.
        h = update_status(path, "abandoned", by=by, reason=reason or "proposal declined")
        _sync_index(path, "abandoned")
        return {"ok": True, "handover_id": h.handover_id, "status": "abandoned"}
    if h.status != "running":
        raise LifecycleError(
            f"cannot abandon a handover in status {h.status!r} (only running children); "
            "use /detach to cut the parent link instead"
        )

    bank: Optional[wt_mod.BankResult] = None
    bank_error: Optional[str] = None
    wt = h.meta.get("worktree")
    if isinstance(wt, dict) and wt.get("path"):
        try:
            bank = _bank_changes(wt["path"], wt.get("branch") or "HEAD",
                                 f"WIP: spawn-session abandoned ({h.handover_id})")
        except wt_mod.WorktreeError as exc:
            bank_error = str(exc)
            logger.warning("banking worktree %s failed: %s", wt["path"], exc)

    h = update_status(path, "abandoned", by=by, reason=reason)
    if isinstance(wt, dict) and wt.get("path"):
        h.meta["worktree_cleanup"] = "awaiting_user"
        if bank is not None:
            h.meta["worktree_bank"] = {"commit": bank.commit, "pushed": bank.pushed,
                                       "remote": bank.remote, "error": bank.error}
        handover_write(h)
    _sync_index(path, "abandoned")

    notice = _abort_report(h, reason, bank, bank_error)
    notified = delivery.send_notice(path, notice)

    archived = False
    child = h.meta.get("child_session_id")
    if child:
        try:
            _archive_session(str(child))
            archived = True
        except gateway.GatewayError as exc:
            logger.warning("could not archive child %s: %s", child, exc)

    out: dict[str, Any] = {
        "ok": True, "handover_id": h.handover_id, "status": "abandoned",
        "parent_notified": notified, "child_archived": archived,
    }
    if isinstance(wt, dict) and wt.get("path"):
        out["worktree"] = {"path": wt["path"], "branch": wt.get("branch"),
                           "bank": h.meta.get("worktree_bank"), "bank_error": bank_error}
        out["question"] = (
            f"Worktree {wt['path']} (branch {wt.get('branch')}) was kept. Remove worktree + branch? "
            f"Run `/spawn-cleanup {h.handover_id} yes` to remove, or `/spawn-cleanup {h.handover_id} no` to keep."
        )
    return out


def _abort_report(h: Handover, reason: Optional[str], bank: Optional[wt_mod.BankResult],
                  bank_error: Optional[str]) -> str:
    lines = [f"[spawn-session aborted: {h.title} ({h.handover_id})]",
             f"Reason: {reason or 'not given'}"]
    if h.reports:
        lines.append(f"Reports so far: {len(h.reports)} (latest in {h.path}).")
    else:
        lines.append("No report was written before the abort.")
    wt = h.meta.get("worktree")
    if isinstance(wt, dict) and wt.get("path"):
        if bank_error:
            lines.append(f"Worktree {wt['path']}: banking failed ({bank_error}); left untouched.")
        elif bank is not None:
            state = (f"WIP commit {bank.commit[:12]}" if bank.commit else "no uncommitted changes")
            push = (f", pushed to {bank.remote}" if bank.pushed else
                    (f", push failed: {bank.error}" if bank.error else ", no remote"))
            lines.append(f"Worktree {wt['path']} (branch {wt.get('branch')}): {state}{push}. "
                         "Kept; the user decides whether to remove it.")
    lines.append("The child session was archived (not deleted).")
    return "\n".join(lines)


def cleanup_worktree(path: Path, *, confirm: bool) -> dict[str, Any]:
    """Act on the user's answer to the D11 removal question."""
    h = handover_read(path)
    wt = h.meta.get("worktree")
    if not (isinstance(wt, dict) and wt.get("path")):
        raise LifecycleError("this handover has no worktree")
    if h.meta.get("worktree_cleanup") != "awaiting_user":
        raise LifecycleError(f"no pending worktree decision (state: {h.meta.get('worktree_cleanup')})")
    if not confirm:
        h.meta["worktree_cleanup"] = "kept"
        handover_write(h)
        return {"ok": True, "worktree": wt["path"], "removed": False}
    repo_root = _find_repo_root(Path(wt["path"]).parent)
    try:
        _remove_worktree(repo_root, wt["path"], wt.get("branch"))
    except wt_mod.WorktreeError as exc:
        raise LifecycleError(f"removal failed, nothing deleted: {exc}") from exc
    h.meta["worktree_cleanup"] = "removed"
    handover_write(h)
    return {"ok": True, "worktree": wt["path"], "removed": True}


# --------------------------------------------------------------------------- detach


def detach(path: Path, *, by: str = "user", settings: Optional[Settings] = None) -> dict[str, Any]:
    """D11 detach: irreversible; B keeps running independently."""
    settings = settings or Settings()
    h = handover_read(path)
    if h.status not in ("running", "reported", "delivered"):
        raise LifecycleError(f"cannot detach a handover in status {h.status!r}")
    h = update_status(path, "detached", by=by)
    # Index entry stays (status mirrored): B is still a spawned child for D10.
    _sync_index(path, "detached")

    title_set = False
    child = h.meta.get("child_session_id")
    new_title = f"{settings.title_prefix}{settings.detached_prefix}{h.title}"
    if child:
        try:
            _set_title(str(child), new_title)
            title_set = True
        except gateway.GatewayError as exc:
            logger.warning("could not retitle detached child %s: %s", child, exc)
    if not title_set:
        h.meta["pending_title"] = new_title
        handover_write(h)

    notified = delivery.send_notice(
        path, f"[spawn-session detached: {h.title} ({h.handover_id})] The child session now "
              "continues independently; no report will be sent back."
    )
    return {"ok": True, "handover_id": h.handover_id, "status": "detached",
            "title": new_title, "title_set": title_set, "parent_notified": notified}


# --------------------------------------------------------------------------- helpers


def _sync_index(path: Path, status: str) -> None:
    try:
        state_mod.load_index().set_status(path, status)
    except Exception:
        logger.debug("index status sync skipped for %s", path)


def find_by_handover_id(index: state_mod.StateIndex, handover_id: str) -> Path:
    seen: set[str] = set()
    for entry in index.children.values():
        p = entry.get("handover_path")
        if not isinstance(p, str) or p in seen:
            continue
        seen.add(p)
        try:
            if handover_read(p).handover_id == handover_id:
                return Path(p)
        except HandoverError:
            continue
    raise LifecycleError(f"unknown handover id {handover_id!r}")
