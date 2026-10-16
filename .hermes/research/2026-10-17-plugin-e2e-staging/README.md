# Corpus: 2026-10-17-plugin-e2e-staging

Question: How can Hermes plugins (both the backend half and the Desktop half) be e2e-tested fully automatically without disturbing the live instance? This includes evaluating a staging instance scaled to 0.

| File | Axis / sub-question | One-line claim summary | Tier scheme | Status | C#/D# |
|---|---|---|---|---|---|
| REPORT.md | Synthesis | D (sandbox fast gate) + A (ephemeral k8s Job) recommended; B (replicas=0 staging) second; profile-in-live rejected | V/P/S + [live] | CURRENT | |
| hermes-tooling/lane1.md | Backend half: official Hermes tooling | validate/doctor are headless CI gates but skip dashboard/plugin_api.py and miss undeclared deps already in the venv; isolated `serve --port 0` + log grep catches plugin_api failures | V/P/S + [live] | CURRENT | |
| desktop-automation/lane2.md | Frontend half: Desktop GUI automation | Upstream ships Playwright `_electron` + xvfb harness with remote `hermes serve`; Electron 40 + Playwright run headless in the wrk pod (toy app) | V/P/S + [live] | CURRENT | |
| community-issues/lane3.md | Upstream issues/PRs + community | Undeclared plugin deps are a known upstream bug class; `--yes-deps` for headless install; Desktop GUI install with deps broken (#124784) | V/P/S | CURRENT | |
| staging-infra/lane4.md | Staging on k3s (nixos-infra) | Ephemeral Job on wrk with emptyDir HERMES_HOME fits best; Flux reconciles replicas; wrk RAM tight; F13/F20 PTY workaround superseded by `--yes-deps` (see REPORT) | V/P/S | CURRENT (F20a superseded) | |
| ci-practice/lane5.md | CI practice in other ecosystems | VS Code/Obsidian/Grafana/Galata/HA all test against a disposable, version-pinned host per run, never the user's live instance | V/P/S | CURRENT | |
