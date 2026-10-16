# .hermes — Project Working Archive

Session research and working documents for this project. This directory is
committed to the repo so the research travels with the project.

Language note: research documents are kept in the language they were produced
in (German); project docs (README, spec, code) are in English.

## research/

### 2026-10-16-model-routing/

Deep research: how to mix expensive (Claude Opus) and cheap (local Qwen)
models in long Hermes projects **without switching the model of an existing
chat** (prefill cost + context-length mismatch).

- `REPORT-model-routing-de.md` — final report (38 cited sources)
- `lane1-hermes-docs.md` — official Hermes docs
- `lane2-github.md` — GitHub issues/PRs
- `lane3-source.md` — source-code verification
- `lane4-community.md` — community practice
- `lane5-cost-mechanics.md` — prompt-cache / prefill cost mechanics

Core answer: do not switch — spawn. Subagents with a pinned model
(`delegation.model`/`delegation.provider`), Kanban per-task model override,
or a fresh chat with a handover file.

### 2026-10-16-spawn-with-report/

Deep research: replicating Claude Desktop's "Spawn with Report" (nested
sessions) in Hermes Desktop — natively, via plugin, or via slash command.

- `REPORT-spawn-with-report-de.md` — final report (62 cited sources)
- `ledger.json` — citation ledger (62 sources, verified)
- `lane1-claude-feature.md` — identification of the Claude feature
- `lane2-hermes-native-session-spawning.md` — Hermes native mechanisms
- `lane3-github-issues-source.md` — GitHub/source verification
- `lane4-plugin-feasibility.md` — plugin build feasibility
- `lane5-community-practice.md` — community practice
- `claude-desktop-spawn-with-report-ui.png` — screenshot of the Claude
  Desktop "Spawn with Report" UI (the feature being replicated)

Core answer: no native equivalent (verified negative). Zero-build:
`delegate_task` + `sessions.show_subagents: true` + `/bg`. Build options:
plugin tool `spawn_session` (~80–150 lines), desktop plugin ⌘K (~100–250
lines, only path to a visible top-level tab), slash command `/spawn`
(~60–120 lines), api_server REST.

### 2026-10-16-plugin-existence-search-de.md

Search for an existing "spawn session with report" plugin (official catalog,
awesome-hermes-agent, 42-evey/hermes-plugins, GitHub topic `hermes-plugin`).
Result: none exists — the gap this project fills.
