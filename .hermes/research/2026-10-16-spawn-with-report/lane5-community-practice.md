# Research Lane: COMMUNITY & PRACTICE — Multi-session orchestration in Hermes + reports on Claude's session-spawning feature

**Scope:** Community/practice sources only (Reddit, Hacker News, X, blogs, GitHub issues). Official docs are owned by other lanes.
**Method:** web_search + web_extract; Reddit read via www (worked) and saved full-text.
**Date of research:** 2026-10-16.
**Tier key:** `Plausible` = community report (multi-source or detailed); `Speculative` = single anecdote; `Authoritative` = official/vendor (Anthropic blog, official @ClaudeOfficial Reddit, docs) or user-filed issue in the official `anthropics/claude-code` repo with a concrete repro (treated as high-confidence community evidence of shipped behavior).

---

## PART A — How Hermes users actually run sub-problems in separate sessions today

### A1. `delegate_task` (synchronous subagents) — the default, "disposable clone"
- **Claim:** Hermes's built-in subagent mechanism is `delegate_task`; it runs up to ~10 children in parallel, each with its own context + terminal, and is *synchronous* (parent blocks until children finish). Community frames it as ephemeral, not persistent.
- **Source:** https://www.reddit.com/r/hermesagent/comments/1uvzqim/subagents/ (reddit) + https://agentbuildershq.com/blog/hermes-agent-multiple-agents-one-window (blog)
- **Verbatim (u/Xiaomin4114, r/hermesagent):** "subagents in Hermes are automatic and ephemeral. you just tell the agent 'hey, instead of doing the task yourself, spin up a subagent to do it. and then once the subagent is done, it stops ... you're trying to treat it like a mini Hermes, like a helpful pet. when in fact it's more like a disposable clone. nobody installs a 'subagent' in their Hermes. at best their skill just says 'ok but use a subagent for this' ... PROFILES on the other hand, especially with the kanban tools, makes more sense ... Hermes profiles work more like Claude subagents."
- **Verbatim (agentbuildershq.com, checked vs v0.21.3):** "Subagents: the main agent calls its delegate_task tool and runs up to 10 child agents in parallel by default, each with its own context and terminal."
- **Tier:** Plausible (multiple independent sources agree).

