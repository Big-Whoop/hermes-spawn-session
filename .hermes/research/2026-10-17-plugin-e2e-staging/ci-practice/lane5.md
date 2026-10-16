# Lane 5 — CI practice for host-app plugin e2e in other ecosystems (what transfers to Hermes)

Date: 2026-10-17 · Card: t_9a4fe34d · Tiers: Verified / Plausible / Speculative
Method: web_search -> web_extract (char_limit 60000/80000; all load-bearing pages were under the limit, so they were read whole) -> regex over the full text.

## TL;DR
Every mature ecosystem tests plugins against a DISPOSABLE, VERSION-PINNED host started per run (downloaded binary or docker image), with an isolated profile/data dir, a headless display (Xvfb) for Electron hosts, Playwright/WebdriverIO as the driver, and trace/video/report artifacts uploaded on failure. None of them test against a user's live instance. Dependency gaps are caught by installing the plugin into a fresh environment and running a manifest validator plus an import/load smoke test. For Hermes the direct analogues already exist: `hermes plugins validate --install-deps` (= catalog CI) and `hermes plugins doctor` (temporary HERMES_HOME). That makes the "parallel staging instance" a heavier extra; most of the backend half fits into a throwaway HERMES_HOME/container per run.

## Findings

### A. VS Code (@vscode/test-electron)
1. The test runner downloads a pinned VS Code build and launches it per run, separate from the user's install. Verified.
   Source: https://code.visualstudio.com/api/working-with-extensions/testing-extension (official docs)
   Quote: "Downloads and unzips latest version of VS Code." / "`version` - The version of VS Code to use for running tests (defaults to `stable`)."
2. The extension under test is injected through CLI flags, not installed into a profile. Verified.
   Same source. Quote: "VS Code provides two CLI parameters for running extension tests, `--extensionDevelopmentPath` and `--extensionTestsPath`."
3. Isolation is done with `--disable-extensions` and a dedicated `--user-data-dir`. Verified.
   Same source. Quote: "You can add `--disable-extensions` configuration to the `launch.json` or the `launchArgs` option of `@vscode/test-electron`'s `runTests` API." / "Using a dedicated `--user-data-dir` prevents previously persisted trust decisions from making this run accidentally trusted."
4. Headless Linux CI needs Xvfb (`xvfb-run -a`) plus the GTK/NSS libs, also inside Docker images on GitLab. Verified.
   Source: https://code.visualstudio.com/api/working-with-extensions/continuous-integration (official docs)
   Quote: "In headless Linux CI machines `xvfb` is required to run VS Code ... - run: xvfb-run -a npm test" / "apt install -y libasound2 libgbm1 libgtk-3-0 libnss3 xvfb"
   Transfer: the Hermes Desktop Electron app in a k8s pod needs the same lib set plus Xvfb. Plausible (same Electron/Chromium base, not tested with Hermes Desktop).

### B. Obsidian (wdio-obsidian-service)
5. A WebdriverIO service downloads several Obsidian versions and runs them sandboxed so tests don't touch the user's system and can run in parallel. Verified.
   Source: https://webdriver.io/docs/wdio-obsidian-service/ (official WDIO docs)
   Quote: "Download and test multiple versions of Obsidian" / "Sandbox Obsidian so tests don't interfere with your system and can run in parallel" / "Open and switch between vaults"
6. Downloaded host binaries are kept in a cache dir (`cacheDir: ".obsidian-cache"`), so repeat runs are cheap. Verified.
   Source: https://github.com/jesse-r-s-hines/wdio-obsidian-service/blob/main/packages/wdio-obsidian-service/README.md (README)
   Quote: "wdio-obsidian-service will download Obsidian versions into this directory  cacheDir: path.resolve(\".obsidian-cache\")"
   Transfer: a fixture vault maps to a seeded fixture HERMES_HOME; the cache maps to a pre-pulled staging image. Plausible.

### C. JupyterLab (Galata)
7. Galata is a set of Playwright fixtures/helpers that isolate state between tests. Verified.
   Source: https://github.com/jupyterlab/jupyterlab/blob/main/galata/README.md (README)
   Quote: "Galata is a set of helpers and fixtures for JupyterLab UI Testing using Playwright Test Runner" / "Dedicated fixtures ... to hooks the helpers in the Playwright Page and ensure state isolation between tests."
8. The host server is started with a dedicated test config (`configure_jupyter_server`) instead of the user's config; every test gets a `tmpPath`. Verified.
   Same source. Quote: "from jupyterlab.galata import configure_jupyter_server  configure_jupyter_server(c)" / "jupyter lab --config jupyter_server_test_config.py" / "test('Create New Notebook', async ({ page, tmpPath }) =>"
