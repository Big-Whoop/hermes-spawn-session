# Lane — PLUGIN / CUSTOM BUILD FEASIBILITY for "Spawn with Report" in Hermes Desktop

- Research date: 2026-10-16 (Europe/Zurich)
- Scope: official docs only (hermes-agent.nousresearch.com/docs). No source code read (separate lane verifies source behavior).
- Target feature: agent in session A spawns a new visible session B with task + context; B runs independently; result reports back to A.
- Environment facts (verified by parent): Hermes v0.22.2, desktop app + telegram gateway + api_server enabled + kanban 2-lane; kanban-mode is a bundled desktop-plugin example.
- Method: web_extract of 12 doc pages (plugins, built-in-plugins, desktop, desktop-plugin-sdk, subagent-lifecycle-api, tools-runtime, webhooks, cron, extending-the-dashboard, api-server, delegation, slash-commands, bot-mode, developer-guide/plugins) + docs/llms.txt index.
- Confidence tiers: **Verified** = authoritative doc read; **Plausible** = sound general behavior not demonstrated on-target; **Speculative** = inferred.

---

## 0. Headline answer

All three custom-build paths are feasible with documented, stable seams; none requires core patches. The minimal build is **(b) a custom tool** using the **Public Subagent Lifecycle API** (`ctx.subagent_lifecycle`) — it is the only documented plugin seam that takes `goal` + `context` + `model`, runs the child independently, and returns the result to the caller. The closest **zero-build** native equivalents already exist: `/bg <prompt>` (new background session, result delivered back to the same chat), `delegate_task` (child agent, result re-enters parent), and Bot Mode `message_agent`/@mention handoff ("hands the message off and reports back").

Key distinction for the target feature: "visible session B" matters. Subagent children (delegate_task, subagent_lifecycle) are visible in the desktop **Subagents frame** above the composer, not as a session row in the sidebar. A true top-level visible session can be created via (a) `ctx.inject_message(origin=...)`, (c) `host.composer.submit('new', …)` / `host.newChat()`, or (6) `POST /api/sessions` + `POST /api/sessions/{id}/chat`.

---

## 1. Sub-question 1 — Custom slash commands

### 1.1 Plugins can register in-session slash commands (CLI + gateway)
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins (official docs, "Register slash commands")
- Quote: "Plugins can register in-session slash commands — commands users type during a conversation (like `/lcm status` or `/ping`). These work in both CLI and gateway (Telegram, Discord, etc.)."
- Quote: "After registration, users can type `/mystatus` in any session. The command appears in autocomplete, `/help` output, and the Telegram bot menu."
- Signature: `ctx.register_command(name: str, handler: Callable, description: str = "", args_hint: str = "")`; handler "Called with the raw argument string. May also be `async`."
- **Verified**

### 1.2 A slash-command handler can orchestrate tools, explicitly including spawning a subagent via delegate_task
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins (official docs, "Dispatch tools from slash commands")
- Quote: "Slash command handlers that need to orchestrate tools (spawn a subagent via `delegate_task`, call `file_edit`, etc.) should use `ctx.dispatch_tool()` instead of reaching into framework internals. The parent-agent context (workspace hints, spinner, model inheritance) is wired up automatically."
- Verbatim documented example (a `/deliver` command that delegates a goal):
  ```python
  def _handle_deliver(raw_args: str):
      result = ctx.dispatch_tool("delegate_task", {"goal": raw_args, "toolsets": ["terminal", "file", "web"]})
      return result
  ctx.register_command("deliver", handler=_handle_deliver, description="Delegate a goal to a subagent")
  ```
- **Verified**

### 1.3 `ctx.dispatch_tool` can invoke ANY registered tool, including cronjob and delegate_task, from any process
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins (official docs, "Act from inside a hook (profile + tools)")
- Quote: "`ctx.dispatch_tool(name, args)` — invoke any registered tool (built-in or plugin), including the `kanban_*` tools, `delegate_task`, `terminal`, `read_file`, etc. Works from hook callbacks regardless of which process the hook fires in."
- **Verified**

