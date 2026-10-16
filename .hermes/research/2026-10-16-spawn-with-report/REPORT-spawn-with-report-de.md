# „Spawn with Report" in Hermes Desktop — Deep-Research-Report

**Datum:** 2026-10-16 · **Methode:** 5 parallele Research-Lanes (Claude-Feature-Identifikation, Hermes-Offiziell-Docs, GitHub/Quellcode-Verifikation, Plugin-Feasibility, Community/Praxis) · **Quellen:** 62 registriert (57 Web + 5 Quellcode-Dateien) · **Lane-Dateien:** siehe §7

## TL;DR

1. **Das Claude-Feature heißt „nested sessions"** (öffentlicher Name aus der Ankündigung vom 14.10.2026; in den Docs: „task chip"). Der Agent in Session A ruft den app-internen MCP-Server `ccd_session` auf (`spawn_task` = Chip mit title/prompt/tldr; `start_session` = klicklos, serverseitig gated) und erzeugt eine **vollständig unabhängige, sichtbare Session** mit `parentSessionId`-Link und eigenem Git-Worktree; pro Spawn ist Modell/Effort wählbar. Report-back ist offiziell angekündigt, aber in der Community als Lücke im Chip-Flow dokumentiert (§1.4).
2. **Hermes hat kein natives Äquivalent** — verifiziert negativ: Kein eingebautes Agent-Tool erstellt eine Session (44-Tool-Registry gescannt), keine Desktop-UI für „neue Session mit Prompt" oder Fork. Aber die komplette Plumbing existiert in drei Schichten (Gateway-RPC `session.create`, api_server-HTTP, `/bg`) — nur dem Agenten nicht ausgesetzt (§2).
3. **Nächste Zero-Build-Optionen:** `delegate_task` (agent-initiiert, goal+context, automatischer Report-back, Subagents-Frame) + Profil-Config `sessions.show_subagents: true` (Subagent-Sessions erscheinen dann in der Session-Liste); `/bg` (user-initiiert, Ergebnis in denselben Chat); Kanban (durable, `notify+wake`-Report-back) (§2.3, §5).
4. **Build-Optionen:** (A) Plugin-Tool `spawn_session` auf der Subagent Lifecycle API (~80–150 Zeilen, agent-initiiert, pro-Spawn-Modell, Report-back; Kind = Subagent, kein Top-Level-Tab); (B) Desktop-Plugin ⌘K (~100–250 Zeilen, **einziger Weg zu einem sichtbaren Top-Level-Session-Tab**); (C) Slash-Command `/spawn` (~60–120 Zeilen); (D) api_server-REST (manuell/scripted, ohne Plugin) (§3).
5. **Empfehlung:** gestuft — Phase 0 Zero-Builder heute, Phase 1 Plugin-Tool wenn agent-initiiertes Spawn mit pro-Spawn-Modell gewünscht ist, Phase 2 Desktop-Plugin wenn ein sichtbarer Tab ein Hard Requirement ist (§5).

## 1. Das Claude-Feature: „nested sessions"

### 1.1 Identifikation

- **Ankündigung:** ClaudeDevs-X-Thread vom 14.10.2026 (Desktop-App-Update) [15]; Anthropic-Mitarbeiter Wes Roth: „Parallel tasks open in nested sessions and report their results back to the main conversation" [14]. Die X-Posts waren nicht direkt lesbar (blocked); die Wortwahl ist durch zwei unabhängige Sekundärquellen korroboriert [16][17].
- **Offizielle Docs:** Der Mechanismus ist als „task chip" unter „Work across sessions" auf der Desktop-Seite dokumentiert: „When it notices something worth fixing that's out of scope for the current task, it offers the work as a task chip in the chat. Click the chip to start that work in a new session with its own worktree" [1] (deutsche Docs: „Task-Chip") [2]. Eine dedizierte „nested sessions"-Docs-Seite existiert noch nicht; das CLI-Changelog enthält keine Spawn-Einträge (Desktop-App-Feature) [6].
- **Zugrundeliegende Tools:** App-interner MCP-Server `ccd_session` mit `mcp__ccd_session__spawn_task` (Chip: `title`, `prompt`, `tldr`) [9] und `mcp__ccd_session__start_session` (klicklos; Parameter `prompt`, `model`, `effort`, `cwd`/worktree, `permission_mode`; Initiation `user_asked` = sofort starten, `own_initiative` = nur Vorschlag) [7]; Management-Server `ccd_session_mgmt` (`get_session` → `parentSessionId`, `list_sessions` → `linked`-Familie) [8]. Interner Feature-Gate-Name: „side sessions" [7].
- **Trigger:** Agent-initiiert ist der Kernmodus — Claude markiert proaktiv out-of-scope Work als „Suggested task"-Chip [10]; der User kann es auch per Plain Language anstoßen [1].
- **Abgrenzung:** Subagents sind ephemeral, in-process, „results return to the caller", ohne Sidebar-Präsenz [3][4]; Agent Teams sind CLI-only, experimentell, explizit „not in Desktop" [1][3]. Nested Sessions sind gewöhnliche Desktop-Sessions, die per Tool-Call einer anderen Session entstehen — mit Parent-Link und Report-back-Vertrag [1][8].

