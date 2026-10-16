"""Tests for spawn_session.parent (state DB resolution)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from spawn_session import parent as parent_mod


def make_db(tmp_path: Path, rows: list[dict]) -> Path:
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE sessions (
            id TEXT PRIMARY KEY, source TEXT, title TEXT, model TEXT, model_config TEXT,
            billing_provider TEXT, cwd TEXT, git_repo_root TEXT, parent_session_id TEXT,
            session_key TEXT
        )"""
    )
    for r in rows:
        keys = ", ".join(r.keys())
        placeholders = ", ".join("?" * len(r))
        conn.execute(f"INSERT INTO sessions ({keys}) VALUES ({placeholders})", list(r.values()))
    conn.commit()
    conn.close()
    return db


def test_resolve_parent_context(tmp_path: Path):
    db = make_db(
        tmp_path,
        [
            {
                "id": "ses-1", "source": "desktop", "title": "A", "model": "claude-opus-5-5",
                "model_config": json.dumps({"provider": "custom:cpa", "reasoning_config": {"enabled": True, "effort": "high"}}),
                "billing_provider": "custom:cpa", "cwd": "/w", "git_repo_root": "/w/repo",
                "parent_session_id": None, "session_key": None,
            }
        ],
    )
    ctx = parent_mod.resolve_parent_context("ses-1", db_path=db)
    assert ctx.session_id == "ses-1"
    assert ctx.source == "desktop"
    assert ctx.model_ref == "custom:cpa:claude-opus-5-5"
    assert ctx.effort == "high"
    assert ctx.cwd == "/w"
    assert ctx.git_repo_root == "/w/repo"


def test_provider_falls_back_to_billing_provider(tmp_path: Path):
    db = make_db(
        tmp_path,
        [
            {
                "id": "ses-2", "source": "desktop", "title": "A", "model": "m",
                "model_config": None, "billing_provider": "openai",
                "cwd": None, "git_repo_root": None, "parent_session_id": None, "session_key": None,
            }
        ],
    )
    ctx = parent_mod.resolve_parent_context("ses-2", db_path=db)
    assert ctx.provider == "openai"
    assert ctx.model_ref == "openai:m"
    assert ctx.effort is None


def test_missing_row_raises(tmp_path: Path):
    db = make_db(tmp_path, [])
    with pytest.raises(parent_mod.ParentNotFound):
        parent_mod.resolve_parent_context("nope", db_path=db)


def test_missing_db_raises(tmp_path: Path):
    with pytest.raises(parent_mod.ParentNotFound):
        parent_mod.resolve_parent_context("ses-1", db_path=tmp_path / "absent.db")


def test_empty_session_id_raises():
    with pytest.raises(parent_mod.ParentNotFound):
        parent_mod.resolve_parent_context("")


def test_lineage_root_walks_parents(tmp_path: Path):
    db = make_db(
        tmp_path,
        [
            {"id": "c1", "source": "desktop", "title": "", "model": "m", "model_config": None,
             "billing_provider": "", "cwd": None, "git_repo_root": None,
             "parent_session_id": "c0", "session_key": None},
            {"id": "c0", "source": "desktop", "title": "", "model": "m", "model_config": None,
             "billing_provider": "", "cwd": None, "git_repo_root": None,
             "parent_session_id": "root", "session_key": None},
            {"id": "root", "source": "desktop", "title": "", "model": "m", "model_config": None,
             "billing_provider": "", "cwd": None, "git_repo_root": None,
             "parent_session_id": None, "session_key": None},
        ],
    )
    assert parent_mod.lineage_root("c1", db_path=db) == "root"
    # Unknown id returns itself.
    assert parent_mod.lineage_root("ghost", db_path=db) == "ghost"
