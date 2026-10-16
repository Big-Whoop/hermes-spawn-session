"""Resolve the calling (parent) session's context from the profile state DB.

The ``spawn_session`` handler receives the parent's durable session id as an
injected ``session_id`` kwarg. Everything else the rules need — surface
(``source``), model/provider, cwd, git repo root — lives in that session's row
in the profile's ``state.db`` (sessions table). This module reads it
read-only; it never writes.

Docs-first note: the sessions store and its columns are described by the
Hermes state docs and the ``session.*`` RPC contracts
(https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration);
the row shape used here (``id``, ``source``, ``model``, ``model_config``,
``cwd``, ``git_repo_root``, ``parent_session_id``) matches the live schema.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


class ParentNotFound(Exception):
    """No session row for the given id in the profile state DB."""


@dataclass(frozen=True)
class ParentContext:
    """Facts about the calling session A that the spawn rules need."""

    session_id: str
    source: str
    title: str
    model: str
    provider: str
    cwd: Optional[str]
    git_repo_root: Optional[str]
    effort: Optional[str] = None

    @property
    def model_ref(self) -> str:
        """``provider:model`` reference of A's model (D6 always-provider syntax)."""
        return f"{self.provider}:{self.model}" if self.provider else self.model


def hermes_home() -> Path:
    """Profile home directory (``HERMES_HOME``), matching Hermes core resolution."""
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def state_db_path(home: Path | None = None) -> Path:
    return (home or hermes_home()) / "state.db"


def _row_to_context(row: sqlite3.Row, session_id: str) -> ParentContext:
    model_config: dict[str, Any] = {}
    raw_config = row["model_config"] if "model_config" in row.keys() else None
    if isinstance(raw_config, str) and raw_config.strip():
        try:
            parsed = json.loads(raw_config)
            if isinstance(parsed, dict):
                model_config = parsed
        except ValueError:
            model_config = {}
    provider = str(model_config.get("provider") or row["billing_provider"] or "").strip()
    effort: str | None = None
    reasoning = model_config.get("reasoning_config")
    if isinstance(reasoning, dict) and reasoning.get("enabled") is not False:
        raw_effort = reasoning.get("effort")
        if isinstance(raw_effort, str) and raw_effort.strip():
            effort = raw_effort.strip()
    return ParentContext(
        session_id=session_id,
        source=str(row["source"] or ""),
        title=str(row["title"] or ""),
        model=str(row["model"] or ""),
        provider=provider,
        cwd=(str(row["cwd"]) if row["cwd"] else None),
        git_repo_root=(str(row["git_repo_root"]) if row["git_repo_root"] else None),
        effort=effort,
    )


def resolve_parent_context(session_id: str, db_path: Path | None = None) -> ParentContext:
    """Return the context of session ``session_id`` (durable id).

    Raises :class:`ParentNotFound` when the profile DB or the row is missing.
    """
    if not session_id:
        raise ParentNotFound("no session id provided")
    path = db_path or state_db_path()
    if not path.exists():
        raise ParentNotFound(f"profile state DB not found at {path}")
    uri = f"file:{path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error as exc:
        raise ParentNotFound(f"cannot open profile state DB {path}: {exc}") from exc
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ? OR session_key = ?", (session_id, session_id)
        ).fetchone()
    except sqlite3.Error as exc:
        raise ParentNotFound(f"cannot read sessions table in {path}: {exc}") from exc
    finally:
        conn.close()
    if row is None:
        raise ParentNotFound(f"no session row for id {session_id!r}")
    return _row_to_context(row, str(row["id"] or session_id))


def lineage_ids(session_id: str, db_path: Path | None = None, max_hops: int = 5) -> list[str]:
    """``session_id`` followed by up to ``max_hops`` ancestors via ``parent_session_id``.

    Compression continuations link to their predecessor through
    ``parent_session_id``; so does the spawn link B -> A. Callers must test each
    hop (e.g. "is this id a spawned child?") rather than only the root, because
    the root of a child's lineage is its spawning parent A (SPEC Q5 / D10).
    Best-effort: DB errors stop the walk; cycles are cut.
    """
    ids = [session_id]
    path = db_path or state_db_path()
    if not session_id or not path.exists():
        return ids
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return ids
    try:
        current = session_id
        for _ in range(max_hops):
            try:
                row = conn.execute(
                    "SELECT parent_session_id FROM sessions WHERE id = ?", (current,)
                ).fetchone()
            except sqlite3.Error:
                break
            if row is None or not row[0] or str(row[0]) in ids:
                break
            current = str(row[0])
            ids.append(current)
        return ids
    finally:
        conn.close()


def lineage_root(session_id: str, db_path: Path | None = None, max_hops: int = 5) -> str:
    """Walk ``parent_session_id`` links upward (compression continuations).

    Returns the first ancestor id whose row has no parent, or ``session_id``
    itself. Best-effort: DB errors stop the walk and return the current id.
    Used to detect "running inside a spawned child" across compression lineage
    (SPEC Q5 / D10).
    """
    path = db_path or state_db_path()
    if not path.exists():
        return session_id
    uri = f"file:{path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error:
        return session_id
    current = session_id
    try:
        for _ in range(max_hops):
            try:
                row = conn.execute(
                    "SELECT parent_session_id FROM sessions WHERE id = ?", (current,)
                ).fetchone()
            except sqlite3.Error:
                break
            if row is None or not row[0]:
                break
            current = str(row[0])
        return current
    finally:
        conn.close()
