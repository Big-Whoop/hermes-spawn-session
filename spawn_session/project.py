"""Desktop Project inheritance for child sessions (decision D7, SPEC Q1).

Hermes has no per-session ``project`` field. A session's Desktop Project is
*derived* from its cwd: the project whose folder is the longest ancestor of
(or equal to) the cwd in the per-profile ``$HERMES_HOME/projects.db``
(``hermes_cli/projects_db.py:462`` ``project_for_path``; used by
``tools/project_tools.py:74`` for ``desktop_project list`` and by
``tui_gateway/server.py:2296`` ``_project_info_for_cwd`` for session.info).
``desktop_project switch`` only re-anchors the session's cwd to the project's
primary path (``tools/project_tools.py:135`` -> ``tui_gateway/agent_callbacks.py:194``).

Therefore "assign A's project to B" == give B a cwd owned by that project, and
verify it with the same lookup. When B's cwd does not resolve to A's project
(e.g. a worktree placed outside every project folder), the fallback is a seed
instruction to call ``desktop_project switch <id>``.

The DB is opened read-only; this module never writes Hermes state.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ProjectInfo:
    id: str
    slug: str
    name: str
    board: Optional[str] = None
    primary_path: Optional[str] = None

    def to_meta(self) -> dict:
        return {"id": self.id, "slug": self.slug, "name": self.name,
                "board": self.board, "primary_path": self.primary_path}


def projects_db_path(home: Path | None = None) -> Path:
    from .parent import hermes_home

    return (home or hermes_home()) / "projects.db"


def _normalize(path: str) -> str:
    # Mirrors projects_db._normalize_path (abspath + expanduser).
    return os.path.abspath(os.path.expanduser(str(path)))


def _owns(folder: str, target: str) -> bool:
    stem = folder.rstrip("/\\")
    return target == folder or target.startswith(stem + os.sep) or target.startswith(stem + "/")


def project_for_path(path: Optional[str], db_path: Path | None = None) -> Optional[ProjectInfo]:
    """The non-archived project owning ``path`` (innermost folder wins), else None.

    Same semantics as Hermes' ``projects_db.project_for_path``; read-only.
    Missing DB / old schema / unreadable DB -> None (never raises).
    """
    if not str(path or "").strip():
        return None
    db = Path(db_path) if db_path else projects_db_path()
    if not db.is_file():
        return None
    target = _normalize(str(path))
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT pf.project_id AS pid, pf.path AS folder FROM project_folders pf "
            "JOIN projects p ON p.id = pf.project_id WHERE p.archived = 0"
        ).fetchall()
        owners = [r for r in rows if _owns(r["folder"], target)]
        if not owners:
            return None
        pid = max(owners, key=lambda r: len(r["folder"]))["pid"]
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        if row is None:
            return None
        keys = row.keys()
        primary = row["primary_path"] if "primary_path" in keys else None
        if not primary:
            prow = conn.execute(
                "SELECT path FROM project_folders WHERE project_id = ? "
                "ORDER BY is_primary DESC, added_at ASC LIMIT 1", (pid,)).fetchone()
            primary = prow["path"] if prow else None
        return ProjectInfo(
            id=row["id"], slug=row["slug"], name=row["name"],
            board=(row["board_slug"] or None) if "board_slug" in keys else None,
            primary_path=primary,
        )
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def switch_instruction(project: ProjectInfo) -> str:
    """Seed-message fallback: ask B to move itself into A's project first."""
    return (
        f"FIRST, before anything else: call the `desktop_project` tool with "
        f"action=\"switch\" and name=\"{project.id}\" to move this session into the "
        f"Desktop Project \"{project.name}\" (inherited from the parent session). "
        "If that tool is unavailable (toolset `project`), mention it in your report."
    )
