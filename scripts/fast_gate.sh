#!/usr/bin/env bash
# Fast gate (Option D of .hermes/research/2026-10-17-plugin-e2e-staging/REPORT.md).
#
# One command, agent-runnable, non-zero exit on any failure:
#   1. pytest
#   2. node scripts/smoke_desktop_plugin.mjs
#   3. deptry (static undeclared-dependency check, throwaway venv under $TMPDIR)
#   4. hermes plugins doctor --ci          (temporary HERMES_HOME)
#   5. hermes plugins validate --json (per-check evaluation with an allowlist)
#   6. isolated `hermes serve --port 0`   (same temporary HERMES_HOME)
#
# Checks the repo state only. Live-install health: scripts/live_health.sh.
#
# Safety: never touches /opt/data (the live HERMES_HOME), never uses
# --install-deps, never installs anything into the Hermes venv, never runs
# `hermes serve --stop` (that stops every server, including live ones).
#
# Usage: scripts/fast_gate.sh            (run from anywhere)
# Env:   HERMES_BIN   Hermes CLI (default /opt/hermes/bin/hermes)
#        PYTHON       Python for pytest (default python3)
#        SERVE_TIMEOUT seconds to wait for HERMES_BACKEND_READY (default 90)

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_BIN="${HERMES_BIN:-/opt/hermes/bin/hermes}"
PYTHON="${PYTHON:-python3}"
SERVE_TIMEOUT="${SERVE_TIMEOUT:-90}"
SCRATCH="${TMPDIR:-/tmp}"
PLUGIN_NAME="spawn-session"

# Allowlist for `plugins validate --json` (stage 5). Known, deferred failures:
#   security scan  - flags German research notes under .hermes/research/ that
#                    ship inside the plugin tree (deferred, see
#                    docs/catalog-contribution.md).
# Warnings are allowlisted by prefix:
#   private core imports - catalog rule 9 (gateway.session_context,
#                    tui_gateway.server); deferred until upstream exposes a
#                    public seam (NousResearch/hermes-agent#140199).
# Everything else must pass.
VALIDATE_ALLOWED_FAILED_CHECKS=("security scan")
VALIDATE_ALLOWED_WARNING_PREFIXES=("private core imports")

declare -a RESULTS=()
FAILED=0
GATE_HOME=""
SERVE_PID=""

log() { printf '\n=== %s\n' "$*"; }
record() { # record <stage> <PASS|FAIL> [detail]
    RESULTS+=("$(printf '%-10s %-4s %s' "$1" "$2" "${3:-}")")
    [ "$2" = "PASS" ] || FAILED=1
}