### A2. `async_delegation` (async subagents, shipped June 2026) — non-blocking, returns `task_id`
- **Claim:** Nous shipped an `async_delegation` toolset (GitHub issue #5586, ~June 16 2026) so delegated work no longer blocks the parent. Six lifecycle tools: `delegate_task_async` (spawn, returns `task_id`), `check_task`, `steer_task`, `collect_task`, `cancel_task`, `list_tasks`. TUI exposes an `/agents` overlay (alias `/tasks`). **Limitation: single-session only — in-process, not durable across restarts/new turns** (cross-turn persistence tracked under ACP #4949).
- **Source:** https://the-agent-report.com/2026/06/hermes-async-subagents-june2026/ (blog) + https://www.reddit.com/r/hermesagent/comments/1u88xbb/hermes_agent_ships_asynchronous_subagents/ (reddit)
- **Verbatim (the-agent-report.com):** "On June 16, Nous Research shipped the `async_delegation` toolset (tracked in GitHub issue #5586). Background agents now run as in-process threads ... The parent receives a `task_id` immediately and stays responsive. ... Async subagents are single-session only — they run in-process and are not durable across restarts or new chat turns. ... The Hermes TUI already exposes an `/agents` overlay (aliased `/tasks`) showing running and finished subagents."
- **Verbatim (u/docdavkitty, r/hermesagent):** "The new `async_delegation` toolset returns a `task_id` immediately — parent chats stay responsive while background agents run research, refactors, and builds in parallel. 6 new lifecycle tools in Hermes Agent: spawn, check, steer, collect, cancel, and list — all non-blocking."
- **Verbatim (u/stuckinmotion, comment):** "What's the difference between this and using the kanban features? those were already background async I think?"
- **Tier:** Plausible (blog cites official issue + docs; corroborated by community thread).

### A3. `/bg` (background session) + TUI live-session switcher
- **Claim:** Besides subagents, Hermes offers `/bg` to start a separate agent on a side task while you keep chatting, and a TUI session switcher (`hermes --tui`) to keep several full conversations open in one terminal and jump between them.
- **Source:** https://agentbuildershq.com/blog/hermes-agent-multiple-agents-one-window (blog)
- **Verbatim:** "It gives you three ways to put more than one agent to work from a single window. Subagents ... Background sessions: /bg starts a separate agent on a side task while you keep chatting. Live sessions: the TUI session switcher keeps several full conversations open in one terminal and lets you jump between them. ... The subagent dock, the roster, and /bg work in the classic CLI and the TUI. The live session switcher ... is a TUI feature, started with hermes --tui."
- **Tier:** Plausible (third-party tutorial, version-checked against v0.21.3).

### A4. Kanban board — the durable, cross-agent coordination primitive (dispatcher spawns workers)
- **Claim:** The community's "official multi-agent coordination primitive" is the Kanban board (SQLite-backed, shared across profiles). A dispatcher running in the gateway polls (default 60s), reclaims stale claims, promotes ready tasks, and **spawns assigned profiles as workers** that get `kanban_*` tools. Workspace types: `scratch` (deleted on completion), `dir:<path>` (preserved), `worktree` (git worktree, preserved).
- **Source:** https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june/ (reddit, mod-curated megathread sourced from 14+ threads)
- **Verbatim (megathread):** "🥇 Pattern 1: Kanban Board (Shared Task Queue) — The official multi-agent coordination primitive. A durable SQLite-backed task board shared across all profiles. ... **Why Kanban beats delegate_task for durable work:** Durability: Lost if parent is interrupted [delegate_task] vs Durable; survives restarts [Kanban]. Human in loop: Not supported mid-task vs Supported via comments, block/unblock, reassignment. ... **Kanban + profiles = a team:** Research agent reads docs, writes findings as comments; Coder agent picks up the task, implements based on findings; Review agent claims next, runs tests, comments review notes; Human approves or sends back with a comment."
- **Verbatim (dispatcher section):** "The Kanban dispatcher runs inside the Hermes gateway and polls every N seconds (default 60): 1. Reclaims stale claims (agent died mid-task) 2. Promotes ready tasks (all parent tasks done → promote) 3. Spawns assigned profiles as workers 4. Workers get `kanban_*` tools to interact with the board."
- **Verbatim (Kanban vs delegate_task):** "Use delegate_task when: Parent needs answer to continue / No humans involved / Result goes into parent's context / Short reasoning task (<50 turns) / Parallel research or code review. Use Kanban when: Work crosses agent boundaries / Might need human input / Needs to survive restarts / Multiple agents over task lifetime / Scheduled recurring work."
- **Tier:** Plausible (mod-curated community megathread; consistent with native feature).

### A5. Profiles — persistent, isolated agents (the "team"), not subagents
- **Claim:** Profiles are the primary *persistent* multi-agent primitive: each is a separate Hermes home (own config.yaml, .env, SOUL.md, memories, sessions, skills, cron, gateway state). Community consensus: profiles = the team; delegate_task = disposable expert. Profiles do NOT sandbox the filesystem.
- **Source:** https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june/ (reddit) + https://www.reddit.com/r/hermesagent/comments/1t29ogw/one_month_with_hermes_agent_what_i_wish_i_knew/ (reddit)
- **Verbatim (megathread FAQ):** "Should I use profiles or delegate_task? A: Profiles = persistent agents with memory and identity. Delegate_task = disposable subagents for one-off reasoning. They're complementary — profiles are the team, delegate_task is consulting an expert for a quick opinion."
- **Verbatim (megathread):** "Profiles are the primary multi-agent primitive in Hermes. Each profile is a separate Hermes home directory with its own config.yaml, .env, SOUL.md, memories, sessions, skills, cron jobs, and gateway state. ... Profiles do NOT sandbox the agent on host installs. The agent still has your user's filesystem access. Profiles isolate Hermes state, not OS access."
- **Verbatim (u/itsdodobitch, one-month thread):** "The second thing I wish I understood earlier: profiles are not just a convenience feature. They are one of the cleanest ways to keep Hermes useful. ... A research profile should not necessarily behave like a coding profile."
- **Tier:** Plausible.

### A6. Telegram topics = one bot, many sessions/profiles (session-per-workstream)
- **Claim:** A common pattern routes different Telegram forum topics to different profiles (or different sessions) using a single bot token. One user explicitly wants "one agent, one bot, a session per topic/workstream."
- **Source:** https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june/ (reddit) + https://www.reddit.com/r/hermesagent/comments/1x6qgz1/hermes_sessions_should_be_able_to_send_messages/ (reddit)
- **Verbatim (megathread):** "🥉 Pattern 3: Telegram Topics (One Bot, Multiple Profiles) — Route different Telegram topics to different Hermes profiles using a single bot token: Topic 1 (Personal) → default profile; Topic 2 (Work) → work profile; Topic 3 (Coding) → coder profile."
- **Verbatim (u/barronlroth, r/hermesagent):** "the reason i'm session-first is telegram. forum topics are the best bot UI telegram has, and a forum is one bot across many topics. so for me the natural setup is one agent, one bot, a session per topic / workstream."
- **Tier:** Plausible.

### A7. `hermes -p <profile> chat -c <topic>` / `hermes -z` one-shot — the "consult" + "one-shot" dispatch pattern
- **Claim:** Power users script an orchestrator's SOUL.md to dispatch to other profiles/sessions via CLI: Kanban card for multi-stage work, `hermes -p <profile> chat -c "consult-<topic>" --create-if-missing -Q --query-file -` for consults (persistent named thread, follow-ups reuse same `-c`), and `hermes -p <p> -z "text"` for small self-contained one-shots. Also `hermes --provider X --model Y --oneshot PROMPT` to spawn a temporary instance with a different model.
- **Source:** https://www.reddit.com/r/hermesagent/comments/1x6qgz1/hermes_sessions_should_be_able_to_send_messages/ (reddit) + https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june/ (reddit)
- **Verbatim (u/gdshadow02, "From my dispatchers SOUL"):** "Card (Kanban; load its skill first): substantial, multi-specialist/multi-stage. Assignee = specialist; body = outcome, context, constraints, dependencies. Consult (Need answers or safe actions): hermes -p <profile> chat -c \"consult-<topic>\" --create-if-missing -Q --query-file -. Include everything needed in the query. Follow-ups on the same topic: same -c. One-shot hermes -p <p> -z \"text\": small self-contained action. Execution only (auto-approves in target). Persistent dispatch thread: create via chat as above, continue with -c <name> -z \"…\"."
- **Verbatim (megathread):** "you can still have the agent use that oneshot command with a model/provider override instead like hermes --provider openai --model gpt-5.5 --oneshot PROMPT which would spawn a temporary instance of the same agent for the new task, but with a different model loaded."
- **Tier:** Plausible (detailed, reproducible community pattern).

### A8. Bot Mode — persistent specialist bots that can message each other (agent-to-agent handoffs)
- **Claim:** Hermes "Bot Mode" gives profiles persistent bot identities (own role, tools, skills, memory, conversation) that can hand off work to each other (Human → A → B → C → Human). It is NOT a DAG engine and does not guarantee parallel execution; for structured/dependent work the community still leans Kanban.
- **Source:** https://www.reddit.com/r/hermesagent/comments/1vrrx9v/i_tested_new_hermes_bot_mode_plugin_heres_what/ (reddit)
- **Verbatim (u/viky_shetye):** "I only gave the task to the Researcher. The Researcher gathered the evidence and handed it to the Risk Analyst. The Risk Analyst reviewed it and was supposed to hand the result to the Thesis Editor. So instead of: Human → Agent A → Human → Agent B → Human → Agent C, I was testing: Human → Agent A → Agent B → Agent C → Human. And for the most part, it worked. ... What I like about Bot Mode is that the agents aren't just invisible calls in a workflow. Each bot has its own identity, role, tools, skills, memory, and persistent conversation, so you can actually inspect what each specialist is doing. But ... It's also not a full workflow/DAG engine, and the handoffs don't mean you're getting guaranteed parallel execution. ... 🧠 Hermes Profiles = specialized isolated brains; 👥 Bot Mode = gives those brains identities, persistent rooms, and communication; 🗂️ Hermes Kanban = better when you need structured tasks, dependencies, and project orchestration."
- **Tier:** Plausible (single detailed showcase, but concrete).

### A9. tmux + separate Hermes instances / `hermes chat -q` subprocesses
- **Claim:** Users run multiple independent Hermes processes (separate sessions/tools/environments) as subprocesses, using tmux for interactive spawning and `-w` worktree mode to avoid git conflicts. (Docs-first lane covers the exact commands; this is the community/practice signal.)
- **Source:** https://www.cuckoom.com/en/2026/07/09/en-hermes-agent-complete-guide/ (blog) + https://github.com/asheshgoplani/agent-deck/issues/2582 (github)
- **Verbatim (cuckoom.com):** "Run multiple interactive Hermes instances via tmux: Use -w (worktree mode) to avoid git conflicts when multiple Agents edit the same repository."
- **Verbatim (agent-deck issue #2582):** "I run several independent Hermes sessions in Agent Deck, all using the same project directory. After a ma[restart]..." (bug: restart resumes another session when multiple sessions share a workspace).
- **Tier:** Plausible.

### A10. Hermes orchestrating Claude Code (claude-code-acp skill)
- **Claim:** Some users install Claude Code locally and have Hermes create a `claude-code-acp` skill (using `claude -p`) to "orchestrate an agentic team of claude code agents."
- **Source:** https://www.reddit.com/r/hermesagent/comments/1uvzqim/subagents/ (reddit)
- **Verbatim (u/EnigmaCrypto):** "Install claude code locally on hermes terminal and then have it create a claude-code-acp skill using claude -p and then prompt it like 'orchestrate an agentic team of claude code agents to do xyz'."
- **Tier:** Speculative (single comment, no outcome reported).

### A11. Voice-driven parallel sessions (HermesWhisper)
- **Claim:** A community tool (HermesWhisper) connects a Mac dictation app to the Hermes API with always-on-top response windows; hotkey fires a task, and if no response window is open it "start[s] a brand-new parallel Hermes session."
- **Source:** https://www.reddit.com/r/hermesagent/comments/1t7vpvg/hermeswhisper_an_ai_voice_dictation_app_to_manage/ (reddit)
- **Verbatim (u/Slumdog_8):** "I wanted something that could sit quietly in the background while I stayed in flow, letting me fire off and manage parallel agent tasks by voice while I kept working. ... When the response is ready, an always-on-top window appears. Hit the hotkey again to reply directly to that response window, or, if no response window is open, start a brand-new parallel Hermes session."
- **Tier:** Plausible (single author, but open-sourced with demo).

### A12. 24/7 orchestrator: cron + `/goal` + task-list that spawns sessions
- **Claim:** For long-running autonomous work, users run a main orchestrator that adds/checks tasks on a schedule (cron every ~10 min) and spawns a session to keep moving if none is on the task; `/goal` is used for long tasks but users report it still stops after ~an hour.
- **Source:** https://www.reddit.com/r/hermesagent/comments/1tdbmm6/how_can_you_have_agent_work_247_without/ (reddit)
- **Verbatim (OP u/ShufflinMuffin):** "I have long running task and I do not want him to ever stop. But it always stop after an hour or so. Even if I use /goal."
- **Verbatim (comment):** "I have the main agent orchestrate and add new tasks it runs every 10mins checking on everything and giving me updates if a task needs my attention. It'll check what's finished and create new tasks. This goes very well with the /goal command." / "You need some kind of task lists system that a cron checks and spawn a session to keep moving if no other session is on the task."
- **Tier:** Plausible.

---

## PART B — Community descriptions of Claude's session-spawning feature (corroboration for the other lane)

> **Bottom line for the target feature:** The Claude Desktop (Code tab) feature is the **`spawn_task` "task chip" mechanism** on the `ccd_session` MCP server. The agent in session A calls `spawn_task` with `title` + `prompt` (+ `tldr`); a chip appears; clicking it starts a **new visible session in the sidebar with its own git worktree** carrying the prepared prompt. This matches the user's German-UI description (session B titled after the sub-problem, structured task+context, "started by Claude from [parent]", running on "this computer"). The **missing piece the user "presumably" expects — the child reporting back to the parent — is explicitly an open, unmet request** (issues #95554, #80478, #71773).

### B1. `spawn_task` / task chips — the core desktop mechanism (with repros)
- **Claim:** In the desktop app, Claude calls `spawn_task` (title/prompt) → a "Suggested task" chip appears top-right → clicking it starts a new session with the prepared prompt in its own worktree. Related MCP tools: `dismiss_task`, `mcp__ccd_session_mgmt__list_sessions` (with `linked: true` = sessions started from this one).
- **Source:** https://github.com/anthropics/claude-code/issues/95554 (github, official repo) + https://github.com/anthropics/claude-code/issues/91820 (github, official repo)
- **Verbatim (#95554, tchwicewski99):** "When I work on a big implementation, I plan it in one Code-tab session and want each task executed in a fresh, clean-context session. The desktop app already supports the first step: Claude can create a 'Suggested task' chip via spawn_task, and clicking it starts a new session with the prepared prompt in its own worktree."
- **Verbatim (#91820, maverick-pkg, repro):** "1. In any desktop session, have Claude call `spawn_task` with any title/prompt. 2. Chip appears top-right. 3. Click it while the thread is open." / "Expected (per the desktop docs): clicking a spawned task chip starts that work in a new session with its own worktree, leaving the current session uninterrupted."
- **Verbatim (#91820, u/blwfish, traced repro 2026-09-25):** "`spawn_task` called with a title/prompt, returned `task_id: task_aeac18a5`. Chip appeared. ... ran `mcp__ccd_session_mgmt__list_sessions` with `linked: true` (sessions started from this one): 'No other sessions found.'"
- **Tier:** Authoritative (user-filed issues in the official repo, with tool names + repros; describes shipped behavior).

### B2. The reporting-back gap (parent can't see child status) — the "presumably reports back" is NOT there yet
- **Claim:** After the click, the planning/parent session has no visibility into the children: which started, running, needs input, done, or failed. The requested fix is a parent→child feedback loop (child's final summary delivered to parent as a tool result/message; read-only `list_spawned_tasks()` / `get_task_status(task_id)`).
- **Source:** https://github.com/anthropics/claude-code/issues/95554 (github, official repo)
- **Verbatim (#95554):** "The problem starts right after the click. The planning session has no idea what happened to the tasks it suggested. It cannot tell which chips were started, which are running, which are waiting for my input, which finished or failed. Neither can I, without opening every child session one by one. ... 2. When a child session finishes, its final summary (or a short tldr it writes back) is delivered to the parent session as a tool result / message, so the parent can update the plan and suggest the next task. 3. The ccd_session MCP server exposes read-only tools to the parent, e.g. list_spawned_tasks() and get_task_status(task_id) ... Related requests that were auto-closed as stale, not declined: #80478 (report back when done), #71773 (parent can observe its spawned children)."
- **Verbatim (#95554, use case):** "In session A I describe a feature; Claude produces a plan with 6 tasks and suggests each as a chip with a self-contained prompt. I click tasks 1–3. Each starts in its own fresh session/worktree. Back in session A, the chips show running. Task 2 hits a design question → chip shows needs input, I click through, answer, come back. Task 1 finishes; its summary appears in session A."
- **Tier:** Authoritative (official repo issue).

### B3. Programmatic (no-click) spawning is requested but not shipped; `start_session`/`hand_off_to_session` exist behind a flag
- **Claim:** Users want a session to start another session *without* a human click, still visible in the sidebar. The `ccd_session` MCP server reportedly already has `start_session` and `hand_off_to_session` next to `spawn_task`, but behind a server-side feature flag. `spawn_task` gives a real sidebar session but "needs a human click for each one."
- **Source:** https://github.com/anthropics/claude-code/issues/94697 (github, official repo; closed as dup of #89783)
- **Verbatim (#94697, jonathan-ngamboe):** "We want to start Claude Code sessions without a person clicking, and still have each one show up in the desktop sidebar as a real conversation. The visibility is the part we cannot give up. When an agent reaches a decision only a human can make, someone has to open that exact conversation and carry on from there. ... Expose `mcp__ccd_session__start_session` (and `hand_off_to_session`). They appear to exist already on the `ccd_session` MCP server, next to `spawn_task`, but behind a server-side feature flag (2371478310). With them, a session could start another session, get its id back, and the new session would show up in the sidebar like any other, with the parent able to stop or detach it. ... `spawn_task` does give a real sidebar session, but needs a human click for each one, which is the thing we are trying to remove."
- **Tier:** Authoritative (official repo issue).

### B4. Spawned tasks can be invisible / unstoppable (visibility gap)
- **Claim:** A task spawned via `mcp__ccd_session__spawn_task` and started by the user can become invisible: not in any session list, no `list_tasks`/`list_spawned_tasks` tool for the agent to get a `task_id`, and `/tasks` unavailable in that environment. The agent also may not honor the spawning session's instructions (e.g. CLAUDE.md).
- **Source:** https://github.com/anthropics/claude-code/issues/53494 (github, official repo; closed as not planned)
- **Verbatim (#53494, sakaal):** "A task spawned via `mcp__ccd_session__spawn_task` and started by the user becomes invisible: it does not appear anywhere in the desktop client, the spawning agent has no way to list it to obtain a `task_id`, and the documented `/tasks` slash command is not available in the environment. The task runs to completion silently and there is no path to inspect or stop it. ... 1. In an active session, the agent calls `mcp__ccd_session__spawn_task` with `title`, `prompt`, `tldr`. A chip appears in the UI. 2. User clicks the chip — task spawns to a fresh worktree. ... Additional finding: cloud-spawned agent doesn't honour the spawning session's instructions."
- **Tier:** Authoritative (official repo issue).

### B5. Agent View (CLI, v2.1.139, May 2026) — the dashboard + background sessions + worktrees + supervisor
- **Claim:** `claude agents` (Agent View, Research Preview) is a single list of all sessions; `claude --bg` / `/bg` start background sessions; each auto-uses a separate git worktree; an independent supervisor process (`claude daemon run --spawned-by xxxx`, PPID=1) keeps them running after the terminal closes. Rough edges: no branch status, no per-project filter (fixed in 2.1.141 via `--cwd`), can't set permission mode at dispatch.
- **Source:** https://www.reddit.com/r/ClaudeCode/comments/1tc3qjp/thoughts_on_claude_code_21139_agent_view/ (reddit) + https://www.reddit.com/r/ClaudeAI/comments/1tag1i9/new_in_claude_code_agent_view/ (reddit, official @ClaudeOfficial)
- **Verbatim (u/ctrlaltdeletel):** "Agent View can launch parallel Claude sessions directly, and each session automatically uses a separate git worktree for isolation, so multiple sessions can run in parallel without conflicts. The background sessions are managed by an independent supervisor process. They continue running even if the terminal or Agent View itself is closed. Closing the terminal does NOT stop the background sessions. ... `claude agents`, `claude --bg`, or `/bg` will spawn the supervisor. ... I do think it can partially replace tools like Conductor."
- **Verbatim (@ClaudeOfficial, official):** "One list of all your sessions, available today as a Research Preview. Run `claude agents` to start dispatching multiple sessions at once. Each one keeps running without taking up a terminal tab. See what's running, what's blocked on you, and what's done at a glance. Reply inline to unblock, or jump in and out of any session without losing your place."
- **Tier:** Authoritative (official announcement) + Plausible (detailed user report).

### B6. Agent Teams (Claude Code, ~Feb 2026) — "orchestrate teams of sessions"
- **Claim:** Anthropic released "Agent Teams" (docs: code.claude.com/docs/en/agent-teams) to orchestrate teams of Claude Code sessions; HN framed it as the long-rumored native "agent orchestrator" (Steve Yegge's "Kubernetes for agents" pitch).
- **Source:** https://news.ycombinator.com/item?id=46902368 (HN, 396 points)
- **Verbatim (HN, u/pronik):** "To the folks comparing this to GasTown: keep in mind that Steve Yegge explicitly pitched agent orchestrators to among others Anthropic months ago: 'I went to senior folks at companies like Temporal and Anthropic, telling them they should build an agent orchestrator, that Claude Code is just a building block, and it's going to be all about AI workflows and Kubernetes for agents.' ... That Anthropic releases Agent Teams now (as rumored a couple of weeks back) ..."
- **Tier:** Plausible (HN discussion of an official feature).

### B7. Cross-session messaging (Claude Code, ~Aug 2026) — sessions can message each other
- **Claim:** Claude Code added cross-session messaging (docs: code.claude.com/docs/en/cross-session-messaging); sessions can reference/message each other (e.g. after `/rename`). HN: security debate + "they just re-invented tmux send keys"; users note subagents are directly observable.
- **Source:** https://news.ycombinator.com/item?id=49222824 (HN, 173 points) + https://www.reddit.com/r/ClaudeAI/comments/1wtdyot/claude_code_can_message_easily_between_sessions/ (reddit)
- **Verbatim (HN, u/eigenblake):** "Like some others, I also built this myself. Overly simply, with tmux, a memory tree, and handoff files and an orchestrator. And yet for how simple it was, it was so effective at minimizing the amount of duplicate context. It's like having shared specialist subagents who source and derive important shared knowledge from separate threads."
- **Verbatim (HN, u/arceister):** "Oh, they just re-invented `tmux send keys` that I've been using."
- **Verbatim (r/ClaudeAI, u/...):** "If you do /rename you can give one of the Claude Code instances an actual name like my-feature then you can reference it in a regular prompt from the other session ... I start all of my coding sessions with a planning session using Fable in Cowork and then have it spin up opus sessions to execute the work in Claude Agents."
- **Tier:** Plausible (HN + reddit, describing an official feature).

### B8. Dispatch (Claude Cowork/Code, ~Oct 2026) — assign a task from phone/desktop; spins up the right session
- **Claim:** "Dispatch" lets you assign Claude a task from phone/desktop; Claude "figures out what kind of work is needed and spins up the right session" (dev → Claude Code, knowledge → Cowork); sessions appear in their sidebars. Community: it drafts a better prompt with a fast model and "orchestrates multiple Claude Code sessions at once if necessary ... without me asking." A GitHub issue notes Dispatch "spawns a new Cowork session for every task sent from mobile" (can't attach to existing).
- **Source:** https://claude.com/blog/dispatch-and-computer-use (official blog) + https://support.claude.com/en/articles/13947068-assign-tasks-from-anywhere-in-claude-cowork (official help) + https://www.reddit.com/r/ClaudeAI/comments/1svamh8/anyone_actually_using_dispatch_for_something/ (reddit) + https://github.com/anthropics/claude-code/issues/41273 (github)
- **Verbatim (official blog):** "Last week, we released Dispatch: a new feature in Claude Cowork (and now available in Claude Code) that lets you have one continuous conversation with Claude from your phone or your desktop. ... With Dispatch, you can tell Claude to automatically check your emails every morning or pull some metrics every week, or spin up a Claude Cowork or Claude Code session for a report or a pull request."
- **Verbatim (official help):** "When you assign a task, Claude figures out what kind of work is needed and spins up the right session. Development tasks run in Claude Code; knowledge work runs in Cowork. These sessions appear in their respective sidebars."
- **Verbatim (r/ClaudeAI):** "as far as I can tell Dispatch essentially takes my prompt, uses a general or fast Claude model to draft a better prompt without showing me, and then orchestrates multiple Claude Code sessions at once if necessary (or Cowork tasks, or managed agents, or whatever), without me asking."
- **Verbatim (github #41273):** "Dispatch currently spawns a new Cowork session for every task sent from mobile."
- **Tier:** Authoritative (official) + Plausible (community).

### B9. Recursive subagent spawning (the cost/visibility cautionary tale)
- **Claim:** Claude Code v2.1.172 (June 10 2026) let sub-agents spawn their own sub-agents up to 5 levels deep; the default `general-purpose` agent has the `Agent` tool so it recurses. One user's single research prompt spawned 339 sub-agent transcripts in ~10 min and burned the MAX 5-hour quota; 87% hit rate limits. No built-in guardrail to disable nested spawning.
- **Source:** https://www.reddit.com/r/ClaudeAI/comments/1u5d02w/til_claude_code_spawned_339_subagents_from_a/ (reddit)
- **Verbatim (u/cvdaystar):** "Claude Code v2.1.172 (June 10, 2026, 3 days before my incident) enabled sub-agents to spawn their own sub-agents, up to 5 levels deep. The key issue is the `general-purpose` agent type. It has access to all tools, including the `Agent` tool itself. So when you ask it to do research, it can (and will) decide to fan out by spawning more agents autonomously. ... 339 sub-agent transcript files created, all spawned within a ~10 minute window ... 295 out of 339 agents (87%) hit rate limits and returned nothing. ... There's no built-in setting to disable nested spawning or set a max depth. ... This feature should be opt-in, not opt-on-by-default."
- **Tier:** Plausible (single detailed incident, but with transcript evidence).

### B10. `/fork` redefined to spawn an independent background session
- **Claim:** Claude Code v2.1.212 redefined `/fork`: it now spawns an independent background session instead of an in-conversation subagent. (Docs: "To copy the whole session into a new background session that runs alongside it, use /fork.")
- **Source:** https://thepromptshelf.dev/blog/claude-code-agent-view-background-sessions-2026/ (blog) + https://code.claude.com/docs/en/agents (docs)
- **Verbatim (thepromptshelf.dev):** "Claude Code v2.1.212 redefined /fork: it now spawns an independent background session instead of an in-conversation subagent."
- **Verbatim (code.claude.com/docs/en/agents):** "It's a way to spawn a subagent, not a separate surface. Start one with /subtask. Claude also spawns one itself where fork mode is on. To copy the whole session into a new background session that runs alongside it, use /fork."
- **Tier:** Plausible (blog) / Authoritative (docs).

### B11. Community workarounds for "agent spawns visible session" before the native feature
- **Claim:** Before/around the native feature, users built their own: an "infinite canvas" (voicetree.io) that spawns terminals for subagents; a session manager + "agent-deck skill" where "you can just ask Claude to spawn sub-agents and it handles the session creation for you"; custom MCP servers where a main assistant "spawn[s] and prompt[s] other Claude codes in their own terminals."
- **Source:** https://www.reddit.com/r/ClaudeCode/comments/1qiv8ps/claude_spawning_transparent_subagents_as_native/ (reddit) + https://www.reddit.com/r/ClaudeAI/comments/1pp1boo/built_a_session_manager_for_claude_code_manage/ (reddit) + https://www.reddit.com/r/ClaudeAI/comments/1q6u7xz/how_do_people_run_multiple_claude_code_sessions/ (reddit)
- **Verbatim (u/manummasson):** "Found it annoying when Claude would spawn subagents but I would have no control or visibility over them. Built this into the infinite canvas I am using for orchestrating Claude code (voicetree.io). Now it can create the tasks on the canvas, and then spawn terminals directly in. Great for long tasks, or tasks that branch off into a few different directions."
- **Verbatim (r/ClaudeAI):** "Also been working on an agent-deck skill for Claude Code - you can just ask Claude to spawn sub-agents and it handles the session creation for you." / "I have a custom mcp server that allows my 'main personal assistant Claude code' in vs code terminal to spawn and prompt other Claude codes in their own terminals."
- **Tier:** Plausible (multiple independent builders).

### B12. Subagents vs separate sessions — the comparison the community draws
- **Claim:** Community consistently distinguishes: subagents (Agent tool) = output flows back into parent, share parent's context budget, can't be opened/steered as real sessions; separate sessions (chips/Agent View) = own context/worktree, visible, steerable, but no automatic report-back.
- **Source:** https://github.com/anthropics/claude-code/issues/95554 (github) + https://www.totalum.app/blog/claude-code-subagents-totalum (blog)
- **Verbatim (#95554, "Alternative Solutions"):** "Subagents (Agent tool): output flows back into the parent, but they share the parent's context budget and I can't open/steer them as real sessions. Manually starting new sessions and pasting a prompt: works, but the plan session loses track of them entirely."
- **Verbatim (totalum.app):** "Claude Code subagents are isolated Claude instances that the main session spawns to work in parallel, each with its own context window, its own tool permissions, and its own model."
- **Tier:** Plausible.

---

## PART C — Gaps people complain about in Hermes regarding session management

### C1. Sessions can't message each other (the loudest, freshest gap)
- **Claim:** A power user (19h before research, 55 upvotes) argues "Sessions can't message each other" is "the major feature holding back Hermes right now," citing Codex's "Coordinator" session and OpenAI Dot as the model. Counterpoints: it's already possible via profiles/bots/kanban/CLI; and a top commenter argues agent-to-agent messaging is a *flawed* approach (token waste, worse answers) vs. hierarchies + subagents.
- **Source:** https://www.reddit.com/r/hermesagent/comments/1x6qgz1/hermes_sessions_should_be_able_to_send_messages/ (reddit)
- **Verbatim (OP u/barronlroth):** "At this moment in time, **Sessions can't message each other**. This is possible in competing harnesses like Codex, where you can create a 'Coordinator' session that handles most of your discussion, and can send prompts to other sessions to organize your work better. The Chief of Staff model becomes possible with this functionality. This is the major feature holding back Hermes right now. ... what i want is simple: my main topic says 'hey other session, check the build and report back' and the other session picks it up with its full history. codex does this today. that's the chief of staff model, and it's the one thing session mode can't do yet."
- **Verbatim (u/FlaTreNeb, rebuttal):** "Agents sending messages to each other is a flawed approach (this includes ACP for most use cases). ... It wastes tokens and makes answers worse. Agents start to discuss with each other, they try to achieve consensus and more agents will turn away from a correct solution ... Hierarchies and step-wise processes are way more efficient. For complex tasks that will take a long time and have many subtasks, scripted workflows + subagents are the way to go."
- **Verbatim (u/stujmiller77, "it's already possible"):** "I use Hermes hard - three sandboxed companies, each with their own set of hermes profiles. They share memory through mnemosyne so can pass that from one session to the next. They can speak to each other. And they use sub-agents to hand off work. And kanban mode is exactly what you say - an orchestrator that hands off to sub-agents with specific roles and toolsets."
- **Verbatim (u/Fit_Advisor8847, workaround):** "But any session can message any other sessions, not only just in Hermes, I have Hermes sending messages to Hermes sessions, Codex sessions, Pi sessions, and other harnesses, too. What I do is either have an orchestrator keep track of the different sessions running in a workspace, or provide the orchestrator with a specific session(s) I want interactions to happen with, then just tell it to use the CLI to send that session a message."
- **Tier:** Plausible (active, upvoted thread; the gap itself is corroborated by the megathread FAQ "Direct agent-to-agent conversation is not a built-in Hermes feature").

### C2. Subagents are not persistent / don't survive reboots
- **Claim:** Users coming from OpenClaw/CrewAI expect persistent, role-based sub-agents; Hermes subagents (delegate_task) are "not considered persistent nor survive reboots."
- **Source:** https://www.reddit.com/r/hermesagent/comments/1tla8oi/multiple_agents/ (reddit)
- **Verbatim (u/Civil-Possibility223):** "I am used to have multiple agents, each one of them focuses on a specific activity (I have a personal assistant, a research companion, a social media manager, and one manager). In hermes it seems this is not possible, as sub-agents are spawned via delegate_task, but are not considered persistent nor survive reboots."
- **Tier:** Plausible.

### C3. Async subagents are single-session only (not durable)
- **Claim:** Even the new async delegation is in-process and dies with the session; cross-turn persistence is a separate open issue (ACP #4949).
- **Source:** https://the-agent-report.com/2026/06/hermes-async-subagents-june2026/ (blog)
- **Verbatim:** "Async subagents are single-session only — they run in-process and are not durable across restarts or new chat turns. Cross-turn persistence is tracked separately under ACP #4949."
- **Tier:** Plausible.

### C4. Telegram vs Desktop sessions are not aware of each other (session visibility)
- **Claim:** A user running the same "conversation" on Telegram and desktop finds they don't share state — "Because that's two different sessions."
- **Source:** https://www.reddit.com/r/hermesagent/comments/1tbkktq/telegram_chat_and_desktop_sessions_confusing/ (reddit)
- **Verbatim (u/Odd-Environment-7193):** "I'm running things in my desktop on hermes agent. I am also running them on telegram. Even though I am on the same conversation they are no aware of what's happening in the different versions. I just did some tests and code changes in telgram now I'm askign about them in the desktop cli and it has no idea wtf is going on?"
- **Tier:** Plausible.

### C5. No per-session/per-board model or profile targeting
- **Claim:** A swarm user hits a limit: "you cannot specify which agent profiles are relevant for which kanban boards." (Related: per-chip model/effort is an open Claude request #95190, showing the same need.)
- **Source:** https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june/ (reddit)
- **Verbatim (u/mitchells00, "Swarm Master Pattern"):** "A Hermes gateway whose job is commissioning new Hermes gateways — each a multi-profile swarm in its own Docker container. Limitation noted: 'I'm hitting limits with how you cannot specify which agent profiles are relevant for which kanban boards.'"
- **Tier:** Plausible.

### C6. No easy session categorization into "projects"
- **Claim:** Users want to group sessions into projects (like ChatGPT folders); the project folder mechanism is confusing/empty.
- **Source:** https://www.reddit.com/r/hermesagent/comments/1wle6r3/putting_sessions_in_projects_in_hermes/ (reddit)
- **Verbatim (u/Coach_Unable):** "I want to sub categorize my sessions into projects in my hermes profile. I noticed every project needs to have a dedicated folder on my system, after creating a folder and setting it for the projects, I noticed it doesnt contain anything. ... I just need a way to categorize sessions logically (same as ChatGPT folders) is that possible in hermes?"
- **Tier:** Plausible.

### C7. Agent-to-agent loops / token waste (the caution behind any "spawn + talk" design)
- **Claim:** Multiple users report agents talking to each other all night (token waste) when A2A messaging is enabled without mention-required mode + circuit breakers.
- **Source:** https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june/ (reddit)
- **Verbatim (megathread):** "Community caution from multiple users: This pattern can lead to agent loops and token waste. 'I woke up one morning to two of my agents complaining all night about how they hadn't heard from me in several hours' — u/thetomsays (+26). Use mention-required mode and circuit breakers." / "Pitfall 2: Agent-to-Agent Loops ... Always set circuit breakers: `tool_loop_guardrails.hard_stop_enabled: true` with reasonable limits."
- **Tier:** Plausible.

### C8. delegate_task is synchronous — lost if the parent is interrupted
- **Claim:** "Created a research task via delegate_task, my laptop went to sleep, lost everything." — delegate_task is synchronous; for durable work use Kanban or cron.
- **Source:** https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june/ (reddit)
- **Verbatim (megathread, Pitfall 4):** "'Created a research task via delegate_task, my laptop went to sleep, lost everything.' — delegate_task is synchronous. For durable work, use Kanban or cronjob."
- **Tier:** Plausible.

---

## PART D — "Orchestrator session + worker sessions" patterns in Hermes with reporting back

### D1. Orchestrator + Specialists org chart (the most common pattern)
- **Claim:** The dominant community pattern: an orchestrator (default profile) reads a "constitution" and routes tasks to specialist profiles (coder/researcher/personal), each with its own SOUL.md, restricted toolset, and gateway; tasks arrive via Kanban or direct delegation.
- **Source:** https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june/ (reddit)
- **Verbatim (megathread):** "The 'Orchestrator + Specialists' Org Chart — The most common pattern across threads: Orchestrator (default profile) (FRIDAY) Reads constitution, routes tasks → Coder profile / Researcher profile / Personal profile. Each specialist has: Its own SOUL.md defining its role; Restricted toolset (coder gets terminal+file+github, researcher gets web+file); Its own gateway (Telegram topic or separate bot); Tasks arrive via Kanban board or direct delegation."
- **Tier:** Plausible.

### D2. The 4-Tier scaling model
- **Claim:** Community scaling framework: Tier 1 = one agent + delegate_task; Tier 2 = orchestrator + specialist profiles, one chat surface; Tier 3 = domain orchestrators with separate bots; Tier 4 = separate instances (VPS). "Most people never need Tier 3 or 4."
- **Source:** https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june/ (reddit)
- **Verbatim (u/nemanja87mn, +20):** "Tier 1: One agent, one gateway, delegate_task for subagents — Protecting context without adding complexity. Tier 2: Orchestrator + specialist profiles, one chat surface. Tier 3: Domain orchestrators with separate bots. Tier 4: Separate instances (same machine or VPS). ... Most people never need Tier 3 or 4. 'Start with a single agent and create as needed' — u/laffytaffykidd (+12)."
- **Tier:** Plausible.

### D3. Constitution pattern (routing doc) — reporting back via delegation result
- **Claim:** A `constitution.md` maps specialties→profiles/personalities; the orchestrator reads it before routing and delegates via delegate_task (result returns to orchestrator context). One user collapsed 3 agents/4 profiles into 1 agent with 8 "personalities."
- **Source:** https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june/ (reddit)
- **Verbatim (u/Starrwulfe, +3):** "Chances are those five agents can be one agent in Hermes that has five split personalities. Those split personalities can then be sub delegated to without you even having to do anything, even set up a profile. ... I went from having three separate agents and four profiles to having one agent with eight personalities and it's way more efficient."
- **Tier:** Plausible.

### D4. Reporting-back channels actually used: Kanban comments, Telegram, files, collect_task
- **Claim:** The concrete "report back" mechanisms in practice are: (1) Kanban comments as an inter-agent protocol (each comment visible to the next agent), (2) Telegram/Discord group posts, (3) shared files / NAS append-only logs with file locking, (4) `collect_task` (async) returning the full result to the parent, (5) A2A Context Bus plugin / agentsocket.dev.
- **Source:** https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june/ (reddit)
- **Verbatim (megathread, Pattern 6):** "Shared Kanban board with comments: Agents use Kanban comments as an inter-agent protocol — each comment is visible to the next agent that picks up the task. ... NAS Shared Log (u/Fun_Firefighter_7785): For agents on different physical machines. Uses append-only `.log` files with `fcntl.flock()` advisory locking over CIFS/NFS. ... agentsocket.dev: A WebSocket-based agent communication service."
- **Verbatim (megathread, FAQ):** "Can agents talk to each other directly? A: Not natively like a group chat. The closest patterns are: (1) Kanban comments as inter-agent protocol, (2) Telegram group with multiple bot tokens, (3) A2A Context Bus plugin. Direct agent-to-agent conversation is not a built-in Hermes feature."
- **Tier:** Plausible.

### D5. "I gave my Hermes team a shared Kanban board. Now they manage themselves."
- **Claim:** A user ran a multi-profile team on a shared Kanban with auto-discovery of profiles (reads SOUL.md for name/description) and an A2A protocol; community noted Hermes already has a built-in native Kanban (web dashboard + desktop app) integrated with profiles and the dispatcher.
- **Source:** https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june/ (reddit)
- **Verbatim (megathread):** "'I gave my Hermes team a shared Kanban board. Now they manage themselves.' — u/Ok_Run_5401 ... Created a third-party Kanban board project (pip install hermes-kanban) with auto-discovery of Hermes profiles. Agents auto-appear from profiles — reads SOUL.md for name/description. Includes an Agent-to-Agent (A2A) protocol for direct inter-agent messages. ... Recommendation: Start with Hermes' built-in Kanban (zero setup, integrated with profiles and the dispatcher)."
- **Tier:** Plausible (note: OP's post showed self-promotion signs per the megathread; the built-in Kanban is the supported path).

### D6. "The Agent That Sets Up Agents" + Swarm Master (meta-orchestration)
- **Claim:** Users have a main agent create profiles for setting up other profiles, and a "Swarm Master" gateway whose job is commissioning new Hermes gateways (each a multi-profile swarm in Docker).
- **Source:** https://www.reddit.com/r/hermesagent/comments/1ucmvi8/multiagent_profiles_megathread_hermes_agent_june/ (reddit)
- **Verbatim (u/MrOzanges):** "Ask your main Hermes agent to create a profile specifically for setting up other profiles. That specialist agent reviews SOUL.md, disables irrelevant tools/skills, and configures new profiles optimally. Meta: your agent architects your agent team."
- **Tier:** Plausible.

---

## Searched, found nothing (negative results)
- **German UI strings verbatim** ("Aufgabe", "Kontext", "Von Claude gestartet aus", "Dieser Computer") as quoted in any community post: **not found.** The exact German localization strings do not appear in indexed community sources; the feature is described in English via the `spawn_task`/task-chip GitHub issues (B1–B4). The German strings are the user's own observation of the localized desktop UI.
- **A community post describing the Claude Desktop spawn feature by the exact name "Von Claude gestartet aus" or a German-language thread about it:** not found (German-language search returned empty).
- **`site:reddit.com/r/hermesagent "/bg"` as a dedicated how-to thread:** no dedicated `/bg` thread surfaced (the `/bg` description came from the agentbuildershq.com tutorial, A3).
- **An authoritative (Anthropic) doc/blog page specifically titled for the desktop `spawn_task`/task-chip feature:** not found in this lane (the mechanism is documented via the desktop docs referenced inside the GitHub issues and the `ccd_session` MCP server; the docs-first lane owns the official doc text).
- **X/Twitter-native threads** on either the Hermes multi-session practice or the Claude desktop spawn feature: not found via web_search (X content is poorly indexed; no load-bearing X post surfaced). The only X reference was a link inside a Reddit comment (u/barronlroth → x.com/linuz90 on Telegram forum topics).

## Source inventory (load-bearing)
**Hermes (reddit):** 1ucmvi8 (Multi-Agent & Profiles Megathread, June 2026 — the anchor source), 1x6qgz1 (sessions should message each other, 19h old), 1u88xbb (async subagents), 1uvzqim (Subagents), 1tla8oi (Multiple agents), 1vrrx9v (Bot Mode plugin), 1t7vpvg (HermesWhisper), 1tdbmm6 (24/7 work), 1t29ogw (one month), 1tbkktq (Telegram vs desktop), 1wle6r3 (sessions in projects), 1srab3d (how does Hermes handle sub agents).
**Hermes (blog):** the-agent-report.com (async subagents, June 2026), agentbuildershq.com (multiple agents one window, Sept 2026, v0.21.3-checked), cuckoom.com (complete guide).
**Claude feature (github, official repo):** #95554 (orchestrator view / report-back), #91820 (spawn_task chip repro + bug), #94697 (programmatic start_session), #53494 (invisible spawned tasks), #41273 (Dispatch spawns new session each time), #95190 (model/effort per chip, referenced).
**Claude (reddit):** 1tc3qjp (Agent View 2.1.139), 1tag1i9 (Agent View official), 1u5d02w (339 subagents), 1q6u7xz (multiple sessions/worktrees), 1qiv8ps (voicetree canvas), 1wtdyot (cross-session messaging), 1svamh8 (Dispatch), 1vm7teh (Dispatch/remote-control), 1pp1boo (session manager/agent-deck), 1q2f6hl (desktop autonomous, deleted OP).
**Claude (HN):** 46902368 (Agent Teams), 49222824 (cross-session messaging).
**Claude (official/blog):** claude.com/blog/dispatch-and-computer-use, support.claude.com (Dispatch/Cowork), code.claude.com/docs (agent-view, agents, cross-session-messaging), thepromptshelf.dev, totalum.app, claudefa.st, mindstudio.ai, cobusgreyling (Medium/Substack).
