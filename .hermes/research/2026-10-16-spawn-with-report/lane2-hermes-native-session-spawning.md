# Research Lane: HERMES NATIVE MECHANISMS FOR SPAWNING NEW SESSIONS

Scope: every native Hermes Agent mechanism that creates a NEW session (visible or not) from/alongside an existing session, carrying a task + context, with any reporting-back path.
Target feature to match (Claude Desktop): agent in session A spawns a new VISIBLE session B with task + context; B runs independently; result reports back to A.
Method: docs-only (hermes-agent.nousresearch.com/docs), fetched 2026-10-16. No source code read.
Tiers: **Verified** = authoritative doc for this exact target; **Plausible** = documented but indirect/partial; **Speculative** = inferred, not stated in docs.

---

## 1. Desktop app: session creation, session list, spawn/fork UI

### 1.1 UI actions that create a new session
- **Claim:** Desktop creates new sessions via keyboard shortcuts and tabs: `Cmd/Ctrl+T` opens a new session tab; `Cmd/Ctrl+N` is the "new session" default shortcut; any session can be popped into its own window; the command palette (Cmd+K) can "jump to a session by title or id".
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/desktop (Windows, tabs & panes; Keyboard & navigation)
- **Type:** official user-guide doc
- **Quote:** "**Tabs** — **Cmd/Ctrl+T** opens a new session tab; **Ctrl+Tab** / **Ctrl+Shift+Tab** cycle sessions … **Cmd/Ctrl+Shift+N** opens a new window, and any session can be popped out via its context menu (**New window**) or from the command palette." / "A few defaults worth knowing: **Cmd/Ctrl+N** new session, **Cmd/Ctrl+.** Command Center, **Cmd/Ctrl+,** Settings, **Cmd/Ctrl+Shift+F** search sessions"
- **Tier:** Verified

### 1.2 NO "new session with initial prompt" / "fork session" / "spawn from this session" in desktop UI
- **Claim:** The desktop docs contain no UI action, command, or Cmd-K palette entry that creates a new session *with an initial prompt*, forks a session, or spawns a session "from this session". Full-text search of the desktop page for `fork`, `spawn`, `initial prompt`, `session.create` returns zero session-forking hits (only terminal-spawn and command-palette "spawn a terminal"). The closest documented primitives are (a) plain new-session shortcuts (no prompt), (b) the plugin SDK doors in 1.3, and (c) gateway-level `session.branch`/`/fork` which are not exposed as a desktop UI action in the docs.
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/desktop (whole page, incl. Command palette: "open any page or settings section, jump to a session by title or id, switch model/theme/color mode, spawn a terminal, restart the gateway, update Hermes, and more")
- **Type:** official user-guide doc (negative finding by exhaustive term search)
- **Quote:** "**Command palette** — press **Cmd+K** or **Cmd+P** … to jump to actions and navigate the app from the keyboard: open any page or settings section, jump to a session by title or id, switch model/theme/color mode, spawn a terminal, restart the gateway, update Hermes, and more."
- **Tier:** Verified (as a negative: no such UI documented)

### 1.3 Desktop plugin SDK: programmatic "new session + send prompt" door
- **Claim:** A desktop plugin can (a) trigger the app's own "start a new chat" action via `ctx.runAction('session.new')`, and (b) write a prompt into the fresh session's composer and send it via `host.composer.submit('new', text)` — i.e., a plugin can create a new visible session and launch a task in it, purely through documented SDK APIs. `host.request` is additionally "the gateway JSON-RPC door: sessions, config, skills, cron — everything the app itself calls" (the same door that carries `session.create`).
- **Source:** https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk (Run app actions; Composer draft API; Mental model)
- **Type:** official developer-guide doc
- **Quote:** "| `session.new` | Start a new chat |" / "Addressing: `null` = the composer the user is typing in; a session id (stored or runtime) = that session's composer … `'new'` = the fresh draft that has no session id yet." / "const sent = host.composer.submit('sess-1', 'ship it')" / "**`host.request`** — the gateway JSON-RPC door: sessions, config, skills, cron — everything the app itself calls."
- **Tier:** Verified (SDK is documented; the exact "spawn B from A's agent turn" composition is a Plausible assembly of two documented doors — see gap analysis §9)

### 1.4 Session list: what is visible
- **Claim:** The desktop session list shows ordinary sessions (with archiving, search by id, per-project grouping). Subagent/kanban/background sessions are NOT ordinary session-list entries: kanban worker sessions are "hidden from session pickers", one-shot and `tool`-source sessions are "Hidden from the TUI, Desktop and dashboard session pickers", and Bot Mode sessions (Bot Chats + group chats) are "always hidden from the global Sessions sidebar". Subagents are surfaced instead as a live **Subagents** frame above the composer.
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/sessions (Session Sources table); https://hermes-agent.nousresearch.com/docs/user-guide/desktop (Live subagents; Bot Mode (built in))
- **Type:** official user-guide docs
- **Quote:** "`oneshot` | Finite non-interactive runs … Hidden from the TUI, Desktop and dashboard session pickers (like `kanban` and `tool`) …" / "`kanban` | Kanban dispatcher workers (read on the board, hidden from session pickers)" / "While delegated workers are live, a **Subagents** frame appears above the composer with their count, task names, elapsed time, and latest activity." / "Bot Mode's sessions — each bot's canonical Bot Chat and every group-chat member session — are always hidden from the global Sessions sidebar."
- **Tier:** Verified

