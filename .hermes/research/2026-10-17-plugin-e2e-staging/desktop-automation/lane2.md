# Lane 2 — Hermes Desktop GUI automation (frontend half)

Card: t_03a6d8eb (parent t_cd95f6bd, collector t_6078e578) · Date: 2026-10-17 · Tiers: Verified / Plausible / Speculative
Sub-question: How can the Desktop frontend half (desktop/plugin.js ESM, panes, GUI interaction) be driven automatically and headless, ideally against a non-live (staging) gateway, on k8s nodes without GPU/display?

Docs-first record: official Hermes docs (user-guide/desktop, developer-guide/desktop-plugin-sdk) and the local skills `inspecting-hermes-desktop-dom` + `hermes-desktop-plugins` were read first. Electron, Playwright and WebdriverIO official docs were read next. Upstream hermes-agent repo files were only used where the docs gave no answer about test harnesses: perf README, e2e/core README, the CI workflow and the e2e fixtures. These files are the project's own test docs and configs. Plugin runtime code was NOT read. Two claims were confirmed by experiment in this sandbox pod; they are tagged [live].

## TL;DR

1. Upstream Hermes already ships a complete headless Electron E2E harness. It uses Playwright `_electron.launch` against `electron .` (the same path as `hermes desktop --source`), runs under `xvfb-run`, and passes `--disable-gpu --no-sandbox`. It uses a sandboxed HOME/HERMES_HOME/user-data dir, a mock LLM provider, and a remote-backend topology via `HERMES_DESKTOP_REMOTE_URL` + token. This is the template for our desktop e2e. We should not invent a new one.
2. [live] Electron 40.10.6 renders, and Playwright `_electron` drives it (text read + screenshot), under Xvfb inside the hermes-suite pod on wrk. No GPU or real display was used, so CPU-only k8s nodes are feasible.
3. A packaged Desktop has no CDP and cannot be automated by attach. Automation needs either the source/dev build (`electron .`) launched by Playwright, or a dev-server build with `HERMES_DESKTOP_CDP_PORT`. The user's own packaged Desktop stays untouched.
4. The plugin SDK can be exercised outside Electron at two levels:
   - our existing node stub smoke (contract only);
   - upstream's vitest `ui` project (`environment: 'jsdom'`, `@hermes/plugin-sdk` aliased to `src/sdk/index.ts`).

   `@hermes/plugin-sdk` is not published on npm, so a jsdom render test must run inside a hermes-agent checkout.

## Findings

### F1 — Desktop plugins load from disk without a build and hot-reload
- Claim: A desktop plugin is one ESM file at `$HERMES_HOME/desktop-plugins/<id>/plugin.js`, or `$HERMES_HOME/plugins/<id>/desktop/plugin.js` for unified packages. It is loaded uncompiled and hot-reloaded. A test can therefore "install" the frontend half by copying one file into a sandbox HERMES_HOME.
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk (official docs)
- Quote: "Drop the file in `$HERMES_HOME/desktop-plugins/<id>/plugin.js` and the app loads it within seconds and hot-reloads every save." / "| **Unified package** | `$HERMES_HOME/plugins/<id>/desktop/plugin.js` | plugins that also ship agent-side code"
- Tier: Verified

### F2 — The unified package's desktop half is copied by the Electron main process
- Claim: When a unified plugin lands in a local `plugins/` root, Electron main copies the desktop half into `desktop-plugins/<id>/` with a `.hermes-package.json` marker. The desktop half is opt-in and must be enabled in Capabilities → Plugins. An e2e test must therefore either enable it via the UI or pre-seed the disk copy.
- Source: desktop-plugin-sdk docs (official) + local skill hermes-desktop-plugins
- Quote: "the Electron main process copies that half into `$HERMES_HOME/desktop-plugins/<id>/` beside a `.hermes-package.json` marker, and the renderer loads it through the exact same pipeline as the standalone disk door" / skill: "In Desktop, go to Capabilities → Plugins, use **Rescan** if needed, and enable the plugin. The desktop half ships opt-in."
- Tier: Verified (docs). The exact pre-seed mechanism for "enabled" state is Speculative.

