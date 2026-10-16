#!/usr/bin/env bash
# Import every plugin module in a brand-new venv that contains ONLY the
# dependencies declared in pyproject.toml (no Hermes, no dev extras).
# Hermes core modules are absent there on purpose: the plugin imports them
# lazily, so module import must still succeed. Needs network access to PyPI.
# Usage: scripts/check_clean_venv.sh [python]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${1:-python3}"
VENV="$(mktemp -d "${TMPDIR:-/tmp}/spawn-session-cleanvenv.XXXXXX")"
trap 'rm -rf "$VENV"' EXIT
"$PY" -m venv "$VENV"
DEPS="$("$VENV/bin/python" -c 'import tomllib,sys; print("\n".join(tomllib.load(open(sys.argv[1],"rb"))["project"]["dependencies"]))' "$ROOT/pyproject.toml")"
echo "declared deps:"; echo "$DEPS"
mapfile -t DEP_ARR <<<"$DEPS"
"$VENV/bin/pip" install -q "${DEP_ARR[@]}"
cd "$VENV"
"$VENV/bin/python" -I - "$ROOT" <<'EOF'
import importlib, importlib.util, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root))
for p in sorted((root / "spawn_session").glob("*.py")):
    importlib.import_module("spawn_session" if p.stem == "__init__" else f"spawn_session.{p.stem}")
spec = importlib.util.spec_from_file_location("spawn_session_plugin", root / "__init__.py", submodule_search_locations=[str(root)])
mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
spec = importlib.util.spec_from_file_location("plugin_api", root / "dashboard" / "plugin_api.py")
api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
print("clean-venv import audit: OK")
EOF