### 1.5 TUI live session switcher (adjacent surface)
- **Claim:** The TUI can start another live session in-process: `/sessions new` "start another live session immediately" (live session switcher).
- **Source:** https://hermes-agent.nousresearch.com/docs/reference/slash-commands (Session table, Notes)
- **Type:** official reference doc
- **Quote:** "`/sessions` (TUI alias: `/switch`) | … TUI: open the live session switcher for currently open TUI sessions. Use `/sessions new` in the TUI to start another live session immediately."
- **Tier:** Verified

---

## 2. `/bg` Background Sessions — full semantics

### 2.1 Supported surfaces
- **Claim:** `/bg` works in **both the CLI and the messaging gateway** (per the central slash-command registry notes). It is NOT documented as a desktop-app chat command (desktop page has no `/bg` section; the only desktop mention of background work is the Subagents frame and background-process notifications).
- **Source:** https://hermes-agent.nousresearch.com/docs/reference/slash-commands (Notes); https://hermes-agent.nousresearch.com/docs/user-guide/cli (Background Sessions); https://hermes-agent.nousresearch.com/docs/user-guide/messaging (Background Sessions)
- **Type:** official reference + user-guide docs
- **Quote:** "`/status`, `/egress`, `/version`, `/whoami`, `/bg`, `/btw`, `/queue`, `/steer`, … work in **both** the CLI and the messaging gateway."
- **Tier:** Verified

### 2.2 Semantics (CLI)
- **Claim:** Each `/bg` prompt spawns a completely separate agent session in a daemon thread; isolated conversation (no parent context, only the prompt); inherits model, provider, toolsets, reasoning settings, and fallback model from the current session; non-blocking; multiple concurrent tasks; result appears as a panel in the terminal on completion; background sessions do not appear in the main conversation history and have their own task ID (`bg_143022_a1b2c3`).
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/cli (Background Sessions → How It Works / Results)
- **Type:** official user-guide doc
- **Quote:** "Each `/bg` prompt spawns a **completely separate agent session** in a daemon thread: **Isolated conversation** — the background agent has no knowledge of your current session's history. It receives only the prompt you provide. **Same configuration** — the background agent inherits your model, provider, toolsets, reasoning settings, and fallback model from the current session." / "When a background task finishes, the result appears as a panel in your terminal" / "Background sessions do not appear in your main conversation history. They are standalone sessions with their own task ID (e.g., `bg_143022_a1b2c3`)."
- **Tier:** Verified

### 2.3 Semantics (messaging)
- **Claim:** On messaging platforms `/bg` spawns a separate agent instance asynchronously; isolated session with its own history, no knowledge of the current chat; inherits model/provider/toolsets/reasoning/routing from the current gateway setup; the result is delivered back to the **same chat or channel** where the command was issued, prefixed "✅ Background task complete" (or "❌ Background task failed"); fire-and-forget.
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/messaging (Background Sessions → How It Works)
- **Type:** official user-guide doc
- **Quote:** "Each `/bg` prompt spawns a **separate agent instance** that runs asynchronously: **Isolated session** — the background agent has its own session with its own conversation history. It has no knowledge of your current chat context and receives only the prompt you provide. … **Result delivery** — when the task finishes, the result is sent back to the **same chat or channel** where you issued the command, prefixed with \"✅ Background task complete\"."
- **Tier:** Verified

### 2.4 Limits
- **Claim:** No documented concurrency cap for `/bg` (the CLI status bar shows "▶ N — Active background tasks — how many `/bg` prompts are still running in the current session"). Background-process notifications from within a background session are separately configurable (`display.background_process_notifications: concise|all|result|error|off`; `off` is "Also honored by the CLI, TUI and Desktop: background-process completions and heartbeats no longer wake the agent (subagent results still do)").
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/cli (Status Bar); https://hermes-agent.nousresearch.com/docs/user-guide/messaging (Background Process Notifications)
- **Type:** official user-guide docs
- **Quote:** "▶ N | **Active background tasks** — how many `/bg` prompts are still running in the current session." / "`off` | No process watcher messages at all. Also honored by the CLI, TUI and Desktop: background-process completions and heartbeats no longer wake the agent (subagent results still do)"
- **Tier:** Verified

**Match to target:** `/bg` is the closest *user-facing* match to "spawn B with a task, result reports back to A" — but B is invisible (not in the session list), B gets no context from A (only the prompt text), and reporting is to the chat/terminal, not into A's agent context as a turn.

---

## 3. `delegate_task` subagents

### 3.1 Spawn + context + report-back
- **Claim:** `delegate_task` spawns child AIAgent instances with isolated context and their own terminal sessions; the child's ONLY context is the `goal` + `context` fields (plus the workspace's project context files); top-level calls run in the background automatically — "Hermes returns a handle immediately so the conversation can continue, then posts the result back as a new message"; only the final summary enters the parent's context.
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (intro; How Subagent Context Works; Lifetime and Durability)
- **Type:** official user-guide doc
- **Quote:** "The `delegate_task` tool spawns child AIAgent instances with isolated context, inherited tool access, and their own terminal sessions. Each child gets a fresh conversation and works independently — only its final summary enters the parent's context." / "Top-level model calls run in the background automatically. Hermes returns a handle immediately so the conversation can continue, then posts the result back as a new message." / "Subagents start with a **completely fresh conversation**. They have zero knowledge of the parent's conversation history … The subagent's only context comes from the `goal` and `context` fields the parent agent populates when it calls `delegate_task`."
- **Tier:** Verified

