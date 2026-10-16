# Lane 1 — Official Hermes tooling for testing the backend half of a plugin (Python plugin + dashboard plugin_api)

Card: t_764f235f (parent t_cd95f6bd, collector t_6078e578) · Date: 2026-10-17 · Hermes under test: v0.22.2 (2026.9.24, upstream d923a5eb), docker install at /opt/hermes
Tiers: Verified (authoritative source for this exact target, or measured live here) / Plausible / Speculative.
[live] = confirmed by a command run in the agent sandbox on 2026-10-17 against v0.22.2, using throwaway HERMES_HOME dirs under /opt/data/cache/scratch/l1 (live /opt/data untouched; `--install-deps` deliberately NOT run, see F4).

## TL;DR

- Three official, headless, CI-capable layers exist: `hermes plugins validate <dir> [--json]` (catalog CI gate), `hermes plugins doctor <dir> --ci` (real loader/registration path in a temp HERMES_HOME), and an isolated `HERMES_HOME=<tmp> hermes serve --port 0` (real backend incl. dashboard plugin_api mounting). None needs a live instance.
- Neither validate nor doctor imports `dashboard/plugin_api.py` [live]: a broken/undeclared import there passes both. Only a real `hermes serve`/`hermes dashboard` start catches it (logged as `Failed to load plugin <name> API routes` in errors.log) [live] — and the HTTP plugin list still returns 200, so the check must grep the log or probe a plugin route.
- Undeclared dependency detection: validate/doctor import `__init__.py` in the *current* venv, so a dependency already present in that venv (e.g. httpx in the Hermes venv) is NOT flagged [live]. Only a clean environment that contains Hermes core + exactly the declared deps catches it. `--install-deps` installs "into this venv" — never run it on the live container.
- spawn-session at HEAD fails `validate` today for 3 reasons (provides_tools/provides_hooks missing; security scan "dangerous" from .hermes/research/*.md files shipped in the tree) [live] — relevant for any CI gate design.

## Findings

### F1. `hermes plugins validate` is the catalog CI gate and is headless/JSON-capable
- Claim: `validate` is the exact check catalog CI runs, offers `--json`, and covers manifest, requires_hermes, loadability, declared-vs-registered capabilities, config_schema, requires_env, Python deps vs core constraints, security scan, desktop-surface and no-core-override rules.
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission (official docs); `hermes plugins validate --help` [live]
- Quote: "Run the same check catalog CI runs ... `hermes plugins validate /path/to/your-plugin --install-deps` It checks the manifest and `requires_hermes`, that the plugin loads, that the `capabilities` you declare match what it registers, `config_schema` and `requires_env`, Python dependencies against Hermes's core constraints, the install security scan, and the `desktop surface` and `no core override` rules." / help: "validate  Validate a plugin directory for catalog admission (CI gate)" ... "--json  Print machine-readable JSON (for CI)"
- Tier: Verified

### F2. validate exits non-zero on failure and runs without a live instance [live]
- Claim: With a throwaway HERMES_HOME, `validate . --json` ran fully offline-from-live and returned exit 1 with `"ok": false` for spawn-session HEAD.
- Source: live run, `HERMES_HOME=/opt/data/cache/scratch/l1/home hermes plugins validate . --json` → `VALIDATE_EXIT=1`
- Quote (JSON): `"name": "capability probe", "ok": true, "detail": "register() ran in isolation"`; `"name": "declared tools", "ok": false, "detail": "undeclared tools registered (not in provides_tools): report_back, spawn_session"`; `"name": "declared hooks", "ok": false, ... pre_tool_call`; `"name": "security scan", "ok": false, "detail": "dangerous: agent_config_mod_shell (lane1-hermes-docs.md:101), context_exfil (lane2-hermes-native-session-spawning.md:266), sys_prompt_override (lane1-hermes-docs.md:316)"`
- Tier: Verified
- Note: the scan hits come from `.hermes/research/2026-10-16-model-routing/*.md` committed in the plugin tree (also in `git archive HEAD`). A catalog/CI gate will fail until those are excluded from the plugin payload or the scan finding is resolved. Warnings also list private core imports: `spawn_session/commands.py:35 gateway.session_context.get_session_env; spawn_session/gateway.py:47 tui_gateway.server.handle_request`.

### F3. validate also reports plugin-host isolation readiness
- Claim: validate/show report whether the plugin can run under `plugins.isolation: host`; spawn-session is host-ready and its dashboard API would be served through the host (buffered).
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins (official) + live JSON
- Quote: "`hermes plugins validate <dir>` and `hermes plugins show <name>` report whether a plugin runs in the host and, if not, why." / live: `"isolation": {"verdict": "host", "host_ready": true, ... "notes": ["dashboard backend API is served through the plugin host (buffered responses)"]}`
- Tier: Verified

### F4. `--install-deps` installs into the CURRENT venv — not a clean-env check, and unsafe on the live container
- Claim: `--install-deps` mutates the venv that runs `hermes`; run it only in a disposable environment (CI image / staging), never in the live hermes-suite container.
- Source: `hermes plugins validate --help` [live]
- Quote: "--install-deps  Install the plugin's declared Python dependencies (pyproject/python_dependencies) into this venv before the capability probe, exactly as `plugins install` would — the catalog CI gate"
- Tier: Verified (help text); not executed here on purpose.
- Corroboration (catalog entry page): https://hermes-agent.nousresearch.com/docs/plugins/doctorpack — "run hermes plugins validate <plugin-directory> --install-deps in a complete, isolated Hermes environment and inspect dependency preparation errors as well as the validation report." (search snippet, third-party plugin page on official site) — Plausible as guidance.

### F5. validate/doctor do NOT catch an undeclared dependency that already exists in the Hermes venv [live]
- Claim: The capability probe imports the plugin in the running Hermes interpreter, so it only catches modules missing from that venv; a module present there (but undeclared) passes.
- Source: live experiment on copies of HEAD: injected `import humanize_nonexistent_xyz` → `capability probe False import failed: No module named 'humanize_nonexistent_xyz'`; injected `import httpx` (present in Hermes venv, not declared) → `capability probe True register() ran in isolation`, `python dependencies True 1 requirements from pyproject`.
- Tier: Verified (for v0.22.2)
- Implication: The live failure that motivated this research (passed in dev venv, failed live) is precisely the class validate cannot see when run in a richer venv. A reliable gate = run validate/doctor in an environment whose site-packages == Hermes core lock + declared deps only (e.g. the official hermes image of the exact live tag, fresh container, `--install-deps`), not a dev venv.

### F6. `hermes plugins doctor <path> --ci` exercises the real loader in a temp HERMES_HOME
- Claim: doctor runs the real discovery/manifest/import/register(ctx)/registries with a temporary HERMES_HOME, blocks sockets during registration, and `--ci` exits non-zero on errors.
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins#validate-with-plugin-doctor (official)
- Quote: "`hermes plugins doctor [path-or-id]` runs the same directory discovery, manifest parser, namespaced import, `register(ctx)`, hook registry, and tool registry used by Hermes itself. ... Doctor uses a temporary `HERMES_HOME`, restores plugin registration state after the check, and blocks direct Python socket connections to catch accidental network access while registration runs. This is not a sandbox"
- Tier: Verified
- Live: HEAD → WARN for undeclared tools/hooks, `OK: runtime discovery, manifest parsing, import, and registration passed`, exit 0 (doctor treats tool/hook drift as warning, validate as failure). Broken `__init__.py` → `ERROR: Plugin registration failed ...`, `DOCTOR_BAD_EXIT=1` [live].

### F7. Neither validate nor doctor loads `dashboard/plugin_api.py` [live]
- Claim: A syntax/import error in dashboard/plugin_api.py passes validate (all non-preexisting checks ok, `loadable: entry: __init__.py, desktop/plugin.js` — dashboard not listed) and doctor (exit 0).
- Source: live experiment `bad_dash` (inserted an import before `from __future__` in dashboard/plugin_api.py).
- Tier: Verified (v0.22.2). Searched docs for a validate/doctor dashboard check: none documented (see "searched, found nothing").

### F8. Dashboard plugin_api routes mount once at backend startup; errors go to errors.log
- Claim: plugin_api.py must export a module-level `router = APIRouter()`, is mounted under `/api/plugins/<name>/` only at startup (rescan does not remount API routes), and import errors are logged, not fatal.
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/extending-the-dashboard (official)
- Quote: "Restart `hermes dashboard` — plugin API routes are mounted once at startup, **not** on rescan." / "Check that `plugin_api.py` exports a module-level `router = APIRouter()`. Other export names are not picked up." / "Tail `~/.hermes/logs/errors.log` for `Failed to load plugin <name> API routes` — import errors are logged there." / "`/api/dashboard/plugins/rescan` | GET | Force re-scan the plugin directories without restarting."
- Tier: Verified

### F9. An isolated headless backend (`HERMES_HOME=<tmp> hermes serve --port 0`) is the cheapest real dashboard-API test [live]
- Claim: `hermes serve` is the headless backend (same server as dashboard); `--port 0` binds an ephemeral port and announces it, making parallel isolated instances scriptable next to the live one.
- Source: https://hermes-agent.nousresearch.com/docs/reference/cli-commands#hermes-serve (official) + live run
- Quote: "It is the same server `hermes dashboard` runs, but **headless** ... Pass `--port 0` to bind a free ephemeral port (the successful boot announces the chosen port via `HERMES_BACKEND_READY port=<port>`)." / port conflict → "prints a machine-readable sentinel line `BACKEND_PORT_IN_USE port=<port>` ... exits with code **75**". / "`--stop` ... Stop the running `hermes dashboard` / `hermes serve` backend **of this Hermes home**"
- Live: temp home with plugin copied to `plugins/spawn-session` + `plugins.enabled: [spawn-session]` → `HERMES_BACKEND_READY port=39117`, agent.log `Mounted plugin API routes: /api/plugins/spawn-session/`. With broken plugin_api.py → errors.log `WARNING hermes_cli.web_server: Failed to load plugin spawn-session API routes: from __future__ imports must occur ... (plugin_api.py, line 27)`; `GET /api/dashboard/plugins` still HTTP 200 in both cases.
- Tier: Verified
- Implication: CI assertion must be "errors.log has no `Failed to load plugin` line AND a known plugin route answers non-404", not a status-code check on the plugin list. Note: `--skip-build` was used; non-loopback bind always requires auth.

### F10. Isolation is by HERMES_HOME; profiles are HERMES_HOME subdirs; PM documents a dev data home
- Claim: HERMES_HOME is the boundary for config, .env, plugins, logs, gateway state; profiles are just HERMES_HOME=~/.hermes/profiles/<name>; PM docs recommend a separate HERMES_HOME (+HERMES_RUNTIME_DIR) for isolated development.
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/profiles ; https://hermes-agent.nousresearch.com/docs/reference/package-management (official)
- Quote: "Profiles use the `HERMES_HOME` environment variable. ... `HERMES_HOME` is the profile boundary. It controls Hermes config, `.env`, memory, sessions, skills, logs, cron jobs, gateway state, and other Hermes data." / "For isolated development, select a separate data home before the first PM command. ... `export HERMES_HOME=\"$HOME/hermes-dev-data\"` `export HERMES_RUNTIME_DIR=\"$HERMES_HOME/tools\"`"
- Tier: Verified

### F11. Profiles share ONE dependency environment — a staging profile inside the live container is NOT dependency-isolated
- Claim: PM resolves the enabled-plugin union across every profile sharing the dependency home; a broken profile config fails dependency prep for all homes. So enabling a test plugin in a "staging" profile of the live container changes the live venv generation.
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins#dependency-preparation-and-preservation ; developer-guide/plugins#python-dependencies (official)
- Quote: "The enabled set is the union over the default home **and every profile** under `profiles/` ... a `config.yaml` that is not valid YAML ... fails dependency preparation for **all** homes" / "PM resolves core, selected extras, and the enabled plugin union across every profile sharing the dependency home, including custom `HERMES_HOME` roots."
- Tier: Verified (docs). Whether a custom HERMES_HOME outside /opt/data shares the container's PM install key: Plausible ("including custom HERMES_HOME roots" suggests yes, per installation). Live-safe consequence: real dependency isolation needs a separate container/image (staging Deployment), not a profile.

### F12. Second gateway per profile; in the Docker image gateways are s6-supervised slots
- Claim: Each profile runs its own gateway; inside the official image `hermes profile create` registers an s6 slot and `hermes -p <name> gateway start/stop/restart` dispatches to s6-svc. Same bot token in two profiles is blocked.
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/profiles (official)
- Quote: "`hermes profile create <name>` automatically registers an s6 service slot at `/run/service/gateway-<name>/`. `hermes -p <name> gateway start/stop/restart` dispatches to `s6-svc`" / "If two profiles accidentally use the same bot token, the second gateway will be blocked with a clear error naming the conflicting profile."
- Tier: Verified (docs); not exercised here (would touch the live container's supervision tree — Peter's step).

### F13. Dependency consent + enable/install flags for headless installs
- Claim: Install requests Python dependency consent; new plugins land disabled; `--yes-deps` is the documented headless (CI/SSH/container entrypoint) path; `--no-deps` leaves it disabled; `--enable` does not bypass consent.
- Source: developer-guide/plugins#python-dependencies; user-guide/features/plugins; `hermes plugins install --help` [live]
- Quote: "**`--yes-deps`** answers the dependency question up front, so a headless install (CI, SSH automation, a container entrypoint) prepares the declared dependencies instead of being refused. It is mutually exclusive with `--no-deps`." / "`plugins install --enable` does not bypass that step. A declined or non-interactive dependency install can leave the plugin installed but disabled."
- Tier: Verified
- Gap: `install` takes a catalog name / Git URL / owner/repo — no documented local-path install. For a local checkout in staging: copy into `$HERMES_HOME/plugins/<name>/` (+ `hermes plugins adopt` for self-cloned dirs) and enable via `plugins.enabled` / `hermes plugins enable` (enable triggers PM admission). Install from a GitHub branch pin `--ref <sha>` is the closest official route. Tier: Plausible.

### F14. Enable/disable + restart semantics
- Claim: PM prepares a new environment generation atomically on enable; a running process keeps old imports and may need a restart; dashboard API routes need a backend restart; disabled list lives in config.yaml `plugins.disabled`.
- Source: package-management; user-guide/features/plugins; cli-commands (official)
- Quote: "If preparation succeeds, a running Hermes process can still require a restart to activate the new environment." / "Restart Hermes when a new selected environment is not yet active in the running process." / "General plugin disabled list is stored in `config.yaml` under `plugins.disabled`." / "Atomic publication — ... Resolution, download, or build failure preserves the previous environment and plugin selection"
- Tier: Verified

### F15. Discovery debugging without the gateway: HERMES_PLUGINS_DEBUG + logs
- Claim: `HERMES_PLUGINS_DEBUG=1 hermes plugins list` gives per-plugin skip/load reasons and register() tracebacks; same at WARNING in agent.log, readable via `hermes logs`.
- Source: developer-guide/plugins#debugging-plugin-discovery (official)
- Quote: "set `HERMES_PLUGINS_DEBUG=1` to get verbose discovery logs on stderr ... on `register()` failure: a full traceback ... The same logs are always written to `~/.hermes/logs/agent.log` at WARNING level ... `hermes logs --level WARNING | grep -i plugin`"
- Tier: Verified

### F16. `hermes plugins show` / `capabilities` read installed metadata
- Claim: `show <name>` shows details for an installed plugin (incl. emits/listens, requires_auth, isolation verdict); it takes a name, not a path — so it is a post-install check, not a pre-install one.
- Source: `hermes plugins show --help` [live]; developer-guide/plugins ("`requires_auth` appears in `hermes plugins show <name>`"); "Hermes reads these from installed metadata without importing your code, so `hermes plugins capabilities` and the consent flow stay accurate"
- Tier: Verified

### F17. Upstream uses the same pattern: frozen plugin fixtures from an isolated HERMES_HOME
- Claim: Hermes' own compatibility tests load external-plugin fixtures from an isolated HERMES_HOME through PluginManager, asserting real registrations — the officially endorsed shape for plugin integration tests.
- Source: developer-guide/plugins (official, plugin contract section)
- Quote: "Hermes enforces this contract with frozen external-plugin fixtures discovered from an isolated `HERMES_HOME`. Those tests load and invoke the plugin through `PluginManager`; they assert real registration and callback outcomes rather than internal symbol lists"
- Tier: Verified (that upstream does it); Plausible that a plugin repo can replicate it in pytest against the pinned Hermes image.

### F18. Clean test interpreter recipes from PM docs
- Claim: PM can build an independent disposable env (`python -m pm.build_env --source . --out .venv --group dev --group test`) or run single commands via `scripts/run-in-hermes-env`; editor/test HERMES_HOME should stay separate from production.
- Source: https://hermes-agent.nousresearch.com/docs/reference/package-management#test-and-editor-environments (official)
- Quote: "a caller can explicitly supply `HERMES_PYTHON` with pytest, or build an independent disposable environment: `python -m pm.build_env --source . --out .venv --group dev --group test`" / "Keep its `HERMES_HOME` separate from production."
- Tier: Verified (docs, for source checkouts). Plausible for the docker install (/opt/hermes is docker-managed and reports "install out of sync (venv: out of sync with uv.lock)" [live] — so the sandbox venv itself is not a faithful copy of the lock; another reason to test in a fresh image).

### F19. Lazy installs and manual pip are not durable
- Claim: Manually pip-installed deps can vanish on the next environment generation; `security.allow_lazy_installs: false` blocks on-demand acquisition — a dev venv with hand-installed packages is not representative.
- Source: developer-guide/plugins#lazy-install-optional-python-dependencies (official)
- Quote: "Dependencies installed manually with pip are not durable PM declarations. A later environment replacement need not retain them." / "discovery never installs."
- Tier: Verified

### F20. `hermes doctor` / `hermes pm doctor|status` give CI-grade exit codes and receipts
- Claim: `hermes doctor` exits 1 on unresolved problems; `hermes pm status` prints the latest sync receipt as JSON (dependency conflicts land there).
- Source: cli-commands; package-management (official)
- Quote: "Exit status: `0` when the report lists no unresolved problems, `1` when at least one remains ... so a health gate or CI step can trust `hermes doctor` as a check." / "**Dependency conflict:** read `hermes pm status`. Correct the plugin requirements before retrying admission."
- Tier: Verified

## Headless-in-CI matrix (no live instance needed)

| Check | Catches | Headless/CI | Needs live? | Caveat |
|---|---|---|---|---|
| `plugins validate <dir> --json` | manifest, register() import in current venv, declared tools/hooks, scan, desktop surface, core override | yes, exit 1 on fail [live] | no | does not load dashboard/plugin_api.py (F7); venv-dependent (F5) |
| `validate --install-deps` | dependency resolution vs core constraints | yes | no | mutates current venv → disposable env only (F4) |
| `plugins doctor <dir> --ci` | real loader/registry path, temp HERMES_HOME, socket block | yes, exit 1 on error [live] | no | tool/hook drift only WARN; no dashboard API (F7) |
| `HERMES_HOME=tmp hermes serve --port 0` + log grep + route probe | plugin_api import/mount, real enable path | yes [live] | no | needs log/route assertion, list API stays 200 (F9) |
| `plugins install --yes-deps` in fresh hermes image | real consent+PM admission, undeclared deps | yes | no (staging/CI container) | no local-path install documented (F13) |
| profile/second gateway in live container | gateway restart semantics | — | yes | shares dependency union with live (F11) — avoid |

Recommended gate order (Plausible, derived): pytest → doctor --ci → validate --json (fresh container of live image tag) → validate --install-deps (same disposable container) → isolated `hermes serve --port 0` with plugin enabled, assert no `Failed to load plugin` + route probe → only then staging/live.

## Searched, found nothing

- Official docs: a validate/doctor check that imports `dashboard/plugin_api.py` — not documented in developer-guide/plugins, extending-the-dashboard, catalog-submission, cli-commands (searched for "plugin_api", "dashboard" in all four). Confirmed absent in behavior [live].
- Official docs: a `hermes plugins install <local-path>` form — cli-commands lists only catalog name / Git URL / owner/repo; `install --help` same [live].
- Official docs: a "clean environment"/"--isolated-venv" flag for validate — none; only `--install-deps` "into this venv".
- Official docs: an `--json` or `--ci` option for `plugins show` — none (`show --help` [live]).
- Web search `hermes-agent release notes "plugins doctor" OR "plugins validate" --install-deps` — returned only docs pages (developer-guide/plugins, catalog-submission, plugin-catalog, doctorpack catalog page) and a third-party note (mnemosyne docs claiming plugins doctor isn't documented — outdated vs current docs); no changelog entry found for when doctor/validate landed.
- Local skill hermes-agent (SKILL.md): no content on plugins validate/doctor/--install-deps (only HERMES_HOME layout + profile management).
- Plugin catalog VALIDATION.md examples: not located via official docs; catalog-submission points to plugin-catalog/README.md in hermes-agent repo instead (not read — GitHub source tree, beyond docs gate; docs page states it mirrors the README word for word).

## Sources read (whole, via saved full text)
- https://hermes-agent.nousresearch.com/docs/developer-guide/plugins (141 KB, keyword-grepped full text)
- https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins
- https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission (read whole)
- https://hermes-agent.nousresearch.com/docs/reference/cli-commands (plugins, serve, dashboard, doctor sections)
- https://hermes-agent.nousresearch.com/docs/user-guide/profiles
- https://hermes-agent.nousresearch.com/docs/user-guide/features/extending-the-dashboard
- https://hermes-agent.nousresearch.com/docs/reference/package-management
- Live CLI help + experiments on Hermes v0.22.2 (this sandbox), 2026-10-17