### 1.2 Screenshot-Mapping

| Screenshot-Element (DE) | Feature-Element |
|---|---|
| „Report the Nomad jobs in the services section" (Sidebar) | `title`-Payload → Session-Titel [9] |
| „Von Claude gestartet aus Sitzung ohne Titel" | `parentSessionId`-Link, Parent-Titel wird angezeigt [8] |
| Abschnitt „Aufgabe" | `prompt` (detaillierte Arbeitsanweisung) [9] |
| Abschnitt „Kontext" (eingeklappt) | `tldr`/Context-Payload [9] |
| „Dieser Computer · Pius" | lokale Umgebung (Maschinenname) [16] |
| „Als Umgebung speichern" | Saved Environments (gleiche Update-Welle vom 14.10.) [15][16] |

(Feld-Mapping ist Inferenz aus Payload-Struktur + beobachteter UI; die exakten Feldnamen der App sind nicht veröffentlicht.)

### 1.3 Ausführung, Modell, Verfügbarkeit

- **Ausführung:** Vollständige unabhängige Session mit eigener Historie/Kontext/Umgebung, verlinkt via `parentSessionId`, standardmäßig eigener Git-Worktree (Chips spawnen immer vom Default-Branch des Repos) [1][9]; in der Sidebar unter dem Parent genistet [18]; Kind-Prozesse tragen den `CLAUDE_CODE_CHILD_SESSION`-Env-Marker [13].
- **Modell:** Pro Spawn Modell/Effort wählbar; ein Modell oder Effort über dem des Aufrufers fragt den User zuerst [7]. Bekannter Bug: Chip-gespawned Sessions starten immer mit medium effort [12].
- **Verfügbarkeit:** Nur Desktop-App (Code-Tab), Pro/Max/Team/Enterprise, macOS/Windows/Linux-Beta [1][16]; kein dokumentierter Concurrency-Cap [16][18].
- **Gates:** Serverseitiger Feature-Gate „side sessions" — `start_session`/`hand_off_to_session` waren vom 8.–14.10. für manche User verfügbar und wurden am **15.10. serverseitig zurückgezogen** [7]; unattended (scheduled) Sessions dürfen keine Sessions starten [7]; Kill-Switch für Chips: `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` [11].

### 1.4 Report-back: Widerspruch (Ankündigung vs. Community)

- **Ankündigungs-Lesart:** „report their results back to the main conversation" [14]; „Each child session works independently and, once done, reports its result back to the main session" [16][17].
- **Community-Lesart (First-Party-Repo):** Im Chip-Flow hat die Parent-Session nach dem Klick keine Sichtbarkeit — „The planning session has no idea what happened to the tasks it suggested"; Report-back (finale Zusammenfassung des Kindes wird als Tool-Result/Message an den Parent geliefert) ist eine explizite offene Request, verwandte Requests #80478/#71773 stale-closed [19]; klickloses `start_session` wird gefordert, ist aber nicht allgemein exponiert [20]; eine nachvollzogene Chip-Repro zeigt `list_sessions` mit `linked: true` → „No other sessions found" [21].
- **Bewertung:** Beide Lesarten sind dokumentiert. Die Ankündigungs-Wortwahl kommt via Sekundärzitat (X nicht direkt lesbar); die Issues sind user-filed im offiziellen Repo mit Repros. Ob der neue nested-sessions-Flow vom 14.10. (im Gegensatz zum älteren Chip-Flow) die Report-back-Lücke schließt, ist nicht dokumentiert — Report-back als angekündigt, aber nicht verifizierbar behandeln. Als wahrscheinlicher Kanal dient die dokumentierte Cross-Session-Messaging-Oberfläche (Messages zwischen Sessions, Delivery als Karte/turn) [5].