### F3 — Backend routes mount only at gateway start
- Claim: `ctx.rest` 404s unless `dashboard/manifest.json` declares `api`, the plugin is in `plugins.enabled`, and the gateway was restarted. A frontend e2e therefore needs a backend that starts *after* the plugin is installed, which a fresh staging/sandbox `hermes serve` gives for free.
- Source: desktop-plugin-sdk docs, Troubleshooting (official)
- Quote: "**`ctx.rest` returns 404.** ... confirm ... `\"api\": \"plugin_api.py\"`, that the plugin is in `plugins.enabled` in `config.yaml`, and restart the gateway (backend routes mount at startup). Tail `~/.hermes/logs/errors.log` for `Failed to load plugin <id> API routes`."
- Tier: Verified

### F4 — `hermes desktop --source` = `electron .` against `dist/`
- Claim: `--source` launches the unpackaged app from `apps/desktop/dist`. `--ignore-existing` skips the local runtime, and `--hermes-root` overrides the source root.
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/desktop (official)
- Quote: "| `--source` | Launch via `electron .` against `apps/desktop/dist` instead of the packaged app |" / "| `--ignore-existing` | Skip the installed Hermes runtime so no local backend starts; offer connect or install |"
- Tier: Verified

### F5 — Dev server and isolation env vars
- Claim: `npm run dev` starts Vite plus Electron. `HERMES_HOME=<throwaway>` sandboxes it from the real config, and `HERMES_DESKTOP_HERMES_ROOT` picks the checkout.
- Source: user-guide/desktop (official)
- Quote: "npm run dev          # Vite renderer + Electron, which boots the Python backend" / "HERMES_HOME=$HOME/.hermes/cache/scratch/throwaway npm run dev"
- Tier: Verified

### F6 — CDP 9222 opens only for dev-server runs, never for packaged builds
- Claim: The CDP port opens only when `HERMES_DESKTOP_DEV_SERVER` is set and the build is unpackaged. Packaged builds never open it; no env value overrides that. `HERMES_DESKTOP_CDP_PORT` moves the port or turns it off.
- Source: local skill inspecting-hermes-desktop-dom (KB/skill, cites apps/desktop/electron/dev-cdp.ts)
- Quote: "Closed in exactly two cases: **packaged builds** — always, and no environment value overrides it; **no `HERMES_DESKTOP_DEV_SERVER`** — an unpackaged `electron .` against `dist/` is how the packaged app gets smoke tested, so it behaves like one." / "`HERMES_DESKTOP_CDP_PORT` moves the port (`=9333`) or disables it (`=off`)."
- Tier: Verified (skill; not re-checked against v0.22.2 code)
- Consequence: the user's packaged Desktop can never be a test target, which is good for "don't disturb live".

### F7 — An isolated second instance never collides with the user's app
- Claim: An isolated second instance avoids the single-instance lock and the real sessions. It needs its own `--user-data-dir`, `HERMES_HOME` and CDP port.
- Source: skill inspecting-hermes-desktop-dom
- Quote: "The separate `--user-data-dir` dodges Electron's single-instance lock, so it cannot collide with a running `hgui`; the separate `HERMES_HOME` keeps it away from real sessions."
- Tier: Verified (skill)

### F8 — `npm run perf:serve` is an isolated CDP-attachable instance
- Claim: `perf:serve` launches a fully isolated instance (temp HERMES_HOME + user-data-dir, CDP :9222 or `PERF_PORT`) and leaves it running for attach. `npm run perf -- --spawn` does the same per run. Synthetic scenarios drive the UI via `window.__PERF_DRIVE__` without LLM credits.
- Source: https://github.com/NousResearch/hermes-agent/blob/main/apps/desktop/scripts/perf/README.md and scripts/perf/serve.mjs header (upstream repo dev docs)
- Quote: "`--spawn` / `perf:serve` launch with their own `--user-data-dir` (separate lock scope), their own `HERMES_HOME` (separate backend + sessions), and their own `--remote-debugging-port`. Synthetic scenarios drive `$messages` directly via `window.__PERF_DRIVE__`, so no LLM credits are spent." / serve.mjs: "npm run perf:serve # :9222, temp HERMES_HOME + user-data-dir … PERF_PORT=9333 npm run perf:serve"
- Tier: Verified (doc)
- Note: perf:serve is a measurement harness. It is good as an "attach and poke" seam (`lib/cdp.mjs` has `SELECTORS` for stable `data-slot` hooks) but has no plugin-assertion features.

