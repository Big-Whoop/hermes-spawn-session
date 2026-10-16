"""Project inheritance (D7 / SPEC Q1): resolution, assignment, fallback."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from spawn_session import project as project_mod
from spawn_session import tools
from spawn_session.handover import read
from spawn_session.project import project_for_path
from tests.conftest import base_args, call_spawn

# Schema subset of hermes_cli/projects_db.py SCHEMA_SQL.
SCHEMA = """
CREATE TABLE projects (id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
  description TEXT, icon TEXT, color TEXT, board_slug TEXT, primary_path TEXT,
  created_at INTEGER NOT NULL, archived INTEGER NOT NULL DEFAULT 0);
CREATE TABLE project_folders (project_id TEXT NOT NULL, path TEXT NOT NULL, label TEXT,
  is_primary INTEGER NOT NULL DEFAULT 0, added_at INTEGER NOT NULL, PRIMARY KEY (project_id, path));
"""


def make_db(home: Path, projects: list[tuple]) -> Path:
    """projects: (id, slug, name, board, folders, archived)."""
    db = home / "projects.db"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA)
    for pid, slug, name, board, folders, archived in projects:
        conn.execute("INSERT INTO projects (id, slug, name, board_slug, primary_path, created_at, archived)"
                     " VALUES (?,?,?,?,?,0,?)", (pid, slug, name, board, folders[0] if folders else None, archived))
        for i, f in enumerate(folders):
            conn.execute("INSERT INTO project_folders VALUES (?,?,NULL,?,0)", (pid, f, int(i == 0)))
    conn.commit()
    conn.close()
    return db


class TestResolution:
    def test_no_db_returns_none(self, tmp_home, tmp_path):
        assert project_for_path(str(tmp_path)) is None

    def test_empty_path_returns_none(self, tmp_home):
        assert project_for_path("") is None and project_for_path(None) is None

    def test_ancestor_folder_owns_path(self, tmp_home, tmp_path):
        make_db(tmp_home, [("p1", "repo", "Repo", "board-a", [str(tmp_path / "repo")], 0)])
        p = project_for_path(str(tmp_path / "repo" / "sub" / "dir"))
        assert p is not None and (p.id, p.name, p.board) == ("p1", "Repo", "board-a")
        assert p.primary_path == str(tmp_path / "repo")

    def test_sibling_prefix_not_owned(self, tmp_home, tmp_path):
        make_db(tmp_home, [("p1", "repo", "Repo", None, [str(tmp_path / "repo")], 0)])
        assert project_for_path(str(tmp_path / "repo2")) is None

    def test_innermost_project_wins(self, tmp_home, tmp_path):
        make_db(tmp_home, [
            ("outer", "outer", "Outer", None, [str(tmp_path / "a")], 0),
            ("inner", "inner", "Inner", None, [str(tmp_path / "a" / "b")], 0),
        ])
        assert project_for_path(str(tmp_path / "a" / "b" / "c")).id == "inner"
        assert project_for_path(str(tmp_path / "a" / "x")).id == "outer"

    def test_archived_ignored(self, tmp_home, tmp_path):
        make_db(tmp_home, [("p1", "repo", "Repo", None, [str(tmp_path / "repo")], 1)])
        assert project_for_path(str(tmp_path / "repo")) is None

    def test_corrupt_db_returns_none(self, tmp_home, tmp_path):
        (tmp_home / "projects.db").write_text("not sqlite")
        assert project_for_path(str(tmp_path)) is None


class TestAssignment:
    def test_no_project_records_null(self, fake_gateway, desktop_parent, tmp_home):
        result = call_spawn(base_args())
        assert read(result["handover_path"]).meta["project"] is None

    def test_cwd_inherits_project_and_board(self, fake_gateway, desktop_parent, tmp_home, monkeypatch):
        monkeypatch.setenv("HERMES_KANBAN_BOARD", "env-board")
        make_db(tmp_home, [("p1", "proj", "Proj", "proj-board", [desktop_parent.cwd], 0)])
        result = call_spawn(base_args())
        meta = read(result["handover_path"]).meta
        assert meta["project"]["id"] == "p1" and meta["project"]["name"] == "Proj"
        assert meta["project"]["assignment"] == "cwd"
        # The project's bound board wins over the env/current fallback.
        assert meta["kanban_board"] == "proj-board"
        create = [f for f in fake_gateway.frames if f["method"] == "session.create"][0]
        assert create["params"]["cwd"] == desktop_parent.cwd
        seed = [f for f in fake_gateway.frames if f["method"] == "prompt.submit"][0]["params"]["text"]
        assert "desktop_project" not in seed
        assert result["project"]["id"] == "p1"

    def test_unbound_project_falls_back_to_env_board(self, fake_gateway, desktop_parent, tmp_home, monkeypatch):
        monkeypatch.setenv("HERMES_KANBAN_BOARD", "env-board")
        make_db(tmp_home, [("p1", "proj", "Proj", None, [desktop_parent.cwd], 0)])
        meta = read(call_spawn(base_args())["handover_path"]).meta
        assert meta["kanban_board"] == "env-board" and meta["project"]["board"] is None


class TestFallback:
    def test_seed_switch_when_child_cwd_outside_project(
        self, fake_gateway, desktop_parent, tmp_home, monkeypatch
    ):
        make_db(tmp_home, [("p1", "proj", "Proj", None, [desktop_parent.cwd], 0)])
        # A's cwd resolves to the project; B's cwd (e.g. an outside worktree) does not.
        seq = iter([project_mod.project_for_path(desktop_parent.cwd), None])
        monkeypatch.setattr(tools, "_project_for_path", lambda p: next(seq))
        result = call_spawn(base_args(allowed_toolsets=["terminal"]))
        meta = read(result["handover_path"]).meta
        assert meta["project"]["assignment"] == "seed_switch"
        assert "project" in meta["allowed_toolsets"]
        seed = [f for f in fake_gateway.frames if f["method"] == "prompt.submit"][0]["params"]["text"]
        assert seed.startswith("FIRST")
        assert 'action="switch"' in seed and 'name="p1"' in seed

    def test_unrestricted_toolsets_untouched(self, fake_gateway, desktop_parent, tmp_home, monkeypatch):
        make_db(tmp_home, [("p1", "proj", "Proj", None, [desktop_parent.cwd], 0)])
        seq = iter([project_mod.project_for_path(desktop_parent.cwd), None])
        monkeypatch.setattr(tools, "_project_for_path", lambda p: next(seq))
        meta = read(call_spawn(base_args())["handover_path"]).meta
        assert meta["project"]["assignment"] == "seed_switch"
        assert meta["allowed_toolsets"] is None