### 1.4 A plugin (command/hook/tool) can start a NEW gateway session in a given chat with a fresh prompt — via `ctx.inject_message(origin=...)`
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins (official docs, "Injecting Messages")
- Quote: "Plugins can inject messages into a CLI conversation, a known gateway session, or a new gateway session in a given chat using `ctx.inject_message()`"
- Quote (origin semantics): "The session is created in **the plugin's own profile** (the profile whose plugin manager loaded it) through the normal session path, with a fresh prompt and an empty history, and the reply is delivered to that chat/thread. If the chat already has a session in that profile, the text joins it exactly like a human message would"
- Quote (gateway mode): "`session_key` is required and must identify an existing gateway session… Injected text is always conversational input. It cannot invoke slash commands, approve tools, or resolve pending confirmation and clarification prompts."
- **Verified**

### 1.5 Built-in precedents for "spawn with report" (no build needed)
- Source: https://hermes-agent.nousresearch.com/docs/reference/slash-commands (official docs)
- Quote (`/bg`): "Run a prompt in a separate background session. The agent processes your prompt independently — your current session stays free for other work. Results appear as a panel when the task finishes." (CLI) / "Results are delivered back to the same chat when the task finishes." (messaging)
- Quote (`/branch`): "Branch the current session into an independent copy (explore a different path). On Discord, Telegram, Slack and Matrix the branch opens in a **new sibling thread** and the current chat stays on the original session"
- Quote (`/review`): "Spawn an independent, full-privilege reviewer subagent to review the work just discussed… It investigates in the background (opens the PR, reads the diff, runs code) and its full review re-enters this session as a background-subagent completion the primary agent can act on."
- **Verified**

### 1.6 Constraints
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins (official docs)
- Quote: "**Conflict protection:** If a plugin tries to register a name that conflicts with a built-in command (`help`, `model`, `new`, etc.), the registration is silently rejected with a log warning. Built-in commands always take precedence."
- Quote (gateway-mode dispatch): "Gateway mode: There is no CLI agent, so tools degrade gracefully — workspace is read from the configured terminal working directory and no spinner is shown."
- **Verified**

