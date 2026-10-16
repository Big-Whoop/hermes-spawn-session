# AGENTS.md — working on hermes-spawn-session

These instructions are for coding agents. They are short; read SPEC.md for
the details.

## Repo layout

- `plugin.yaml`, `__init__.py`: Hermes plugin manifest and `register(ctx)`. It registers the tools `spawn_session` and `report_back`, the slash commands, and the `pre_tool_call` guard.
- `spawn_session/`: agent half, plain Python.
  - `tools.py`: tool handlers and spawn rules.
  - `commands.py`: slash commands.
  - `handover.py`: handover file format.
  - `state.py`: state index.
  - `lifecycle.py`: reports, abort, detach.
  - `delivery.py`: inject_message and delivery confirmation.
  - `gateway.py`: session RPCs.
  - Also `worktree.py`, `project.py`, `parent.py`, `seed.py`, `config.py`.
  - `desktop.py`: the logic behind the REST routes.
- `dashboard/plugin_api.py`: FastAPI router. Hermes mounts it under `/api/plugins/spawn-session/` and imports it by path.
- `desktop/plugin.js`: ESM desktop half. Talks to the backend via `ctx.rest`.
- `tests/`: pytest. Tests use seams (module-level names they monkeypatch), so no live Hermes is needed.
- `scripts/`: `smoke_desktop_plugin.mjs` (Node smoke test). `live_test.py` and `live_report_test.py` are live checks against a running Hermes.

## Sources of truth

1. `.hermes/decisions.md` (D1–D13). Change it only after the user confirms.
2. `SPEC.md`. Update it when behaviour changes.
3. `.hermes/research/`. German and read-only.

If the code and SPEC disagree, report it. Don't silently pick one.

## Workflow

- Kanban board `hermes-spawn-session`. `default` implements, `reviewer` reviews.
- Card → worktree → branch → PR → reviewer merge. The default branch is `main`.
- Never push to `main`.
- Hand off with `kanban request-review <id> --reviewer reviewer`.

## Testing

- `pytest`.
- `tests/test_dependencies.py`: declare every non-host third-party import in `pyproject.toml`. Host-provided modules are not declared: hermes_cli, hermes_constants, tools, gateway, tui_gateway, fastapi.
- `node scripts/smoke_desktop_plugin.mjs`.
- Manual checks in a live Desktop go on the e2e card t_787f6427.

## Rules

- Docs before code for Hermes internals. Read the official docs first. Treat the Hermes source in /opt/hermes as a read-only fallback, and never modify it.
- English for all code and docs.
- `desktop/plugin.js`:
  - Import only from `@hermes/plugin-sdk`, `react` and `react/jsx-runtime`.
  - Call `jsx()`/`jsxs()` directly; no JSX syntax.
  - Use theme variables only; no hardcoded colours.
- Tool handlers never raise and always return JSON.
- The handover file is authoritative. `state.json` can be rebuilt.
- Live install: `/opt/data/plugins/spawn-session` is a symlink to this repo's main checkout. Merging to `main` changes the live plugin after a restart.
