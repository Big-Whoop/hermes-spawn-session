"""Git worktree creation for spawned children (decision D7, SPEC section 5).

``worktree: true`` creates ``<repo_root>/<worktree_dir>/spawn-<slug>`` on a new
branch ``spawn/<slug>`` and the child session's cwd becomes that worktree.
Worktrees are never auto-deleted by this module (D11 cleanup is a later card).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorktreeError(Exception):
    """Worktree creation failed or the repo context is missing."""


@dataclass(frozen=True)
class Worktree:
    path: str
    branch: str


def _run_git(repo_root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise WorktreeError(
            f"git {' '.join(args)} failed in {repo_root}: {(proc.stderr or proc.stdout).strip()}"
        )
    return proc.stdout.strip()


def find_repo_root(cwd: str | Path) -> Path:
    """Git repository root containing ``cwd`` (top-level worktree of the repo)."""
    cwd = Path(cwd)
    if not cwd.exists():
        raise WorktreeError(f"cwd does not exist: {cwd}")
    top = _run_git(cwd, "rev-parse", "--show-toplevel")
    return Path(top)


def create_worktree(
    repo_root: str | Path,
    slug: str,
    *,
    worktree_dir: str = ".worktrees",
    branch_prefix: str = "spawn/",
) -> Worktree:
    """Create ``<repo_root>/<worktree_dir>/<branch_prefix><slug>`` on a fresh branch.

    The directory name mirrors the branch (``spawn-<slug>``) so the worktree and
    its branch are easy to match in listings. Raises :class:`WorktreeError` if
    the branch or path already exists — callers must pick a unique slug or clean
    up first; nothing is ever force-deleted here.
    """
    repo_root = Path(repo_root)
    # Raises WorktreeError with git's message when this is not a repository.
    _run_git(repo_root, "rev-parse", "--git-dir")
    branch = f"{branch_prefix}{slug}"
    wt_name = branch.replace("/", "-")
    wt_path = repo_root / worktree_dir / wt_name
    if wt_path.exists():
        raise WorktreeError(f"worktree path already exists: {wt_path}")
    try:
        _run_git(repo_root, "worktree", "add", str(wt_path), "-b", branch)
    except WorktreeError as exc:
        # Distinguish "branch already exists" for a clearer error.
        if "already exists" in str(exc):
            raise WorktreeError(f"branch or worktree already exists for slug {slug!r}") from exc
        raise
    return Worktree(path=str(wt_path), branch=branch)


@dataclass(frozen=True)
class BankResult:
    """Outcome of :func:`bank_changes` (D11: never lose work before cleanup)."""

    dirty: bool
    commit: str | None
    pushed: bool
    remote: str | None
    error: str | None = None


def bank_changes(worktree_path: str | Path, branch: str, message: str) -> BankResult:
    """WIP-commit uncommitted changes in ``worktree_path`` and push when a remote exists.

    Clean trees are left untouched. Push failures are reported, never fatal:
    the commit is local and nothing is deleted either way.
    """
    wt = Path(worktree_path)
    if not wt.is_dir():
        raise WorktreeError(f"worktree path does not exist: {wt}")
    status = _run_git(wt, "status", "--porcelain")
    commit: str | None = None
    if status:
        _run_git(wt, "add", "-A")
        _run_git(
            wt, "-c", "user.name=spawn-session", "-c", "user.email=spawn-session@localhost",
            "commit", "--no-verify", "-m", message,
        )
        commit = _run_git(wt, "rev-parse", "HEAD")
    remotes = [r for r in _run_git(wt, "remote").splitlines() if r.strip()]
    remote = "origin" if "origin" in remotes else (remotes[0] if remotes else None)
    pushed = False
    error = None
    if remote is not None:
        try:
            _run_git(wt, "push", "-u", remote, branch)
            pushed = True
        except WorktreeError as exc:
            error = str(exc)
    return BankResult(dirty=bool(status), commit=commit, pushed=pushed, remote=remote, error=error)


def remove_worktree(repo_root: str | Path, worktree_path: str | Path, branch: str) -> None:
    """Remove a worktree and its branch. Only call after explicit user confirmation (D11).

    Refuses (git error) when the worktree still has uncommitted changes: bank first.
    """
    repo_root = Path(repo_root)
    _run_git(repo_root, "worktree", "remove", str(worktree_path))
    _run_git(repo_root, "branch", "-D", branch)