### F9 — Upstream ships a Playwright `_electron` E2E suite for Desktop
- Claim: `apps/desktop/package.json` has `test:e2e` (`playwright test e2e/`), `test:ui` (vitest jsdom), `dev:mock` (mock server) and `test:e2e:visual` (headless wlroots `cage`). The devDeps include `@playwright/test`, `jsdom`, `vitest`, and electron 40.10.2.
- Source: https://raw.githubusercontent.com/NousResearch/hermes-agent/main/apps/desktop/package.json (upstream config, fetched 2026-10-17)
- Quote: "test:e2e = npm run build && playwright test e2e/" / "test:e2e:visual = npm run build && WLR_BACKENDS=headless WLR_NO_HARDWARE_CURSORS=1 cage -- npx playwright test e2e/ --reporter=list" / "dev:mock = node ../../tests-js/scripts/mock-server.ts"
- Tier: Verified (main branch; not diffed against the v0.22.2 tag)

### F10 — The e2e fixtures are the isolation recipe
- Claim: The fixtures launch `electron .` (not packaged) with `--disable-gpu --no-sandbox`. They set a sandboxed HOME/HERMES_HOME/user-data dir, strip all `HERMES_*` and credential env vars, and set isolation flags. They offer a `mockBackend` mode (real `hermes serve`, fake LLM) and a `noProvider` mode.
- Source: https://github.com/NousResearch/hermes-agent/blob/main/apps/desktop/e2e/fixtures.ts (upstream test fixture, header doc + env block)
- Quote: "`mockBackend` — starts a mock inference server, writes a config.yaml that points at it, and launches the desktop app so the full chain (electron → hermes serve → provider → inference → renderer) is exercised with a real backend but a fake LLM." / "HERMES_DESKTOP_IGNORE_EXISTING: '1', … HERMES_DESKTOP_ISOLATED_BACKEND: '1', HOME: sandbox.root, … HERMES_DESKTOP_APP_NAME: `HermesE2E-${Date.now()}`, … HERMES_DESKTOP_SKIP_QUIT_CONFIRM: '1', HERMES_DESKTOP_SKIP_PROTOCOL_REGISTRATION: '1'" / "args: [ DESKTOP_ROOT, '--disable-gpu', '--no-sandbox', ]"
- Tier: Verified (upstream test fixture used as harness documentation; not product source)

### F11 — CI runs it under xvfb on plain Ubuntu, without a GPU
- Claim: The upstream workflow "Playwright E2E (Linux)" installs xvfb plus GTK/NSS libs and runs `xvfb-run -a --server-args="-screen 0 1280x1024x24" npx playwright test`.
- Source: https://github.com/NousResearch/hermes-agent/blob/main/.github/workflows/e2e-desktop.yml (upstream CI)
- Quote: "sudo apt-get install -y -qq xvfb libgtk-3-0 libnotify4 libnss3 libxss1 libxtst6 xdg-utils libatspi2.0-0 libdrm2 libgbm1 libasound2t64" / "npm run build && xvfb-run -a --server-args=\"-screen 0 1280x1024x24\" npx playwright test --reporter=list"
- Tier: Verified
- Note: the runner is `blacksmith-32vcpu-ubuntu-2404`. Upstream sizes for 32 vCPU, so expect slower runs on wrk.

### F12 — The core suite already tests Desktop → remote `hermes serve` by URL + token
- Claim: The e2e/core "Remote topology" specs spawn a separate `hermes serve` under its own HOME/HERMES_HOME and connect Desktop only via `HERMES_DESKTOP_REMOTE_URL`/`_TOKEN`. This is exactly the "test Desktop → staging gateway" shape.
- Source: https://github.com/NousResearch/hermes-agent/blob/main/apps/desktop/e2e/core/README.md + e2e/core/remote-helpers.ts header (upstream test docs)
- Quote: "**Remote topology** — `remote-topology.spec.ts`: the whole app on a remote `hermes serve` (`HERMES_DESKTOP_REMOTE_URL` + token)" / remote-helpers.ts: "a real `hermes serve` the TEST spawns (not the app) under its OWN sandbox HOME / HERMES_HOME / cwd, reached by the Desktop only by URL + token (HERMES_DESKTOP_REMOTE_URL/_TOKEN)."
- Tier: Verified

### F13 — The core suite can be run locally with one command
- Claim: The core suite runs locally with `xvfb-run -a npx playwright test -c e2e/core/playwright.config.ts` after `npm run build`. `HERMES_E2E_CORE_KEEP=1` keeps the sandboxes.
- Source: e2e/core/README.md (upstream test docs)
- Quote: "cd apps/desktop / xvfb-run -a npx playwright test -c e2e/core/playwright.config.ts" / "`HERMES_E2E_CORE_KEEP=1` keeps sandboxes for post-mortem."
- Tier: Verified (doc). Not run here: it needs a full hermes-agent checkout and `npm run build`.

