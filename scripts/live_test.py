#!/usr/bin/env python3
"""Live test for the spawn-session backend (Card 2 done criterion).

Creates a REAL child session through the real code path — the same in-process
TUI-gateway JSON-RPC that the Desktop client and this plugin's tool use — with
an ephemeral Hermes profile, and records documented evidence (session ids,
models, handover file).

What is exercised for real:
- ``tui_gateway`` bootstrap + JSON-RPC contracts (session.create validation)
- plugin discovery/loading of THIS repository as an installed plugin
  (plugin.yaml + register() wiring the spawn_session tool)
- the actual ``spawn_session_handler`` (all D-rules) against a real state DB
- child session row creation in the profile's state.db

What is NOT exercised (documented limits):
- The LLM decision to call the tool (unit tests cover the handler; only the
  model turn that would invoke it is simulated by calling the handler directly).
- B's first agent turn: ``prompt.submit`` is accepted and scheduled, but with
  an ephemeral profile without provider credentials the turn cannot complete.
  Pass --run-turn plus a working credential set to execute it end-to-end.

Usage:
    python scripts/live_test.py [--model provider:model] [--run-turn]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def log(msg: str) -> None:
    print(f"[live] {msg}", flush=True)


def setup_ephemeral_home(model_ref: str) -> Path:
    """Create a temp profile with this repo installed as the spawn-session plugin."""
    home = Path(tempfile.mkdtemp(prefix="spawn-session-live-"))
    (home / "plugins").mkdir(parents=True)
    # Install the plugin by pointing at the repository checkout (read-only use).
    link = home / "plugins" / "spawn-session"
    link.symlink_to(REPO)

    provider, model_name = model_ref.rsplit(":", 1)
    config_yaml = f"""
model:
  default: {json.dumps(model_name)}
  provider: {json.dumps(provider)}
plugins:
  enabled:
    - spawn-session
