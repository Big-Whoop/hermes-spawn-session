# Plugin-Existenz-Suche: "Spawn Session with Report" (2026-10-16)

Frage: Gibt es bereits ein Plugin, das in Hermes eine neue (sichtbare)
Top-Level-Session spawnt, deren Ergebnis in die Eltern-Session
zurückgemeldet wird (Äquivalent zu Claude Desktop "Spawn with Report")?

**Ergebnis: Nein. Kein solches Plugin existiert.**

## Durchsuchte Quellen

### 1. Offizieller Hermes-Katalog (manage_catalog)

Suchen: `spawn session`, `session`, `orchestrator`, `subagent delegation`.

- Kein Plugin, das Sessions spawnt.
- Einzige "spawn"-Treffer sind Community-**Skills** aus dem skills.sh-Registry:
  - `skills-sh/alirezarezvani/claude-skills/spawn`
  - `skills-sh/alannkl/skills/spawn-agent`
  - `skills-sh/anfreire/summon-cc/summon-cc`
  - `skills-sh/travisjneuman/.claude/agent-teams`
  - `skills-sh/davidondrej/skills/corral-launch-agents`
- Alle sind Claude-Code-orientiert (Pfad `.claude/` bzw. `claude-skills/`),
  keine Hermes-Session-Spawner.
- `orchestrator`-Treffer: `agent-batch` (Plugin), `pstack` (Plugin),
  diverse Orchestrator-Skills — keine Session-Spawner.

### 2. awesome-hermes-agent (0xNyk, 5.9k Stars)

Komplettes README gelesen (1316 Zeilen), alle Sektionen inkl. "Plugins" und
"Multi-Agent & Swarms". Kein Session-Spawner. Nächste Kandidaten:

| Projekt | Was es tut | Warum es nicht passt |
|---|---|---|
| **hermes-dynamic-workflows** (lingjiuu, 119 Stars, beta) | Claude-Code-artige Workflows: Modell schreibt Workflow-Skripte, orchestriert **Subagents** (`agent`/`parallel`/`pipeline`, bis 1000 Subagents, persistierbare Runs, Live-Dashboard) | Subagents, keine sichtbaren Top-Level-Sessions |
| **hermes-conductor** (forcewake, experimental) | Kanban-orchestrierter Multi-Harness-Coding-Swarm; Orchestrator routet und verifiziert, Worker brauchen auditierbare Evidenz | Kanban-basiert, Multi-Harness |
| **evey-bridge-plugin** (42-evey, beta) | Bridge zwischen Hermes und **Claude Code**: Kontext-Handoff zwischen den beiden Systemen | Cross-Agent, kein Session-Spawn |
| **hermes-delegation-gate** (kenpritchard, experimental) | Human-Approval vor `delegate_task`, Block-Modus für unattended Runs | Nur Gate, kein Spawner |
| **agentplane-hermes-plugin** (Basilisk Labs, beta) | Kanban-Assignees `agentplane-*` spawnen AgentPlane-Supervision | Externe Worker-Lane |
| **mission-control** (builderz-labs, 5.7k Stars) | Externes Dashboard für Agent-Flotten, Task-Dispatch, Kosten | Externes Dashboard, kein Hermes-Desktop-Plugin |
| **Hermes Studio** (EKKOLearnAI, 9.1k Stars) | Dashboard mit Multi-Agent-Group-Chat + @mention-Routing | Externes Dashboard |
| **Nora** (solomon2773, beta) | Self-hosted Control Plane für Hermes/OpenClaw-Flotten (Docker/K8s) | Externe Control Plane |
| **oh-my-hermes** (witt3rd, beta) | Multi-Agent-Orchestrierungs-Skills (deep-research, ralph, autopilot) auf Hermes-Primitiven | Skills auf `delegate_task`, kein Session-Spawn |
| **PolyBrain** (mosesman831, beta) | Multi-Agent/Multi-Model-Orchestrierung, pro Rolle anderes LLM | Subagents, kein Session-Spawn |
| **hermes-live-voice** (bielcarpi, beta) | Voice, während "durable Hermes runs" im Hintergrund laufen | Voice-Plugin, kein Spawner |
| **agent-heartbeat** (Love-AronaPlana, experimental) | Weckt Agent periodisch in derselben Gateway-Session | Gleiche Session, kein Spawn |

### 3. 42-evey/hermes-plugins (23 Plugins, beta)

- `evey-bridge` — Claude-Code-Bridge (Inbox/Outbox + MCP-Server)
- `evey-delegate-model` — Smart Model-Routing mit Task-Type-Erkennung, 3 Retries/Modell, 4-Modell-Fallback-Kette
- `evey-delegation-score` — Scoring von Delegation-Ergebnissen
- `evey-session-guard` — Session-Lifecycle-Management und Cleanup
- **Kein Session-Spawner.**

### 4. GitHub-Topic `hermes-plugin` (496 Repos)

Top-Repos geprüft (planning-with-files, ReMe, token-optimizer, babysitter,
digital-marketing-pro, scope-recall, signetai, remnic, minimalist-themes,
hermes-live-voice, hermes-speech, hermes-bot-kit, hermes-dynamic-workflows,
fish-audio-hermes, Aphrodite, hermes-bot-forge, hermes-plan-mode, yantrikdb,
hermes-quota-plugin, Aether-desktop-orchestrator): Memory-Provider, Themes,
Voice/TTS, Plan-Mode, Quotas — **nichts in die Richtung**.

## Bestätigung aus Upstream

- **PR #131283** (jonpol01, 02.10.2026, fixt #131282):
  `SubagentLifecycleService.launch` — der Plugin-Pfad
  `ctx.subagent_lifecycle.launch()` — erhielt Admission-Checks
  (pause/depth/oneshot-budget). Bestätigt: Plugins können **Subagents**
  starten. Aber Subagents ≠ sichtbare Top-Level-Sessions.
- Upstream-Lücke (aus dem Spawn-with-Report-Report): Issue #76221 (Roadmap),
  PR #106423 (Fundament), #94697 (programmatic no-click spawning hinter
  Flag), #53494 (spawned tasks invisible).

## Fazit

Die Lücke ist real — niemand hat "Spawn with Report" für Hermes gebaut.
Build-Optionen (aus REPORT-spawn-with-report-de.md):

1. **Plugin-Tool `spawn_session`** (~80–150 Zeilen): Gateway-RPC
   `session.create` + Cross-Session-Messaging für Report-back.
2. **Desktop-Plugin ⌘K** (~100–250 Zeilen): einziger Weg zu einem sichtbaren
   Top-Level-Tab im Hermes Desktop.
3. **Slash-Command `/spawn`** (~60–120 Zeilen).
4. **api_server-REST** (ohne Plugin).
