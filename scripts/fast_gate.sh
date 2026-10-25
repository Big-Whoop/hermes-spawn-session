#!/usr/bin/env bash
# Fast gate (Option D of ~/hermes-research/2026-10-17-plugin-e2e-staging/REPORT.md).
#
# One command, agent-runnable, non-zero exit on any failure:
#   1. pytest
#   2. node scripts/smoke_desktop_plugin.mjs
#   3. deptry (static undeclared-dependency check, throwaway venv under $TMPDIR)
#   4. hermes plugins doctor --ci          (temporary HERMES_HOME)
#   5. hermes plugins validate --json (per-check evaluation with an allowlist)
#   6. isolated `hermes serve --port 0`   (same temporary HERMES_HOME)
#   7. Playwright backend project (e2e/, `--project=backend`): the e2e global
#      setup starts its own sandbox HERMES_HOME + `hermes serve --port 0`;
#      TMPDIR points under the gate's temp HOME, so that sandbox and the
#      artifacts (E2E_ARTIFACTS_DIR) live there and are removed with it.
#      The desktop project is EXCLUDED: Electron does not render in this
#      sandbox; it runs only in the hermes-e2e k8s Job.
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
#        HERMES_PYTHON Python of the Hermes install, for the e2e helper
#                      (default /opt/hermes/.venv/bin/python3)

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_BIN="${HERMES_BIN:-/opt/hermes/bin/hermes}"
PYTHON="${PYTHON:-python3}"
SERVE_TIMEOUT="${SERVE_TIMEOUT:-90}"
SCRATCH="${TMPDIR:-/tmp}"
PLUGIN_NAME="spawn-session"

# Allowlist for `plugins validate --json` (stage 5). Known, deferred failures:
#   (none; the research archive that failed the security scan moved out of
#   the repo to ~/hermes-research/)
# Warnings are allowlisted by prefix:
#   private core imports - catalog rule 9 (tui_gateway.server); deferred
#                    until upstream exposes a public session-creation seam
#                    (NousResearch/hermes-agent#140199, part 2).
# Everything else must pass.
VALIDATE_ALLOWED_FAILED_CHECKS=()
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

gate_pids() { # PIDs (ours, not $$) with HERMES_HOME or TMPDIR at/below $GATE_HOME
    local p env
    for p in $(pgrep -u "$(id -u)" 2>/dev/null); do
        [ "$p" = "$$" ] && continue
        env=$({ tr '\0' '\n' <"/proc/$p/environ"; } 2>/dev/null) || continue
        if printf '%s\n' "$env" | grep -qE "^(HERMES_HOME|TMPDIR)=$GATE_HOME(/|\$)"; then
            echo "$p"
        fi
    done
}

kill_gate_processes() {
    # Kill every process of ours whose environment carries the temp HERMES_HOME
    # or a HERMES_HOME below it (the e2e sandbox of stage 7).
    # `hermes serve` forks; killing only $SERVE_PID can leave the listener up.
    [ -n "$GATE_HOME" ] || return 0
    local p pids=()
    for p in $(gate_pids); do pids+=("$p"); done
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
log "1/7 pytest"
if out=$("$PYTHON" -m pytest -q 2>&1); then
    echo "$out" | tail -3
    record pytest PASS "$(echo "$out" | tail -1)"
else
    echo "$out" | tail -40
    record pytest FAIL "$(echo "$out" | tail -1)"
fi

# --- 2. desktop smoke --------------------------------------------------------
log "2/7 node scripts/smoke_desktop_plugin.mjs"
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
log "3/7 deptry"
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
log "4/7 hermes plugins doctor --ci (temp HOME)"
out=$(HERMES_HOME="$GATE_HOME" "$HERMES_BIN" plugins doctor --ci "$ROOT" 2>&1); rc=$?
echo "$out" | grep -v 'install out of sync'
if [ $rc -eq 0 ]; then
    record doctor PASS
else
    record doctor FAIL "$(echo "$out" | grep -m1 'ERROR' | sed 's/^ *//')"
fi

# --- 5. plugins validate --json ----------------------------------------------
log "5/7 hermes plugins validate --json"
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
    PASS) record validate PASS "allowlisted: rule-9 warning" ;;
    *)    record validate FAIL "${verdict#FAIL }" ;;