### 3.2 Session rows: existence, source tag, visibility
- **Claim:** Subagent runs are real sessions in `state.db` with source tag `subagent` (the sessions doc lists `subagent` among the state-owned sources whose orphaned open sessions get auto-closed). The docs do NOT document a `parent_session_id` column or a `_delegate_from` marker for these rows (that is a source-level fact from prior research, unconfirmed in docs). Subagent sessions are not presented as entries in the desktop/CLI session list; monitoring is via the Subagents frame (Desktop), `/agents` overlay (TUI), and per-task live transcript logs.
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/sessions (Automatic Cleanup); https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (Monitoring Running Subagents; Live Transcripts)
- **Type:** official user-guide docs
- **Quote:** "Some producers — cron jobs, kanban workers, subagents, one-shot CLI runs — can die without ever marking their session ended … each auto-prune pass also _closes_ open sessions from those state-owned sources (`cli`, `cron`, `kanban`, `acp`, `api_server`, `subagent`, `tool`, …)" / "Every `delegate_task` dispatch also creates one **append-only, human-readable log per task** … `<hermes_home>/cache/delegation/live/<delegation_id>/task-<n>.log`"
- **Tier:** Verified (rows exist, source tag `subagent`); **Speculative** (visibility in desktop session list — docs neither show nor exclude it; all documented surfaces treat subagents as children, not listable sessions)

### 3.3 Ephemeral vs persistent
- **Claim:** Delegation is ephemeral by design: "A Hermes process restart does **not** resume a running child" (becomes `unknown`); `/stop` or closing/resetting the owning session ends its background children; for durable work the docs point to `cronjob` or `terminal(background=True, notify_on_complete=True)`. Completion events ARE durable: "Hermes stores its completion event in the active profile's `state.db` before publishing it to the normal fresh-turn queue" (survives restart, delivered at-least-once).
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (Lifetime and Durability; Durable background completions)
- **Type:** official user-guide doc
- **Quote:** "A Hermes process restart does **not** resume a running child. Its attempt becomes `unknown` …" / "For **durable execution** that must survive session closure or process restart, use: `cronjob` (action=`create`) … `terminal(background=True, notify_on_complete=True)`" / "When a background delegation finishes, Hermes stores its completion event in the active profile's `state.db` before publishing it to the normal fresh-turn queue."
- **Tier:** Verified

### 3.4 Model/provider, tools, depth
- **Claim:** Subagents inherit the parent's enabled toolsets, API key, provider configuration, and credential pool; a different model can be pinned via `delegation.model` / `delegation.provider` in config.yaml ("If omitted, subagents use the same model as the parent"). Default depth is flat (1); `role="orchestrator"` + `delegation.max_spawn_depth` enables nested trees; leaf subagents cannot call `delegate_task`, `clarify`, `memory`, `send_message`, `cronjob`.
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (Key Properties; Model Override; Depth Limit and Nested Orchestration)
- **Type:** official user-guide doc
- **Quote:** "Subagents inherit the parent's **API key, provider configuration, and credential pool**" / "You can configure a different model for subagents via `config.yaml` … If omitted, subagents use the same model as the parent." / "By default, delegation is **flat**: a parent (depth 0) spawns children (depth 1), and those children cannot delegate further."
- **Tier:** Verified

### 3.5 Control & observability (steering, monitoring)
- **Claim:** The parent agent can `list`/`steer`/`stop` its own running children through the same `delegate_task` tool (actions, scoped to its own spawn tree). Programmatic hosts use the session-scoped gateway RPCs `subagent.steer` / `subagent.interrupt` (ids from `delegation.status`). TUI has `/agents` overlay (tree view, kill/pause, post-hoc review); Desktop shows the Subagents frame with Steer/Stop.
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (Steering a Running Subagent; Monitoring Running Subagents)
- **Type:** official user-guide doc
- **Quote:** "The parent agent orchestrates its own running children with the same `delegate_task` tool it spawned them with — no separate control tool: `{\"action\": \"list\"} {\"action\": \"steer\", …} {\"action\": \"stop\", …}`" / "Programmatic hosts reach it through the session-scoped `subagent.steer` gateway RPC, which sits beside `subagent.interrupt`."
- **Tier:** Verified

