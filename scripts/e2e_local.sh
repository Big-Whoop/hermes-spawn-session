#!/usr/bin/env bash
# Local e2e run (backend + Hermes Desktop) without root, xvfb or /opt/hermes.
#
# Usage: scripts/e2e_local.sh setup                 install everything (idempotent)
#        scripts/e2e_local.sh backend|desktop|all [playwright args...]
#
# setup installs into the user's home only:
#   - Node $NODE_VERSION     -> ~/.local/opt/node (+ node/npm/npx in ~/.local/bin)
#   - uv                     -> ~/.local/bin
#   - hermes-agent $HERMES_REF -> $HERMES_ROOT (git clone), venv via `uv sync`,
#     plus this plugin's runtime deps (pyproject.toml) in that venv
#   - Hermes Desktop build   -> $HERMES_ROOT/apps/desktop (npm ci + npm run build)
#   - e2e/node_modules       -> npm ci
#
# The desktop project runs Electron with `--headless=new`, so no display server
# is needed and no window opens. Set E2E_HEADED=1 to see it. (Electron 44 in
# v0.22.5 crashes with SIGSEGV under `--ozone-platform=headless`, which worked
# for Electron 40 in v0.22.2.)
#
# Env: HERMES_ROOT (default ~/dev/hermes-agent), HERMES_REF (default v0.22.5),
#      NODE_VERSION (default v24.22.1), E2E_ARTIFACTS_DIR (default
#      /tmp/spawn-session-e2e-artifacts), E2E_KEEP=1 keeps the sandboxes.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_ROOT="${HERMES_ROOT:-$HOME/dev/hermes-agent}"
HERMES_REF="${HERMES_REF:-v0.22.5}"
NODE_VERSION="${NODE_VERSION:-v24.22.1}"
export PATH="$HOME/.local/bin:$PATH"

setup() {
  mkdir -p "$HOME/.local/opt" "$HOME/.local/bin"
  if ! command -v node >/dev/null; then
    echo "== node $NODE_VERSION"
    curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-linux-x64.tar.xz" | tar xJ -C "$HOME/.local/opt"
    ln -sfn "node-$NODE_VERSION-linux-x64" "$HOME/.local/opt/node"
    for b in node npm npx; do ln -sf "$HOME/.local/opt/node/bin/$b" "$HOME/.local/bin/$b"; done
  fi
  if ! command -v uv >/dev/null; then
    echo "== uv"
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
  fi
  if [ ! -d "$HERMES_ROOT/.git" ]; then
    echo "== hermes-agent $HERMES_REF"
    git clone -q --depth 1 --branch "$HERMES_REF" https://github.com/NousResearch/hermes-agent "$HERMES_ROOT"
  elif [ "$(git -C "$HERMES_ROOT" rev-parse HEAD)" != "$(git -C "$HERMES_ROOT" rev-parse -q --verify "$HERMES_REF^{commit}" 2>/dev/null)" ]; then
    echo "== hermes-agent -> $HERMES_REF"
    git -C "$HERMES_ROOT" fetch -q --depth 1 origin tag "$HERMES_REF"
    git -C "$HERMES_ROOT" -c advice.detachedHead=false checkout -q "$HERMES_REF"
  fi
  echo "== hermes venv"
  # The lockfile only resolves for Python >= 3.14.
  (cd "$HERMES_ROOT" && uv sync --python 3.14 --frozen --extra web)
  # The plugin's own runtime deps (a live install gets them via `plugins install --yes-deps`).
  uv pip install --python "$HERMES_ROOT/.venv/bin/python" -q \
    $(python3 -c 'import tomllib,sys; print(" ".join(tomllib.load(open(sys.argv[1],"rb"))["project"]["dependencies"]))' "$REPO/pyproject.toml")
  echo "== Hermes Desktop build"
  (cd "$HERMES_ROOT" && npm ci --no-audit --no-fund && cd apps/desktop && npm run build)
  echo "== e2e deps"
  (cd "$REPO/e2e" && npm ci --no-audit --no-fund)
  "$HERMES_ROOT/.venv/bin/hermes" --version | head -1
}

run() {
  local project="$1"; shift
  [ -x "$HERMES_ROOT/.venv/bin/hermes" ] || { echo "missing $HERMES_ROOT; run: $0 setup" >&2; exit 2; }
  export HERMES_BIN="$HERMES_ROOT/.venv/bin/hermes"
  export HERMES_PYTHON="$HERMES_ROOT/.venv/bin/python3"
  export HERMES_DESKTOP_ROOT="$HERMES_ROOT/apps/desktop"
  export E2E_ARTIFACTS_DIR="${E2E_ARTIFACTS_DIR:-/tmp/spawn-session-e2e-artifacts}"
  if [ -z "${E2E_HEADED:-}" ]; then export E2E_ELECTRON_ARGS="${E2E_ELECTRON_ARGS:---headless=new}"; fi
  cd "$REPO/e2e"
  case "$project" in
    backend) npx playwright test --project=backend "$@" ;;
    desktop) npx playwright test --project=desktop --no-deps "$@" ;;
    all) npx playwright test "$@" ;;
  esac
  echo "artifacts: $E2E_ARTIFACTS_DIR (screenshots/, html/, output/)"
}

case "${1:-}" in
  setup) setup ;;
  backend|desktop|all) cmd="$1"; shift; run "$cmd" "$@" ;;
  *) sed -n '2,6p' "$0" >&2; exit 2 ;;
esac
