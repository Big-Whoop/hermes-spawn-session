# Research report: fully automated e2e testing of Hermes plugins without disturbing the live instance

Date: 2026-10-17 · Collector card t_6078e578 · Hermes under test v0.22.2 · Tiers: Verified (V) / Plausible (P) / Speculative (S); [live] = measured in the agent sandbox on 2026-10-17.
Corpus: lane files in this directory (see README.md). They carry the per-finding citations with verbatim quotes. This report cites only the primary sources it relies on directly.

## Best result (TL;DR)

Recommended: a two-stage gate. No long-lived staging instance.

1. Fast gate (Option D) in the agent sandbox, which the agent can run on its own:
   - pytest and the node smoke;
   - `hermes plugins doctor --ci`;
   - `hermes plugins validate --json`;
   - an isolated `HERMES_HOME=<tmp> hermes serve --port 0` with the plugin enabled. Assert that errors.log has no `Failed to load plugin` line and that a plugin route answers.
2. Full gate (Option A) as an ephemeral k8s Job on wrk. It uses the exact live image tag and an emptyDir HERMES_HOME, and does these steps:
   - install with `--yes-deps` into a fresh venv;
   - start `hermes serve`;
   - run the backend live checks;
   - drive Desktop with Playwright `_electron` under Xvfb against that backend;
   - write artifacts to /workspace.

   The Job does not exist between runs, which delivers "scaled to 0" without fighting Flux.

Your idea of a staging Deployment scaled to 0 (Option B) is feasible, but it ranks second. It persists state between runs, which hides exactly the missing-dependency class that started this research. Flux also reconciles `replicas`. Pick B only if you want to watch the GUI over noVNC, and then wipe HERMES_HOME on every start.

Why this ranking, each point with its tier:
- Live-safety. Nothing touches /opt/data or your packaged Desktop. The packaged Desktop has no CDP port (V, lane 2 F6). The live PV is single-writer SQLite (V, lane 4 F3). A staging profile inside the live container is not isolated: plugin dependencies are resolved over the union of all profiles (V docs[13], lane 1 F11). So the profile route is excluded.
- The motivating bug class is undeclared deps that pass in the dev venv and fail live. Validate and doctor import the plugin in the current venv, so a dependency that is already present there is not flagged (V [live], lane 1 F5). Upstream has the same bug class open (V[9]). Only a fresh environment built from the live image catches it. That is the Job.
- Consent. A headless install answers dependency consent with `install --yes-deps` (V[8]; [live]: flag present in v0.22.2 `plugins install --help`). The Desktop GUI install of a plugin with Python deps is broken upstream because the consent gate checks for a TTY (V[7]). The GUI e2e therefore tests the loaded plugin, not the GUI install flow.
- GUI. Upstream already uses this pattern: Playwright `_electron`, xvfb, `--disable-gpu --no-sandbox`, a sandbox HOME, a mock provider and a remote `hermes serve`[5][6]. Electron 40 and Playwright ran headless in the wrk pod without a GPU (V [live], lane 2 F23/F24, toy app only).

## Lane conflict resolved

Lane 4 (F13/F20, "Searched, found nothing") reported no non-interactive consent flag and proposed a PTY wrapper. Lanes 1 and 3 cite `--yes-deps`[2][8]. A live `hermes plugins install --help` on v0.22.2 shows `--yes-deps  Answer the Python dependency consent question yourself, so non-interactive installs (SSH automation, CI, Docker entrypoints) finish in one run`. The PTY workaround is therefore unnecessary. Lane 4 F20(a) is superseded. Lane 4 had searched only the docs page and `validate --help`.

## Options matrix

### Option A: ephemeral k8s Job `hermes-plugin-e2e` (RECOMMENDED as the full gate)
- Mechanism:
  - Own namespace `hermes-staging` with its own Flux Kustomization. Never suspend `apps`, because that would freeze live (V, lane 4 F7).
  - A suspended CronJob serves as the template. Peter runs `kubectl create job --from=cronjob/...`.
  - `ttlSecondsAfterFinished` cleans up finished runs[11].
  - The pod uses the live image tag from Nexus, so no pull secret is needed (V, lane 4 F11).
  - HERMES_HOME is an emptyDir. /workspace is mounted read-only through a second hostPath PV (P).
