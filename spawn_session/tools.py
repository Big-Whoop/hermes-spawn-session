"""``spawn_session`` tool handler and rules (SPEC section 4.1, decisions D2/D3/D6/D7/D10/D12/D13).

The handler is a plain function so it can be unit-tested without a live plugin
context; the seams it uses (parent resolution, state index, gateway calls,
worktree creation) are module-level names that tests monkeypatch.

Rule summary (see SPEC.md section 4.1 for the canonical text):
- D13: Desktop sessions only; other surfaces refuse with a hint to use
  ``delegate_task`` or a Kanban card.
- D10: refused inside spawned child sessions (one level only); at most
  ``max_children`` running agent-initiated children per parent — the next one
  becomes a ``proposed`` handover with a "limit reached" note.
- D6: model must be ``provider:model``; default = parent's model/effort; a more
  expensive model than A's always requires user confirmation (``proposed``),
  even when ``user_asked``. Cost rank from config ``cost_rank``; unknown ranks
  count as most expensive.
- D3: ``own_initiative`` always starts as ``proposed`` (no session created);
  ``user_asked`` starts immediately unless the cost or cap rule applies.
- D7: default cwd = A's cwd; ``worktree: true`` (immediate start only; proposals
  record ``worktree_requested`` and create nothing) creates a git worktree +
  branch ``spawn/<slug>`` and B's cwd becomes it. The Kanban board is resolved
  by name and passed in the seed message (never mutated globally).
- D12: ``allowed_toolsets`` may only narrow A's toolsets; ``spawn_session`` is
  never granted to a child (enforced here plus by the ``pre_tool_call`` guard
  in :func:`toolset_guard`).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from . import gateway, parent as parent_mod, seed as seed_mod, state as state_mod, worktree as wt_mod
from .config import Settings
from .handover import HandoverError, create as handover_create, read as handover_read, update_status

logger = logging.getLogger("hermes.spawn-session")

def _default_broadcast(event: str, payload: dict) -> None:
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event

        broadcast_plugin_event("spawn-session", event, payload)
    except Exception:  # no desktop client / not in gateway: logged no-op (SPEC Q2)
        logger.debug("broadcast %s skipped", event)


# --------------------------------------------------------------------------- seams

# Tests replace these; production defaults bind to the real implementations.
_resolve_parent: Callable[[str], parent_mod.ParentContext] = parent_mod.resolve_parent_context
_load_index: Callable[..., state_mod.StateIndex] = state_mod.load_index
_gateway_create: Callable[..., dict] = gateway.create_session
_gateway_submit: Callable[[str, str], dict] = gateway.submit_prompt
_find_repo_root: Callable[[str | Path], Path] = wt_mod.find_repo_root
_create_worktree: Callable[..., wt_mod.Worktree] = wt_mod.create_worktree
_broadcast_event: Callable[[str, dict], None] = _default_broadcast
_lineage_ids: Callable[[str], list[str]] = parent_mod.lineage_ids


def _child_in_lineage(index: state_mod.StateIndex, session_id: str) -> Optional[str]:
    """Return the spawned-child id found in ``session_id``'s lineage, or None.

    Tests ``is_child`` at EACH hop (SPEC Q5 / D10): a compression continuation
    of child B links to B via ``parent_session_id``, and B links to A the same
    way, so only a per-hop check (not a root walk) recognises the continuation.
    """
    try:
        ids = _lineage_ids(session_id)
    except Exception:
        ids = [session_id]
    for sid in ids or [session_id]:
        if index.is_child(sid):
            return sid
    return None


def _resolve_kanban_board() -> Optional[str]:
    """A's Kanban board by name: ``HERMES_KANBAN_BOARD`` env, else the profile's
    ``kanban/current`` symlink (SPEC Q1); never mutates any global state."""
    board = os.environ.get("HERMES_KANBAN_BOARD")
    if board and board.strip():
        return board.strip()
    try:
        current = parent_mod.hermes_home() / "kanban" / "current"
        if current.exists():
            target = os.path.realpath(current)
            name = Path(target).name
            if name and not name.startswith("."):
                return name
    except OSError:
        pass
    return None


def _known_toolsets() -> set[str]:
    """Toolset names registered in this process (best effort)."""
    try:
        from tools.registry import registry

        return {ts for ts in registry.get_tool_to_toolset_map().values() if ts}
    except Exception:
        return set()


# --------------------------------------------------------------------------- helpers

DESKTOP_SOURCES = frozenset({"desktop"})

SPAWN_SESSION_SCHEMA: dict[str, Any] = {
    "name": "spawn_session",
    "description": (
        "Spawn a visible child session for a self-contained task. It reports back here when done."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "maxLength": 80},
            "task": {"type": "string", "description": "Detailed instructions for the child."},
            "context": {"type": "string", "description": "Short background summary (TL;DR)."},
            "initiation": {"type": "string", "enum": ["user_asked", "own_initiative"]},
            "model": {
                "type": "string",
                "description": "provider:model; default = parent's model",
            },
            "effort": {"type": "string", "enum": ["low", "medium", "high", "xhigh"]},
            "worktree": {"type": "boolean", "default": False},
            "allowed_toolsets": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "task", "initiation"],
    },
}

D10_MESSAGE = (
    "spawn_session is not available in a spawned session (one level only). "
    "Ask the parent session to coordinate, or use delegate_task for subtasks."
)
D13_MESSAGE = (
    "spawn_session is only available in Hermes Desktop sessions. On this surface use "
    "delegate_task for an isolated subagent run, or create a Kanban card for queued work."
)


class SpawnError(ValueError):
    """Invalid spawn request (bad arguments)."""


def split_model_ref(model: str) -> tuple[str, str]:
    """Split ``provider:model`` into ``(provider, model_name)``.

    The provider part may itself contain a colon (e.g. ``custom:cpa``), so the
    LAST colon separates provider from model name. Bare names are rejected
    (D6 billing trap). Model names containing colons are not supported by this
    reference syntax.
    """
    if not isinstance(model, str) or ":" not in model:
        raise SpawnError(
            f"model must use 'provider:model' syntax (got {model!r}); bare model names "
            "are rejected to avoid mis-billing"
        )
    provider, name = model.rsplit(":", 1)
    if not provider.strip() or not name.strip():
        raise SpawnError(f"model must use 'provider:model' syntax (got {model!r})")
    return provider.strip(), name.strip()


def _cost_rank(model_ref: str, cost_rank: dict[str, int]) -> float:
    """Cost rank of ``provider:model``; unknown models count as most expensive."""
    if model_ref in cost_rank:
        return float(cost_rank[model_ref])
    return float("inf")


def more_expensive_than(child_ref: str, parent_ref: str, cost_rank: dict[str, int]) -> bool:
    """True when the child model is strictly more expensive than the parent's.

    Unknown ranks are ``inf``: a known parent + unknown child is "more
    expensive" (confirm); two unknowns are treated as equal (no confirm).
    """
    return _cost_rank(child_ref, cost_rank) > _cost_rank(parent_ref, cost_rank)


def _validate_toolsets(allowed_toolsets: Any) -> Optional[list[str]]:
    """Validate ``allowed_toolsets`` (D12): list of known toolset names, or None."""
    if allowed_toolsets is None:
        return None
    if not isinstance(allowed_toolsets, list) or not all(isinstance(t, str) for t in allowed_toolsets):
        raise SpawnError("allowed_toolsets must be a list of toolset name strings")
    known = _known_toolsets()
    if known:
        unknown = [t for t in allowed_toolsets if t not in known]
        if unknown:
            raise SpawnError(
                f"unknown toolset(s) in allowed_toolsets: {', '.join(sorted(set(unknown)))}; "
                f"valid: {', '.join(sorted(known))}"
            )
    deduped = list(dict.fromkeys(allowed_toolsets))
    # D10/D12: the spawn toolset is never granted to a child, even if requested.
    return [t for t in deduped if t != "spawn-session"]


def _handover_base_dir(parent_cwd: Optional[str]) -> Path:
    """``<A.cwd>/.hermes/handovers``; profile fallback when cwd is unwritable."""
    from .config import DEFAULT_HANDOVER_DIR

    if parent_cwd:
        candidate = Path(parent_cwd) / DEFAULT_HANDOVER_DIR
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write-probe"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            return candidate
        except OSError:
            pass
    fallback = parent_mod.hermes_home() / "spawn-session" / "handovers"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


# --------------------------------------------------------------------------- the handler


def spawn_session_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """Tool handler for ``spawn_session``. Returns a JSON string (tool contract)."""
    try:
        result = _plan_and_spawn(args or {}, kwargs)
    except SpawnError as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    except parent_mod.ParentNotFound as exc:
        return json.dumps({"ok": False, "error": f"cannot resolve parent session: {exc}"})
    except gateway.GatewayError as exc:
        return json.dumps({"ok": False, "error": f"gateway error: {exc}"})
    except (HandoverError, wt_mod.WorktreeError) as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    except Exception as exc:  # tool contract: never raise, always JSON
        logger.exception("spawn_session failed")
        return json.dumps({"ok": False, "error": f"internal error: {exc}"})
    return json.dumps(result)


def _plan_and_spawn(args: dict[str, Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    settings = _settings()

    # ---- argument validation (SPEC 4.1 schema)
    title = args.get("title")
    if not isinstance(title, str) or not title.strip():
        raise SpawnError("title is required (string)")
    title = title.strip()
    if len(title) > 80:
        raise SpawnError("title must be at most 80 characters")
    task = args.get("task")
    if not isinstance(task, str) or not task.strip():
        raise SpawnError("task is required (string)")
    context = args.get("context") or ""
    if not isinstance(context, str):
        raise SpawnError("context must be a string when provided")
    initiation = args.get("initiation")
    if initiation not in ("user_asked", "own_initiative"):
        raise SpawnError("initiation must be 'user_asked' or 'own_initiative'")
    effort = args.get("effort")
    if effort is not None and effort not in ("low", "medium", "high", "xhigh"):
        raise SpawnError("effort must be one of low, medium, high, xhigh")
    worktree = bool(args.get("worktree", False))
    allowed_toolsets = _validate_toolsets(args.get("allowed_toolsets"))

    # ---- parent context (D13 surface check)
    session_id = str(kwargs.get("session_id") or "")
    a = _resolve_parent(session_id)
    if a.source not in DESKTOP_SOURCES:
        return {"ok": False, "error": D13_MESSAGE}

    # ---- D10: no nesting (child sessions, incl. detached ones, cannot spawn)
    index = _load_index()
    if _child_in_lineage(index, a.session_id) is not None:
        return {"ok": False, "error": D10_MESSAGE}

    # ---- D6: model resolution
    if args.get("model") is None and ":" not in a.model_ref:
        raise SpawnError(
            "the parent session's provider could not be resolved; pass an explicit "
            "model='provider:model' (bare model names are rejected to avoid mis-billing)"
        )
    model_ref = args.get("model") or a.model_ref
    provider, model_name = split_model_ref(model_ref)
    child_effort = effort if effort is not None else a.effort

    needs_confirmation: list[str] = []
    if more_expensive_than(model_ref, a.model_ref, dict(settings.cost_rank)):
        needs_confirmation.append(
            f"model {model_ref} is more expensive than the parent's {a.model_ref}"
        )

    base_cwd = a.cwd or os.getcwd()
    wt_info: Optional[dict[str, str]] = None
    child_cwd = base_cwd

    # ---- D3/D10: decide immediate start vs. proposal
    running_children = state_mod.running_agent_children(index, a.session_id)
    if running_children >= settings.max_children:
        needs_confirmation.append(
            f"limit reached: {running_children} agent-initiated child(ren) already "
            f"running (max_children={settings.max_children})"
        )
    if initiation == "own_initiative":
        needs_confirmation.append("agent own initiative — awaiting user confirmation")

    status = "running" if not needs_confirmation else "proposed"

    # ---- D7: worktree only on the immediate-start path. A proposal must not
    # touch the user's repo before approval (D3); it records the intent in the
    # frontmatter (``worktree_requested``) and the confirm path creates it.
    if worktree and status == "running":
        repo_root = a.git_repo_root
        if not repo_root:
            repo_root = str(_find_repo_root(base_cwd))
        from .handover import slugify

        wt = _create_worktree(
            repo_root, slugify(title),
            worktree_dir=settings.worktree_dir, branch_prefix=settings.branch_prefix,
        )
        wt_info = {"path": wt.path, "branch": wt.branch}
        child_cwd = wt.path

    # ---- handover file (authoritative record, SPEC section 5)
    base_dir = _handover_base_dir(a.cwd)
    h = handover_create(
        base_dir,
        title=title,
        task=task.strip(),
        context=context.strip(),
        parent_session_id=a.session_id,
        model=model_ref,
        provider=provider,
        effort=child_effort,
        cwd=child_cwd,
        status=status,
        initiation=initiation,
        initiator="agent",
        worktree=wt_info,
        kanban_board=_resolve_kanban_board(),
        allowed_toolsets=allowed_toolsets,
    )
    assert h.path is not None  # handover_create always sets the path
    handover_path = Path(h.path)
    from .handover import write as handover_write

    try:
        index.register_handover_root(handover_path.parent)
    except OSError:
        logger.warning("could not record handover root %s", handover_path.parent)

    if status == "proposed":
        if worktree:
            h.meta["worktree_requested"] = True
            handover_write(h)
        # No session created yet (D3). The desktop half shows the proposal card.
        _broadcast_event("child.proposed", {
            "handover_id": h.handover_id,
            "parent_session_id": a.session_id,
            "title": title,
            "reasons": needs_confirmation,
            "handover_path": str(handover_path),
        })
        return {
            "ok": True,
            "handover_id": h.handover_id,
            "status": "proposed",
            "child_session_id": None,
            "handover_path": str(handover_path),
            "confirmation_required": needs_confirmation,
        }

    # ---- create the child session (gateway session.create)
    child_title = settings.title_prefix + title
    try:
        created = _gateway_create(
            title=child_title,
            cwd=child_cwd,
            model=model_name,
            provider=provider,
            reasoning_effort=child_effort,
            parent_session_id=a.session_id,
            idempotency_key=h.handover_id,
            source=a.source,  # B lives on A's surface (D13)
        )
    except gateway.GatewayError as exc:
        # The handover file is authoritative: a failed create must not leave a
        # 'running' record without a child session. Abandon it with the reason.
        try:
            update_status(handover_path, "abandoned", by="agent", reason=f"session.create failed: {exc}")
        except HandoverError:
            logger.exception("could not abandon handover %s after create failure", h.handover_id)
        if wt_info is not None:
            logger.warning(
                "worktree %s was created but the session create failed; it is kept for "
                "manual cleanup (never auto-deleted, D11)", wt_info["path"],
            )
        raise
    child_runtime = str(created["session_id"])
    child_stored = str(created.get("stored_session_id") or created["session_id"])

    # Record the child ids in the handover + state index (authoritative first).
    h.meta["child_session_id"] = child_stored
    handover_write(h)
    index.register_child(
        [child_stored, child_runtime],
        handover_path=handover_path, parent_session_id=a.session_id, status="running",
    )

    # ---- start B's first turn with the seed message (SPEC section 5).
    # Submitted on a background thread: prompt.submit runs B's whole first
    # turn, which must not block this tool call.
    seed_text = seed_mod.build_seed_message(h)
    try:
        threading.Thread(
            target=_submit_seed_safe,
            args=(child_runtime, seed_text),
            name=f"spawn-session-seed-{h.handover_id}",
            daemon=True,
        ).start()
    except RuntimeError as exc:  # interpreter shutdown etc.
        logger.warning("could not schedule seed prompt for %s: %s", child_stored, exc)

    _broadcast_event("child.created", {
        "handover_id": h.handover_id,
        "child_session_id": child_stored,
        "parent_session_id": a.session_id,
        "title": title,
        "model": model_ref,
        "cwd": child_cwd,
        "worktree": wt_info,
        "handover_path": str(handover_path),
    })

    return {
        "ok": True,
        "handover_id": h.handover_id,
        "status": "running",
        "child_session_id": child_stored,
        "handover_path": str(handover_path),
    }


def _submit_seed_safe(child_session_id: str, text: str) -> None:
    try:
        _gateway_submit(child_session_id, text)
    except gateway.GatewayError as exc:
        # The handover stays 'running'; the user can re-trigger from B's composer.
        logger.error("seed prompt for child %s failed: %s", child_session_id, exc)


def _settings() -> Settings:
    """Read plugin settings from config (seam for tests)."""
    if _settings_override is not None:
        return _settings_override
    try:
        from hermes_cli.config import load_config_readonly

        cfg = load_config_readonly() or {}
        entry = ((cfg.get("plugins") or {}).get("entries") or {}).get("spawn-session") or {}
        return Settings.from_mapping(entry)
    except Exception:
        return Settings()


_settings_override: Optional[Settings] = None


def set_settings_override(settings: Optional[Settings]) -> None:
    """Test seam: pin the settings used by :func:`_settings`."""
    global _settings_override
    _settings_override = settings


# --------------------------------------------------------------------------- report_back (D4, SPEC 4.2)

REPORT_BACK_SCHEMA: dict[str, Any] = {
    "name": "report_back",
    "description": (
        "Only in a session spawned by spawn_session: send a structured report back to the "
        "parent session (appended to the handover file; the parent runs a turn on it). "
        "The session stays open; call again for a follow-up report."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "result": {"type": "string", "description": "What was achieved (summary)."},
            "changes": {"type": "array", "items": {"type": "string"}},
            "open_items": {"type": "array", "items": {"type": "string"}},
            "artifacts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["path", "commit", "branch", "url", "pr"]},
                        "value": {"type": "string"},
                    },
                    "required": ["kind", "value"],
                },
            },
        },
        "required": ["result"],
    },
}

NOT_A_CHILD_MESSAGE = (
    "report_back is only available in a session spawned by spawn_session; this session has "
    "no parent to report to."
)


def report_back_handler(args: dict[str, Any], **kwargs: Any) -> str:
    """Tool handler for ``report_back``. Returns a JSON string (tool contract)."""
    from . import lifecycle

    try:
        session_id = str(kwargs.get("session_id") or "")
        index = _load_index()
        child_id = _child_in_lineage(index, session_id) if session_id else None
        path = index.handover_for(child_id) if child_id else None
        if path is None:
            return json.dumps({"ok": False, "error": NOT_A_CHILD_MESSAGE})
        return json.dumps(lifecycle.report(path, args or {}, by="agent", settings=_settings()))
    except (lifecycle.LifecycleError, HandoverError) as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    except Exception as exc:  # tool contract: never raise, always JSON
        logger.exception("report_back failed")
        return json.dumps({"ok": False, "error": f"internal error: {exc}"})


# --------------------------------------------------------------------------- pre_tool_call guard (D10/D12)

_guard_cache: dict[str, tuple[float, Optional[list[str]]]] = {}
_GUARD_TTL_S = 2.0


def toolset_guard(**kwargs: Any) -> Optional[dict]:
    """``pre_tool_call`` hook: enforce child-session restrictions.

    - D10/D12: ``spawn_session`` is never available in a spawned child
      session — the handler refuses anyway, this blocks it before execution.
      ``report_back`` is the child's own tool and is never narrowed away.
    - D12: when the handover carries ``allowed_toolsets``, any tool whose
      toolset is not in that list is blocked with an explanatory message.
    """
    tool_name = kwargs.get("tool_name") or ""
    session_id = str(kwargs.get("session_id") or "")
    if not session_id:
        return None
    try:
        index = _load_index()
    except Exception:
        return None  # fail open for the guard; the handler re-checks D10 itself
    child_id = _child_in_lineage(index, session_id)
    if child_id is None:
        return None
    handover_path = index.handover_for(child_id)
    if tool_name == "spawn_session":
        return {"action": "block", "message": D10_MESSAGE}
    if tool_name == "report_back":
        return None  # child-only tool: always allowed here; the handler checks status
    if handover_path is None:
        return None
    allowed = _allowed_toolsets_cached(handover_path)
    if allowed is None:
        return None  # unrestricted child (full A toolset minus spawn tools)
    try:
        from tools.registry import registry

        toolset = registry.get_toolset_for_tool(tool_name)
    except Exception:
        return None
    if toolset is not None and toolset not in allowed:
        return {
            "action": "block",
            "message": (
                f"tool '{tool_name}' (toolset '{toolset}') is not in this session's "
                f"allowed_toolsets {sorted(allowed)}; the parent session restricted it"
            ),
        }
    return None


def _allowed_toolsets_cached(handover_path: Path) -> Optional[list[str]]:
    import time

    key = str(handover_path)
    try:
        mtime = handover_path.stat().st_mtime
    except OSError:
        return None
    cached = _guard_cache.get(key)
    if cached is not None and time.monotonic() - cached[0] < _GUARD_TTL_S:
        return cached[1]
    try:
        h = handover_read(handover_path)
    except Exception:
        return None
    allowed = h.meta.get("allowed_toolsets")
    value = list(allowed) if isinstance(allowed, list) else None
    _guard_cache[key] = (time.monotonic(), value)
    return value
