#!/usr/bin/env python3
"""Hermes-side helper for the spawn-session e2e specs.

Some scenarios start with something the agent does, not the user: A's agent
proposes a session (``own_initiative``), or B's agent calls ``report_back``.
A mock LLM could script those tool calls, but only inside a real agent turn.
This helper calls the same plugin handlers directly instead, as
``scripts/live_test.py`` does. It runs with the Hermes venv python and the
backend's HERMES_HOME and prints exactly one JSON line.

Commands:
    seed-parent --title T --cwd DIR [--source desktop]
        Create a parent session row through the in-process TUI-gateway
        ``session.create`` RPC (same call the Desktop makes).
    propose --session-id A --title T --task X [--context C] [--model provider:model]
        Call ``spawn_session`` with ``initiation=own_initiative`` as A's agent
        would. The result is a ``proposed`` handover (no session created yet).
    report --session-id B --result R [--open-item ...]
        Call ``report_back`` as B's agent would.

Example:
    HERMES_HOME=/tmp/h /opt/hermes/.venv/bin/python e2e/support/hermes_helper.py seed-parent --title A --cwd /tmp/p
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# The TUI gateway rebinds sys.stdout to stderr on import (stdout is its JSON-RPC
# channel). Keep a handle on the real stdout for the single result line.
_RESULT_FD = os.dup(1)


def _emit(obj: object, code: int = 0) -> None:
    os.write(_RESULT_FD, (json.dumps(obj) + "\n").encode())
    # The in-process gateway may leave worker threads behind; exit hard.
    os._exit(code)


def _bootstrap_gateway():
    import hermes_bootstrap

    hermes_bootstrap.harden_import_path()
    from tui_gateway import server  # noqa: F401  (bootstraps the RPC method registry)
    from tui_gateway.server import handle_request

    return handle_request


def _tools():
    sys.path.insert(0, str(REPO))
    from spawn_session import tools

    return tools


def cmd_seed_parent(a: argparse.Namespace) -> None:
    handle_request = _bootstrap_gateway()
    resp = handle_request({"id": "e2e-seed", "method": "session.create", "params": {
        "title": a.title,
        "source": a.source,
        "cwd": a.cwd,
        "cwd_explicit": True,
        "messages": [{"role": "user", "content": f"e2e parent session: {a.title}"}],
    }})
    if not isinstance(resp, dict) or "error" in resp:
        _emit({"ok": False, "error": resp.get("error") if isinstance(resp, dict) else "no response"}, 1)
    result = resp.get("result") or {}
    _emit({"ok": True, "session_id": result.get("session_id"),
           "stored_session_id": result.get("stored_session_id")})


def cmd_propose(a: argparse.Namespace) -> None:
    _bootstrap_gateway()
    tools = _tools()
    args = {"title": a.title, "task": a.task, "initiation": "own_initiative"}
    if a.context:
        args["context"] = a.context
    if a.model:
        args["model"] = a.model
    res = json.loads(tools.spawn_session_handler(args, session_id=a.session_id))
    _emit(res, 0 if res.get("ok") else 1)


def cmd_report(a: argparse.Namespace) -> None:
    _bootstrap_gateway()
    tools = _tools()
    args: dict = {"result": a.result}
    if a.open_item:
        args["open_items"] = a.open_item
    res = json.loads(tools.report_back_handler(args, session_id=a.session_id))
    _emit(res, 0 if res.get("ok") else 1)


def main() -> None:
    if not os.environ.get("HERMES_HOME"):
        _emit({"ok": False, "error": "HERMES_HOME is not set"}, 2)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("seed-parent")
    p.add_argument("--title", required=True)
    p.add_argument("--cwd", required=True)
    p.add_argument("--source", default="desktop")
    p = sub.add_parser("propose")
    p.add_argument("--session-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--context")
    p.add_argument("--model")
    p = sub.add_parser("report")
    p.add_argument("--session-id", required=True)
    p.add_argument("--result", required=True)
    p.add_argument("--open-item", action="append")
    a = ap.parse_args()
    try:
        {"seed-parent": cmd_seed_parent, "propose": cmd_propose, "report": cmd_report}[a.cmd](a)
    except Exception as exc:  # always one JSON line
        _emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 1)


if __name__ == "__main__":
    main()
