#!/usr/bin/env bash
# Live-install health check for the spawn-session plugin. READ-ONLY.
#
# Run after a restart of the live Hermes. Not part of scripts/fast_gate.sh
# (the gate checks the repo state only). Checks:
#   1. `hermes plugins list` shows spawn-session as enabled;
#   2. no "Failed to load plugin 'spawn-session'" in the live errors.log
#      since the last gateway start (last "Gateway running" in gateway.log).
# Exits 0 if healthy, 1 if broken, 2 if it cannot tell.
#
# Never writes to HERMES_HOME, never restarts, never installs anything.
#
# Env: HERMES_BIN   Hermes CLI (default /opt/hermes/bin/hermes)
#      HERMES_HOME  live home (default /opt/data)

set -uo pipefail

HERMES_BIN="${HERMES_BIN:-/opt/hermes/bin/hermes}"
LIVE_HOME="${HERMES_HOME:-/opt/data}"
PLUGIN_NAME="spawn-session"
LOGS="$LIVE_HOME/logs"
BROKEN=0

echo "live health: $LIVE_HOME ($("$HERMES_BIN" --version 2>/dev/null | head -1))"

# --- 1. enabled --------------------------------------------------------------
row=$("$HERMES_BIN" plugins list 2>/dev/null | grep -m1 "│ $PLUGIN_NAME ")
if [ -z "$row" ]; then
    echo "FAIL  list     $PLUGIN_NAME not listed"; BROKEN=1
elif echo "$row" | grep -q "│ enabled "; then
    echo "PASS  list     $PLUGIN_NAME enabled"
else
    echo "FAIL  list     $PLUGIN_NAME not enabled: $(echo "$row" | tr -s ' ')"; BROKEN=1
fi

# --- 2. load errors since last start -----------------------------------------
if [ ! -r "$LOGS/errors.log" ] || [ ! -r "$LOGS/gateway.log" ]; then
    echo "UNKNOWN logs   $LOGS/errors.log or gateway.log not readable"
    exit 2
fi
since=$(grep 'Gateway running' "$LOGS/gateway.log" | tail -1 | cut -c1-19)
if [ -z "$since" ]; then
    echo "UNKNOWN logs   no 'Gateway running' line in gateway.log"
    exit 2
fi
# Log lines start with "YYYY-MM-DD HH:MM:SS", so string comparison is chronological.
errs=$(awk -v since="$since" -v pat="Failed to load plugin '$PLUGIN_NAME'" \
    'substr($0,1,19) >= since && index($0, pat)' "$LOGS/errors.log")
count=$(printf '%s' "$errs" | grep -c . )
if [ "$count" -eq 0 ]; then
    echo "PASS  logs     no load errors since $since"
else
    echo "FAIL  logs     $count load error(s) since $since; last:"
    printf '%s\n' "$errs" | tail -1 | sed 's/^/      /'
    BROKEN=1
fi

if [ $BROKEN -eq 0 ]; then echo "LIVE HEALTH: OK"; else echo "LIVE HEALTH: BROKEN"; fi
exit $BROKEN