## 2. Hermes nativ: Was existiert, was nicht

### 2.1 Verifizierte Negativ-Ergebnisse

- **Kein eingebautes Agent-Tool erstellt eine Session.** Die Core-Tool-Registry (44 Tools) wurde gescannt; die einzige Spawn-Oberfläche des Agenten ist `delegate_task` (Subagent) [62]. Die plugin-facing Spawn-Oberfläche ist `ctx.subagent_lifecycle.launch` — Subagent, keine allgemeine Session [29][62].
- **Keine Desktop-UI** für „neue Session mit Initial-Prompt", „fork session" oder „spawn from this session" (Volltextsuche der Desktop-Docs) [22]. Neue Sessions nur via Cmd/Ctrl+T/N (ohne Prompt) [22]. Fork existiert nur auf Gateway-Ebene: `session.branch`-RPC, `POST /api/sessions/{id}/fork`, CLI `/branch` [32][33].
- **Subagent-Sessions sind standardmäßig aus der Session-Picker-Liste ausgeblendet** (`_delegate_from`-Marker bei Erstellung) [60] — die Profil-Config `sessions.show_subagents` nimmt sie in die Session-Liste wieder auf [59].

### 2.2 Mechanismen-Übersicht

| Mechanismus | Agent-initiiert | Neue Session | Sichtbar in Session-Liste | Task+Context | Report-back an A |
|---|---|---|---|---|---|
| `delegate_task` / async_delegation | ✅ Model-Tool | ✅ (source `subagent`) | ❌ Subagents-Frame; ✅ mit `sessions.show_subagents` | ✅ goal+context | ✅ Ergebnis re-enters A als Message [26][59][60] |
| `/bg` | ❌ User-Command | ✅ (`bg_*`) | ❌ eigener Task-ID | ❌ nur Prompt | ✅ gleicher Chat/Terminal [24][25][35] |
| Kanban-Karte | ✅ `kanban_create` oder User | ✅ Worker pro Karte (source `kanban`) | ❌ hidden (Board-UI) | ✅ Card-Body + Parent-Link | ✅ `notify+wake`-Synthetic-Turn [27] |
| Bot Mode `message_agent`/@mention | ✅ Tool oder User | ❌ bestehende Bot Chats | ❌ hidden | ✅ Message | ✅ Reply attributed [28] |
| api_server Sessions API | ❌ externes HTTP | ✅ (source `api_server`) | ✅ Dashboard/History | ✅ via `/chat`-Turn | n/a (Poll/SSE) [32] |
| Gateway-RPC `session.create` | ❌ externer Client | ✅ | ✅ (oder `hidden`) | ✅ Seed-Messages | n/a (Events) [33][58] |
| Compression-Split | ❌ intern | ✅ Continuation | ✅ nummerierter Titel | Summary | n/a [23] |

### 2.3 Kern-Findings