**Match to target:** `delegate_task` is the strongest *agent-initiated* match (A's model spawns B with task+context, B runs independently, result re-enters A as a message/turn). Gaps vs Claude target: B is not a visible first-class session in the desktop session list (docs), B is ephemeral (no resume), and B's context is only what A writes in `goal`/`context`.

---

## 4. Kanban: per-card sessions

### 4.1 How a card becomes a session
- **Claim:** Each kanban task is executed by a worker that is "a full OS process with its own identity"; the gateway-embedded dispatcher "spawns assigned profiles" (spawning `hermes -p <assignee>` with a profile-scoped `HERMES_HOME`), sets `HERMES_KANBAN_TASK` in the child env, which flips on the dedicated `kanban_*` toolset. Worker sessions are tagged source `kanban` and are "hidden from session pickers"; the worker session is titled with the card name at spawn so `hermes sessions` and session search show the card.
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban (intro; Gateway-embedded dispatcher; How workers interact with the board; worker model section); https://hermes-agent.nousresearch.com/docs/user-guide/sessions (Session Sources)
- **Type:** official user-guide docs
- **Quote:** "Every task is a row in `~/.hermes/kanban.db`; every handoff is a row anyone can read and write; every worker is a full OS process with its own identity." / "When the dispatcher spawns a worker it sets `HERMES_KANBAN_TASK=t_abcd` in the child's env, and that env var flips on a dedicated **kanban toolset** in the model's schema." / "the dispatcher injects the profile-scoped `HERMES_HOME` when it spawns `hermes -p <assignee>`, so each worker reads its own profile's model settings" / "`kanban` | Kanban dispatcher workers (read on the board, hidden from session pickers)" / "…after its card (`Fix the swap modal`, or `Kanban task <id>` when the board row can't be read) at spawn, so `hermes sessions` and session search show the card, not a model's guess."
- **Tier:** Verified

### 4.2 Worker profile/model
- **Claim:** The assignee is a profile name; each worker profile has its own `config.yaml` under `~/.hermes/profiles/<name>/` with its own model settings (recommended: frontier orchestrator, cheap workers).
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban (worker model section)
- **Type:** official user-guide doc
- **Quote:** "Run your orchestrator/dispatcher profile on a frontier model and point worker profiles at inexpensive models. Each profile has its own `config.yaml` under `~/.hermes/profiles/<name>/`."
- **Tier:** Verified

### 4.3 Handoff (parent link)
- **Claim:** A parent link is the context-handoff channel from a completed card to a new one: the child's `worker_context` (what `kanban_show()` returns) contains a `## Parent task results` section with each parent's completion `summary` and `metadata` verbatim. Pattern: "a new child card, not reopening the done card".
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban (Handing context to follow-up cards (the parent link))
- **Type:** official user-guide doc
- **Quote:** "A parent link is not just a scheduling gate — it is the context handoff channel from a **completed** card to a new one. … The worker context assembled for the child (`build_worker_context`, what `kanban_show()` returns) contains a `## Parent task results` section with each parent's completion `summary` and `metadata`, verbatim."
- **Tier:** Verified

### 4.4 How completion reports back to the orchestrator
- **Claim:** When a task is created from a gateway chat (`/kanban create` or `kanban_create`), the originating chat is auto-subscribed (in `notify+wake` mode): on terminal events (`completed`, `blocked`, `gave_up`, `crashed`, `timed_out`, `review_requested`, `block_loop_detected`) the notifier delivers a passive message AND "a 'wake' forges a synthetic inbound message to the destination gateway agent so it takes a normal turn (reads the comment + result, reasons, replies)"; "When a `completed` or `review_requested` event carries a summary, that handoff rides the wake turn, so the woken agent sees what the worker actually did." Delivery modes: `notify` (passive), `notify+wake` (passive + agent turn), `wake` (agent turn only). Subscriptions can also be created explicitly via `hermes kanban notify-subscribe` (any chat, any profile, `--delivery-mode`). With `kanban.auto_subscribe_on_create: true`, "a task's terminal event resumes the originating agent with a synthetic status turn".
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban (Gateway notifications; Delivery modes; Auto vs Manual orchestration)
- **Type:** official user-guide doc
- **Quote:** "When you run `/kanban create …` from the gateway (Telegram, Discord, Slack, etc.), the originating chat is automatically subscribed to the new task. … Completed tasks also send the first line of the worker's `--result`" / "A \"wake\" forges a synthetic inbound message to the destination gateway agent so it takes a normal turn (reads the comment + result, reasons, replies) instead of getting a one-line passive notification." / "A chat-originated auto-subscribe is created in `notify+wake` mode: on a terminal event the destination agent both receives the passive message **and** takes a real turn, so it can read the board context and reply in its own voice."
- **Tier:** Verified

### 4.5 Visibility in desktop
- **Claim:** The Desktop Kanban plugin displays the board (Kanban tab; read-through-the-DB + write-through-kanban_db; live updates via WebSocket tailing `task_events`). "The Desktop Kanban plugin displays the board; it does not grant the chat agent permission to manage tasks." Dashboard plugin API exposes read-only worker-visibility endpoints: `GET /api/plugins/kanban/workers/active` (PID, profile, task id, started-at, last heartbeat), `GET /api/plugins/kanban/runs/{id}`.
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban (Dashboard (GUI); What the plugin gives you; Architecture; Worker visibility endpoints)
- **Type:** official user-guide doc
- **Quote:** "The Desktop Kanban plugin displays the board; it does not grant the chat agent permission to manage tasks." / "`GET /api/plugins/kanban/workers/active` | Currently spawned workers with PID, profile, task id, started-at, last heartbeat"
- **Tier:** Verified

**Match to target:** Kanban is the most durable "spawn B with task+context, report back to A" mechanism: B is a real OS process + real (hidden) session with its own profile/model, context flows via card body + parent-link handoff + comments, and completion wakes A's session with a synthetic turn carrying the result. Gaps: B's session is hidden from the session picker; the "spawn" is a card on a board (fire-and-forget), not a direct A→B call; reporting is event-driven via the notifier.

---

## 5. Bot Mode: named bots, bot-to-bot messaging

### 5.1 Bots = profiles with a canonical persistent session
- **Claim:** A Bot is a Hermes profile with one canonical, persistent **Bot Chat** session (titled exactly `Bot Chat`), created (and pinned) when the Bot is born; `/new` inside it is rerouted to `/compact`. Bot Chats are hidden from the global Sessions sidebar (shown in the Bots pane).
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode (The Bots pane; What actually makes a chat a Bot Chat); https://hermes-agent.nousresearch.com/docs/user-guide/desktop (Bot Mode (built in))
- **Type:** official user-guide docs
- **Quote:** "every Bot has a canonical, persistent **Bot Chat** conversation that is created (and pinned) the moment the Bot is born" / "Typing `/new` (or `/reset`) inside a Bot's canonical chat would fork the relationship into a scratch session — the one thing Bot Mode promises never happens. The composer reroutes it to `/compact` instead" / "Bot Mode's sessions … are always hidden from the global Sessions sidebar."
- **Tier:** Verified

### 5.2 Can a session spawn/message a bot's session?
- **Claim:** Yes — two documented paths: (a) **@mention handoff**: "type `@researcher have a look at this` in any chat … The Bot then composes its own message and sends it with `message_agent` — your text is never forwarded verbatim, and the reply comes back attributed to that agent"; (b) **`message_agent` tool**: "every Bot Chat carries the `message_agent` tool: a Bot messages a teammate by calling `message_agent(target=\"researcher\", message=\"…\")`". Delivery is per-invocation: "the receiving Bot picks the message up when it next runs. Live interrupt of a Bot mid-conversation is future work."
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode (Bot-to-bot messaging; What actually makes a chat a Bot Chat)
- **Type:** official user-guide doc
- **Quote:** "**@mentions** — type `@researcher have a look at this` in any chat … The Bot then composes its own message and sends it with `message_agent` … and the reply comes back attributed to that agent." / "Bot-to-bot delivery is per-invocation: the receiving Bot picks the message up when it next runs."
- **Tier:** Verified

### 5.3 Cross-machine: `hermes peer`
- **Claim:** `hermes peer dm <peer>` "delivers into the remote agent's canonical Bot Chat over the peer's existing API server, runs one agent turn there, and prints the reply on stdout"; `hermes peer run` returns a `run_id` for long tasks (poll with `peer status`, stop with `peer stop`); `message_agent` accepts peer targets (`spark/researcher`).
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode (Bot-initiated DMs across machines (`hermes peer`))
- **Type:** official user-guide doc
- **Quote:** "`hermes peer dm` delivers into the remote agent's canonical Bot Chat over the peer's existing API server, runs one agent turn there, and prints the reply on stdout — the exact cross-machine twin of the local `hermes -p <bot> chat` command."
- **Tier:** Verified

**Match to target:** Bot Mode is a "spawn + report" *substitute*: A's agent (or user) sends a task to a Bot's session; the Bot runs a turn in its own persistent session; the reply comes back attributed. Gaps: it targets an EXISTING canonical session (no new session is created), delivery is per-invocation (not a guaranteed live wake), and it requires the Bot Mode protocol markers (desktop-managed or hand-configured headless).

---

## 6. Subagent Lifecycle API (developer guide)

### 6.1 What it exposes
- **Claim:** Plugins can launch and supervise fresh Hermes child sessions programmatically — without importing `tools.delegate_tool`, gateway internals, or `AIAgent` fields. The service resolves its parent from the current agent turn, so it works in CLI, gateway, non-interactive, and kanban-worker sessions; launching outside an active agent turn fails closed with `No active Hermes parent session`.
- **Source:** https://hermes-agent.nousresearch.com/docs/developer-guide/subagent-lifecycle-api
- **Type:** official developer-guide doc
- **Quote:** "Plugins can launch and supervise fresh Hermes child sessions without importing `tools.delegate_tool`, gateway internals, TUI state, or `AIAgent` fields. The service resolves its parent from the current agent turn, so it works in CLI, gateway, non-interactive, and kanban-worker sessions. Launching outside an active agent turn fails closed with `No active Hermes parent session`."
- **Tier:** Verified

### 6.2 Launch parameters & control surface
- **Claim:** `SubagentLaunchRequest` accepts `goal`, `context`, `role`, `model`, `provider`, `allowed_toolsets`, `blocked_tools`, `working_directory`, `parent_session_id`, `correlation_id`, `metadata`, `timeout_seconds`. `SubagentHandle` is serializable; `status`/`wait`/`cancel`/`steer`/`result`/`reconnect` drive it. Stable states: `PENDING, STARTING, RUNNING, SUCCEEDED, FAILED, INTERRUPTED, CANCEL_REQUESTED, CANCELLED, UNKNOWN`. Terminal results are immutable, idempotent, bounded to 32k chars, omit transcripts/hidden reasoning, include a stable result hash.
- **Source:** https://hermes-agent.nousresearch.com/docs/developer-guide/subagent-lifecycle-api
- **Type:** official developer-guide doc
- **Quote:** "Requests accept `goal`, `context`, `role`, `model`, `provider`, `allowed_toolsets`, `blocked_tools`, `working_directory`, `parent_session_id`, `correlation_id`, `metadata`, and `timeout_seconds`" / "`SubagentHandle` is serializable and carries a versioned, opaque capability." / "Terminal results are immutable, idempotent, bounded to 32k characters, omit transcripts and hidden reasoning, and include a stable result hash."
- **Tier:** Verified

### 6.3 Relationship to delegate_task; durability limits
- **Claim:** "Child construction and completion use the same host-owned path as `delegate_task`, including parent tool-resolution restoration, memory notification, serialized `subagent_stop` hooks, resource cleanup, and child-cost rollup. It does not change the synchronous `delegate_task` tool, batch delegation, or its gateway/TUI display." Routing follows the `delegation` config; the request's `model` overrides it; provider precedence is request > delegation config > parent. Durability is in-process: "The initial implementation retains metadata and terminal results in-process for one hour. After a process restart, `reconnect` returns `RECONNECT_UNAVAILABLE` and never starts a replacement child."
- **Source:** https://hermes-agent.nousresearch.com/docs/developer-guide/subagent-lifecycle-api
- **Type:** official developer-guide doc
- **Quote:** "Child construction and completion use the same host-owned path as `delegate_task` …" / "The initial implementation retains metadata and terminal results in-process for one hour. After a process restart, `reconnect` returns `RECONNECT_UNAVAILABLE` and never starts a replacement child."
- **Tier:** Verified

**Match to target:** This is the only documented API where *external code (a plugin tool/hook running inside session A's turn)* can create a child session with `goal`+`context`+`parent_session_id`, wait/steer/cancel it, and collect a bounded result — i.e., the exact "A spawns B, B runs, result reports to A" contract, but for *subagent* (non-visible, in-process) sessions. It is the natural building block for a desktop-visible variant.

---

## 7. Session splitting on compression (parent session ID / lineage)

### 7.1 What it is
- **Claim:** When a session's context is compressed (manually `/compress` or automatically), Hermes creates a NEW continuation session linked by parent session ID; numbered titles (`"my project" → "my project #2" → "my project #3"`); resuming by name auto-picks the most recent lineage member. The `sessions` table stores "Parent session ID (for compression-triggered session splitting)". A compression child inherits the parent's source tag (and thus picker visibility).
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/sessions (Auto-Lineage on Compression; How Sessions Work; Session Sources)
- **Type:** official user-guide doc
- **Quote:** "When a session's context is compressed (manually via `/compress` or automatically), Hermes creates a new continuation session. If the original had a title, the new session automatically gets a numbered title: \"my project\" → \"my project #2\" → \"my project #3\". When you resume by name (`hermes -c \"my project\"`), it automatically picks the most recent session in the lineage." / "Parent session ID (for compression-triggered session splitting)" / "A session compressed mid-conversation continues under the same source: the compression child of a `--source tool` or `oneshot` run is tagged the same way, so it inherits the same picker visibility."
- **Tier:** Verified

### 7.2 User-visible / resumable
- **Claim:** Yes — the continuation is a normal session row (numbered title, resumable by name or id; `hermes sessions export --lineage logical` exports a whole compression lineage as one document). Desktop plugins see lineage via a durable id: "a live id is resolved to its durable lineage root, so pins and colours survive compression's id rotation" (`_lineage_root_id`).
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/sessions (Resume by Name; Export Sessions); https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk (Session rows)
- **Type:** official user-guide + developer-guide docs
- **Quote:** "Ids are STORED session ids: a live id is resolved to its durable lineage root, so pins and colours survive compression's id rotation"
- **Tier:** Verified

**Match to target:** Not a spawn mechanism (no task+context transfer, no report-back) — it's an internal continuation. Relevant only as evidence that parent/child session lineage is a first-class, user-visible concept in Hermes (numbered titles, lineage export, durable lineage root ids).

---

## 8. Webhooks / API server / cron: create a NEW session with a prompt, deliver result somewhere

### 8.1 Webhooks
- **Claim:** The webhook adapter accepts POST requests, validates HMAC, "transforms payloads into agent prompts, and routes responses back to the source or to another configured platform" — each event triggers a fresh agent run (session source `webhook`). Per-route `deliver` targets: `github_comment`, `telegram`, `discord`, `slack`, …, or `log` (default); `deliver_only` skips the agent; `cron_job` fires an existing cron job instead of a fresh session; `mirror_to_session` writes the delivered message into the target chat's session transcript "so when you reply in that chat the agent knows what it just sent you".
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/messaging/webhooks (intro; Route properties; Replying to a delivery)
- **Type:** official user-guide doc
- **Quote:** "The webhook adapter runs an HTTP server that accepts POST requests, validates HMAC signatures, transforms payloads into agent prompts, and routes responses back to the source or to another configured platform." / "`mirror_to_session` | Default `false`. When `true`, after a successful delivery to a chat platform the delivered message is also written into that chat's session transcript …"
- **Tier:** Verified

### 8.2 API server (REST) — the most direct programmatic "new session + prompt"
- **Claim:** The API server (enabled in this environment) exposes a Sessions API over REST: `POST /api/sessions` "Create an empty session"; `POST /api/sessions/{id}/fork` "Branch the session via `SessionDB` lineage (matches CLI `/branch` semantics)"; `POST /api/sessions/{id}/chat` "Run one synchronous agent turn"; `POST /api/sessions/{id}/chat/stream` (SSE). Plus `/v1/chat/completions` (stateless), `/v1/responses` with `previous_response_id` chaining and named `conversation` parameter ("multi-turn conversations appear as a single entry in the dashboard and session history"), and `X-Hermes-Session-Key` for memory scoping. Sessions created this way have source `api-server`.
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server (Sessions API; Named conversations; Endpoints)
- **Type:** official user-guide doc
- **Quote:** "| `POST` | `/api/sessions` | Create an empty session |" / "| `POST` | `/api/sessions/{id}/fork` | Branch the session via `SessionDB` lineage (matches CLI `/branch` semantics) |" / "| `POST` | `/api/sessions/{id}/chat` | Run one synchronous agent turn |" / "Chained requests also share the same session, so multi-turn conversations appear as a single entry in the dashboard and session history."
- **Tier:** Verified

### 8.3 TUI gateway JSON-RPC (the protocol desktop/TUI/dashboard speak)
- **Claim:** The TUI gateway JSON-RPC method catalog includes `session.create` (with per-session `model`/`provider` overrides, validated up front), `session.branch` (the Pi-spec `fork` equivalent), `prompt.submit`, `prompt.background`, `session.list`, `session.active_list`, `session.activate`, `session.close`, `session.interrupt`, `session.history`, `session.compress`, `session.title`, `delegation.status`, `subagent.interrupt`, `subagent.steer`, `spawn_tree.save / list / load`. "Within one authenticated gateway, resuming or activating a live session attaches another event subscriber rather than replacing the previous connection."
- **Source:** https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration (TUI Gateway JSON-RPC; Method catalog; Model overrides on session.create; Pi-style RPC mapping)
- **Type:** official developer-guide doc
- **Quote:** "prompt.submit prompt.background session.steer session.create session.list session.active_list session.activate session.close session.interrupt session.history session.compress session.branch … delegation.status subagent.interrupt subagent.steer spawn_tree.save / list / load" / "`session.create` accepts per-session `model` / `provider` overrides." / "| `fork` | `session.branch` |"
- **Tier:** Verified

### 8.4 Cron
- **Claim:** Cron jobs "run in fresh agent sessions with the normal static tool list" (source `cron`); one-shot or recurring; model resolution per-job pin → `cron.model` → main agent model. Delivery targets include `origin` (back to where the job was created), `local`, any platform, `all`, and **`bot-chat`** — "delivers the output **into a profile's canonical \"Bot Chat\" session as a real message** … the recipient here is the bot itself: it receives the output as an incoming message, acts on anything that needs action, and responds in its chat" (each delivery costs the target bot one full agent turn; `bot-chat:<profile>` targets another local profile). **Continuable jobs** (`cron.mirror_delivery` / `attach_to_session`) make the delivery a conversation you can reply into (thread-per-run or mirrored into the DM session). `context_from` chains one job's output into the next job's prompt; `no_agent` mode runs scripts with zero LLM. Webhook routes with `cron_job` set fire a cron job on external events.
- **Source:** https://hermes-agent.nousresearch.com/docs/user-guide/features/cron (What cron can do now; Delivery options; Bot Chat delivery; Continuable jobs; Chaining jobs with context_from); https://hermes-agent.nousresearch.com/docs/user-guide/messaging/webhooks (Event-Triggered Cron Jobs)
- **Type:** official user-guide docs
- **Quote:** "run in fresh agent sessions with the normal static tool list" / "`bot-chat` delivers the output **into a profile's canonical \"Bot Chat\" session as a real message**. … the recipient here is the bot itself: it receives the output as an incoming message, acts on anything that needs action, and responds in its chat." / "Cron jobs run in isolated sessions with no memory of previous runs. … The `context_from` parameter wires that connection automatically — Job B's prompt gets Job A's most recent output prepended as context at runtime."
- **Tier:** Verified

**Match to target:** API server (`POST /api/sessions` + `POST /api/sessions/{id}/chat`) and TUI-gateway `session.create`+`prompt.submit` are the most direct "create new session with prompt" primitives (external code, not an in-session agent). Cron `bot-chat` delivery + kanban `notify+wake` are the documented "result reports back into an agent's session as a real turn" mechanisms.

---

## 9. Gap analysis vs the Claude Desktop target

Target: agent in session A spawns a new **visible** session B with task + context; B runs independently; result reports back to A.

| Mechanism | A's agent initiates | New session | Visible in session list | Task+context transfer | Independent run | Report back to A |
|---|---|---|---|---|---|---|
| `delegate_task` | ✅ (model tool) | ✅ (source `subagent`) | ❌ (Subagents frame / `/agents` only) | ✅ goal+context fields | ✅ background, steerable | ✅ result re-enters A as a message |
| Subagent Lifecycle API (plugin) | ✅ (plugin tool/hook in A's turn) | ✅ child session | ❌ (same host path as delegate_task) | ✅ goal/context/parent_session_id | ✅ async, wait/steer/cancel | ✅ bounded result via `result(handle)` |
| `/bg` | ❌ (user command) | ✅ standalone session | ❌ (own task ID, not in history) | ❌ prompt only, no A context | ✅ | ✅ to same chat/terminal (not into A's agent context) |
| Kanban card | ✅ (`kanban_create` tool) or user/CLI | ✅ per-card worker session (source `kanban`) | ❌ hidden from pickers (board UI + worker endpoints) | ✅ card body + parent-link handoff + comments | ✅ full OS process, durable | ✅ `notify+wake` synthetic turn into originating session |
| Bot Mode `message_agent` / @mention | ✅ (tool) or user | ❌ targets existing canonical Bot Chat | ❌ hidden from Sessions sidebar | ✅ message text (bot composes) | ✅ per-invocation turn | ✅ reply attributed back to the chat |
| API server Sessions API | ❌ (external HTTP client) | ✅ (`POST /api/sessions`) | ✅ (source `api-server`; dashboard/session history) | ✅ via `POST …/chat` turn | ✅ | n/a (client polls/SSE) |
| TUI-gateway `session.create`+`prompt.submit` | ❌ (external host) | ✅ | ✅ | ✅ | ✅ | n/a (events to client) |
| Cron `bot-chat` / continuable | ❌ (schedule) | ✅ fresh session per run | ❌ (source `cron`) | ✅ prompt + skills + context_from | ✅ | ✅ into a Bot Chat as a real message/turn |
| Webhook agent run | ❌ (external event) | ✅ (source `webhook`) | ❌ | ✅ prompt template | ✅ | ✅ to configured deliver target |
| Compression split | ❌ (internal) | ✅ continuation | ✅ (numbered title) | summary of A | n/a | n/a |

**Bottom line:** No single documented mechanism exactly equals the Claude Desktop feature (agent-initiated + VISIBLE new session + task+context + report-back). The two closest are:
1. **`delegate_task` / Subagent Lifecycle API** — full A→B spawn with context and report-back, but B is a non-visible subagent session (ephemeral, not in the session list).
2. **API server / TUI-gateway `session.create` + prompt** — creates a real, visible, resumable session with a prompt, but is driven by an external client (a plugin could drive it: desktop plugin `host.request` is "the gateway JSON-RPC door: sessions … everything the app itself calls", and `ctx.runAction('session.new')` + `host.composer.submit('new', text)` is a documented desktop-plugin path to open a new chat and send a prompt).
A desktop plugin combining `host.request` (`session.create` with model/provider) + `prompt.submit` (or `session.new` + composer submit) + a kanban-style `notify+wake` or Subagent Lifecycle API result path is the documented building-block route to the target feature.

---

## 10. Searched, found nothing

1. **Desktop UI "new session with initial prompt" / "fork session" / "spawn from this session" action** — searched the entire desktop page for `fork`, `spawn`, `initial prompt`, `session.create`, `New session`: no such UI action, command, or Cmd-K palette entry is documented. (Fork exists only at gateway level: `session.branch` RPC, `POST /api/sessions/{id}/fork`, CLI `/branch`.)
2. **`/bg` on the desktop app** — the slash-commands registry lists `/bg` as working "in both the CLI and the messaging gateway"; the desktop docs never list `/bg` as a desktop chat command.
3. **`parent_session_id` column / `_delegate_from` marker on delegate_task session rows** — the delegation docs never name these; docs only confirm subagent sessions exist in `state.db` (source tag `subagent` in the orphan-reap list). The prior-research claim is unverified in docs.
4. **Delegate_task subagent sessions in the desktop session list** — no doc statement either way; all documented monitoring surfaces (Subagents frame, `/agents`, live transcript logs) treat subagents as children, not listable sessions.
5. **Desktop "Command Center" contents** — documented only as "**Agents** and **Command Center** — orchestration surfaces for multi-agent work" (one line, no detail).
6. **Concurrency cap for `/bg` tasks** — no documented limit (only the status-bar counter).
7. **A desktop UI to pin a model at session-creation time** — model picker is per-composer (per-session after first use), not a session-creation parameter in the UI docs (the RPC `session.create` does accept model/provider overrides).
8. **`/docs/user-guide/features/webhooks`** — 404; the webhooks doc lives at `/docs/user-guide/messaging/webhooks` (found via the cron page's cross-reference).
9. **Live interrupt of a Bot mid-conversation** — explicitly "future work" per bot-mode docs.
10. **Subagent Lifecycle API durability beyond one hour / across restarts** — explicitly not supported ("After a process restart, `reconnect` returns `RECONNECT_UNAVAILABLE`").

---

## Sources fetched (all official hermes-agent.nousresearch.com/docs)

- /docs/llms.txt (index)
- /docs/user-guide/desktop
- /docs/user-guide/sessions
- /docs/user-guide/messaging (incl. Background Sessions)
- /docs/user-guide/cli (incl. Background Sessions)
- /docs/user-guide/features/delegation
- /docs/user-guide/features/kanban
- /docs/user-guide/bot-mode
- /docs/developer-guide/subagent-lifecycle-api
- /docs/user-guide/multi-connection-desktop
- /docs/user-guide/messaging/webhooks
- /docs/user-guide/features/cron
- /docs/user-guide/features/api-server
- /docs/developer-guide/programmatic-integration
- /docs/developer-guide/desktop-plugin-sdk
- /docs/reference/slash-commands