9. Videos and an HTML report land in `test-results` / `playwright-report`. Verified.
   Same source. Quote: "Test assets (including test videos) will be saved in a `test-results` folder and by default a HTML report will be created in `playwright-report` folder."
   Transfer: closest model for the Hermes dashboard/webui half (a browser-served UI): start a throwaway dashboard with a test config, drive it with Playwright Chromium headless, no Electron needed. Plausible.

### D. Grafana (@grafana/plugin-e2e)
10. The scaffolded plugin ships a docker compose dev server; the host version is picked with `GRAFANA_VERSION`. Verified.
    Source: https://grafana.com/developers/plugin-tools/set-up/set-up-docker and .../e2e-test-a-plugin/get-started (official docs)
    Quote: "Use `GRAFANA_VERSION` to set the Grafana version: GRAFANA_VERSION=10.0.0 npm run server"
11. CI runs a version matrix: compose up -> wait-for-grafana readiness action -> Playwright -> upload report artifacts with `if: always()`. Verified.
    Source: https://grafana.com/developers/plugin-tools/e2e-test-a-plugin/ci (official docs)
    Quote: "GRAFANA_VERSION=${{ matrix.GRAFANA_IMAGE.VERSION }} GRAFANA_IMAGE=${{ matrix.GRAFANA_IMAGE.NAME }} docker compose up -d - name: Wait for grafana server uses: grafana/plugin-actions/wait-for-grafana@main - name: Run Playwright tests" / "uses: grafana/plugin-actions/playwright-gh-pages/upload-report-artifacts@main if: ${{ (always() && !cancelled()) }}"
12. The matrix comes from the plugin's declared minimum host version (`grafanaDependency`), capped at 6 versions. Verified.
    Same source. Quote: "returns all the latest patch releases of Grafana Enterprise since the version specified as `grafanaDependency` in the `plugin.json` file. To prevent the initiation of too many jobs, the output is capped at 6 versions."
    Transfer: Hermes `requires_hermes` in plugin.yaml could drive the same kind of image-tag matrix. Plausible.
13. Grafana warns that reports can leak screenshots, traces and internal URLs. Verified.
    Same source. Quote: "Playwright reports can include screenshots, traces, HTML output, and internal URLs, so review the published content carefully". Transfer: keep artifacts in-cluster/private (there are tokens in Hermes traces). Plausible.
    This is the pattern closest to the user's staging idea: a disposable host container per run, a readiness gate, the driver, and artifacts. Here the "staging instance" lives only for the length of a job, not as a scaled-to-0 long-lived Deployment.

### E. Home Assistant custom components
14. pytest-homeassistant-custom-component pulls HA core's test fixtures (`hass`) into a pip package pinned to an HA version, so the integration loads into an in-process, throwaway HA instance. Verified.
    Source: https://github.com/MatthewFlamm/pytest-homeassistant-custom-component (README)
    Quote: "All pytest fixtures can be used as normal, like `hass`" / "`enable_custom_integrations` fixture is required (versions >=2021.6.0b0)"
