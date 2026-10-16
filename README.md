# hermes-spawn-session

A Hermes Agent plugin that brings **Spawn with Report** to Hermes Desktop:
spawn a new, visible top-level session from an active chat — with its own
model/effort selection — and have the spawned session report its result back
into the parent conversation.

This is the Hermes equivalent of the "nested sessions" feature in Claude
Desktop (announced 2026-10-14), where parallel tasks open in nested sessions
and report their results back to the main conversation.

## Status

Backend tool `spawn_session` (agent-initiated) plus the desktop half
(⌘K "Spawn session with report" and the confirmation card for agent
`own_initiative` proposals). Report-back, status cards and sidebar
presentation are follow-up cards.

## Install (Hermes Desktop)

1. Link or copy this repository to `~/.hermes/plugins/spawn-session/`
   (unified package: agent half, `dashboard/` backend, `desktop/plugin.js`).
2. Add `spawn-session` to `plugins.enabled` in `config.yaml` and restart the
   gateway (the REST backend mounts at startup).
3. In Desktop: Capabilities → Plugins → enable **Spawn session** (the desktop
   half ships opt-in per Hermes policy) — use **Rescan** if it is not listed.
4. ⌘K → **Spawn session with report**.

Checks without Desktop: `pytest` (Python half and REST routes) and
`node scripts/smoke_desktop_plugin.mjs` (desktop half loads, registers its
contributions, uses only allowed imports, no hardcoded colours).

- Research archive: [`.hermes/research/`](.hermes/research/)
- Kanban board: `hermes-spawn-session` (2-lane: `default` / `reviewer`)
- Workflow: card → worktree → branch → PR → reviewer merge

## Why

Long projects mix routine and complex tasks. Switching the model of an
existing chat is expensive (full prompt-cache loss + re-prefill) and awkward
(context-length mismatch). Spawning a fresh session with a pinned model —
and getting the result back — is the cost-safe pattern. The research archive
documents the cost mechanics, the verified upstream state of Hermes session
spawning, and the build options for this plugin.

## Key research findings (short form)

- Hermes has **no native agent tool** that creates a top-level session
  (verified against the tool registry, gateway RPC, and source).
- The gateway RPC `session.create` and the `api_server` HTTP endpoint exist
  but are not agent-exposed; a plugin tool can call them.
- The plugin API route `ctx.subagent_lifecycle.launch()` exists (subagents,
  not top-level sessions).
- **No existing plugin** in the official catalog, the awesome-hermes-agent
  directory, or the `hermes-plugin` GitHub topic implements session spawning
  with report-back (searched 2026-10-16).
- Upstream: issue #76221 (roadmap), PR #106423 (foundation), #94697
  (programmatic no-click spawning behind a flag), #53494 (spawned tasks
  invisible).

## License

MIT — see [LICENSE](LICENSE).
