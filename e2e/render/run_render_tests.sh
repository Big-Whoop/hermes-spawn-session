#!/usr/bin/env bash
# Render tests for desktop/plugin.js with the real @hermes/plugin-sdk (jsdom).
# See docs/desktop-render-tests.md.
#
# Env:
#   HERMES_AGENT_CHECKOUT  hermes-agent checkout (default: $TMPDIR/hermes-agent-v0222).
#                          Cloned at HERMES_AGENT_REF and npm-installed if missing.
#   HERMES_AGENT_REF       tag to clone (default v0.22.2, the target Hermes version).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
ref="${HERMES_AGENT_REF:-v0.22.2}"
checkout="${HERMES_AGENT_CHECKOUT:-${TMPDIR:-/tmp}/hermes-agent-${ref//./}}"
desk="$checkout/apps/desktop"

if [ ! -d "$checkout/.git" ]; then
  git clone --depth 1 --branch "$ref" https://github.com/NousResearch/hermes-agent "$checkout"
fi
if [ ! -x "$checkout/node_modules/.bin/vitest" ]; then
  (cd "$checkout" && npm ci --include=dev --workspace apps/desktop --include-workspace-root=false --ignore-scripts --no-audit --no-fund)
fi

dest="$desk/src/__spawn_session__"
rm -rf "$dest"
mkdir -p "$dest"
trap 'rm -rf "$dest"' EXIT
cp "$repo/desktop/plugin.js" "$dest/plugin.js"
cp "$here"/*.render.test.tsx "$dest/"

cd "$desk"
NODE_ENV=development "$checkout/node_modules/.bin/vitest" run --project ui src/__spawn_session__ "$@"
