"""State index for spawn-session (SPEC.md section 6).

``$HERMES_HOME/spawn-session/state.json`` maps every known child session id to
its handover file. The handover files are authoritative; the index is a
convenience cache rebuilt from them whenever it looks stale (missing file,
unknown shape) — so deleting or moving a handover file self-heals on next use.

Layout::

    {
      "children": {
        "<session_id>": {
          "handover_path": "/abs/path/to/handover.md",
          "parent_session_id": "<durable id of A>",
          "status": "running"
        }
      }
    }

Both the child's runtime id and its durable (stored) id are indexed, because
tool handlers see the durable id while RPC results carry both.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Optional

from .handover import HandoverParseError, parse, slugify  # noqa: F401  (parse used by rebuild)

_LOCAL_LOCK = threading.RLock()


class StateIndex:
    """File-backed child-session index with self-healing rebuild."""

    def __init__(self, path: Path):
        self.path = Path(path)

    # ------------------------------------------------------------------ io

    def _read_raw(self) -> dict[str, Any]:
        try:
            with open(self.path, encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            return {}  # corrupt index: treat as empty, rebuild next write
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        from .handover import atomic_write_text

        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        with _LOCAL_LOCK:
            # flock across processes (the gateway and any CLI tool share the file).
            lock_path = self.path.with_name(f".{self.path.name}.lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with open(lock_path, "a+b") as handle:
                try:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                except (ImportError, OSError):
                    pass
                try:
                    atomic_write_text(self.path, text)
                finally:
                    try:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    except (ImportError, OSError):
                        pass

    # ------------------------------------------------------------- children

    @property
    def children(self) -> dict[str, dict[str, Any]]:
        """Child id -> entry, dropping entries whose handover file is gone."""
        data = self._read_raw()
        children = data.get("children")
        if not isinstance(children, dict):
            return {}
        live: dict[str, dict[str, Any]] = {}
        for sid, entry in children.items():
            if not isinstance(entry, dict):
                continue
            path = entry.get("handover_path")
            if isinstance(path, str) and Path(path).exists():
                live[str(sid)] = entry
        return live

    def is_child(self, session_id: str | None) -> bool:
        return bool(session_id) and session_id in self.children

    def handover_for(self, session_id: str | None) -> Optional[Path]:
        entry = self.children.get(session_id or "")
        if not entry:
            return None
        path = entry.get("handover_path")
        return Path(path) if isinstance(path, str) and Path(path).exists() else None

    def register_child(
        self, session_ids: list[str], *, handover_path: Path, parent_session_id: str, status: str
    ) -> None:
        """Index every id of one child session (runtime + durable)."""
        data = self._read_raw()
        children = data.get("children")
        if not isinstance(children, dict):
            children = {}
        entry = {
            "handover_path": str(handover_path),
            "parent_session_id": parent_session_id,
            "status": status,
        }
        for sid in session_ids:
            if sid:
                children[str(sid)] = dict(entry)
        data["children"] = children
        self._write(data)

    def set_status(self, handover_path: Path | str, status: str) -> None:
        """Mirror a handover's status onto every index entry pointing at it."""
        key = str(handover_path)
        data = self._read_raw()
        children = data.get("children")
        if not isinstance(children, dict):
            return
        changed = False
        for entry in children.values():
            if isinstance(entry, dict) and entry.get("handover_path") == key:
                entry["status"] = status
                changed = True
        if changed:
            self._write(data)

    def handovers_for_parent(self, parent_session_id: str) -> list[Path]:
        """Distinct existing handover files whose child belongs to ``parent_session_id``."""
        seen: dict[str, Path] = {}
        for entry in self.children.values():
            if entry.get("parent_session_id") == parent_session_id:
                p = entry.get("handover_path")
                if isinstance(p, str):
                    seen.setdefault(p, Path(p))
        return list(seen.values())

    def remove_child(self, *session_ids: str) -> None:
        data = self._read_raw()
        children = data.get("children")
        if not isinstance(children, dict):
            return
        for sid in session_ids:
            children.pop(sid, None)
        data["children"] = children
        self._write(data)

    def register_handover_root(self, directory: Path) -> None:
        """Remember a handover directory so :func:`load_index` can rescan it.

        Roots live in a sidecar file next to ``state.json`` (not inside it), so
        losing or corrupting the index does not also lose the per-cwd
        ``<A.cwd>/.hermes/handovers`` locations needed to rebuild it.
        """
        roots_path = handover_roots_path(self.path)
        roots = read_handover_roots(roots_path)
        entry = str(Path(directory).resolve())
        if entry in roots:
            return
        from .handover import atomic_write_text

        roots_path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCAL_LOCK:
            atomic_write_text(
                roots_path, json.dumps(sorted(set(roots) | {entry}), indent=2) + "\n"
            )

    def rebuild(self, handover_files: list[Path]) -> int:
        """Rebuild the index from authoritative handover files. Returns entries."""
        children: dict[str, dict[str, Any]] = {}
        for path in handover_files:
            try:
                h = parse(path.read_text(encoding="utf-8"), path=path)
            except (HandoverParseError, OSError, ValueError):
                continue  # unreadable/unparsable file: skip, never fatal
            meta = h.meta
            parent = meta.get("parent_session_id")
            if not isinstance(parent, str) or not parent:
                continue
            child = meta.get("child_session_id")
            status = meta.get("status", "running")
            entry = {"handover_path": str(path), "parent_session_id": parent, "status": status}
            if isinstance(child, str) and child:
                children[child] = dict(entry)
        data = self._read_raw()
        data["children"] = children
        self._write(data)
        return len(children)