- **`session.create` (tui_gateway JSON-RPC):** Parameter umfassen Seed-`messages`, `model`/`provider`/`reasoning_effort`, `cwd`, `title`, `parent_session_id`, `hidden`, `idempotency_key` [58]. Aufrufbar von jedem authentifizierten Gateway-Client (Desktop-WS mit Token, TUI-stdio, Remote-Desktop) und vom Server selbst (hosted rooms) — **aber von keinem Agent-Tool** [58].
- **`/bg`:** Implementiert auf drei Surfaces — CLI, Messaging-Gateway, Desktop/TUI (via `prompt.background`-RPC, Ergebnis als `background.complete`-Event auf der Parent-Session) [45][46]. Der Desktop-Delivery-Bug (Ergebnis in falschem Dialog) wurde am 26.09.2026 per PR #122859 gefixt [45][46]. Jedes `/bg` ist one-shot amnesisch (keine Historie, kein Reply-Kanal; offenes Issue #123607) [47]; Continuation ist eine offene Request (#22191) [48].
- **async_delegation (Juni 2026):** Ergänzend zu synchronem `delegate_task` liefert das `async_delegation`-Toolset sofort eine `task_id` und sechs Lifecycle-Tools (spawn/check/steer/collect/cancel/list); es ist aber single-session-only und nicht durable über Restarts [55][56].
- **Kanban:** Jede Karte = voller OS-Prozess mit eigenem Profil/Modell, echte (versteckte) Session mit Kartennamen als Titel; Completion meldet sich via `notify+wake` zurück — eine synthetische Inbound-Message, die den ursprunglichen Agenten zu einem echten Turn mit der Worker-Zusammenfassung bringt [27].
- **api_server (in diesem Setup aktiv):** `POST /api/sessions` (create, title, model/provider), `POST /api/sessions/{id}/chat[/stream]` (sync Turn), `POST /api/sessions/{id}/fork` (destruktiver Fork), `POST /v1/runs` (one-shot + SSE) — alles hinter `API_SERVER_KEY` [32][61]. **Grenze:** API-Sessions können sich nicht an Sessions binden, die andere Surfaces besitzen (HTTP 409) — A's eigenes Transcript lässt sich so nicht steuern [32].
- **Subagent Lifecycle API (öffentliche Plugin-API):** `launch(SubagentLaunchRequest(goal, context, model, provider, allowed_toolsets, working_directory, parent_session_id, timeout_seconds))` + `wait`/`result`/`steer`/`cancel`; gleicher Host-Pfad wie `delegate_task`; Terminal-Result ≤32k Zeichen; in-process 1h; fail-closed außerhalb eines aktiven Agent-Turns [29][62].

## 3. Build-Optionen für „Spawn with Report" in Hermes

