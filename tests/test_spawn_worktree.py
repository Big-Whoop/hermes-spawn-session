"""Tests for spawn_session.worktree (real git in a temp repo)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from spawn_session.worktree import WorktreeError, create_worktree, find_repo_root


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

    def sh(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)

    sh("init", "-b", "main")
    (repo / "a.txt").write_text("hello\n", encoding="utf-8")
    sh("add", "a.txt")
    sh("commit", "-m", "init")
    return repo


def test_find_repo_root(git_repo: Path):
    assert find_repo_root(git_repo) == git_repo.resolve()


def test_create_worktree(git_repo: Path):
    wt = create_worktree(git_repo, "fix-flaky-test")
    assert wt.branch == "spawn/fix-flaky-test"
    assert wt.path.endswith("/.worktrees/spawn-fix-flaky-test")
    assert Path(wt.path).is_dir()
    # The worktree is on its own branch.
    out = subprocess.run(
        ["git", "-C", wt.path, "branch", "--show-current"], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "spawn/fix-flaky-test"


def test_create_worktree_custom_dirs(git_repo: Path):
    wt = create_worktree(git_repo, "x", worktree_dir="wt", branch_prefix="sp/")
    assert wt.branch == "sp/x"
    assert wt.path.endswith("/wt/sp-x")


def test_existing_branch_rejected(git_repo: Path):
    create_worktree(git_repo, "dup")
    with pytest.raises(WorktreeError, match="already exists"):
        create_worktree(git_repo, "dup")


def test_not_a_repo(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(WorktreeError):
        create_worktree(empty, "x")