### F14 — The packaged-build smoke spec exists but proves only the shell
- Claim: `packaged-smoke.spec.ts` boots the `electron-builder --dir` output to a first chat, but it uses the checkout's Python backend.
- Source: e2e/core/README.md
- Quote: "It runs this checkout's Python backend, so it proves the packaged shell and renderer, not a bundled runtime. Skipped without a build unless `HERMES_E2E_REQUIRE_PACKAGED=1`."
- Tier: Verified

### F15 — The remote URL can be set by env; sign-in is a UI step
- Claim: Docs say `HERMES_DESKTOP_REMOTE_URL` sets the backend without the UI, but you still sign in from Settings → Gateways. Unattended tests therefore need the token path (`_TOKEN`, F12) or a pre-seeded `connections.json`.
- Source: user-guide/desktop, "In the app" (official)
- Quote: "You can also set the backend URL without the UI via the `HERMES_DESKTOP_REMOTE_URL` environment variable before launching the app (it overrides the in-app setting); you still sign in from the Gateways settings panel."
- Tier: Verified (docs). `HERMES_DESKTOP_REMOTE_TOKEN` is documented only in the upstream test docs (F12); treat it as a test seam, Plausible as a stable interface.

### F16 — The remote backend must be `hermes serve` (port 9119)
- Claim: Desktop's remote mode talks to a `hermes serve` backend on 9119. Messaging gateways are a separate process, so a staging instance for desktop tests only needs `hermes serve`.
- Source: user-guide/desktop (official)
- Quote: "\"Remote backend\" means a **`hermes serve`** server running on the remote machine — that is the process the desktop app connects to." / "**Remote URL** — `http://<backend-host>:9119`"
- Tier: Verified

### F17 — Playwright Electron support is experimental, needs v21+ and the nodeCliInspect fuse
- Claim: Playwright `_electron` is experimental and supports Electron v21+. Launch hangs if the `nodeCliInspect` fuse is disabled, which many packaged apps do. That is one more reason to target the source build.
- Source: https://playwright.dev/docs/api/class-electron (official)
- Quote: "Playwright has **experimental** support for Electron automation." / "**Supported Electron versions are:** v21+" / "Ensure that `nodeCliInspect` (FuseV1Options.EnableNodeCliInspectArguments) fuse is **not** set to `false`."
- Tier: Verified

### F18 — Native dialogs must be stubbed via `electronApp.evaluate`
- Claim: Playwright does not intercept native dialogs; they must be stubbed in the main process via `electronApp.evaluate`. This is relevant if a plugin flow hits a save dialog (`host` download path).
- Source: playwright.dev class-electron (official)
- Quote: "Playwright does not intercept the native Electron dialog API ... Use electronApplication.evaluate() to replace the relevant methods in the main process so tests run deterministically without any OS-level UI"
- Tier: Verified

### F19 — connectOverCDP is a lower-fidelity fallback
- Claim: `chromium.connectOverCDP` can attach to an already-running instance (perf:serve / dev-server CDP port), but at lower fidelity than a Playwright launch.
- Source: https://playwright.dev/docs/api/class-browsertype#browser-type-connect-over-cdp (official)
- Quote: "This connection is significantly lower fidelity than the Playwright protocol connection via browserType.connect()."
- Tier: Verified
- Use it for ad-hoc attach. For CI use `_electron.launch` (F10).

### F20 — Electron needs a display; Xvfb is the official headless answer
- Claim: Electron cannot launch without a display driver. The official headless-CI recipe is Xvfb plus `DISPLAY`, optionally via `xvfb-maybe`.
- Source: https://www.electronjs.org/docs/latest/tutorial/testing-on-headless-ci (official)
- Quote: "Being based on Chromium, Electron requires a display driver to function. If Chromium can't find a display driver, Electron will fail to launch" / "create a virtual Xvfb screen and export an environment variable called DISPLAY that points to it."
- Tier: Verified

### F21 — Electron docs list three automation drivers
- Claim: Electron's official testing guide lists WebdriverIO, Selenium (ChromeDriver), and Playwright (CDP-based, experimental).
- Source: https://www.electronjs.org/docs/latest/tutorial/automated-testing (official)
- Quote: "Playwright has experimental Electron support via Electron's support for the Chrome DevTools Protocol (CDP)." / "WebdriverIO (WDIO) is a test automation framework that provides a Node.js package for testing with WebDriver."
- Tier: Verified