**Feasibility verdict (a): YES.** A `/spawn <task>` plugin command is a ~60–120 line plugin. Three report-back flavors, all documented: (i) `dispatch_tool("delegate_task", …)` → child result re-enters session A as a background completion (child is a subagent, visible in the Subagents frame, not a sidebar session row); (ii) `inject_message(origin=…)` → new session in a chat, reply delivered to that chat (session lives in the plugin's profile); (iii) `dispatch_tool("cronjob", …)` → one-shot job in a fresh session with a configured delivery target.

---

## 2. Sub-question 2 — Custom tools

### 2.1 Plugins register model-visible tools
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins (official docs)
- Quote: "Add tools | `ctx.register_tool(name=..., toolset=..., schema=..., handler=...)`"
- Quote: "Start Hermes — your tools appear alongside built-in tools. The model can call them immediately."
- **Verified**

### 2.2 THE key seam: Public Subagent Lifecycle API — `ctx.subagent_lifecycle`
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/subagent-lifecycle-api (official docs)
- Quote: "Plugins can launch and supervise fresh Hermes child sessions without importing `tools.delegate_tool`, gateway internals, TUI state, or `AIAgent` fields. The service resolves its parent from the current agent turn, so it works in CLI, gateway, non-interactive, and kanban-worker sessions. Launching outside an active agent turn fails closed with `No active Hermes parent session`."
- Quote (request fields): "Requests accept `goal`, `context`, `role`, `model`, `provider`, `allowed_toolsets`, `blocked_tools`, `working_directory`, `parent_session_id`, `correlation_id`, `metadata`, and `timeout_seconds`, subject to the restrictions below."
- Verbatim documented pattern (plugin tool launches a child, waits, returns result):
  ```python
  service = ctx.subagent_lifecycle
  handle = service.launch(SubagentLaunchRequest(
      goal="Review this change for regressions.",
      context="Only inspect the supplied repository.",
      role="leaf",
      correlation_id="review-42",
      allowed_toolsets=("file",),
  ))
  if service.wait(handle, timeout_seconds=2).timed_out:
      return handle.to_dict()
  return service.result(handle)
  ```
- Quote (supervision): "`steer(handle, text)` queues text for the child's next iteration boundary… The stable states are `PENDING`, `STARTING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `INTERRUPTED`, `CANCEL_REQUESTED`, `CANCELLED`, and `UNKNOWN`."
- Quote (report-back shape): "Terminal results are immutable, idempotent, bounded to 32k characters, omit transcripts and hidden reasoning, and include a stable result hash."
- Quote (hosting): "Child construction and completion use the same host-owned path as `delegate_task`, including parent tool-resolution restoration, memory notification, serialized `subagent_stop` hooks, resource cleanup, and child-cost rollup."
- Quote (durability limit): "The initial implementation retains metadata and terminal results in-process for one hour. After a process restart, `reconnect` returns `RECONNECT_UNAVAILABLE` and never starts a replacement child."
- Quote (routing): "Children follow the `delegation` config (`provider`, `model`, …) exactly as `delegate_task` children do. The request's `model` overrides the configured model."
- **Verified**

### 2.3 Tool runtime: registration + dispatch mechanics
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/tools-runtime (official docs)
- Quote: "Each tool module calls `registry.register(...)` at import time… `name` — Unique tool name (used in API schemas), `toolset`, `schema` — Model-facing schema (description, parameters), `handler` — The function that executes when the tool is called"
- Quote: "Plugin tools — `hermes_cli.plugins.discover_plugins()` loads user/project/pip plugins that may register additional tools."
- Quote (built-in precedent): "`delegate_task` — spawns subagent sessions" (listed among agent-loop tools intercepted before registry dispatch).
- **Verified**

### 2.4 delegate_task semantics (what a spawn tool inherits if it wraps it)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (official docs)
- Quote: "The `delegate_task` tool spawns child AIAgent instances with isolated context, inherited tool access, and their own terminal sessions. Each child gets a fresh conversation and works independently — only its final summary enters the parent's context."
- Quote (report-back): "Top-level model calls run in the background automatically. Hermes returns a handle immediately so the conversation can continue, then posts the result back as a new message."
- Quote (context isolation): "Subagents start with a **completely fresh conversation**. They have zero knowledge of the parent's conversation history… The subagent's only context comes from the `goal` and `context` fields the parent agent populates when it calls `delegate_task`."
- Quote (durability): "A Hermes process restart does **not** resume a running child. Its attempt becomes `unknown`… For **durable execution** that must survive session closure or process restart, use: `cronjob` (action=`create`) — schedules a separate agent run; immune to parent-turn interrupts."
- **Verified**

**Feasibility verdict (b): YES — strongest option.** A `spawn_session(task, context, model, toolsets)` tool is ~80–150 lines. `ctx.subagent_lifecycle` is purpose-built for exactly this (goal + context + model in; independent run; result out to the caller's turn). Report-back is automatic: the tool returns the terminal result (≤32k chars) to session A's model, or the tool returns a handle and the completion re-enters A as a background message. Limits: child is a subagent (Subagents-frame visibility, not a sidebar session row); launch must happen inside an active agent turn; results not durable across process restart.

---

## 3. Sub-question 3 — Desktop plugins (Cmd-K / button)

### 3.1 Desktop plugins register palette commands, keybinds, panes, pages
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk (official docs)
- Quote: "The native Hermes Desktop app is contribution-driven: every surface in the window — panes, routes, sidebar nav, status-bar items, palette entries, keybinds, themes — registers into one central registry."
- Quote (delivery): "A **desktop plugin** is a single ESM file that default-exports a `HermesPlugin`. It imports one module — `@hermes/plugin-sdk`… Drop the file in `$HERMES_HOME/desktop-plugins/<id>/plugin.js` and the app loads it within seconds and hot-reloads every save."
- Verbatim palette-command example:
  ```js
  ctx.register({ id: 'open', area: PALETTE_AREA,
    data: { id: 'my-page.open', label: 'Open My Page', keywords: ['my','page'],
            run: () => host.navigate('/my-page') } })
  ```
- **Verified**

### 3.2 The app's Cmd+K palette is where plugin commands land
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/desktop (official docs, "Keyboard & navigation")
- Quote: "**Command palette** — press **Cmd+K** or **Cmd+P** (Ctrl+K / Ctrl+P on Windows/Linux) to jump to actions and navigate the app from the keyboard: open any page or settings section, jump to a session by title or id, switch model/theme/color mode, spawn a terminal, restart the gateway, update Hermes, and more."
- Quote: "Rebindable shortcuts — … any shortcuts contributed by desktop plugins."
- **Verified**

### 3.3 Spawn mechanism: `host.composer.submit` + `host.newChat` (create a session and send a prompt)
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk (official docs, "Composer draft API")
- Quote: "For everything the composer areas can't do — put text INTO the input, replace what's there, read the current draft, or send it — use `host.composer`."
- Quote (addressing): "`null` = the composer the user is typing in; a session id (stored or runtime) = that session's composer, in the primary pane or a tile; `'new'` = the fresh draft that has no session id yet."
- Quote (submit): "`const sent = host.composer.submit('sess-1', 'ship it')` — Send as if the user typed + pressed Enter. Fail-closed like the app's own panels: no visible surface for the address → false, never a broadcast."
- Quote (new chat): "`host.newChat(profile?)` // fresh chat draft, optionally in another profile"
- **Verified**

### 3.4 Gateway JSON-RPC door + app actions + event stream
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk (official docs, "Host API")
- Quote: "`host.request` — the gateway JSON-RPC door: sessions, config, skills, cron — everything the app itself calls."
- Quote: "`host.request` is the same JSON-RPC the app itself uses (sessions, config, skills, cron, kanban, …)."
- Quote (runAction allowlist includes): "`session.new` | Start a new chat"
- Quote (monitoring B): "`host.state.busyBySession` // ReadableAtom<Record<string, boolean>> runtime id → mid-turn"; "`host.onEvent(type, fn)` // gateway event stream ('*' = all)"; "For token-level detail, listen with `host.onEvent` (`message.start`, `message.delta`, `message.complete`)."
- Quote (documented RPC for slash execution, from the migration table): "`host.request('slash.exec', { session_id, command })` for `/memory …` — already SDK-only"
- **Verified**

### 3.5 Optional Python backend: `plugin_api.py` runs inside the gateway process
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk (official docs, "The Python side")
- Quote: "Routes mount under `/api/plugins/<id>/`… Backend code runs inside the gateway process, so it can import from the hermes-agent codebase directly (`hermes_state`, `hermes_cli.config`, …)."
- Quote (push events to the UI half): "Your backend runs inside the gateway process, so it can push an update to your own desktop half over the app's global event stream — the same stream `host.onEvent` subscribes to" (`broadcast_plugin_event(plugin_id, event, payload)`)
- Quote (gating): "A user plugin's `plugin_api.py` is imported only when the plugin is in the `plugins.enabled` allow-list in `config.yaml`"
- **Verified**

### 3.6 Precedent: bundled kanban dashboard plugin (sidebar page + REST router)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/built-in-plugins (official docs)
- Quote: "`kanban/dashboard` | dashboard tab | Kanban board UI for the multi-agent dispatcher — tasks, comments, fan-out, board switching."
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/extending-the-dashboard (official docs)
- Quote: "**Backend plugins** — a Python file inside that plugin directory that exposes a FastAPI `router`; routes are mounted under `/api/plugins/<name>/` and called from the plugin's UI."
- (Task-verified local fact: the user's kanban-mode plugin is a bundled desktop-plugin example with a sidebar page + REST router `/api/plugins/kanban`.)
- **Verified**

### 3.7 Security / enablement
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/desktop (official docs, "Extending the desktop app")
- Quote: "A desktop plugin is **not sandboxed**: it runs inside the app with the app's own authority (gateway RPC, the native bridge, other plugins' storage). Only load files you wrote or reviewed"
- Source: https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk (official docs)
- Quote: "the desktop half ships opt-in — it inventories in **Capabilities → Plugins** but stays disabled until the user toggles it — matching the Python half's `plugins.enabled` gate in `config.yaml`"
- **Verified**

**Feasibility verdict (c): YES.** A "Spawn with Report" ⌘K command + button is ~100–250 lines of ESM (no build step). Flow: prompt for task+context → `host.newChat()` (or `ctx.runAction('session.new')`) → `host.composer.submit('new', prompt)` → session B appears as a real visible session tab; watch `host.state.busyBySession` / `host.onEvent('message.complete')`; on completion push the result into A via `host.composer.insertText(A_session_id, result, {mode:'block'})` or a `host.notify` toast. Report-back to A's *agent* (not just its composer) needs the backend half (`plugin_api.py` can import gateway internals) or a companion tool from option (b).

---

## 4. Sub-question 4 — Webhooks (agent calls an HTTP endpoint)

### 4.1 A POST to a webhook route triggers a one-shot agent run with a prompt and delivers the result to a channel
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/messaging/webhooks (official docs)
- Quote: "Receive events from external services (GitHub, GitLab, JIRA, Stripe, etc.) and trigger Hermes agent runs automatically. The webhook adapter runs an HTTP server that accepts POST requests, validates HMAC signatures, transforms payloads into agent prompts, and routes responses back to the source or to another configured platform."
- Quote (route props): "`prompt` — Template string with dot-notation payload access… If omitted, the full JSON payload is dumped into the prompt." / "`deliver` — Where to send the response: `github_comment`, `telegram`, `discord`, `slack`, … or `log` (default)." / "`deliver_extra` — Additional delivery config — keys depend on `deliver` type (e.g. `repo`, `pr_number`, `chat_id`)."
- Quote (targeting a specific chat): "When `chat_id` is not provided in `deliver_extra`, the delivery falls back to the home channel configured for the target platform."
- Quote (cron interplay): "`cron_job` — Fire an existing cron job (by ID or name) on each event instead of starting a fresh webhook agent session."
- Setup: `WEBHOOK_ENABLED=true`, `WEBHOOK_PORT=8644`, `WEBHOOK_SECRET=…`; routes under `platforms.webhook.extra.routes`; endpoint `http://your-server:8644/webhooks/<route-name>`.
- **Verified**

**Feasibility verdict: YES as an "agent A calls HTTP" path** — but it is the heaviest of the four: agent A must sign each POST with the route's HMAC secret, and the result lands in the configured `deliver` target (e.g. a Telegram chat), not into session A's transcript. A webhook route is a fresh session per event ("a fresh webhook agent session"). Best fit: external systems triggering runs, not intra-agent spawn/report.

---

## 5. Sub-question 5 — Cron (one-shot job in a NEW session with delivery)

### 5.1 One-shot cron jobs run in fresh sessions and deliver to a target
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/cron (official docs)
- Quote: "Cron jobs can: schedule one-shot or recurring tasks… deliver results back to the origin chat, local files, or configured platform targets; run in fresh agent sessions with the normal static tool list"
- Quote (agent-created): "All of this is available to Hermes itself through the `cronjob_manage` tool, so you can create, pause, edit, and remove jobs by asking in plain language — no CLI required."
- Quote (recursion guard): "Cron-run sessions cannot recursively create more cron jobs. Hermes disables cron management tools inside cron executions to prevent runaway scheduling loops."
- Quote (model): "Resolution at fire time is: per-job pin → `cron.model` in `config.yaml` → the main agent model from `hermes model`."
- **Verified**

**Feasibility verdict: YES.** Session A (agent or user) creates a one-shot job (`cronjob_manage` tool / `/cron add "in 30m" …` / `POST /api/jobs`); the job runs the prompt in a NEW session and delivers the result to the origin chat or a configured platform target (e.g. a specific Telegram chat/thread via `TELEGRAM_CRON_THREAD_ID`). Durability is the strongest of all paths (survives restarts; "Agent-backed runs retain their fire identity until output and a durable delivery handoff are recorded"). Limitation: the run session is not a visible desktop session tab (it's a cron run; its delivery shows up in the target chat / desktop timeline disclosures — "Async cron and delegation completions appear as collapsed timeline disclosures").

---

## 6. Sub-question 6 — API server (user has api_server enabled)

### 6.1 Documented REST endpoints for session creation and one-shot runs
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server (official docs, "Sessions API (session control over REST)")
- Quote: "External UIs can manage Hermes sessions over REST without standing up the dashboard. All endpoints are gated by `API_SERVER_KEY` and live under `/api/sessions/*`."
- Verbatim endpoint table:
  | Method | Path | Description |
  |---|---|---|
  | `GET` | `/api/sessions` | List sessions (paginated — `limit`, `offset`, `source`, `include_children`) |
  | `POST` | `/api/sessions` | Create an empty session |
  | `GET` | `/api/sessions/{id}` | Read session metadata |
  | `PATCH` | `/api/sessions/{id}` | Update title or `end_reason` |
  | `DELETE` | `/api/sessions/{id}` | Delete a session |
  | `GET` | `/api/sessions/{id}/messages` | Message history for a session |
  | `POST` | `/api/sessions/{id}/fork` | Branch the session via `SessionDB` lineage (matches CLI `/branch` semantics) |
  | `POST` | `/api/sessions/{id}/chat` | Run one synchronous agent turn |
  | `POST` | `/api/sessions/{id}/chat/stream` | SSE wrapper over a single turn |
- Verbatim example: "fork a session and run one turn: `curl -X POST …/api/sessions/$ID/fork … -d '{"title": "explore alt path"}'`" then "`curl -N -X POST …/api/sessions/$ID/chat/stream … -d '{"input": "what files changed in the last hour?"}'`"
- **Verified**

### 6.2 Runs API (async run + poll/stream the result)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server (official docs, "Runs API")
- Quote: "Create a new agent run. Returns a `run_id` that can be used to subscribe to progress events." / "Runs accept a simple `input` string and optional `session_id`, `instructions`, `conversation_history`, or `previous_response_id`."
- Quote (result): `GET /v1/runs/{run_id}` → `{"object": "hermes.run", "run_id": "run_abc123", "status": "completed", "session_id": "space-session", …, "output": "Done.", …}`
- **Verified**

### 6.3 Jobs API (cron over REST)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server (official docs, "Jobs API")
- Quote: "`POST /api/jobs` — Create a new scheduled job. Body accepts the same shape as `hermes cron` — prompt, schedule, skills, provider override, delivery target." / "`POST /api/jobs/{job_id}/run` — Trigger the job to run immediately, out of schedule."
- **Verified**

### 6.4 Critical boundary: API sessions cannot bind to sessions owned by other surfaces
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server (official docs)
- Quote: "**API sessions are their own sessions.** `session_id` (here) and the `X-Hermes-Session-Id` header … may name a session the API server created or one it may create; they cannot bind a session that another surface owns — a CLI, TUI, Desktop, ACP or messaging conversation. Such a request is refused with HTTP 409 and error code `permission_denied`… To work on a chat from another surface, attach through the gateway WebSocket (a `prompt.submit` on the shared session) instead of the OpenAI-compatible routes."
- **Verified**

**Feasibility verdict: YES.** With api_server enabled, agent A (or any plugin backend) can: `POST /api/sessions` → `POST /api/sessions/{id}/chat` (synchronous turn) or `POST /v1/runs` + `GET /v1/runs/{id}` / `/events` (async). The created session is a real session (visible in dashboard/session history). Report-back to A's *agent* requires A to poll, or a plugin backend to read `GET /api/sessions/{id}/messages` and inject into A. Cannot be used to drive session A's own transcript (409 boundary).

---

## 7. Comparison matrix — (a) slash command / (b) custom tool / (c) desktop plugin

| Dimension | (a) Custom slash command | (b) Custom tool (subagent_lifecycle) | (c) Desktop plugin ⌘K/button |
|---|---|---|---|
| Mechanism | `ctx.register_command("spawn", h)`; `h` calls `ctx.dispatch_tool("delegate_task", {goal, context})` or `ctx.inject_message(origin=…)` or `dispatch_tool("cronjob", …)` | `ctx.register_tool("spawn_session", schema, h)`; `h` calls `ctx.subagent_lifecycle.launch(SubagentLaunchRequest(goal, context, model, allowed_toolsets))`, then `wait`/`result` | `PALETTE_AREA`/`KEYBINDS_AREA` contribution; `run:` → `host.newChat()` + `host.composer.submit('new', prompt)`; watch `host.onEvent`/`busyBySession`; push result via `host.composer.insertText(A, …)` or `host.notify`; optional `plugin_api.py` backend for gateway-side work |
| Prereqs | Plugin in `~/.hermes/plugins/` + `plugins.enabled` entry; restart gateway | Same as (a); launch must occur inside an active agent turn | File in `~/.hermes/desktop-plugins/<id>/plugin.js` (no build); desktop half toggled on in Capabilities → Plugins; Python backend additionally needs `plugins.enabled` |
| Key steps | 1) plugin.yaml + `__init__.py` 2) `register_command` 3) handler dispatches tool 4) enable plugin | 1) plugin.yaml + `__init__.py` 2) `register_tool` with schema (task, context, model, toolsets) 3) handler uses `ctx.subagent_lifecycle` 4) enable plugin | 1) `plugin.js` (ESM, `jsx()` calls only) 2) register palette command + optional pane/button 3) spawn via `host.composer.submit('new', …)` 4) subscribe to completion 5) report back into A 6) (optional) `dashboard/plugin_api.py` |
| Rough effort | ~60–120 lines Python | ~80–150 lines Python | ~100–250 lines JS (+ ~50–150 lines Python if backend needed) |
| Session B visibility | subagent: Subagents frame only; `inject_message(origin)`: real gateway session in a chat; cron: not a visible tab | Subagents frame only (child session, not sidebar row) | **Real visible session tab** (created through the app's own new-chat path) |
| Independence | yes (background) | yes (async, `wait` optional) | yes (own turn in B) |
| Report-back to A | delegate_task completion re-enters A automatically; inject_message reply goes to target chat; cron delivery to configured target | `result(handle)` returned to A's model (≤32k chars) or completion re-enters A | plugin watches B and writes into A's composer / toasts; or backend injects into A's session; or B's agent calls a companion tool |
| Persistence across `hermes update` | yes — "Ordinary Hermes application updates preserve user plugin directories" (plugins page) | yes (same) | yes — standalone `desktop-plugins/<id>/` "is never overwritten"; unified-package copy refreshed on update |
| Main risks | handler context differs CLI vs gateway ("degrade gracefully"); built-in name conflicts rejected; `inject_message` origin session lives in plugin's profile | fail-closed outside active turn; results in-process 1h only; process restart → `RECONNECT_UNAVAILABLE`; goal/context/metadata size caps; toolsets can't be broadened beyond parent | not sandboxed (full app authority); desktop half opt-in; no JSX (uncompiled ESM); only 3 importable specifiers; exact `host.request` RPC method names for session creation not enumerated in SDK docs (documented doors are `host.composer.submit`, `host.newChat`, `ctx.runAction('session.new')`) |

**Recommended minimal build:** (b) — a `spawn_session` tool on `ctx.subagent_lifecycle` (the documented, versioned seam for exactly goal+context→independent run→result), optionally paired with a (c) ⌘K command that calls the same flow through `host.composer.submit('new', …)` when the user wants a *visible* session tab. If "visible session B" is a hard requirement, (c) or (a)-via-`inject_message(origin)` / (6)-via-`/api/sessions` are the only paths that create a top-level session.

---

## 8. Zero-build native alternatives (for the parent's decision)

### 8.1 `/bg <prompt>` — built-in "spawn with report"
- Source: https://hermes-agent.nousresearch.com/docs/reference/slash-commands (official docs)
- Quote: "`/bg <prompt>` — Run a prompt in a separate background session. The agent processes your prompt independently — your current session stays free for other work. Results appear as a panel when the task finishes." (CLI); "Results are delivered back to the same chat when the task finishes." (messaging)
- **Verified**

### 8.2 `delegate_task` — agent-initiated spawn with automatic report-back
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (official docs)
- Quote: "Each child gets a fresh conversation and works independently — only its final summary enters the parent's context." / "Hermes returns a handle immediately so the conversation can continue, then posts the result back as a new message."
- Desktop visibility: https://hermes-agent.nousresearch.com/docs/user-guide/desktop — "While delegated workers are live, a **Subagents** frame appears above the composer with their count, task names, elapsed time, and latest activity… select a worker for details and **Steer** / **Stop** controls."
- **Verified**

### 8.3 Bot Mode — built-in inter-agent handoff with report-back
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/desktop (official docs, "Bot Mode (built in)")
- Quote: "Bots message each other: type `@researcher have a look at this` in any chat and the active bot hands the message off and reports back, and bots reach each other's Bot Chats directly (`hermes -p <bot> chat`)."
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode (official docs, "Bot-to-bot messaging")
- Quote: "every Bot Chat carries the `message_agent` tool: a Bot messages a teammate by calling `message_agent(target=\"researcher\", message=\"…\")`… Delivery is **fire-and-forget**: the sender gets a _dispatch_ acknowledgement… and that process's completion notification carries the outcome — the reply, or the delivery failure."
- Quote: "The tool exists **only** in canonical Bot Chat sessions on Bot-Mode-managed installs; regular chats, group-room member sessions, and CLI sessions never see it."
- **Verified**

---

## 9. Searched, found nothing

1. **No documented one-call desktop-SDK method that creates a new session AND sends a prompt atomically.** The documented doors are `host.newChat()` (draft only) + `host.composer.submit('new', text)` (send), or `ctx.runAction('session.new')` (new chat, no prompt). The exact `host.request` JSON-RPC method names for session creation are not enumerated in the SDK docs ("everything the app itself calls" — method list not published).
2. **No documented plugin seam that creates a TOP-LEVEL visible session from a plugin tool.** `ctx.subagent_lifecycle` creates child sessions (Subagents-frame visibility); `ctx.inject_message(origin=…)` creates a gateway session in a chat (plugin's own profile); no documented `register_session_spawner`-style API.
3. **No documented way for a subagent-lifecycle child to appear as a session row in the desktop sidebar** — docs only show the Subagents frame / `/agents` overlay for children.
4. **No built-in or catalog slash command named `/spawn`** in the slash-commands reference (closest: `/bg`, `/branch`, `/new`, `/review`).
5. **No documented `spawn_session`-style tool in the built-in tools reference** (the built-in pattern is `delegate_task`).
6. **URLs from the task list that 404'd** (correct paths used instead): `…/docs/user-guide/features/desktop` → `…/docs/user-guide/desktop`; `…/docs/user-guide/features/webhooks` → `…/docs/user-guide/messaging/webhooks`.
7. **No documented way to make a cron-run session appear as a visible desktop session tab** — cron runs are headless sessions whose results surface via delivery (chat) or "collapsed timeline disclosures" for async completions.
