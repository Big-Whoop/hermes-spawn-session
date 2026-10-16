# Lane: GitHub Issues/PRs + Source Verification — session-spawning surface

Research date: 2026-10-16. Repo: github.com/NousResearch/hermes-agent.
Line refs are to **branch main** (verified 2026-10-16 via raw.githubusercontent.com single-file fetches; local v0.22.2 tree at /opt/hermes used for discovery, main line numbers cited). Tiers: **Verified** = page/code read directly.

---

## Part A — GitHub issues/PRs

### A1. Direct feature requests: agent-triggered session spawning / A2A

**A1.1** Claim: A feature request for agent-callable A2A session tools (`sessions_list` / `sessions_history` / `sessions_send` / `sessions_spawn`) exists and was **closed as completed** in favor of the A2A plugin (cross-machine, not local visible-session spawning).
- Issue: #8948 "feat: multi-agent A2A — sessions_list/history/send/spawn tools"
- URL: https://github.com/NousResearch/hermes-agent/issues/8948
- State: **closed (completed) 2026-06-08**; labels P3, comp/agent, tool/delegate, type/feature
- Verbatim (closing comment, teknium1, 2026-06-08): "Closing in favor of #41711, which consolidates the entire A2A protocol cluster into a single platform-adapter plugin with zero core edits. This issue contributed the sessions_list/history/send/spawn A2A tools request. Cross-agent discovery + messaging is now covered by the a2a_discover/a2a_call/a2a_list client tools and the inbound adapter in the consolidated plugin."
- Issue body (request): "Add A2A session tools: 1. sessions_list … 2. sessions_history … 3. sessions_send … 4. sessions_spawn (already exists as delegate_task, but could be enhanced with persistence)"
- Tier: **Verified**