def default_state_path(home: Path | None = None) -> Path:
    if home is None:
        from .parent import hermes_home

        home = hermes_home()
    return Path(home) / "spawn-session" / "state.json"


def handover_roots_path(state_path: Path) -> Path:
    return Path(state_path).with_name("handover-roots.json")


def read_handover_roots(roots_path: Path) -> list[str]:
    try:
        with open(roots_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    return [str(x) for x in data if isinstance(x, str)] if isinstance(data, list) else []


def load_index(path: Path | None = None) -> StateIndex:
    """Open the index; rebuild it when empty but handover files exist."""
    path = path or default_state_path()
    index = StateIndex(path)
    if not index.children:
        files = _find_handover_files(path)
        if files:
            index.rebuild(files)
    return index


def _find_handover_files(state_path: Path) -> list[Path]:
    """Handover files live under ``<cwd>/.hermes/handovers`` (per repo) plus the
    profile fallback ``$HERMES_HOME/spawn-session/handovers``. Per-cwd dirs are
    recorded in the ``handover-roots.json`` sidecar at creation time and
    rescanned here. Residual risk: if the sidecar is lost too, per-cwd children
    are not rediscovered until a new spawn re-registers their directory."""
    from .parent import hermes_home

    home = hermes_home()
    dirs: list[Path] = [home / "spawn-session" / "handovers"]
    dirs.extend(Path(d) for d in read_handover_roots(handover_roots_path(state_path)))
    found: list[Path] = []
    seen: set[str] = set()
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.md")):
            key = str(f.resolve())
            if key not in seen:
                seen.add(key)
                found.append(f)
    return found


def running_agent_children(index: StateIndex, parent_session_id: str) -> int:
    """Count RUNNING handover files of ``parent_session_id`` initiated by the agent.

    The handover file is authoritative (SPEC section 6), so this counts files,
    not index entries: one child is indexed under several ids (runtime +
    durable), so entries are de-duplicated by handover path.
    """
    count = 0
    seen: set[str] = set()
    for sid, entry in index.children.items():
        if entry.get("parent_session_id") != parent_session_id:
            continue
        path = index.handover_for(sid)
        if path is None:
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        try:
            h = parse(path.read_text(encoding="utf-8"), path=path)
        except (HandoverParseError, OSError, ValueError):
            continue
        if h.meta.get("status") == "running" and h.meta.get("initiator") == "agent":
            count += 1
    return count