Alle Optionen funktionieren mit **null Core-Edits** (Maintainer-endorsed Muster: A2A-Plugin, merged 2026-08-02, „zero core edits") [42].

### Option A — Plugin-Tool `spawn_session` (Subagent Lifecycle API)

- **Mechanik:** `ctx.register_tool("spawn_session", …)`; Handler ruft `ctx.subagent_lifecycle.launch(SubagentLaunchRequest(goal, context, model, provider, allowed_toolsets, working_directory))` auf, dann `wait`/`result` (oder liefert Handle zurück; Completion re-enters A als Background-Message) [29][36][38].
- **Eigenschaften:** Agent-initiiert (Modell ruft das Tool auf); **pro-Spawn-Modell-Override** (das `model`-Feld der Request überschreibt die `delegation`-Config) [29]; Report-back automatisch (Result ≤32k Zeichen) [29]; funktioniert in CLI/Gateway/Kanban-Worker [29].
- **Limits:** Kind ist ein Subagent — sichtbar im Subagents-Frame, in der Sidebar nur mit `sessions.show_subagents` [29][59]; fail-closed außerhalb aktiver Turns; Result nicht durable über Process-Restarts [29].
- **Aufwand:** ~80–150 Zeilen Python [Lane 4].
- **Präzedenz:** A2A-Plugin #77109 (merged) [42]; #8948 (sessions_spawn-Request) wurde zugunsten des Plugin-Ansatzes geschlossen [41]; #133212 requestet subagent_lifecycle v1.1 (steer, effort/route) [50].
- **Bekannter Bug:** `launch` umgeht derzeit Delegation-Safety-Checks (pause, max_spawn_depth, child budget) — offen #131282 [51].

### Option B — Desktop-Plugin ⌘K „Spawn with Report"

- **Mechanik:** Palette-Command (⌘K) oder Button; Spawn via `host.newChat()` + `host.composer.submit('new', prompt)` — „Send as if the user typed + pressed Enter" [34]. B überwachen via `host.state.busyBySession` / `host.onEvent('message.complete')`; Report-back via `host.composer.insertText(A, result)` oder Toast; agent-level Report-back via optionalem `plugin_api.py`-Backend (läuft im Gateway-Prozess, kann hermes-internals importieren) [34][40].
- **Eigenschaften:** **Einziger Weg zu einem echten sichtbaren Top-Level-Session-Tab** (wird über den eigenen New-Chat-Pfad der App erstellt) [34]; user-initiiert (⌘K/Button) — Agent-Initiation erfordert Kombination mit Option A.
- **Limits:** Nicht sandboxed (volle App-Autorität) [34]; Desktop-Hälfte opt-in [34]; kein Build-Step (einzelne ESM-Datei) [34].
- **Aufwand:** ~100–250 Zeilen JS (+50–150 Zeilen Python bei Backend) [Lane 4].
- **Präzedenz:** Bundled-Kanban-Desktop-Plugin (Sidebar-Page + REST-Router) [39][40].

### Option C — Slash-Command `/spawn <task>`

- **Mechanik:** `ctx.register_command("spawn", handler)`; Handler ruft `ctx.dispatch_tool("delegate_task", {"goal": …, "context": …})` auf (dokumentiertes Verbatim-Beispiel-Muster) [36]. Alternative: `ctx.inject_message(origin=…)` → neue Gateway-Session in einem Chat mit frischem Prompt, Reply wird an diesen Chat geliefert (Session lebt im Profil des Plugins) [37].
- **Eigenschaften:** User-initiiert, funktioniert in CLI + Gateway (Telegram etc.) [36]; Report-back via delegate_task-Completion (re-enters A) oder an den Ziel-Chat [36][37].
- **Aufwand:** ~60–120 Zeilen Python [Lane 4].

### Option D — api_server-REST (ohne Plugin)

- **Mechanik:** `POST /api/sessions` (title, model/provider) → `POST /api/sessions/{id}/chat` (sync Turn) oder `POST /v1/runs` + `GET /v1/runs/{id}` / `/events` (async) [32].
- **Eigenschaften:** Session ist echt und sichtbar (source `api_server`; Dashboard/Session-History) [32]; pro-Spawn-Modell via Create-Parameter [32][61]; Report-back via Polling (Skript oder kleines Plugin-Backend).
- **Limits:** 409-Grenze — kann A's eigenes Transcript nicht steuern [32]; externer Client, nicht der Agent.
- **Aufwand:** null Code (curl) bis kleines Skript.

**Weitere, verworfene Pfade:** Webhooks (POST → one-shot-Agent-Run → Delivery an Channel; schwerster Pfad, Ergebnis landet am Delivery-Target statt in A's Transcript) [30]; Cron-One-Shot-Jobs (frische Session pro Run, Delivery an Origin-Chat; Run-Session ist kein sichtbarer Desktop-Tab) [31].

### Vergleich

| Dimension | A: Plugin-Tool | B: Desktop-Plugin | C: Slash-Command | D: api_server |
|---|---|---|---|---|
| Initiation | Agent (Model-Tool) | User (⌘K/Button) | User (Command) | extern (HTTP) |
| Session B sichtbar | Subagents-Frame (+`show_subagents`) | **Top-Level-Tab** | Subagents-Frame / Chat-Session | ✅ (api_server) |
| Task+Context | ✅ | ✅ (Prompt-Text) | ✅ | ✅ |
| Pro-Spawn-Modell | ✅ | ✅ (Composer) | ✅ (delegation-Config) | ✅ |
| Report-back an A | ✅ automatisch (≤32k) | Plugin überwacht + injiziert | ✅ (delegate_task) | Poll/SSE |
| Persistenz | ❌ (in-process 1h) | ✅ (echte Session) | ❌/✅ (je nach Variante) | ✅ (echte Session) |
| Aufwand | ~80–150 Zeilen | ~100–250 Zeilen | ~60–120 Zeilen | 0–50 Zeilen |
| Core-Edits | keine | keine | keine | keine |

## 4. Upstream-Status (was in der Pipeline ist)

- **#76221** „Multi-Session Collaboration" Roadmap (open, needs-decision): `session.send`-RPC + `session.create_role` (persistente Role-Session mit Persona/Memory/Modell); User-Votes für Path B; keine PRs angehängt [44].
- **PR #106423** (open, teknium1): `peer_sessions`/`peer_send`-Tools — Cross-Session-Messaging (Mailbox, Mid-Turn-Delivery), kein Spawning [43].
- **#125346** (open): Create-time-Plugin-Hook (per-Project-Default-Modell auf `session.create`) [49].
- **#133212** (open): subagent_lifecycle v1.1 (steer, effort/route/follow-up) [50].
- **#22191** (open): `/bg`-Continuation (Reply auf Ergebnis → dieselbe Background-Session fortsetzen) [48].
- **#25176** (closed via A2A-Plugin): A2A-Messaging-Request [52].
- **Kein offenes Issue/PR implementiert das exakte Claude-Desktop-Analog** (agent-gespawned sichtbare Session mit Report-back) — die Lücke ist unbesetzt [Lane 3].

## 5. Empfehlung (gestufter Plan)

**Phase 0 — heute, Zero-Build:**
1. `sessions.show_subagents: true` in der Profil-Config → `delegate_task`-Kinder werden in der Session-Liste sichtbar (nächster Zero-Code-Ansatz am Claude-Feeling) [59].
2. `delegate_task` weiter für agent-initiiertes Spawn nutzen (Report-back automatisch) [26]; `/bg` für user-initiierte Seitenaufgaben (auf Desktop seit #122859 funktionsfähig) [45][46]; Kanban für durable Work mit `notify+wake`-Report-back [27].

**Phase 1 — wenn agent-initiiertes Spawn mit pro-Spawn-Modell gewünscht ist:**
3. Option A: Plugin-Tool `spawn_session` auf `ctx.subagent_lifecycle` (~80–150 Zeilen, null Core-Edits). Pro-Spawn-Modell (z. B. lokales Qwen für Bulk-Work, Opus für harte Tasks) + Report-back ≤32k Zeichen [29]. #131282 (Safety-Check-Bug) beobachten [51].

**Phase 2 — wenn ein sichtbarer Top-Level-Tab ein Hard Requirement ist:**
4. Option B: Desktop-Plugin ⌘K „Spawn with Report" (~100–250 Zeilen ESM) [34]. Optional kombiniert mit Option A (Agent ruft das Tool; Plugin liefert den sichtbaren Tab + Report-back).

**Entscheidungskriterien:**
- Sichtbarkeit: Subagents-Frame (A/C) vs. Sidebar-Row (`show_subagents`) vs. Top-Level-Tab (B/D).
- Persistenz: ephemeral (A/C) vs. echte Session (B/D) vs. Kanban (durable).
- Modell: pro-Spawn in allen Optionen möglich.
- Aufwand: D < C < A < B.

## 6. Widersprüche, Caveats, offene Fragen

1. **Claude Report-back:** Ankündigung [14][16][17] vs. First-Party-Issues [19][20] — siehe §1.4. Gewichtung: Die Issues tragen Repros; die Ankündigung ist ein Sekundärzitat.
2. **Claude-Feature in Fluss:** `start_session` am 15.10. serverseitig zurückgezogen [7]; noch keine dedizierte Docs-Seite [6].
3. **Hermes #131282:** `subagent_lifecycle.launch` umgeht Delegation-Safety-Checks (offen) [51] — relevant für Option A.
4. **api_server-409-Grenze:** Kann Sessions anderer Surfaces nicht steuern [32].
5. **Desktop-Plugins sind nicht sandboxed** [34].
6. **Kein dokumentierter Concurrency-Cap** für Claude-gespawned Sessions [16][18]; bei Hermes: kein dokumentierter `/bg`-Cap, `delegate_task` default ~10 parallel [53][57].
7. **Community-Kontext:** „Sessions can't message each other" ist die lauteste Hermes-Lücke (55 Upvotes) [54]; Gegenargument: A2A-Messaging verschwendet Tokens, Hierarchien + Subagents seien effizienter [54].

## 7. Methode

5 parallele Research-Lanes (2026-10-16): (1) Claude-Feature-Identifikation (Docs/Changelog/Issues/Blogs), (2) Hermes-Offiziell-Docs (16 Seiten), (3) Hermes-GitHub-Issues/PRs + Quellcode-Verifikation (main-Branch, Line-Refs), (4) Plugin-Feasibility (14 Docs-Seiten), (5) Community/Praxis (Reddit/HN/Blogs, ~20 Threads). Lane-Dateien: `/opt/data/cache/scratch/research-claude-spawn-feature.md`, `/opt/data/research/hermes-native-session-spawning.md`, `/opt/data/research/github-issues-source-lane.md`, `/opt/data/cache/scratch/research-spawn-with-report/lane-plugin-feasibility.md`, `/opt/data/research/community-practice-lane.md`. Quellcode-Zitate beziehen sich auf github.com/NousResearch/hermes-agent, Branch main, verifiziert 2026-10-16.

## Sources

[1] https://code.claude.com/docs/en/desktop
[2] https://code.claude.com/docs/de/desktop
[3] https://code.claude.com/docs/en/agent-teams
[4] https://code.claude.com/docs/en/agents.md
[5] https://code.claude.com/docs/en/cross-session-messaging.md
[6] https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md
[7] https://github.com/anthropics/claude-code/issues/100913
[8] https://github.com/anthropics/claude-code/issues/99393
[9] https://github.com/anthropics/claude-code/issues/53494
[10] https://github.com/anthropics/claude-code/issues/80238
[11] https://github.com/anthropics/claude-code/issues/72915
[12] https://github.com/anthropics/claude-code/issues/99862
[13] https://github.com/anthropics/claude-code/issues/101386
[14] https://x.com/WesRoth/status/2110513483833921828
[15] https://x.com/ClaudeDevs/status/2110445844675838148
[16] https://pasqualepillitteri.it/en/news/24032/claude-code-desktop-nested-sessions-environments
[17] https://alphasignal.ai/news/anthropic-s-claude-code-now-runs-nested-sessions-and-saves-dev-environments
[18] https://www.mindstudio.ai/blog/claude-code-3-0-parallel-sessions
[19] https://github.com/anthropics/claude-code/issues/95554
[20] https://github.com/anthropics/claude-code/issues/94697
[21] https://github.com/anthropics/claude-code/issues/91820
[22] https://hermes-agent.nousresearch.com/docs/user-guide/desktop
[23] https://hermes-agent.nousresearch.com/docs/user-guide/sessions
[24] https://hermes-agent.nousresearch.com/docs/user-guide/messaging
[25] https://hermes-agent.nousresearch.com/docs/user-guide/cli
[26] https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation
[27] https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
[28] https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode
[29] https://hermes-agent.nousresearch.com/docs/developer-guide/subagent-lifecycle-api
[30] https://hermes-agent.nousresearch.com/docs/user-guide/messaging/webhooks
[31] https://hermes-agent.nousresearch.com/docs/user-guide/features/cron
[32] https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server
[33] https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration
[34] https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk
[35] https://hermes-agent.nousresearch.com/docs/reference/slash-commands
[36] https://hermes-agent.nousresearch.com/docs/developer-guide/plugins
[37] https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins
[38] https://hermes-agent.nousresearch.com/docs/developer-guide/tools-runtime
[39] https://hermes-agent.nousresearch.com/docs/user-guide/features/built-in-plugins
[40] https://hermes-agent.nousresearch.com/docs/user-guide/features/extending-the-dashboard
[41] https://github.com/NousResearch/hermes-agent/issues/8948
[42] https://github.com/NousResearch/hermes-agent/pull/77109
[43] https://github.com/NousResearch/hermes-agent/pull/106423
[44] https://github.com/NousResearch/hermes-agent/issues/76221
[45] https://github.com/NousResearch/hermes-agent/issues/97635
[46] https://github.com/NousResearch/hermes-agent/pull/122859
[47] https://github.com/NousResearch/hermes-agent/issues/123607
[48] https://github.com/NousResearch/hermes-agent/issues/22191
[49] https://github.com/NousResearch/hermes-agent/issues/125346
[50] https://github.com/NousResearch/hermes-agent/issues/133212
[51] https://github.com/NousResearch/hermes-agent/issues/131282
[52] https://github.com/NousResearch/hermes-agent/issues/25176
[53] https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june
[54] https://www.reddit.com/r/hermesagent/comments/1x6qgz1/hermes_sessions_should_be_able_to_send_messages
[55] https://www.reddit.com/r/hermesagent/comments/1u88xbb/hermes_agent_ships_asynchronous_subagents
[56] https://the-agent-report.com/2026/06/hermes-async-subagents-june2026
[57] https://www.reddit.com/r/hermesagent/comments/1uvzqim/subagents
[58] https://github.com/NousResearch/hermes-agent/blob/main/tui_gateway/contracts/sessions.py
[59] https://github.com/NousResearch/hermes-agent/blob/main/hermes_state_sessions.py
[60] https://github.com/NousResearch/hermes-agent/blob/main/tools/delegate_tool.py
[61] https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server.py
[62] https://github.com/NousResearch/hermes-agent/blob/main/agent/subagent_lifecycle.py
