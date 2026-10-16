#!/usr/bin/env python3
"""Live test for report-back (Card 4 done criterion: "B reports and A runs a turn on it").

Real code path, ephemeral profile:
- real in-process TUI gateway + its Desktop/TUI ``inject_message`` host
  (``install_tui_message_injector``, as on Desktop/TUI startup)
- this repository loaded through the real plugin loader; the ``spawn_session``
  and ``report_back`` handlers are taken from the tool registry (the plugin's
  own module instances, as the agent would call them)
- parent A is a live desktop session; child B is spawned by the real handler
- ``report_back`` in B -> report injected into A -> A runs a real LLM turn ->
  the handover is confirmed ``delivered`` from A's persisted history

Model: a local OpenAI-compatible endpoint (default: the keyless ``ryzen``
llama-swap at http://ryzen.lan.fahsel.ch:8080/v1). No credentials are copied.

Usage: python scripts/live_report_test.py [--base-url URL] [--model NAME] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def log(msg: str) -> None:
    print(f"[live] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://ryzen.lan.fahsel.ch:8080/v1")
    ap.add_argument("--model", default="model")
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    home = Path(tempfile.mkdtemp(prefix="spawn-report-live-"))
    (home / "plugins").mkdir()
    (home / "plugins" / "spawn-session").symlink_to(REPO)
    (home / "config.yaml").write_text(f"""
model:
  default: {json.dumps(args.model)}
  provider: custom:live
  base_url: {json.dumps(args.base_url)}
custom_providers:
  - name: live
    base_url: {json.dumps(args.base_url)}
    model: {json.dumps(args.model)}
agent:
  max_turns: 6
plugins:
  enabled:
    - spawn-session
  entries:
    spawn-session:
      allow_gateway_injection: true
      delivery_confirm_timeout_s: {args.timeout}
""", encoding="utf-8")
    project = Path(tempfile.mkdtemp(prefix="spawn-report-live-work-")) / "project"
    project.mkdir()
    subprocess.run(["git", "-C", str(project), "init", "-q", "-b", "main"], check=True)
    log(f"ephemeral home: {home}")

    os.environ["HERMES_HOME"] = str(home)
    sys.path.insert(0, str(REPO))  # for reading the handover file with this repo's parser
    import hermes_bootstrap  # noqa: E402

    hermes_bootstrap.harden_import_path()
    from tui_gateway import server  # noqa: E402
    from tui_gateway.server import handle_request  # noqa: E402

    server.install_tui_message_injector()

    def rpc(method: str, params: dict | None = None) -> dict:
        resp = handle_request({"id": "live", "method": method, "params": params or {}})
        if not isinstance(resp, dict) or "error" in resp:
            raise RuntimeError(f"{method}: {resp}")
        return resp.get("result") or {}

    from hermes_cli.plugins import get_plugin_manager  # noqa: E402

    get_plugin_manager().discover_and_load()
    from tools.registry import registry  # noqa: E402

    spawn = registry.get_entry("spawn_session")
    report_back = registry.get_entry("report_back")
    if spawn is None or report_back is None:
        log("FATAL: plugin tools not registered")
        return 1
    commands = sorted(get_plugin_manager()._plugin_commands) if hasattr(
        get_plugin_manager(), "_plugin_commands") else None

    evidence: dict = {
        "commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                 capture_output=True, text=True).stdout.strip(),
        "ephemeral_home": str(home), "model": f"custom:live:{args.model}", "base_url": args.base_url,
        "registered_commands": commands,
    }

    a = rpc("session.create", {
        "title": "LIVE: report-back parent", "source": "desktop", "cwd": str(project), "cwd_explicit": True,
        "messages": [{"role": "user", "content": "You are the parent session of a report-back live test."},
                     {"role": "assistant", "content": "Understood."}],
    })
    a_id = a["stored_session_id"]
    evidence["parent_session"] = {"runtime_id": a["session_id"], "stored_id": a_id}
    log(f"parent A: {a_id}")

    res = json.loads(spawn.handler({
        "title": "Live report child", "initiation": "user_asked", "model": f"custom:live:{args.model}",
        "task": "Live test child. Reply briefly with: CHILD-OK", "context": "Card 4 live evidence.",
    }, session_id=a_id))
    evidence["spawn_result"] = res
    if not res.get("ok"):
        log(f"FATAL: spawn failed: {res}")
        return 1
    b_id = res["child_session_id"]
    log(f"child B: {b_id}")

    db = home / "state.db"

    def q(sql: str, *p):
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            return conn.execute(sql, p).fetchall()
        finally:
            conn.close()

    def wait(pred, timeout: float, step: float = 1.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            try:
                if pred():
                    return True
            except sqlite3.Error:
                pass
            time.sleep(step)
        return False

    # Let B's seed turn finish so B is idle (realistic: B reports at the end of its work).
    wait(lambda: q("SELECT COUNT(*) FROM messages WHERE session_id=? AND role='assistant'", b_id)[0][0] >= 1,
         args.timeout)

    a_assist_before = q("SELECT COUNT(*) FROM messages WHERE session_id=? AND role='assistant'", a_id)[0][0]
    t0 = time.time()
    rb = json.loads(report_back.handler({
        "result": "Live child finished: replied CHILD-OK.",
        "changes": ["none (live test)"],
        "open_items": ["parent: acknowledge with the exact word REPORT-RECEIVED"],
        "artifacts": [{"kind": "path", "value": res["handover_path"]}],
    }, session_id=b_id))
    evidence["report_back_result"] = rb
    log(f"report_back: {rb}")
    if not rb.get("ok"):
        return 1

    from spawn_session.handover import read  # noqa: E402  (file read only)

    hp = Path(res["handover_path"])

    def all_delivered() -> bool:
        h = read(hp)
        n = len(q("SELECT 1 FROM messages WHERE session_id=? AND role='user' AND content LIKE ?",
                  a_id, "[spawn-session report: Live report child%"))
        return h.status == "delivered" and n == len(h.reports)

    # Every report (B may also have called report_back itself during its seed
    # turn) must reach A; later ones queue behind A's running turn (AT4.3).
    delivered = wait(all_delivered, args.timeout)
    turn_ran = wait(lambda: q("SELECT COUNT(*) FROM messages WHERE session_id=? AND role='assistant'",
                              a_id)[0][0] > a_assist_before, args.timeout)
    wait(lambda: not q("SELECT 1 FROM messages WHERE session_id=? ORDER BY id DESC LIMIT 1", a_id)
         or q("SELECT role FROM messages WHERE session_id=? ORDER BY id DESC LIMIT 1", a_id)[0][0] == "assistant",
         args.timeout)
    evidence["reports_in_handover"] = len(read(hp).reports)
    rows = q("SELECT role, substr(content,1,300), timestamp FROM messages WHERE session_id=? ORDER BY id", a_id)
    evidence["parent_messages"] = [{"role": r, "content": c, "ts": ts} for r, c, ts in rows]
    evidence["report_delivered_status"] = read(hp).status
    evidence["handover_history"] = read(hp).meta.get("history")
    evidence["parent_turn_ran"] = turn_ran
    evidence["seconds_to_delivered"] = round(time.time() - t0, 1)
    marker_ok = any(m["role"] == "user" and m["content"].startswith("[spawn-session report: Live report child")
                    for m in evidence["parent_messages"])
    evidence["marker_in_parent_history"] = marker_ok

    out = Path(args.out) if args.out else home / "live-report-evidence.json"
    out.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"evidence: {out}")
    ok = delivered and turn_ran and marker_ok
    log("LIVE TEST " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