15. HA declares integration deps in `manifest.json` `requirements`, and the `hassfest` validator checks every manifest (it's also on offer as a GitHub Action in home-assistant/actions). Verified (manifest + hassfest docs); the Action's existence is from the repo listing only.
    Source: https://developers.home-assistant.io/docs/creating_integration_manifest/ (official docs); https://github.com/home-assistant/actions (repo)
    Quote: "\"requirements\": [\"airgradient==0.10.0\"]" / "Hassfest, the validation script of core, checks every manifest."
    Transfer: equivalent to Hermes `python_dependencies` + `hermes plugins validate`. Note: an in-process fixture does NOT catch an undeclared dependency when the dev venv already has the package. Only a clean install does. Plausible (inference from mechanism).

### F. Electron in general
16. Electron officially points to WebdriverIO and Playwright `_electron.launch` for e2e, including window screenshots. Verified.
    Source: https://www.electronjs.org/docs/latest/tutorial/automated-testing (official docs)
    Quote: "Playwright launches your app in development mode through the `_electron.launch` API." / "await window.screenshot({ path: 'intro.png' })"
17. Playwright Electron supports v21+, can record video and has `artifactsDir`. Launch hangs if the `EnableNodeCliInspectArguments` fuse is off, which is a real risk for packaged apps. Verified.
    Source: https://playwright.dev/docs/api/class-electron (official docs)
    Quote: "Supported Electron versions are: v21+" / "If you are not able to launch Electron and it will end up in timeouts during launch ... Ensure that `nodeCliInspect` (FuseV1Options.EnableNodeCliInspectArguments) fuse is not set to `false`." / "If specified, artifacts (traces, videos, downloads, HAR files, etc.) are saved into this directory."
    Transfer: whether the packaged Hermes Desktop disables that fuse is not checked. If it does, fall back to the dev build (`--source`, CDP 9222) or to WDIO. Speculative until checked (Lane 2 owns this).

### G. Dependency-gap detection (the actual root-cause class here)
18. Hermes already ships the catalog-CI check: `hermes plugins validate <path> --install-deps` checks manifest, load, capabilities, and Python deps against core constraints. Verified.
    Source: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission (official Hermes docs)
    Quote: "hermes plugins validate /path/to/your-plugin --install-deps  It checks the manifest and `requires_hermes`, that the plugin loads, that the `capabilities` you declare match what it registers, `config_schema` and `requires_env`, Python dependencies against Hermes's core constraints, the install security scan, and the `desktop surface` and `no core override` rules."
19. `hermes plugins doctor` runs the real discovery/register path with a temporary HERMES_HOME, which is Hermes's own "disposable host instance". Verified.
    Source: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins (official Hermes docs)
    Quote: "`hermes plugins doctor [path-or-id]` runs the same discovery, manifest parser, `register(ctx)` and registries Hermes uses, with a temporary `HERMES_HOME`." / "list them under `python_dependencies` in `plugin.yaml`, or in a `pyproject.toml` next to it."
    Whether doctor/validate catch an undeclared import when the package happens to be present in the Hermes venv is not documented. Run them inside a clean image (the stock Hermes image, not the dev venv). Plausible.
20. deptry statically flags imports that aren't declared (DEP001), with no install needed. That makes it a cheap pre-gate. Verified.
    Source: https://deptry.com/ (official docs)
    Quote: "DEP001 'matplotlib' imported but missing from the dependency definitions". Hermes caveat: the plugin declares deps in plugin.yaml `python_dependencies`, which deptry doesn't read unless they're mirrored in pyproject.toml. Plausible.
21. `pip check` / `uv pip check` only verify consistency of what is installed, not undeclared imports. That makes them a complement, not a fix. Verified.
    Source: https://pip.pypa.io/en/stable/cli/pip_check/ ; https://docs.astral.sh/uv/pip/compatibility/ (official docs)
    Quote: "No broken requirements found." / "At present, `uv pip check` will surface the following diagnostics: A package has no METADATA file ... Requires-Python lower bound..."
22. Common community practice: a CI "fresh venv / wheel install, no source tree" smoke job that imports and starts the thing. Verified as practice (multiple independent issues/PRs).
    Source: https://github.com/janusson/PySharpe/issues/29 ; https://github.com/cognizant-ai-lab/neuro-san-studio/pull/1392 ; https://github.com/leonarduk/allotmint/issues/8144 (GitHub issues/PRs)
    Quote (titles): "Wheel-install smoke test in CI (fresh venv, no source tree)" / "Smoke test the packaged pip install in CI"

## Transferable patterns -> Hermes mapping
- Disposable host per run (VS Code, Obsidian, Grafana): a k8s Job/pod from the pinned hermes-suite image with an emptyDir HERMES_HOME, created and deleted per run. That's an alternative to a long-lived scaled-to-0 staging Deployment, with no RWO iSCSI conflict with live /opt/data. Plausible.
- Version pin/matrix (Grafana `grafanaDependency`): `requires_hermes` maps to image tags. Plausible.
- Isolated profile (`--user-data-dir`, sandboxed vault, Galata test config): a seeded fixture HERMES_HOME + test config.yaml with no real tokens. Plausible.
- Readiness gate (wait-for-grafana): poll the dashboard on 9119 / gateway health before driving it. Plausible.
- Headless display (xvfb-run -a + GTK/NSS libs): needed only for the Electron Desktop half. The dashboard/webui half can use headless Chromium with no X. Verified for the mechanism, Plausible for Hermes.
- Artifacts (Playwright traces/video/report, upload `if: always()`): keep them private, since they contain secrets. Verified (Grafana warning).
- Dependency gate order: deptry (static) -> `hermes plugins validate --install-deps` in the clean stock image -> `hermes plugins doctor` -> import/load smoke -> e2e. Plausible ordering (inference).

## Searched, found nothing / skipped
- "hermes plugins validate" behaviour on an undeclared import that's already present in the venv: official docs give no statement (Hermes docs). Source code not read (docs-first gate).
- Grafana set-up-docker page: no inline compose file text found by regex ("docker compose up", "provisioning"); the compose usage came from the CI page instead.
- hassfest GitHub Action page (marketplace): the extract came back as nav chrome only, so the Action's existence comes from the home-assistant/actions repo listing.
- Galata README: no "trace" keyword (traces come from Playwright defaults, not Galata docs).
- Reddit / Stack Overflow: skipped. Official docs answered every sub-question with Verified sources, and rate limiting applied.
- Not covered by this lane (owned by others): nixos-infra cluster layout (Lane 4), Hermes Desktop fuse/CDP specifics (Lane 2).
