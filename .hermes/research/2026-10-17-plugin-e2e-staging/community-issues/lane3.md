# Lane 3 — Upstream issues/PRs + community reports (plugin testing, deps, parallel instances, desktop e2e)

Date: 2026-10-17. Method: `gh` CLI (search issues/PRs, view bodies, contents API on workflow files) + web_search/web_extract on official docs.
Tiers: Verified (V) = read on the authoritative source for this exact claim; Plausible (P) = sound, not on-target confirmed; Speculative (S).
Docs-first: official docs (developer-guide/plugins, catalog-submission) read first; GitHub issues/PRs = primary for this lane; workflow YAML read as CI config (not used as documentation of Hermes behavior). No Hermes Python source read.

## TL;DR
- The "passes in dev venv, fails live" gap is a well-known upstream bug CLASS, not unique to us: plugin deps not present in the staged runtime venv, ImportError swallowed at DEBUG, and `plugins doctor` probing the wrong interpreter (#134469, #136519, #138220, #140174; fix PR #136043 open).
- Official answer for headless installs: `hermes plugins install <x> --enable --yes-deps` (fixed on main, #122134). Desktop GUI install with Python deps is STILL broken (consent requires a TTY) — #124784, #135653 open. So a staging toolset must install via CLI, not via the Desktop GUI.
- Official per-plugin CI pattern (hermes-official-plugins tests.yml): temp `HERMES_HOME`, `hermes plugins validate`, pytest against a hermes-agent checkout, Linux/macOS/Windows, nightly. Catalog CI runs `hermes plugins validate --install-deps`.
- Upstream Desktop e2e = Playwright + Electron under `xvfb-run` on Linux, with mock backend / packaged app; the broad suite is `if: false` (flaky), a deterministic "core" suite is required. No public desktop-plugin e2e harness for third parties exists; community authors test desktop halves with `node --check` + Node `.mjs` unit tests.
- No upstream issue/discussion describes a "staging Hermes instance scaled to 0"; nearest: temp/isolated `HERMES_HOME`, multi-profile gateways (which themselves have dep-collision bugs #125252/#138702).

## Findings

### A. Plugin dependency failures at load time (our motivating gap)

1. `hermes update` rebuilds the staged runtime venv without plugin deps; failure is silent and `plugins doctor` reports OK because it probes a different venv. — V
   Source: https://github.com/NousResearch/hermes-agent/issues/134469 (GitHub issue, open)
   Quote: "`hermes plugins doctor` reports **OK** (\"import, and registration passed\") because its probe runs against the *old* 3.11 venv ... not the staged runtime venv." / "The staged venv has **no pip**"
2. Plugin requirements.txt is not consulted; the loader catches the ImportError at DEBUG level, so the cause is never surfaced. — V
   Source: https://github.com/NousResearch/hermes-agent/issues/136519 (issue, open)
   Quote: "The plugin's requirements.txt was not consulted by the update pipeline. The loader catches the resulting ImportError at DEBUG level, so the actual cause is never surfaced"
3. Only deps DECLARED in `plugin.yaml` (`python_dependencies`/`pip_dependencies`) or `[project].dependencies` become workspace members of the runtime env (maintainer-level comment on #134469). — V (comment), P (as current-version behavior on v0.22.2)
   Source: https://github.com/NousResearch/hermes-agent/issues/134469 (issue comment)
   Quote: "builds the runtime environment as a workspace whose members are the enabled plugins that **declare** their Python dependencies: `python_dependencies` / `pip_dependencies` in `plugin.yaml`, or `[project].dependencies`"
4. Docker image case: venv has no pip/uv, an undeclared dep (PyYAML) breaks the plugin; fix was to declare `pyyaml` in `[project].dependencies`. Directly analogous to our container. — V
   Source: https://github.com/NousResearch/hermes-agent/issues/138220 (issue, open)
   Quote: "The venv has no `pip` and no `uv` binary available inside the container, so there's no way to self-heal" / "nujovich/hermes-telemetry#118 added `pyyaml>=6.0` to `[project].dependencies`"
5. Fix in flight: doctor re-checks declared deps with the staged runtime venv's own interpreter. — V (PR open, not merged)
   Source: https://github.com/NousResearch/hermes-agent/pull/136043 (PR, open)
   Quote: "re-checks the manifest's declared `python_dependencies` with that venv's own interpreter via a read-only `importlib.metadata` subprocess probe"
   Note: it checks DECLARED deps only — an undeclared import (our case) would still pass doctor. Only an actual load in the runtime venv catches it. — P (inference)
6. Managed config (HERMES_MANAGED_DIR) plugins are omitted from dependency selection → ModuleNotFoundError at runtime (repro on Docker v0.22.2). — V
   Source: https://github.com/NousResearch/hermes-agent/issues/140174 (issue, open)
   Quote: "Plugins enabled ... only in the managed config are absent from the dependency selection."
7. Catalog CI itself found entries whose pinned SHA fails because `register()` imports an undeclared dep (aiohttp) — the same failure mode surfacing in CI via `pinned-source-validate`. — V
   Source: https://github.com/NousResearch/hermes-agent/issues/121403 (issue, open)
   Quote: "`plugin.yaml` declares zero Python dependencies, but the plugin's `register()` imports `gateway.platforms.api_server`, which needs `aiohttp` ... Fails with: ModuleNotFoundError"
8. A failed plugin load at boot (e.g. load timeout 10s) leaves the platform dead for the gateway lifetime, only one WARNING line. Relevant for e2e assertions: check logs/plugin list, not just "gateway up". — V
   Source: https://github.com/NousResearch/hermes-agent/issues/126356 (issue, closed)
   Quote: "leaves that platform **permanently unavailable for the entire gateway lifetime**, with no retry ... only a single WARNING line in the log."
9. Batch plugin-load failures "dictionary changed size during iteration" silently drop registrations (open). Flake source for any e2e. — V (exists), P (affects v0.22.2)
   Source: https://github.com/NousResearch/hermes-agent/issues/131817, https://github.com/NousResearch/hermes-agent/issues/125746

### B. Headless install + dependency consent (part (a) of the staging toolset)

10. Non-TTY `hermes plugins install --enable` used to refuse deps; fixed on main with `--yes-deps`. — V
    Source: https://github.com/NousResearch/hermes-agent/issues/122134 (issue, closed)
    Quote: "Fixed on main in 169e77039a38: `hermes plugins install <name> --enable --yes-deps` now answers both dependency-consent gates for headless installs"
11. Official docs confirm `--yes-deps` for CI/SSH/container entrypoints. — V
    Source: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins (official docs)
    Quote: "**`--yes-deps`** answers the dependency question up front, so a headless install (CI, SSH automation, a container entrypoint) prepares the declared dependencies instead of being refused."
12. Desktop "Install from Git" can never install a plugin with Python deps (consent gate needs a TTY the serve backend lacks). — V (open bug)
    Source: https://github.com/NousResearch/hermes-agent/issues/124784 (issue, open)
    Quote: "**no plugin with Python dependencies can be installed or reinstalled from the Desktop.** The CLI works"
13. Desktop plugin UPDATE with new deps: consent accepted, then non-interactive refusal. — V (open)
    Source: https://github.com/NousResearch/hermes-agent/issues/135653
    Quote: "So from Desktop, accepting the consent can never succeed for such a pin."
    Implication: GUI-driven install of the hermes-spawn-session plugin is NOT a valid e2e step today; do the install via CLI `--yes-deps`, then GUI-test the loaded plugin. — P
14. Failed installs leak `.install-*` staging dirs that nothing reaps; a staging toolset doing repeated install/uninstall should clean them. — V
    Source: https://github.com/NousResearch/hermes-agent/issues/136121
15. Desktop install from local repo on Windows fails (file:// URL) — relevant if the user's PC is Windows. — V
    Source: https://github.com/NousResearch/hermes-agent/issues/131406 (open; fix PR #131407)

### C. Official test tooling / harness

16. Official docs: `hermes plugins validate <path> --install-deps` = the catalog-CI check; `hermes plugins doctor [path-or-id]` runs real discovery/register with a temporary HERMES_HOME. — V
    Source: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins
    Quote: "`hermes plugins doctor [path-or-id]` runs the same discovery, manifest parser, `register(ctx)` and registries Hermes uses, with a temporary `HERMES_HOME`."
17. Validate covers manifest, load, capabilities vs registration, deps vs core constraints, security scan, desktop-surface check. — V
    Source: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission
    Quote: "It checks the manifest and `requires_hermes`, that the plugin loads, that the `capabilities` you declare match what it registers, ... Python dependencies against Hermes's core constraints, the install security scan, and the `desktop surface`"
18. Hermes core tests external plugins via frozen fixtures from an isolated HERMES_HOME through PluginManager. — V
    Source: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins
    Quote: "Hermes enforces this contract with frozen external-plugin fixtures discovered from an isolated `HERMES_HOME`."
19. A standalone pytest test harness for plugin authors (temp HERMES_HOME fixture runtime) was proposed in #64230 and the issue is CLOSED; not verified whether the harness shipped as a public package. — V (issue state), S (shipping status)
    Source: https://github.com/NousResearch/hermes-agent/issues/64230
    Quote: "ship a pytest-based test harness plugin authors can use from a standalone repo — fixture runtime with a temp HERMES_HOME"
20. `plugins validate` has known false-admission bugs (requires_hermes CalVer floor). Validate-green ≠ installable. — V
    Source: https://github.com/NousResearch/hermes-agent/issues/130656 (reproduced on "clean throwaway `HERMES_HOME`")

### D. How official/community plugin authors test both halves

21. Official plugins repo CI: per plugin, Linux/macOS/Windows, nightly cron; installs hermes-agent editable + plugin `[project].dependencies`, runs `plugins validate` with `HERMES_HOME: ${{ runner.temp }}/hermes-home`, then pytest, then optional `evals/ci.sh`. — V
    Source: https://github.com/NousResearch/hermes-official-plugins/blob/main/.github/workflows/tests.yml (CI config)
    Quote: "The nightly run catches a core change that breaks a plugin before a user does." / "run: python -m hermes_cli.main plugins validate \"pantheon/${{ matrix.plugin }}\" env: HERMES_HOME: ${{ runner.temp }}/hermes-home"
    Caveat: it installs deps with pip into a normal venv — i.e. it would NOT catch an undeclared dep that happens to be present transitively. — P
22. Official CONTRIBUTING: run the suite against a side-by-side hermes-agent checkout via PYTHONPATH, then `hermes plugins validate`. — V
    Source: https://github.com/NousResearch/hermes-official-plugins/blob/main/CONTRIBUTING.md
    Quote: "HERMES_AGENT_REPO=../../hermes-agent PYTHONPATH=../../hermes-agent python -m pytest -q"
23. Community catalog plugin with backend+desktop halves (jacobhausler/hermes-workflows): CI = `node --check` on desktop/plugin.js as ESM, serial suite of Python + Node `.mjs` tests, `hermes plugins validate .` against a PINNED hermes-agent commit. No GUI-driving e2e. — V
    Source: https://github.com/jacobhausler/hermes-workflows/blob/main/.github/workflows/ci.yml
    Quote: "1. desktop half parses as ESM 2. serial test suite (stdlib Python + Node .mjs) ... 4. `hermes plugins validate .` against a PINNED upstream commit"
    Catalog page: "Node for the desktop half's tests only; the app loads `plugin.js` uncompiled" (https://hermes-agent.nousresearch.com/docs/plugins/hermes-workflows)
24. VALIDATION.md is used by some catalog submitters as a QA record (e.g. hermes-lang-vi: "recorded in `VALIDATION.md`"), not an official required artifact. — V (mention), P (not required — not found in catalog-submission docs)
    Source: https://github.com/NousResearch/hermes-agent/pull/130281
25. A PR author testing a desktop-plugin UX against the packaged app used upstream's Playwright `launch-packaged-app.spec.ts` with a plugin fixture + `mock-server.ts` — i.e. the only GUI-level plugin e2e found lives INSIDE hermes-agent's own e2e suite. — V
    Source: https://github.com/NousResearch/hermes-agent/pull/98173 (open)
    Quote: "`npx playwright test e2e/launch-packaged-app.spec.ts --grep 'Follow-up'`" / "apps/desktop/e2e/fixtures/follow-up-plugin.js apps/desktop/e2e/mock-server.ts"

### E. Upstream Desktop e2e harness (model for part (b))

26. Upstream runs Desktop e2e as Playwright + Electron under `xvfb-run -a --server-args="-screen 0 1280x1024x24"` on Linux, installing xvfb + GTK/NSS libs. — V
    Source: https://github.com/NousResearch/hermes-agent/blob/main/.github/workflows/e2e-desktop.yml and e2e-desktop-core.yml (CI config)
    Quote: "xvfb-run -a --server-args=\"-screen 0 1280x1024x24\" npx playwright test -c e2e/core/playwright.config.ts"
27. The "core" suite builds and packages the app (`electron-builder --dir`) and runs with `HERMES_E2E_REQUIRE_PACKAGED: '1'`, `HERMES_E2E_PYTHON`, and all provider API keys emptied (no live LLM). — V
    Source: e2e-desktop-core.yml (same)
28. The broad Desktop e2e lane is disabled (`if: false`) because it is flaky; core suite is required, retries 0. — V
    Source: https://github.com/NousResearch/hermes-agent/blob/main/.github/workflows/ci.yaml ; https://github.com/NousResearch/hermes-agent/issues/76627 (closed)
    Quote: "Re-disabled (Sep 2026): the Sep 1 re-enable is still incredibly flaky." / "The lane stays `if: false`"
29. Root cause of flake: each spec launches a full Electron + `hermes serve` stack; parallel workers race startup → serialize to 1 worker. — V (PR open)
    Source: https://github.com/NousResearch/hermes-agent/pull/101149
    Quote: "The suite launches a full Electron app and backend for each spec; CI's default worker count launches those stacks concurrently and makes startup flaky."
    Implication for staging: run GUI specs serially, one Electron+backend per spec. — P
30. Upstream e2e spec list includes mock-backend and boot specs (`boot.spec.ts`, `mock-backend-setup`, `fixtures.ts`, `real-session-builder.ts`) — the harness can run against a mock backend, not only a real gateway. — V (file listing via GitHub contents API, apps/desktop/e2e)

### F. Parallel / multiple Hermes instances side by side

31. Gateway "scoped lock" prevents two gateways using one bot token, and has race windows; tests reproduced it against a temp HERMES_HOME. A staging instance must NOT share bot tokens with live. — V
    Source: https://github.com/NousResearch/hermes-agent/issues/124285 (open)
    Quote: "`acquire_scoped_lock` (the lock that stops two gateways using one bot token) has two windows in which both gateways end up owning the lock"
32. Running the same buildable plugin in multiple profiles of one gateway breaks uv workspace resolution ("Two workspace members are both named") — argues for a separate instance/HERMES_HOME over a staging PROFILE inside live. — V
    Source: https://github.com/NousResearch/hermes-agent/issues/125252, https://github.com/NousResearch/hermes-agent/issues/138702 (open)
    Quote: "this now also blocks plugin management ... `hermes plugins disable` fails at admission with the same conflict"
33. Linux Desktop second-instance launches poison sandbox fallback markers (sticky --no-sandbox); relevant if a test Electron runs alongside a user Desktop on the same machine. — V (open; fix PR #131067)
    Source: https://github.com/NousResearch/hermes-agent/issues/131055
34. Community (Reddit megathread) reports multiple Telegram bots from one instance via separate profiles with per-profile tokens — profiles as isolation, not separate instances. — P (community summary)
    Source: https://www.reddit.com/r/hermesagent/comments/1ui5a91/integrations_plugins_skills_ecosystem_megathread/ (search snippet only, not read whole)
35. The isolated-HERMES_HOME pattern (temp home per run) is the de-facto upstream way to get a "second instance" for testing; it appears in docs (#16, #18), official plugin CI (#21) and multiple bug repros (#124285, #130656, #138334 "explicitly isolate `HERMES_HOME`"). — V (pattern), P (that it fully isolates a gateway+dashboard pair on one host)

### G. Planned / in-flight
36. Open PRs relevant to staging e2e: #136043 (doctor runtime-venv dep check), #138334 (refresh plugin deps per generation), #137317 (point non-interactive refusal at --yes-deps), #101149 (serialize desktop e2e). None is a plugin-author e2e harness. — V (states as of 2026-10-17)
37. Catalog admission will enforce a 3-day release-age on plugin Python deps (design open). Pin plugin deps accordingly; staging should use the same resolver. — V (issue open)
    Source: https://github.com/NousResearch/hermes-agent/issues/137541

## Searched, found nothing (evidence of absence)
- gh search issues/PRs NousResearch/hermes-agent: "plugin requirements install" (0), "multiple instances HERMES_HOME" (0), "mock backend desktop" (0 issues/PRs), "plugin_api dashboard test" (0), "plugins install --yes consent" (0), "profile parallel gateway" (0 issues), "test harness plugin" (only #64230 + unrelated).
- No issue/discussion about a "staging" Hermes instance (query "staging" returned only plugin-install staging dirs / memory staging — unrelated semantics).
- No public desktop-plugin e2e harness for third-party authors; no docs page on GUI-testing desktop plugins (developer-guide/plugins + catalog-submission read; only `desktop surface` static check).
- No dashboard `plugin_api` e2e/test guidance found in issues/PRs.
- No VALIDATION.md requirement in catalog-submission docs; gh code search `filename:VALIDATION.md` returned no Hermes plugin repos.
- web_search "reddit hermesagent plugin staging/test profile second gateway" → 0 results; "plugin testing staging instance reddit/discord" → only Discord setup blogs (irrelevant).
- Discord/forum mirrors: no indexed results found (skipped beyond web_search; Discord not crawlable).
- Separate desktop repo: none — Desktop lives in hermes-agent `apps/desktop` (repo list of NousResearch checked; no standalone desktop repo).
- nixos-infra: not in this lane's source types (owned by lane 4) — skipped.

## Implications for the staging design (lane-level, for the collector)
- Backend half: test by actually loading the plugin in a runtime-equivalent env (same image, `--yes-deps` install, gateway start, assert plugin listed + no load WARNING), not only pytest in a dev venv — upstream doctor/validate do not catch undeclared imports reliably (#5, #21). — P
- Install step must be CLI (`--yes-deps`); Desktop GUI install with deps is broken upstream (#12, #13). — V-based
- GUI half: upstream's own pattern is Playwright+Electron+xvfb, serial, provider keys emptied, packaged app (#26–#29); feasible in a Linux pod with xvfb. — P
- Separate instance (own HERMES_HOME/PVC, no shared bot tokens) over a staging profile in live (#31, #32). — P