### F22 — WebdriverIO's electron service is a viable alternative
- Claim: `@wdio/electron-service` auto-sets up Chromedriver, detects Forge/Builder apps, and can mock Electron APIs. It needs `appEntryPoint` for an unpackaged bundle. Upstream Hermes already uses Playwright, so WDIO would mean a second, divergent harness.
- Source: https://webdriver.io/docs/desktop-testing/electron (official)
- Quote: "auto-setup of required Chromedriver … automatic path detection of your Electron application - supports Electron Forge and Electron Builder … mocking of Electron APIs via a Vitest-like API" / "appEntryPoint: './path/to/bundled/electron/main.bundle.js'"
- Tier: Verified (capability). The recommendation against it is an inference (Plausible).

### F23 — [live] Electron renders under Xvfb in the hermes-suite pod without a GPU
- Claim: Electron 40.10.6 started under `Xvfb :99 -screen 0 1280x1024x24` with `--disable-gpu --no-sandbox` inside this sandbox (hermes-suite pod on wrk; 4 vCPU / 13 GiB visible). It loaded a page and returned renderer JS output.
- Source: experiment, 2026-10-17, /opt/data/cache/scratch/l2/eprobe (npm electron@40)
- Excerpt: stdout `RENDER hi`. Non-fatal noise: "Failed to connect to the bus … system_bus_socket" and "Failed to adjust OOM score of renderer … Permission denied".
- Tier: Verified [live]
- Caveat: `xvfb-run` failed here with "xauth command not found", so start `Xvfb` directly or install `xauth`.

### F24 — [live] Playwright `_electron` drives Electron under Xvfb in the same pod
- Claim: `playwright-core` `_electron.launch({executablePath: electron, args:['.','--disable-gpu','--no-sandbox']})` drove Electron headlessly in the pod: `firstWindow()`, `textContent`, and `screenshot`.
- Source: experiment, 2026-10-17 (pw.js in the same probe dir)
- Excerpt: stdout `PW_TEXT hi` / `SHOT ok`
- Tier: Verified [live] (toy app, not the Hermes Desktop)

### F25 — The plugin SDK can be exercised outside Electron via upstream's vitest jsdom project
- Claim: Upstream's vitest `ui` project runs `src/**/*.test.tsx` in jsdom. Vite aliases `@hermes/plugin-sdk` to `./src/sdk/index.ts`. Upstream already has plugin tests there (e.g. `src/contrib/plugin.test.ts`, `plugin-run-action.test.ts`, `plugin-pane-close.test.ts`). A real-SDK render test of our plugin.js is therefore possible inside a hermes-agent checkout.
- Source: upstream apps/desktop/vitest.config.ts, vite.config.ts, and the repo tree (config, fetched 2026-10-17)
- Quote: vitest.config.ts: "name: 'ui', environment: 'jsdom', … include: ['src/**/*.test.{ts,tsx}']" / vite.config.ts: "'@hermes/plugin-sdk': path.resolve(__dirname, './src/sdk/index.ts')"
- Tier: Verified (configs). Rendering *our* plugin there is untested, so Plausible.

### F26 — `@hermes/plugin-sdk` is not on npm
- Claim: The SDK is not on the public npm registry, so a standalone repo cannot `npm i` it. Our repo's node smoke stubs it (only `@hermes/plugin-sdk`, `react`, `react/jsx-runtime` are allowed imports).
- Source: https://registry.npmjs.org/@hermes%2fplugin-sdk → `{"error":"Not found"}` (live HTTP 2026-10-17); repo scripts/smoke_desktop_plugin.mjs header
- Quote: smoke: "Loads the plugin under Node with stub `@hermes/plugin-sdk`, `react` and `react/jsx-runtime` modules (the only specifiers the desktop loader allows)"
- Tier: Verified [live]

### F27 — The current local skill rule is outdated for isolated instances
- Claim: The `hermes-desktop-plugins` skill says the agent cannot click through Desktop and plans manual checklists. That holds for the user's packaged app (F6). An isolated source build under Xvfb (F10/F23/F24) removes the limitation for automated tests.
- Source: /opt/data/skills/hermes-desktop-plugins/SKILL.md (local skill)
- Quote: "The agent cannot click through Desktop. A packaged app has no CDP port. Automated checks are pytest plus a node smoke script that imports `plugin.js` and asserts its registrations."
- Tier: Plausible (on-target Hermes Desktop run not yet done). Flag for the collector: skill update candidate.