esac

# --- 6. isolated serve -------------------------------------------------------
log "6/7 isolated hermes serve --port 0"
# Strip inherited HERMES_* (e.g. HERMES_DASHBOARD_OIDC_* inside a Hermes pod,
# which switch the temp server to OIDC auth and make the route answer 401),
# the same way e2e/support/backend.ts cleanEnv() does.
mapfile -t HERMES_VARS < <(compgen -e | grep -E '^_?HERMES_')
env "${HERMES_VARS[@]/#/-u}" HERMES_HOME="$GATE_HOME" "$HERMES_BIN" serve --port 0 --host 127.0.0.1 --skip-build \
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

# Stop stage 6's server before the e2e stage starts its own.
kill_gate_processes

# --- 7. Playwright backend project -------------------------------------------
log "7/7 playwright --project=backend (e2e sandbox under temp HOME)"
E2E_TMP="$GATE_HOME/e2e"
mkdir -p "$E2E_TMP"
lock_sha=$(sha256sum e2e/package-lock.json | cut -d' ' -f1)
stamp="e2e/node_modules/.fast-gate-lock-sha256"
npm_ok=1
if [ ! -f "$stamp" ] || [ "$(cat "$stamp")" != "$lock_sha" ]; then
    echo "npm ci (node_modules missing or package-lock.json changed)"
    if out=$(cd e2e && npm ci --include=dev --no-audit --no-fund 2>&1); then
        echo "$lock_sha" >"$stamp"
    else
        echo "$out" | tail -20
        npm_ok=0
    fi
else
    echo "node_modules up to date (package-lock.json unchanged), skipping npm ci"
fi
if [ $npm_ok -eq 0 ]; then
    record e2e FAIL "npm ci failed"
else
    # Force local sandbox mode BEFORE Playwright starts: strip every inherited
    # HERMES_* (external-backend selectors HERMES_DESKTOP_REMOTE_URL/_TOKEN,
    # HERMES_DASHBOARD_* auth) and every E2E_* (E2E_HERMES_HOME, E2E_STATE_FILE,
    # E2E_PROJECT_DIR, E2E_MOCK_LLM_*, E2E_KEEP, ...), then set only the
    # stage-owned values. externalBackend() therefore always returns null and
    # the state file is pinned under $E2E_TMP.
    e2e_python="${HERMES_PYTHON:-/opt/hermes/.venv/bin/python3}"
    mapfile -t E2E_STRIP < <(compgen -e | grep -E '^(_?HERMES_|E2E_)')
    out=$(cd e2e && env "${E2E_STRIP[@]/#/-u}" TMPDIR="$E2E_TMP" \
        E2E_ARTIFACTS_DIR="$E2E_TMP/artifacts" E2E_STATE_FILE="$E2E_TMP/state.json" \
        HERMES_BIN="$HERMES_BIN" HERMES_PYTHON="$e2e_python" \
        npx playwright test --project=backend --reporter=line 2>&1); rc=$?
    echo "$out" | grep -E '\[e2e\] backend|passed|failed|skipped|flaky|Error' | tail -40
    # The e2e sandbox HERMES_HOME must live under this stage's TMPDIR.
    if ! echo "$out" | grep -q "^\[e2e\] backend .* HERMES_HOME=$E2E_TMP/"; then
        rc=99; echo "e2e sandbox HERMES_HOME is not under $E2E_TMP"
    fi
    summary=$(echo "$out" | grep -Eo '[0-9]+ (passed|failed|skipped|flaky)' | paste -sd' ' -)
    sleep 1
    left=$(gate_pids)
    if [ -n "$left" ]; then
        echo "leftover processes after e2e:"; for p in $left; do ps -o pid=,args= -p "$p"; done
        kill_gate_processes
        record e2e FAIL "leftover processes after stage"
    elif [ $rc -eq 0 ]; then
        record e2e PASS "$summary"
    else
        record e2e FAIL "rc=$rc ${summary}"
    fi
fi

# --- summary -----------------------------------------------------------------
log "summary"
printf '%s\n' "${RESULTS[@]}"
if [ $FAILED -eq 0 ]; then echo "FAST GATE: GREEN"; else echo "FAST GATE: RED"; fi
exit $FAILED