kill_gate_processes() {
    # Kill every process of ours whose environment carries the temp HERMES_HOME.
    # `hermes serve` forks; killing only $SERVE_PID can leave the listener up.
    [ -n "$GATE_HOME" ] || return 0
    local p pids=()
    for p in $(pgrep -u "$(id -u)" 2>/dev/null); do
        if { tr '\0' '\n' <"/proc/$p/environ"; } 2>/dev/null | grep -qxF "HERMES_HOME=$GATE_HOME"; then
            pids+=("$p")
        fi
    done
    [ ${#pids[@]} -eq 0 ] && return 0
    kill "${pids[@]}" 2>/dev/null
    for _ in $(seq 1 20); do
        local alive=0
        for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null && alive=1; done
        [ $alive -eq 0 ] && return 0
        sleep 0.5
    done
    kill -9 "${pids[@]}" 2>/dev/null
    return 0
}

cleanup() {
    kill_gate_processes
    if [ -n "$GATE_HOME" ]; then
        case "$GATE_HOME" in
            "$SCRATCH"/fast-gate-home.*) rm -rf "$GATE_HOME" ;;
        esac
        if [ -e "$GATE_HOME" ]; then
            echo "WARNING: temp HOME not removed: $GATE_HOME" >&2
        else
            echo "temp HOME removed: $GATE_HOME"
        fi
    fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM

cd "$ROOT" || exit 2
echo "fast gate: $ROOT ($(git rev-parse --short HEAD 2>/dev/null || echo no-git))"
echo "hermes: $("$HERMES_BIN" --version 2>/dev/null | head -1)"

# --- 1. pytest ---------------------------------------------------------------
log "1/6 pytest"
if out=$("$PYTHON" -m pytest -q 2>&1); then
    echo "$out" | tail -3
    record pytest PASS "$(echo "$out" | tail -1)"
else
    echo "$out" | tail -40
    record pytest FAIL "$(echo "$out" | tail -1)"
fi

# --- 2. desktop smoke --------------------------------------------------------
log "2/6 node scripts/smoke_desktop_plugin.mjs"
if out=$(node scripts/smoke_desktop_plugin.mjs 2>&1); then
    echo "$out" | tail -3
    record smoke PASS
else
    echo "$out" | tail -40
    record smoke FAIL
fi

# --- 3. deptry ---------------------------------------------------------------
# Config lives in pyproject.toml [tool.deptry]: host-provided modules are
# ignored for DEP001. deptry is installed into a throwaway venv only.
log "3/6 deptry"
DEPTRY_VENV="$SCRATCH/fast-gate-deptry-venv"
if [ ! -x "$DEPTRY_VENV/bin/deptry" ]; then
    rm -rf "$DEPTRY_VENV"
    python3 -m venv "$DEPTRY_VENV" >/dev/null 2>&1 \
        && "$DEPTRY_VENV/bin/pip" install -q --disable-pip-version-check deptry >/dev/null 2>&1
fi
if [ ! -x "$DEPTRY_VENV/bin/deptry" ]; then
    echo "could not install deptry into $DEPTRY_VENV"
    record deptry FAIL "deptry install failed"
elif out=$("$DEPTRY_VENV/bin/deptry" . 2>&1); then
    echo "$out" | tail -3
    record deptry PASS
else
    echo "$out" | grep -v '^Assuming' | tail -40
    record deptry FAIL "$(echo "$out" | grep -c ' DEP0') issue(s)"
fi

# --- isolated HERMES_HOME (stages 4 and 6) -----------------------------------
# The gate checks the REPO state only. Doctor and serve both run against a
# fresh temporary HERMES_HOME with the repo linked in as the plugin, so the
# live install (/opt/data) is never read or written. Live-install health is
# a separate, read-only script: scripts/live_health.sh.
GATE_HOME="$(mktemp -d "$SCRATCH/fast-gate-home.XXXXXX")"
case "$GATE_HOME" in "$SCRATCH"/fast-gate-home.*) ;; *) echo "refusing: unexpected temp HOME $GATE_HOME"; exit 2 ;; esac
case "$(cd "$GATE_HOME" && pwd -P)" in /opt/data|/opt/data/) echo "refusing: temp HOME is the live HOME"; exit 2 ;; esac
mkdir -p "$GATE_HOME/plugins"
ln -s "$ROOT" "$GATE_HOME/plugins/$PLUGIN_NAME"
# Enable via config instead of `hermes plugins enable`: enable runs the
# dependency installer, which builds a multi-GB environment in the HOME.
printf 'plugins:\n  enabled:\n    - %s\n  disabled: []\n' "$PLUGIN_NAME" >"$GATE_HOME/config.yaml"
echo "temp HOME: $GATE_HOME"

# --- 4. plugins doctor --ci --------------------------------------------------
log "4/6 hermes plugins doctor --ci (temp HOME)"
out=$(HERMES_HOME="$GATE_HOME" "$HERMES_BIN" plugins doctor --ci "$ROOT" 2>&1); rc=$?
echo "$out" | grep -v 'install out of sync'
if [ $rc -eq 0 ]; then
    record doctor PASS
else
    record doctor FAIL "$(echo "$out" | grep -m1 'ERROR' | sed 's/^ *//')"
fi