### F28 — Infra fit: wrk (role=apps) can host it; no GPU or display needed
- Claim: No GPU or display is required (F11/F23). The k3s app node wrk (`role=apps`) is the natural host. The GPU host llmp is reserved for the LLM stack. hermes-suite storage is a static hostPath PV with `storageClassName: ""` pinned to wrk, so a staging/test pod should use its own emptyDir/tmp HERMES_HOME (as the e2e fixtures do) and never the live `/mnt/iscsi/hermes-data`.
- Source: nixos-infra hosts/wrk/configuration.nix ("--node-label=role=apps"), hosts/llmp/configuration.nix ("GPU-LLM-Host (Phase 7 … k3s-GPU-Agent"), clusters/cpl/apps/hermes-suite/storage.yaml ("static hostPath PV/PVC (storageClassName \"\" + claimRef, nodeAffinity wrk)") (local repo, read-only)
- Tier: Verified (repo state). The staging pod design itself is Plausible; lane 4 owns it.

### F29 — Desktop must be built from a hermes-agent checkout
- Claim: Our image (`/opt/hermes`) has `apps/` but no `apps/desktop` (only `shared`). The e2e harness cannot run from the runtime image as-is. A test job must clone hermes-agent at the matching tag, then `npm ci` + `npm run build` + system libs (F11).
- Source: local `ls /opt/hermes/apps` → `shared` (live 2026-10-17)
- Tier: Verified [live]

## Feasible paths (lane view, for the collector)

A. Contract smoke (exists): node + stubbed SDK. It is cheap and already in the repo, but it cannot catch real-loader or render errors.

B. jsdom render test with the real SDK: add a vitest file inside a hermes-agent checkout at the matching tag (F25/F26). It catches SDK API drift but not the Electron loader or backend.

C. Full headless E2E (recommended):
  - Clone hermes-agent at the v0.22.2 tag, then `npm ci && npm run build`.
  - Use a sandbox HERMES_HOME with the plugin copied to `plugins/<id>/` and `plugins.enabled` set.
  - Start a fresh `hermes serve` (F3/F12) with a mock provider (`dev:mock` / fixtures `mockBackend`).
  - Launch Playwright `_electron` with `--disable-gpu --no-sandbox` under Xvfb (F10/F11/F23/F24).
  - Assert the plugin pane/status item via DOM `data-slot` selectors, and check `errors.log` for "Failed to load plugin".
  - It runs as a k8s Job on wrk with emptyDir. It never touches the live pod or the user's Desktop.

D. Attach mode: `perf:serve` or a dev-server CDP port plus `connectOverCDP`/`lib/cdp.mjs` (F8/F19). Good for interactive debugging, weaker for CI.

E. WebdriverIO (F22): works, but diverges from upstream's harness. Not recommended.

Untested on target: steps A–C against the real Hermes Desktop v0.22.2 build. Only a toy Electron app was driven (F23/F24). Also untested: the exact env/seed to auto-enable an opt-in desktop half without UI clicks, and whether `HERMES_DESKTOP_REMOTE_TOKEN` exists in v0.22.2 (the docs read were main).

## Searched, found nothing (evidence of absence)
- Web search "hermes-agent apps/desktop perf:serve OR remote-debugging-port OR 9222" (web): returned only the Browser Automation doc (agent browser tool, unrelated). No desktop-dev doc page on the docs site.
- Web search "NousResearch hermes-agent apps/desktop scripts/perf README perf:serve" (web): 0 results, so the repo was fetched directly.
- Official docs user-guide/desktop + desktop-plugin-sdk, keywords "9222", "CDP", "remote-debugging", "playwright", "Xvfb", "test" (in a testing sense): none found. Automated GUI testing is not documented on the docs site; it lives only in the repo test docs.
- npm registry `@hermes/plugin-sdk`: not found (F26).
- Upstream repo tree, `apps/desktop/e2e/**plugin**`: no e2e spec exercises a disk/desktop plugin. There is no upstream example of plugin GUI e2e; we would write the first.
- GitHub code search: unauthenticated API refused ("Requires authentication"), skipped.
- Electron headless/Docker: found issue electron/electron#26974 (crash headless in Docker) in a search snippet only, not read. It was superseded by the live test (F23).
- Not covered (budget): WebdriverIO configuration subpages, noVNC for human watching (lane 4/5 territory), and Reddit/community posts (lane 3).