**A1.2** Claim: The A2A plugin (merged) implements cross-machine agent-to-agent messaging as a **plugin with zero core edits** — the maintainer-endorsed pattern for this kind of feature.
- PR: #77109 "feat(a2a): Agent-to-Agent protocol plugin, A2A v1.0 (closes #514)"
- URL: https://github.com/NousResearch/hermes-agent/pull/77109
- State: **merged 2026-08-02** (API: state=closed, merged=true, merged_at=2026-08-02T22:10:16Z)
- Predecessor PR #41711 (same author, opened as draft) was **closed unmerged** and superseded by #77109.
- Verbatim (PR #41711 body, describing the merged design): "A single plugin — plugins/platforms/a2a/ — gives Hermes full A2A (Agent-to-Agent) protocol support in both directions with zero core edits … Outbound — client tools (a2a toolset): a2a_discover(url) … a2a_call(agent, message, context_id?) … a2a_list() … Inbound — platform adapter … Live-session injection … inbound tasks route through the normal MessageEvent → handle_message path keyed by the A2A contextId, so the agent that answers is the same one serving the user — full memory/context, not a clone."
- Verbatim (PR #41711, out of scope): "Local multi-agent orchestration / per-agent profiles … — a different problem (in-process delegation), left to their own threads"
- Tier: **Verified**

**A1.3** Claim: An **open, unmerged** PR by a collaborator adds agent tools for cross-session messaging between *local* sessions (`peer_sessions`, `peer_send`) — the closest existing implementation to "session A talks to session B". It is messaging, not spawning; it does not create sessions.
- PR: #106423 "feat(tools): peer session messaging — one session can warn or unblock another (inspired by Muse Code)"
- URL: https://github.com/NousResearch/hermes-agent/pull/106423
- State: **open** (API: state=open, merged=false, draft=false); author teknium1 (Collaborator), opened 2026-09-09
- Verbatim (PR body): "New opt-in peer_messaging toolset (hermes tools → Peer Messaging) with two tools: peer_sessions — lists the user's other recently active sessions (id, title, source, cwd, last activity) from the session store; the current session and ended sessions are excluded. peer_send — queues a message for an exact session id in a filesystem mailbox at $HERMES_HOME/runtime/peer_messages/<session>/ (0700 dir, atomic os.replace publish …). … Delivery rides the existing mid-turn steer channel. … a running peer gets the message mid-turn as an OUT-OF-BAND user row after the current tool batch; an idle session gets it at the start of its next turn. … Provenance is explicit. The injected text attributes the message to the sending session id and states it carries peer-agent — not user — authority."
- Verbatim (validation): "Live repro (before): On origin/main: registry.get_entry(\"peer_send\") → None; no peer_messaging toolset — no way for one session to message another"
- Tier: **Verified**

**A1.4** Claim: The most on-point open roadmap issue for the target feature (session A spawns/prompts session B with context, B reports back) is **#76221** — open, needs-decision, no PRs attached.
- Issue: #76221 "[Feature]: Roadmap Proposal: Multi-Session Collaboration for Hermes Agent"
- URL: https://github.com/NousResearch/hermes-agent/issues/76221
- State: **open**; labels P3, area/sessions, comp/agent, innovation, needs-decision, tool/delegate, type/feature; opened 2026-08-01 (echoflying)
- Verbatim (problem): "sessions are isolated islands. There is no native way for two sessions to: 1. Share a persistent, isolated context … 2. Send messages to each other (one session cannot prompt another) 3. Share state information … 4. Run simultaneously and communicate actively (not just parent-child delegation)"
- Verbatim (gap table): "delegate_task - persistent session | No. Each call is a fresh session, no memory … prompt.background - persistent | skip_memory=True, temp session_id … Session pairing / handshake | Does not exist"
- Verbatim (Path B proposal): "session.send RPC (Cross-Session Messaging) … Send a message to a target session and receive a reply. … 5. Append the exchange to the target session's history in state.db … 6. Return synchronously (wait=True) or emit session.complete (wait=False)" — plus `session.query` and `session.create_role` (create a persistent role session with persona/memory/model).
- Verbatim (user vote, barronlroth, 2026-09-11): "Adding a concrete user vote for Path B: one existing session prompting another while preserving the receiving session's context. … PR #106423 looks like a useful foundation. Its described idle-session behavior waits for the next turn; optional wake-on-delivery would make this much more useful for actual handoffs."
- Verbatim (AI triage, GottZ, 2026-08-02): "No pull requests currently address or reference #76221. The issue remains an open roadmap proposal …"
- Tier: **Verified**

**A1.5** Claim: A related A2A messaging feature request (agent-to-agent message bus for delegate_task groups) was closed as completed via the A2A plugin.
- Issue: #25176 "[Feature]: Multi-Agent Communication Channel (Agent-to-Agent Messaging)"
- URL: https://github.com/NousResearch/hermes-agent/issues/25176
- State: **closed (completed) 2026-06-08**
- Verbatim (request): "delegate_task spawns isolated subagents that work independently and report only to the parent. … many real-world workflows require agents to discuss, critique, iterate … I propose adding a lightweight message-passing layer to the delegation system …"
- Tier: **Verified**

### A2. /bg (background session) — requests, bugs, desktop

**A2.1** Claim: `/bg` on desktop had a real delivery bug (result never reached the originating conversation); it was **fixed 2026-09-26** by routing desktop /background through the dedicated `prompt.background` RPC with a `background.complete` event appended to the originating conversation.
- Issue: #97635 "Bug: /background results silently not delivered on desktop-originated sessions (response generated+persisted, no error)"
- URL: https://github.com/NousResearch/hermes-agent/issues/97635
- State: **closed (completed) 2026-10-06**
- Verbatim (refined symptom, reporter): "the background task response did arrive, but the desktop app surfaced it in a newly-opened chat/dialog, not in the conversation where /background was issued … Task runs in bg session bg_104613_385db3 (logged as platform=cli)"
- Verbatim (fix note, OutThisLife, 2026-10-06): "Fixed on main by PR #122859 (commit d73a542b777, merged 2026-09-26): /background now routes through the dedicated prompt.background RPC and the finished result is appended to the originating conversation when the background.complete gateway event arrives, instead of surfacing in an unlinked dialog."
- Tier: **Verified**

**A2.2** Claim: /bg sessions are one-shot and amnesiac — no reply channel; an open bug documents the misleading "You can continue chatting" banner, with a **draft** PR to fix the banner only.
- Issue: #123607 "Bug: /bg says 'You can continue chatting' but background tasks have no history and cannot be replied to"
- URL: https://github.com/NousResearch/hermes-agent/issues/123607
- State: **open**; linked PR #123634 (draft, open): "fix(cli): /bg banner no longer reads as a reply channel for the task"
- Verbatim (issue): "each /bg is a one-shot amnesiac with no reply channel. … /bg at :1978 constructs AIAgent(session_id=task_id) with no history and discards the thread on exit. A follow-up /bg referencing the first gets a blank agent that has no idea what's being discussed."
- Tier: **Verified**

**A2.3** Claim: Open feature request to make /bg sessions continuable (reply to the result message → continue the same background session) — i.e., "spawn with report + follow-up" for messaging platforms.
- Issue: #22191 "feat(gateway): continue Telegram background tasks from replies"
- URL: https://github.com/NousResearch/hermes-agent/issues/22191
- State: **open**; labels P3, comp/gateway, platform/telegram, type/feature
- Verbatim (request): "When Hermes delivers the final result of a Telegram /background / /bg task, replying to that result message should continue the same background task/session in the background. … Hermes should launch a background continuation using the prior background session/context plus the user's follow-up message."
- Tier: **Verified**

**A2.4** Claim: Historical /bg bugs (all closed/completed): /bg queued until active CLI turn finished (#75221, closed 2026-08-01); background tasks had no observable state (#8568, closed 2026-05-16). Open: /detach (run agent in background after CLI exit, #11347, open).
- URLs: https://github.com/NousResearch/hermes-agent/issues/75221 · https://github.com/NousResearch/hermes-agent/issues/8568 · https://github.com/NousResearch/hermes-agent/issues/11347
- States: #75221 closed (completed); #8568 closed (completed); #11347 open
- Verbatim (#11347, distinguishing /bg): "/background (/bg) — Runs a prompt in a separate background session, but the user stays in the current TUI. … don't cover this use case"
- Tier: **Verified**

### A3. session.create — bugs and extension requests (proves it is a live, client-facing RPC)

**A3.1** Claim: `session.create` is a real client-facing RPC with a parameter contract that has drifted between client and backend at least once (client/backend version-skew bug, fixed).
- Issue: #128971 "[Bug]: invalid params for session.create: cwd_explicit: Extra inputs are not permitted — the client and the Hermes backend are out of sync (different versions)"
- URL: https://github.com/NousResearch/hermes-agent/issues/128971
- State: **closed (completed) 2026-09-30**
- Tier: **Verified** (title + state via API; body not loaded)

**A3.2** Claim: Desktop "new chat" routing through session.create had profile-routing bugs (both fixed).
- Issue: #79005 "[Bug]: Desktop profile swap can route session.create to the wrong backend" — **closed (completed) 2026-09-02**; https://github.com/NousResearch/hermes-agent/issues/79005
- Issue: #124265 "Desktop: clicking '+' on a project while a chat is open still routes session.create to the wrong profile (incomplete fix for #79005)" — **closed (completed) 2026-09-28**; https://github.com/NousResearch/hermes-agent/issues/124265
- Tier: **Verified**

**A3.3** Claim: Open feature request for a **create-time route hook for plugins** (per-project default model on session.create) — i.e., plugins want to influence session creation.
- Issue: #125346 "[Feature]: Per-project default model route for new desktop chats (or a create-time route hook for plugins)"
- URL: https://github.com/NousResearch/hermes-agent/issues/125346
- State: **open**
- Verbatim (request): "An optional model, provider and reasoning_effort in project settings. The desktop sends them on session.create when a chat starts inside that project, unless the user explicitly picks something in the composer for that chat."
- Tier: **Verified**

### A4. Subagent lifecycle (plugin surface for spawning)

**A4.1** Claim: Open feature request to extend the plugin subagent lifecycle facade (steer, follow-up, effort/route) — confirms `ctx.subagent_lifecycle` is the plugin-facing spawn surface and is being evolved.
- Issue: #133212 "[Feature]: subagent_lifecycle v1.1 for plugin orchestrators: steer, host-isolation transport, then effort/route/follow-up on the facade"
- URL: https://github.com/NousResearch/hermes-agent/issues/133212
- State: **open**
- Verbatim: "The plugin gives the agent operator-defined teammates through five tools (teammates_roster, teammate_assign, teammate_check, teammate_message, teammate_stop). … On stock Hermes it uses only ctx.subagent_lifecycle, ctx.register_tool, plugin_db and the Kanban DB functions, and it feature-detects every item above."
- Tier: **Verified**

**A4.2** Claim: Open bug: plugin `SubagentLifecycleService.launch` bypasses delegation safety checks (pause, max_spawn_depth, one-shot child budget) — relevant if a plugin implements "spawn with report" via the lifecycle API.
- Issue: #131282 "[Bug]: plugin SubagentLifecycleService.launch ignores the delegation pause, max_spawn_depth and the one-shot child budget"
- URL: https://github.com/NousResearch/hermes-agent/issues/131282
- State: **open**
- Verbatim: "_build_child_agent only downgrades an at-limit child to a leaf, and the child keeps the parent's plugin toolsets, so a child can call the plugin tool again and launch a grandchild one level deeper … A plugin tool that calls ctx.subagent_lifecycle.launch(…)"
- Tier: **Verified**

**A4.3** Claim: Open (unmerged) PR adding a deterministic contract eval for the public subagent lifecycle API.
- PR: #102737 "test(evals): add deterministic subagent lifecycle contract"
- URL: https://github.com/NousResearch/hermes-agent/pull/102737
- State: **open** (merged=false)
- Tier: **Verified**

### A5. Desktop session UX (context for "visible session B")

**A5.1** Claim: Desktop multi-window/split-view for parallel session monitoring was implemented (closed completed 2026-09-13).
- Issue: #62806 "Desktop: Multi-window / split-view for parallel session monitoring" — **closed (completed)**; https://github.com/NousResearch/hermes-agent/issues/62806
- Verbatim (request): "The TUI lets you open multiple terminal windows, each running an independent Hermes session, so you can watch several agents working in real time …"
- Tier: **Verified**

**A5.2** Claim: Desktop "new session window reuses existing agent context" bug was fixed (session isolation, closed completed 2026-07-16).
- Issue: #65597 — **closed (completed)**; https://github.com/NousResearch/hermes-agent/issues/65597
- Verbatim (request): "A new session window should spawn an independent agent process with its own isolated session, so the agent …"
- Tier: **Verified**

**A5.3** Claim: Two desktop session-lifecycle requests were **declined** (not_planned): per-session workspace selection (#40297, closed 2026-07-14) and "start with a fresh session on launch" (#82641, closed 2026-09-02).
- URLs: https://github.com/NousResearch/hermes-agent/issues/40297 · https://github.com/NousResearch/hermes-agent/issues/82641
- Tier: **Verified** (state_reason=not_planned via API)

**A5.4** Claim: Open bug: plugin session state cannot follow /new or /reset (plugin-command scope binds no session id) — relevant to plugins tracking spawned sessions.
- Issue: #123245 "Plugin session state cannot follow /new or /reset: the plugin-command scope binds no session id"
- URL: https://github.com/NousResearch/hermes-agent/issues/123245
- State: **open**
- Tier: **Verified**

**A5.5** Claim: Open feature: carry last N messages into a new session on auto-reset; maintainer pointed to the built-in cross-session search tool instead.
- Issue: #5810 "Feature: Carry last N messages into new session on auto-reset" — **open**; https://github.com/NousResearch/hermes-agent/issues/5810
- Verbatim (maintainer reply): "Instead of adding context_carry logic, you can already solve this with snow_search — the built-in cross-session search tool."
- Tier: **Verified**

---

## Part B — Source verification (behavioral questions; line refs to main)

### B1. /bg implementation — which surfaces, what it does

**B1.1** Claim: `/bg` is implemented in **three** surfaces, each spawning a fresh AIAgent with a fresh `bg_*` session id; none forks the current context; the result is delivered back to the originating surface.

(a) CLI (TUI) — file `hermes_cli/cli_commands_mixin.py`, main line 1598:
```python
def _handle_background_command(self, cmd: str):
    """Handle /bg <prompt> — run a prompt in a separate background session (its own AIAgent
    on a thread); the result prints here without touching the active history."""
```
- task id minted as `bg_{HHMMSS}_{hex6}`; agent built with `session_id=task_id, platform="cli", side_agent=True, session_db=self._session_db` (main ~line 1630-1642; v0.22.2 lines 1653, 1672-1682); result printed into a side-result panel in the same terminal (`_side_worker`, daemon thread).
- Tier: **Verified**

(b) Gateway (messaging platforms) — file `gateway/slash_commands.py`, main line 828:
```python
async def _handle_background_command(self, event: MessageEvent) -> str:
    """Handle /bg <prompt> — run a prompt in a background thread with its own session; the
    result is sent to the same chat without touching the active session's history."""
```
- task id: `task_id = f"bg_{datetime.now().strftime('%H%M%S')}_{os.urandom(3).hex()}"` (main line 834).
- Execution: `gateway/run_turn.py` main line 483 `_run_background_task_inner` — "Execute a background agent task and deliver the result to the chat." Builds a fresh `AIAgent(... session_id=task_id, platform=platform_key ...)` (main line 531/549) and delivers via `await adapter.send(chat_id=source.chat_id, content=header + text_content, metadata=_thread_metadata)` (main line 581). Media (images/voice/video/docs) is also delivered.
- Tier: **Verified**

(c) Desktop/TUI — tui_gateway RPC `prompt.background` — file `tui_gateway/contracts/prompt_voice.py`, main line 234:
```python
method("prompt.background", params=SideAgentParams, result=TaskIdResult,
       doc="Run a task on a fresh agent in the background; the answer arrives as background.complete.")
```
- `SideAgentParams` = `SessionParams` + `text: str` (main line 223-224). Result: `TaskIdResult` — "The side agent runs detached; its answer lands on the parent session as an event carrying this task_id."
- Implementation `tui_gateway/methods_prompt.py` (v0.22.2 line 1094; same method on main): builds a fresh `AIAgent` on a daemon thread via `_spawn_side_agent(..., "background.complete", body)`; `_spawn_side_agent` (v0.22.2 line 1337) docstring: "Run body() on a daemon thread … its text — or error: <exc> — lands on parent as event with task_id (+ extra). Replies {task_id}." i.e., **the report-back is a `background.complete` event on the parent session** (event contract: `tui_gateway/contracts/events.py:475` — `event("background.complete", SideAgentCompletePayload, doc="A /background side agent finished.")`).
- Companion RPC `prompt.btw` (main line 236): "Side question over a snapshot of the live conversation; the answer arrives as btw.complete."
- Desktop /background was re-routed onto this RPC by PR #122859 (merged 2026-09-26, see A2.1) — before that, desktop /bg went through the CLI slash-worker path and the result surfaced in a wrong/new dialog.
- Tier: **Verified**

**B1.2** Claim: The TUI/desktop slash-command path (for commands not handled as RPCs) runs a persistent HermesCLI "slash worker" subprocess per session.
- File `tui_gateway/server.py` (v0.22.2 lines 255-341): "Persistent HermesCLI subprocess for slash commands." spawned as `-m tui_gateway.slash_worker --session-key <key>`; protocol: "reads JSON lines from stdin {id, command}, writes {id, ok, output|error} to stdout" (`tui_gateway/slash_worker.py` docstring).
- Tier: **Verified**

### B2. Gateway 'session.create' method — who can call it, parameters

**B2.1** Claim: `session.create` is a **tui_gateway JSON-RPC method** (the desktop/TUI gateway protocol, not the messaging gateway). Full parameter set:
- File `tui_gateway/contracts/sessions.py`, main lines 118-151:
```python
class SessionCreateParams(ProfileParams):
    cols: int | None = None
    source: str | None = None
    cwd: str | None = None
    # #52589: provenance for ``cwd`` — true only for a deliberate workspace pick;
    cwd_explicit: bool | None = None
    messages: list[SeedMessage] | None = None
    parent_session_id: str | None = None
    title: str | None = None
    model: str | None = None
    provider: str | None = None
    reasoning_effort: str | None = None
    fast: bool | None = None  # presence is the contract: omitted inherits, true pins priority, false pins normal
    service_tier: str | None = None
    close_on_disconnect: bool = False
    hidden: bool = False
    room_plumbing: bool = False
    follow_profile_config: bool = False
    # #65410: stable caller-chosen key so a retried create (response lost in
    # transit) returns the SAME session instead of a duplicate child.
    idempotency_key: str | None = None

method("session.create", params=SessionCreateParams, result=SessionCreateResult,
       doc="Mint a live session (agent builds after the reply); a DB row appears on the first prompt unless seeded.")
```
- So: **initial prompt** (via `messages` seed rows — `SeedMessage` with role/content, "only display_kind: 'hidden' is accepted from the wire"), **model/provider/reasoning_effort/fast/service_tier**, **cwd** (+cwd_explicit), **title**, **parent_session_id**, **hidden**, **idempotency_key**.
- Tier: **Verified**

**B2.2** Claim: Callers of `session.create`:
- **Desktop** (Electron) and **TUI** are tui_gateway clients. Desktop connects over WebSocket at `/api/ws` on the web server with credential auth; TUI over stdio (the Node TUI spawns the gateway as a child).
  - File `hermes_cli/web_server_chat.py` (v0.22.2 line 250): `_ws_auth_reason(ws)` — "Loopback / --insecure: legacy ?token= (constant-time compared) … or ?token= holding a user session access token (verified against the dashboard auth session …) — e.g. a token-mode Remote desktop connection."
  - File `tui_gateway/ws.py` (v0.22.2 lines 97-105): WSTransport carries `auth_identity` — "Server-verified identity from the WS-upgrade credential … RPC params can never populate it: sole identity authority for browser controllers and for the user_id the agent is built with."
  - Generated client contract: `apps/shared/src/gateway-contract.generated.ts:5489` — `'session.create': { params: SessionCreateParams; result: SessionCreateResult }` (confirms the desktop TS calls it via the JSON-RPC channel; `json-rpc-channel.test.ts:20` shows `channel.request('session.create', {...})`).
- **The gateway server itself** calls `session.create` for hosted-room member sessions, with `hidden: True`:
  - File `tui_gateway/hosted_room_server_rpc.py`, main lines 62-64:
  ```python
  return self._call("session.create", {
      "profile": profile, "title": title, "source": source, "hidden": True,
      "room_plumbing": True, "follow_profile_config": True, "close_on_disconnect": False})
  ```
- **Any client** that can authenticate to the WS endpoint (loopback token, dashboard session token, token-mode remote desktop) can call it — it is not desktop-UI-exclusive.
- **Agent tools: NO.** No built-in tool invokes `session.create` (see B3). The plugin-facing spawn surface is `ctx.subagent_lifecycle.launch` (B3.2), a different mechanism (subagent, not a general session).
- Tier: **Verified**

**B2.3** Claim: Branching RPCs exist alongside create (desktop "branch" feature):
- `session.branch` — `tui_gateway/contracts/sessions.py` main line 420: `doc="Fork a live session into a new stored child that shares the parent's history so far."` (params: name, count, idempotency_key)
- `session.branch_stored` — main line 173: `doc="Whole-session branch of a stored parent: the owning backend reads and copies the transcript, which never crosses the wire …"`
- `session.branch_whole` — main line 440: `doc="session.branch of the whole history without echoing the copied transcript back."`
- Tier: **Verified**

### B3. Built-in tool that lets the agent create a new session?

**B3.1** Claim: **No.** The core tool registry (scanned all `registry.register(name=…)` in tools/*.py) contains 44 tools; none creates a session. Full list: annotate_preview, browser_cdp, browser_dialog, browser_exec, browser_vault, clarify, close_terminal, computer_use, cronjob_manage, delegate_task, desktop_preview, desktop_project, drive_preview, execute_code, feishu_doc_read, focus_pane, gui_tour, image_generate, memory, patch, process_manage, react_to_message, read_file, read_terminal, read_window_below, search_files, session_search, set_theme, setup_beat, show_tip, skill_manage, skill_view, skills_list, terminal, text_to_speech, todo_list, video_analyze, video_generate, vision_analyze, web_extract, web_search, write_file, x_search.
- Closest surfaces: `delegate_task` (spawns subagent sessions — B4), `session_search` (read-only cross-session search), `cronjob_manage` (scheduled runs).
- Tier: **Verified**

**B3.2** Claim: The plugin-facing spawn surface is `ctx.subagent_lifecycle.launch` — launches a **subagent** (hidden session row), not a general visible session.
- File `agent/subagent_lifecycle.py`, main lines 49-61 (request) and 277 (launch):
```python
class SubagentLaunchRequest:
    goal: str
    context: Optional[str] = None
    role: str = "leaf"
    model: Optional[str] = None
    provider: Optional[str] = None
    allowed_toolsets: Optional[tuple[str, ...]] = None
    blocked_tools: tuple[str, ...] = ()
    working_directory: Optional[str] = None
    parent_session_id: Optional[str] = None
    correlation_id: Optional[str] = None
    metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    timeout_seconds: Optional[float] = None
```
- Module docstring (main line 1): "Public, plugin-safe lifecycle API for delegated Hermes subagents: immutable contracts, not AIAgent objects. Plugins obtain it via PluginContext.subagent_lifecycle."
- `launch()` (main line 277) builds the child via `tools.delegate_tool._build_child_preserving_parent_tools(...)` and returns a `SubagentHandle`; `status()` / `wait(handle, timeout_seconds=…)` / `cancel()` give the plugin the report-back (wait blocks on the child's future).
- Tier: **Verified**

### B4. Subagent session rows — visible in desktop session list?

**B4.1** Claim: Subagent sessions are marked at creation and **hidden from session pickers by default**; a profile config re-admits them.
- File `tools/delegate_tool.py`, main lines 317-320:
```python
# Sidebar marker: subagent sessions stay out of session pickers even when a
# parent delete orphans them (mirrors /branch's ``_branched_from``).
if parent_sid and getattr(child, "_session_init_model_config", None) is not None:
    child._session_init_model_config["_delegate_from"] = parent_sid
```
- Child construction (main ~line 284): `session_db=child_session_db, parent_session_id=parent_sid, request_overrides=request_overrides` — dedicated SessionDB handle, `side_agent=True`.
- Tier: **Verified**

**B4.2** Claim: The list filter hides `_delegate_from` rows (and compression continuations) but keeps branch/reset children; `session.list` takes `include_hidden` as an RPC param, while subagent visibility comes from the profile config `sessions.show_subagents` (not an RPC param).
- File `hermes_state_sessions.py`, main lines 113-128 (`_session_filter_where`):
```python
"""Shared ``sessions s`` WHERE builder so counts line up with listed rows. ``exclude_children``
hides sub-agent runs and compression continuations but keeps branch/reset children
(``_LISTABLE_CHILD_SQL``); ``include_subagents`` re-admits the sub-agent runs only
(``sessions.show_subagents``). Clause order is part of the SQL text contract."""
...
if exclude_children and include_subagents:
    where.append(f"({_LISTABLE_CHILD_SQL} OR {_delegate_from_json('s.model_config')} IS NOT NULL)")
elif exclude_children:
    where += [_LISTABLE_CHILD_SQL, f"{_delegate_from_json('s.model_config')} IS NULL"]
```
- File `tui_gateway/methods_session.py`, main lines 541-558 (`session.list`):
```python
# Over-fetch: per-source filtering + tip merging must not leave us short. ``include_hidden`` is for
# surfaces that OWN hidden sessions (Bots pane, pickers).
from hermes_cli.session_listing import show_subagent_sessions
# ``sessions.show_subagents`` (the store's own profile config) re-admits delegate runs (#97202).
db_path = getattr(db, "db_path", None)
include_subagents = bool(db_path) and show_subagent_sessions(Path(db_path).parent)
rows = _listing_rows(db, max(limit * 2, 200), include_hidden=_flag(params, "include_hidden"),
                     include_subagents=include_subagents)[:limit]
```
- The `hidden` column itself: `hermes_state_common.py` main line 465 — `hidden INTEGER NOT NULL DEFAULT 0` (sessions table, main lines 403-470; `parent_session_id TEXT` at line 421, FK at table end).
- Tier: **Verified**

### B5. Session splitting on compression — mechanism, visibility, resume

**B5.1** Claim: On compression, the session is **rotated**: the parent row is ended with `end_reason='compression'`, a new child session row is published with the compressed transcript, and the live agent is re-pointed to the child.
- File `agent/conversation_compression.py`, main line 3308:
```python
def _publish_rotated_compaction(
    agent: Any, messages: list, compressed: list, *, new_system_prompt: str, lease: _CompressionLease,
    old_session_id: str, compressed_user_turn_outcome: str,
) -> None:
    """Rotate the session: flush the parent, publish the child, re-point the agent. …"""
```
- main line 3341: `new_session_id = mint_session_id()`
- main line 3344: `agent._session_db.publish_compression_child(parent_session_id=old_session_id, child_session_id=new_session_id, source=…, model=agent.model, model_config=with_session_yolo(agent._session_init_model_config, old_session_id), system_prompt=new_system_prompt, messages=compressed, cwd=…, profile_name=…)`
- main line 3372: `agent.session_id = new_session_id`
- Parent-ended check: `hermes_state_compression.py` (v0.22.2 line 1440-1446): `_session_was_rotated_by_compression` — "return bool(session and session.get('ended_at') is not None and session.get('end_reason') == 'compression')"
- Tier: **Verified**

**B5.2** Claim: The compression child is **not user-visible as a separate row** in session listings — it is treated as a continuation of the parent's lineage (the list shows the tip).
- `hermes_state_sessions.py` main lines 118-121 (docstring quoted in B4.2): "exclude_children hides sub-agent runs and compression continuations but keeps branch/reset children".
- `hermes_state_compression.py` main line 779: `get_compression_tip(session_id)` — "Live tip of a compression chain (get_compression_chain semantics); the input id when no continuation exists."
- Tier: **Verified**

**B5.3** Claim: Resuming an old (pre-compression) session id lands on the live tip — i.e., compression splits are transparently resumable via `--resume`.
- File `hermes_cli/main.py` (v0.22.2 lines 1350-1367):
```python
def _resolve_session_by_name_or_id(name_or_id: str) -> Optional[str]:
    """Resolve a session title or ID to a session ID (None if neither matches).

    A compression root is followed forward to its latest continuation so an
    old root ID (exit summary, notes) resumes at the live tip.
    """
    ...
            # Project forward through compression chain so resumes land on
            # the live tip instead of a dead compressed parent.
            try:
                resolved_id = db.get_compression_tip(resolved_id) or resolved_id
```
- Tier: **Verified**

### B6. API server platform — HTTP endpoints for creating sessions / one-shot prompts

**B6.1** Claim: With `api_server` enabled, the gateway serves an OpenAI-compatible HTTP API (default port 8642) with **session creation, session forking, session chat, and one-shot runs** endpoints, all behind `API_SERVER_KEY` auth.
- File `gateway/platforms/api_server.py`, main:
  - Module docstring (line 1-7): "OpenAI-compatible API server platform adapter (aiohttp). Serves /v1/chat/completions, /v1/responses, /v1/models, /v1/capabilities, /api/sessions, /v1/runs, /api/jobs and /health* … any OpenAI-compatible frontend connects at http://localhost:8642/v1 with API_SERVER_KEY."
  - Capability table, main lines 71-96 (feature flags + endpoints):
  ```python
  "session_chat_streaming": True, "session_fork": True, "session_model_lock": True,
  ...
  ("sessions", ("GET", "/api/sessions")),
  ("session_create", ("POST", "/api/sessions")),
  ("session", ("GET", "/api/sessions/{session_id}")),
  ("session_update", ("PATCH", "/api/sessions/{session_id}")),
  ("session_delete", ("DELETE", "/api/sessions/{session_id}")),
  ("session_messages", ("GET", "/api/sessions/{session_id}/messages")),
  ("session_fork", ("POST", "/api/sessions/{session_id}/fork")),
  ("session_chat", ("POST", "/api/sessions/{session_id}/chat")),
  ("session_chat_stream", ("POST", "/api/sessions/{session_id}/chat/stream")),
  ("session_model_lock", ("POST", "/api/sessions/{session_id}/model")),
  ```
  - Auth: `@_require_auth` on the handlers (main line 3067 above `_handle_create_session`); key resolution main line ~1190 (v0.22.2 line 1196): `self._api_key: str = extra.get("key", _get_scoped_secret("API_SERVER_KEY", ""))`.
- Tier: **Verified**

**B6.2** Claim: `POST /api/sessions` creates an **empty** session row (no prompt execution).
- File `gateway/platforms/api_server.py`, main line 3068:
```python
async def _handle_create_session(self, request: web.Request) -> web.Response:
    """POST /api/sessions -- create an empty Hermes session row. Existence check, insert and
    title handling run as ONE off-loop write so concurrent same-id creates can't both 201."""
```
- Body fields: `id`/`session_id` (optional; default `api_{ts}_{hex8}`), `system_prompt`, `source` (default "api_server"), model/provider (runtime lock), `title`. Returns 201 with the session object; 409 on duplicate id.
- Tier: **Verified**

**B6.3** Claim: `POST /api/sessions/{id}/fork` is a **destructive fork** with CLI /branch semantics: child created first, then the source is ended as "branched"; all messages copied to the child.
- File `gateway/platforms/api_server.py`, main line 3260:
```python
async def _handle_fork_session(self, request: web.Request) -> web.Response:
    """POST /api/sessions/{session_id}/fork — branch via current SessionDB primitives."""
```
- Verbatim (main lines ~3276-3286, v0.22.2 lines 3322-3333):
```python
# CLI /branch semantics: create the child, then end the original as branched (child first, so
# a failed create never leaves the source ended with no fork, #11030).
# ``_branched_from`` is the durable branch marker (same as CLI /branch): …
await asyncio.to_thread(
    db.create_session, fork_id, "api_server", model=source.get("model"),
    system_prompt=source.get("system_prompt"), parent_session_id=source_id,
    model_config={"_branched_from": source_id})
await asyncio.to_thread(db.end_session, source_id, "branched")
messages = await asyncio.to_thread(db.get_messages, source_id)
await asyncio.to_thread(db.replace_messages, fork_id, messages)
```
- Tier: **Verified**

**B6.4** Claim: One-shot prompt execution surfaces: `POST /v1/runs` ("start an agent run, return run_id immediately"; SSE events at `/v1/runs/{run_id}/events`; steer/stop/approval endpoints) and `POST /api/sessions/{id}/chat[/stream]` (run a prompt inside an existing session; `_prepare_session_chat` at v0.22.2 line 3347: "Shared prelude for /api/sessions/{id}/chat[/stream]: header/body validation, then runtime selection …").
- File `gateway/platforms/api_server_runs.py` (v0.22.2 line 620): `"""POST /v1/runs — start an agent run, return run_id immediately."""`
- Tier: **Verified**

**B6.5** Claim: The messaging-gateway `/branch` slash command (user-triggered fork) creates the child with the durable `_branched_from` marker and, on thread-capable platforms, opens a sibling thread bound to the clone.
- File `gateway/slash_commands_session.py`, main line 1021:
```python
async def _handle_branch_command(self, event: MessageEvent) -> str:
    """Handle /branch [--here] [name] — fork the current session into an independent copy.

    Thread-capable platforms (Discord/Telegram/Slack/Matrix) open a NEW sibling thread bound
    to the clone and leave this chat on the original session; ``--here`` (and every platform
    without threads) switches the current chat onto the clone instead (#66023).
    """
```
- Child creation (main line 1075): `model_config={"_branched_from": parent_session_id}, parent_session_id=parent_session_id, …` — "``_branched_from`` keeps the branch visible in /resume and /sessions after the parent is reopened and re-ended."
- Tier: **Verified**

---

## Synthesis for the target feature (agent in A spawns visible session B with task+context; B reports back to A)

1. **No built-in agent tool spawns a session today.** The agent's only spawn surface is `delegate_task` (subagent: hidden row, `_delegate_from` marker, final summary returns to parent) and, for plugins, `ctx.subagent_lifecycle.launch` (same mechanism, handle with wait/status/cancel). Both are *subagents*, not visible sessions.
2. **The plumbing for "spawn with report" already exists at three layers**, none exposed to the agent:
   - tui_gateway RPCs: `session.create` (seed messages, model, cwd, parent_session_id, hidden, idempotency_key) + `prompt.background` (fresh agent, result as `background.complete` event on the parent) + `session.branch*` (forks).
   - api_server HTTP: `POST /api/sessions` (create), `POST /api/sessions/{id}/fork` (destructive fork), `POST /api/sessions/{id}/chat[/stream]` (run prompt in session), `POST /v1/runs` (one-shot run with SSE).
   - CLI/gateway `/bg` (fresh `bg_*` session, result delivered to originating surface).
3. **Precedent for doing it as a plugin with zero core edits**: A2A plugin (#77109, merged 2026-08-02) and the open peer-messaging PR (#106423) both live entirely in plugins/ and use `ctx.register_tool` (+ platform adapter for A2A). A "spawn with report" plugin tool would most naturally call the api_server HTTP endpoints (create + chat, or fork + chat) or `ctx.subagent_lifecycle.launch` if a hidden subagent is acceptable.
4. **Open demand signals**: #76221 (roadmap, needs-decision, user votes for Path B cross-session messaging), #22191 (/bg continuation), #125346 (create-time plugin hook), #133212 (subagent_lifecycle v1.1). No open issue/PR implements the exact Claude-Desktop-style "spawn visible session B, report back to A" — that gap is unclaimed.

## Searched, found nothing

- No merged PR adding an agent-callable "spawn new visible session" tool (closest: #106423 peer messaging, still open; it messages, does not spawn).
- No issue/PR titled or scoped as "spawn with report" / "agent in session A spawns visible session B that reports back" (the exact Claude-Desktop analog) — nearest are #76221, #8948 (→A2A plugin), #22191.
- No "session splitting" issues in NousResearch/hermes-agent (the phrase appears only in third-party nesquena/hermes-webui#1004, which references the same `parent_session_id` mechanism verified in B5).
- No desktop-specific /bg feature request (it exists via `prompt.background`; the desktop delivery bug #97635 is fixed).
- No PR implementing session creation from a slash command beyond the existing `/branch` fork (no `/spawn` command exists in gateway or CLI).
- No session-creation surface in the core tool registry (44 tools scanned).
- No `session.send` / `session.create_role` / `session.pair` RPCs implemented (proposed only in #76221).
- gh CLI unauthenticated: PR/issue states verified via public REST API (api.github.com) instead; code-search API unavailable (auth required) — mitigated by local tree + raw file fetches.

## Caveats

- Line refs are to main as of 2026-10-16; the local v0.22.2 tree (/opt/hermes) differs slightly (e.g., gateway/run_turn.py was restructured: `_run_background_task_inner` at v0.22.2:2411 vs main:483). Where I cite v0.22.2 line numbers, they are marked.
- Desktop TS source (apps/desktop) is not present in the /opt/hermes install (only apps/shared); desktop-side behavior was verified via the generated contract (apps/shared/src/gateway-contract.generated.ts) and issue #97635's fix note (which names apps/desktop/src/app/session/hooks/use-prompt-actions/slash.ts).
- Issue bodies for #128971/#124265/#79005 were verified via API title+state only (not full text).