# --- 5. plugins validate --json ----------------------------------------------
log "5/6 hermes plugins validate --json"
json=$("$HERMES_BIN" plugins validate --json "$ROOT" 2>/dev/null)
verdict=$(VALIDATE_JSON="$json" \
    ALLOWED_CHECKS="$(printf '%s\n' "${VALIDATE_ALLOWED_FAILED_CHECKS[@]}")" \
    ALLOWED_WARNINGS="$(printf '%s\n' "${VALIDATE_ALLOWED_WARNING_PREFIXES[@]}")" \
    python3 - <<'PY'
import json, os, sys
try:
    data = json.loads(os.environ["VALIDATE_JSON"])
except Exception as exc:
    print(f"FAIL unparseable validate output: {exc}")
    sys.exit(0)
allowed_checks = {c for c in os.environ["ALLOWED_CHECKS"].splitlines() if c}
allowed_warn = [w for w in os.environ["ALLOWED_WARNINGS"].splitlines() if w]
bad = []
for check in data.get("checks", []):
    mark = "ok " if check.get("ok") else ("ALLOWED" if check.get("name") in allowed_checks else "FAIL")
    print(f"  [{mark}] {check.get('name')}: {check.get('detail')}", file=sys.stderr)
    if mark == "FAIL":
        bad.append(check.get("name"))
for warning in data.get("warnings", []):
    ok = any(warning.startswith(p) for p in allowed_warn)
    print(f"  [{'ALLOWED' if ok else 'FAIL'} warning] {warning[:160]}", file=sys.stderr)
    if not ok:
        bad.append("warning: " + warning[:60])
print(("FAIL " + ", ".join(bad)) if bad else "PASS")
PY
)
case "$verdict" in
    PASS) record validate PASS "allowlisted: ${VALIDATE_ALLOWED_FAILED_CHECKS[*]}; rule-9 warning" ;;
    *)    record validate FAIL "${verdict#FAIL }" ;;
esac

# --- 6. isolated serve -------------------------------------------------------
log "6/6 isolated hermes serve --port 0"
HERMES_HOME="$GATE_HOME" "$HERMES_BIN" serve --port 0 --host 127.0.0.1 --skip-build \
    </dev/null >"$GATE_HOME/serve.out" 2>&1 &
SERVE_PID=$!
port=""
for _ in $(seq 1 "$SERVE_TIMEOUT"); do
    port=$(sed -n 's/^HERMES_BACKEND_READY port=\([0-9]*\).*/\1/p' "$GATE_HOME/serve.out" | head -1)
    [ -n "$port" ] && break
    kill -0 "$SERVE_PID" 2>/dev/null || break
    sleep 1
done

if [ -z "$port" ]; then
    tail -20 "$GATE_HOME/serve.out"
    record serve FAIL "no HERMES_BACKEND_READY within ${SERVE_TIMEOUT}s"
else
    echo "HERMES_BACKEND_READY port=$port"
    base="http://127.0.0.1:$port"
    # The served index carries this temporary server's own session token,
    # the same one the dashboard SDK's fetchJSON sends. Never printed.
    token=$(curl -s "$base/" | sed -n 's/.*__HERMES_SESSION_TOKEN__="\([^"]*\)".*/\1/p' | head -1)
    code=$(curl -s -o "$GATE_HOME/route.json" -w '%{http_code}' \
        -H "Authorization: Bearer $token" \
        "$base/api/plugins/$PLUGIN_NAME/proposals?session_id=fast-gate-probe")
    body=$(head -c 200 "$GATE_HOME/route.json")
    echo "GET /api/plugins/$PLUGIN_NAME/proposals -> $code $body"
    sleep 1
    load_err=$(grep -rh "Failed to load plugin.*$PLUGIN_NAME\|Failed to load plugin $PLUGIN_NAME" \
        "$GATE_HOME/logs" "$GATE_HOME/serve.out" 2>/dev/null | head -3)
    mounted=$(grep -rhc "Mounted plugin API routes: /api/plugins/$PLUGIN_NAME/" "$GATE_HOME/logs" 2>/dev/null \
        | awk '{s+=$1} END {print s+0}')
    if [ -n "$load_err" ]; then
        echo "$load_err"
        record serve FAIL "plugin load error in temp HOME logs"
    elif [ "$code" != "200" ] || ! grep -q '"proposals"' "$GATE_HOME/route.json"; then
        record serve FAIL "plugin route answered $code"
    elif [ "$mounted" -lt 1 ]; then
        record serve FAIL "routes not reported as mounted"
    else
        record serve PASS "port $port, route 200, no load errors"
    fi
fi

# --- summary -----------------------------------------------------------------
log "summary"
printf '%s\n' "${RESULTS[@]}"
if [ $FAILED -eq 0 ]; then echo "FAST GATE: GREEN"; else echo "FAST GATE: RED"; fi
exit $FAILED