"""
    (home / "config.yaml").write_text(config_yaml, encoding="utf-8")
    log(f"ephemeral home: {home}")
    return home


def create_git_project(base: Path) -> Path:
    project = base / "project"
    project.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "live", "GIT_AUTHOR_EMAIL": "l@t",
           "GIT_COMMITTER_NAME": "live", "GIT_COMMITTER_EMAIL": "l@t"}

    def sh(*a: str) -> None:
        subprocess.run(list(a), check=True, capture_output=True, env=env)

    sh("git", "-C", str(project), "init", "-b", "main")
    (project / "README.md").write_text("# live test project\n", encoding="utf-8")
    sh("git", "-C", str(project), "add", "README.md")
    sh("git", "-C", str(project), "commit", "-m", "init")
    return project


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="custom:cpa:qwen38vl-27b-kvu",
                    help="provider:model for the child session (default: cheap local model)")
    ap.add_argument("--run-turn", action="store_true",
                    help="wait for B's first agent turn to complete (needs provider "
                         "credentials in this environment; may cost tokens)")
    ap.add_argument("--turn-timeout", type=int, default=120)
    args = ap.parse_args()

    base = Path(tempfile.mkdtemp(prefix="spawn-session-live-work-"))
    home = setup_ephemeral_home(args.model)
    project = create_git_project(base)

    # --- bootstrap the real TUI gateway in-process (same as `hermes --tui`) ---
    os.environ["HERMES_HOME"] = str(home)
    sys.path.insert(0, str(REPO))
    import hermes_bootstrap  # noqa: E402

    hermes_bootstrap.harden_import_path()
    from tui_gateway import server  # noqa: E402,F401  (bootstraps the RPC method registry)
    from tui_gateway.server import handle_request  # noqa: E402  (rebound onto server globals)

    def rpc(method: str, params: dict | None = None) -> dict:
        resp = handle_request({"id": "live", "method": method, "params": params or {}})
        if not isinstance(resp, dict):
            raise RuntimeError(f"no response frame for {method}")
        if "error" in resp:
            raise RuntimeError(f"{method} error: {resp['error']}")
        return resp.get("result") or {}

    evidence: dict = {
        "repo": str(REPO),
        "commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                 capture_output=True, text=True).stdout.strip(),
        "ephemeral_home": str(home),
        "project_cwd": str(project),
    }

    # --- plugin loading through the real loader ---
    from hermes_cli.plugins import get_plugin_manager  # noqa: E402

    manager = get_plugin_manager()
    manager.discover_and_load()
    from tools.registry import registry  # noqa: E402

    entry = registry.get_entry("spawn_session")
    if entry is None:
        log("FATAL: spawn_session tool not registered after plugin discovery")
        return 1
    evidence["plugin_tool_registered"] = {"toolset": getattr(entry, "toolset", None)}
    log(f"plugin loaded; spawn_session tool registered "
        f"(toolset={evidence['plugin_tool_registered']['toolset']})")

    # --- create parent A (desktop source, seeded so the DB row exists) ---
    a = rpc("session.create", {
        "title": "LIVE: spawn-session parent",
        "source": "desktop",
        "cwd": str(project),
        "cwd_explicit": True,
        "messages": [{"role": "user", "content": "Live-test parent session for spawn-session."}],
    })
    a_stored = a["stored_session_id"]
    evidence["parent_session"] = {"runtime_id": a["session_id"], "stored_id": a_stored}
    log(f"parent A created: stored={a_stored}")

    # --- call the real tool handler (what session A's agent would do) ---
    from spawn_session.tools import spawn_session_handler  # noqa: E402

    raw = spawn_session_handler(
        {
            "title": "Live child task",
            "task": "This is a live test. Reply with exactly: SPAWN-LIVE-OK",
            "context": "Card 2 live evidence for the spawn_session backend.",
            "initiation": "user_asked",
            "model": args.model,
        },
        session_id=a_stored,
    )
    result = json.loads(raw)
    evidence["spawn_result"] = result
    if not result.get("ok"):
        log(f"FATAL: spawn_session failed: {result}")
        return 1
    log(f"spawn ok: status={result['status']} child={result.get('child_session_id')} "
        f"handover={result.get('handover_path')}")

    # --- verify B's row in the profile state DB ---
    import sqlite3  # noqa: E402

    db = home / "state.db"
    deadline = time.time() + 15  # prompt.submit persists the row shortly after acceptance
    b_row = None
    while time.time() < deadline and b_row is None:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            conn.row_factory = sqlite3.Row
            b_row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (result["child_session_id"],)
            ).fetchone()
        except sqlite3.Error:
            pass
        finally:
            conn.close()
        if b_row is None:
            time.sleep(0.5)
    if b_row is None:
        log("FATAL: child session row never appeared in state.db")
        return 1

    # Seed message lands as B's first user row once turn admission persists it.
    seed_seen = False
    deadline2 = time.time() + 15
    while time.time() < deadline2 and not seed_seen:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'",
                (result["child_session_id"],),
            ).fetchone()[0]
            seed_seen = n >= 1
        except sqlite3.Error:
            pass
        finally:
            conn.close()
        if not seed_seen:
            time.sleep(0.5)

    evidence["child_session_row"] = {
        "id": b_row["id"],
        "source": b_row["source"],
        "title": b_row["title"],
        "model": b_row["model"],
        "provider": (b_row["billing_provider"] or ""),
        "cwd": b_row["cwd"],
        "parent_session_id": b_row["parent_session_id"],
    }
    evidence["seed_message_persisted"] = seed_seen

    if args.run_turn:
        deadline3 = time.time() + args.turn_timeout
        done = False
        while time.time() < deadline3 and not done:
            conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            try:
                n = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'assistant'",
                    (result["child_session_id"],),
                ).fetchone()[0]
                done = n >= 1
            except sqlite3.Error:
                pass
            finally:
                conn.close()
            if not done:
                time.sleep(2)
        evidence["first_turn_completed"] = done
        if not done:
            log(f"note: first turn did not complete within {args.turn_timeout}s "
                "(provider credentials likely unavailable in this environment)")

    # --- handover file sanity ---
    h_path = Path(result["handover_path"])
    evidence["handover_file"] = {"path": str(h_path), "exists": h_path.exists(),
                                 "content_head": h_path.read_text(encoding="utf-8")[:400]
                                 if h_path.exists() else None}

    out = base / "live-evidence.json"
    out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"evidence written: {out}")
    print(json.dumps({k: evidence[k] for k in
                      ("commit", "parent_session", "spawn_result", "child_session_row",
                       "seed_message_persisted", "plugin_tool_registered")},
                     indent=2, ensure_ascii=False))

    ok = (result["status"] == "running"
          and evidence["child_session_row"]["source"] == "desktop"
          and evidence["child_session_row"]["parent_session_id"] == a_stored
          and evidence["child_session_row"]["model"])
    log("LIVE TEST " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