- Prerequisites:
  - Peter applies the manifests. The agent has no kubectl (V).
  - LLM access through an ESO secret pointing at CPA, or a mock provider. A mock provider needs no secret, which is preferable.
  - RAM headroom on wrk. Live has limit 6Gi and the comment says "wrk has 6 GB until probe retires" (V, lane 4 F10). Fitting Desktop + Xvfb + backend at roughly 1.5–3 GB is S.
  - A Hermes Desktop build. It is not in the runtime image (V [live], lane 2 F29). The Job must clone hermes-agent at v0.22.2 and `npm ci && npm run build`, or use a prebuilt test image.
- Key steps:
  1. Run `validate --install-deps --json` in the fresh venv.
  2. Run `plugins install <git-url> --ref <sha> --enable --yes-deps`. There is no documented local-path install, so the alternative is to copy into `plugins/` and run `enable` (P, lane 1 F13).
  3. Start `hermes serve`. Keep the s6 ENTRYPOINT and use only `args:`, never `command:` (V, lane 4 F12).
  4. Assert: no `Failed to load plugin` line, and the plugin routes answer[3].
  5. Run `scripts/live_test.py` against it.
  6. Run Xvfb with `Xvfb :99` directly. `xauth` is missing for `xvfb-run` (V [live]).
  7. Launch Playwright `_electron` with `HERMES_DESKTOP_REMOTE_URL`/`_TOKEN`[5]. Run specs serially, because parallel Electron+backend stacks are flaky upstream[14].
  8. Write JUnit, screenshots and traces to `/workspace/.../e2e-runs/<ts>/`. Keep them private: traces can contain tokens (V, lane 5 #13).
- Confidence per part:
  - Storage, scheduling, image, Flux and TTL: V.
  - `--yes-deps` headless: V.
  - Electron in the pod: V for a toy app, P for Hermes Desktop.
  - Auto-enabling the opt-in desktop half without UI clicks: S.
  - `HERMES_DESKTOP_REMOTE_TOKEN` in v0.22.2: P (documented only in main-branch test docs).
- Verification status: the pieces are documented or measured live. The whole chain is untested.
- Trade-offs:
  - Gains: no idle footprint, a fresh state per run (catches undeclared deps), no Flux replica fights.
  - Costs: no interactive debugging unless you add noVNC, a slow cold start, and a manual trigger by Peter.

### Option B: staging Deployment, replicas=0 (your idea)
- Mechanism:
  - A copy of the hermes-suite manifests with its own PV directory, no Telegram token, and a Basic Auth secret.
  - An HTTPRoute `hermes-staging.homelab.fahsel.ch` (V: the gateway listener allows labelled namespaces).
  - An optional x11vnc/noVNC sidecar.
  - So that the scale sticks, either omit `replicas` (P) or set the annotation `kustomize.toolkit.fluxcd.io/reconcile: disabled`[10]. Without that, Flux reverts `kubectl scale` (V, lane 4 F5).
- Prerequisites: the same as A, plus a persistent PV and a route.
- Key steps: scale to 1, then install with `--yes-deps` and restart the backend, because routes mount only at startup[3]. Drive the GUI, then scale to 0.
- Confidence: P overall. Wipe-on-start is P.
- Verification status: inferred from repo and docs.
- Trade-offs:
  - Gains: you can watch or drive the GUI, and multi-step debugging works.
  - Costs: state drift hides dependency bugs, there are more objects to keep in sync with live, and it adds RAM pressure on wrk when it runs alongside live.

### Option C: NixOS VM test (`runNixOSTest`) on bld
- Mechanism: a QEMU VM with the test driver, screenshot and OCR (V, NixOS manual, lane 4 F29). Hermes would run in podman inside the VM.
- Prerequisites: KVM on bld, and Hermes packaged for the VM. Nothing exists yet; tests/ has only bash QEMU scripts (V, lane 4 F17).
- Confidence: P. Trade-off: the strongest isolation, but the highest effort. It is overkill for plugin tests.

### Option D: in-sandbox isolated run (RECOMMENDED as the fast gate)
- Mechanism: a scratch HERMES_HOME for doctor, validate and `serve --port 0`. `serve --port 0` announces `HERMES_BACKEND_READY port=<n>`[4] (V [live]). Xvfb is present in the image.
- Prerequisites: none new. Never run `--install-deps` there, because it installs "into this venv", which is the live container's venv (V, lane 1 F4).
- Confidence: V [live] for doctor, validate and serve with the route and log assertion.
- Limits:
  - It does not catch undeclared deps already present in the Hermes venv (V [live]). deptry is a cheap static pre-gate for that (P, lane 5 #20).
  - It shares the OS and volume with live.
  - It has no Desktop build, so the GUI half needs a hermes-agent checkout (V, lane 2 F29).
- Trade-offs: agent-runnable, per-commit, seconds to minutes.

### Option E: Desktop render tests only (contract and jsdom)
- Mechanism: the existing node stub smoke, or upstream's vitest jsdom project with the real SDK alias (V config, P for our plugin, lane 2 F25). `@hermes/plugin-sdk` is not on npm (V [live]).
- Trade-off: catches SDK API drift cheaply. It does not exercise the Electron loader or the backend. It complements A; it does not replace A.

### Option F: KEDA HTTP scale-to-zero (rejected)
- KEDA is not installed (V, grep). The workload is batch, not HTTP-triggered, and the cold start is about 10 min (P). The effort is disproportionate.

### Option G: native "no", i.e. a staging profile or second gateway inside the live container (rejected)
- Profiles share one dependency environment[13]. Running the same plugin in several profiles breaks uv workspace resolution (V, lane 3 #32). Shared bot tokens are lock-raced (V, lane 3 #31). This option disturbs live by construction.

### Option H: WebdriverIO or connectOverCDP instead of Playwright `_electron` (not recommended)
- Both work (V capability). They diverge from upstream's harness. CDP attach has lower fidelity and needs a dev-server build (V, lane 2 F19/F22).

## Ranking
1. D + A: a fast agent gate plus a full cluster gate.
2. B with wipe-on-start, only if watching the GUI matters.
3. C: host-level regressions only.
4. E: as a supplement.
5. F, G, H: rejected.

## Gate order (P, derived from lanes 1/5)
1. pytest and node smoke
2. deptry
3. doctor --ci
4. validate --json, in the sandbox (D)
5. isolated serve: route probe and log grep (D)
6. Job: validate --install-deps in a fresh image, install --yes-deps, serve, live checks, serial Playwright Desktop specs (A)
7. live, after the user merges and restarts

## Side findings that need action (V [live], lane 1 F2)
- spawn-session HEAD fails `validate` today:
  - `provides_tools` and `provides_hooks` are not declared;
  - the security scan flags `.hermes/research/**/*.md` files shipped inside the plugin tree.

  A CI gate stays red until these are fixed. Candidate follow-up card.
- Skill `hermes-desktop-plugins` says "the agent cannot click through Desktop". That holds only for the packaged app; it is outdated for isolated source builds. This is a skill update candidate (P, lane 2 F27).
- KB page `concepts/nixos-infra-naming` has a stale wrk RAM figure. The repo says 6 GB (lane 4 F10).

## Untested on the exact target (v0.22.2, wrk)
- The Hermes Desktop v0.22.2 build launched by Playwright. Only a toy Electron was driven. Unknown: whether the `nodeCliInspect` fuse matters for the source build.
- Seeding the "enabled" state of the opt-in desktop half without UI clicks (S).
- Whether `HERMES_DESKTOP_REMOTE_TOKEN` exists in v0.22.2 (the docs read were main).
- `install --yes-deps` end to end in a fresh container of the live tag. The flag is present, but the full run was not executed.
- RAM headroom on wrk for the Job next to live.
- Whether the suite image can run the test flow as s6 `args:` inside a Job.

Detailed citations: lane files hermes-tooling/lane1.md, desktop-automation/lane2.md, community-issues/lane3.md, staging-infra/lane4.md, ci-practice/lane5.md.

## Sources

[2] https://hermes-agent.nousresearch.com/docs/developer-guide/plugins
[3] https://hermes-agent.nousresearch.com/docs/user-guide/features/extending-the-dashboard
[4] https://hermes-agent.nousresearch.com/docs/reference/cli-commands
[5] https://github.com/NousResearch/hermes-agent/blob/main/apps/desktop/e2e/fixtures.ts
[6] https://github.com/NousResearch/hermes-agent/blob/main/.github/workflows/e2e-desktop.yml
[7] https://github.com/NousResearch/hermes-agent/issues/124784
[8] https://github.com/NousResearch/hermes-agent/issues/122134
[9] https://github.com/NousResearch/hermes-agent/issues/134469
[10] https://fluxcd.io/flux/components/kustomize/kustomizations
[11] https://kubernetes.io/docs/concepts/workloads/controllers/ttlafterfinished
[13] https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins
[14] https://github.com/NousResearch/hermes-agent/pull/101149
