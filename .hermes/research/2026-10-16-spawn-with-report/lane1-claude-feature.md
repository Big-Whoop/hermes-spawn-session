# Research Lane: Claude "Spawn with Report" Feature — Identification

Research date: 2026-10-16 · Lane: Claude Desktop/Code feature identification (web research, docs-first)
Screenshot under investigation: Claude Desktop (German UI), new sidebar session titled "Report the Nomad jobs in the services section", header "Von Claude gestartet aus Sitzung ohne Titel vor 18 Minuten" (= "Started by Claude from session without title, 18 minutes ago"), body with structured sections "Aufgabe" (Task) + "Kontext" (Context, collapsed), environment line "Dieser Computer · Pius · Als Umgebung speichern" (= "This Computer · Pius · Save as environment").

## TL;DR — What the feature is

The feature is **agent-initiated session spawning in the Claude Desktop app (Code tab)**, publicly named **"nested sessions"** in Anthropic's Oct 14, 2026 desktop-app update announcement. In the official docs it is documented (partially) as the **"task chip"** / "suggested task" mechanism under "Work across sessions" on the Desktop application page. The underlying mechanism is the app-internal MCP server **`ccd_session`** with tools **`mcp__ccd_session__spawn_task`** (creates a clickable chip/card) and **`mcp__ccd_session__start_session`** (starts a session immediately or as a proposal), plus the **`ccd_session_mgmt`** server (`get_session` with `parentSessionId`, `list_sessions` with `linked: true`, `set_session_model`, `set_session_effort`, `detach_session`, `stop_session`, `open_session_in`, `archive_session`). Internal feature-gate name: **"side sessions"**.

It is a **distinct mechanism from subagents** (ephemeral, in-process, in-session) and from **agent teams** (CLI-only, experimental, peer teammates with shared task list + mailboxes). A spawned session is a **full, independent, visible session** with its own history, context window, environment, and optional git worktree, linked to its parent via `parentSessionId`, and it **reports its result back to the parent session** when finished.

---

## Findings (per sub-question)

### 1. Exact feature name + documentation location

**F1.1 — Public/announcement name: "nested sessions" (desktop app update of Oct 14, 2026).**
- Source: https://x.com/ClaudeDevs/status/2110445844675838148 (Anthropic's ClaudeDevs X thread, Oct 14, 2026) — type: vendor announcement (X; direct fetch blocked, content corroborated by secondary sources below)
- Verbatim (via Wes Roth, Anthropic, X post 2026-10-14T23:30Z, https://x.com/WesRoth/status/2110513483833921828, search snippet): "Anthropic updated Claude Code's desktop app to make parallel sessions easier to start and manage. … **Parallel tasks open in nested sessions and report their results back to the main conversation.** The sidebar shows which sessions are working and which need attention, with live task lists and recap cards inside each session."
- Verbatim (via ClaudeDevs, quoted in https://pasqualepillitteri.it/en/news/24032/claude-code-desktop-nested-sessions-environments, article dated 15/10/2026): "We've been working hard on making the Claude Code desktop app great for running lots of sessions side by side. It's now much quicker to start sessions, easier to split work across a few, and you can always see what each of them is doing."
- Tier: **Verified** (announcement date + wording corroborated by two independent secondary sources; X thread itself not directly readable)

**F1.2 — Official docs name: "task chip" (a.k.a. "Suggested task" chip), documented on the Desktop application page.**
- Source: https://code.claude.com/docs/en/desktop (section "Work across sessions") — type: vendor doc (read in full)
- Verbatim: "Claude can also suggest new sessions. When it notices something worth fixing that's out of scope for the current task, it offers the work as a **task chip** in the chat. Click the chip to start that work in a **new session with its own worktree**; Claude continues your current session uninterrupted."
- German docs (same section, https://code.claude.com/docs/de/desktop): "Claude kann auch neue Sitzungen vorschlagen. … bietet es die Arbeit als **Task-Chip** im Chat an. Klicken Sie auf den Chip, um diese Arbeit in einer neuen Sitzung mit eigenem Worktree zu starten. Claude setzt Ihre aktuelle Sitzung ungestört fort."
- Tier: **Verified** (official docs, read directly)

**F1.3 — Underlying tool names: `mcp__ccd_session__spawn_task`, `mcp__ccd_session__start_session`, `hand_off_to_session`, `list_start_targets`; mgmt server `ccd_session_mgmt`.**
- Source: https://github.com/anthropics/claude-code/issues/100913 (opened Oct 9, 2026; comments through Oct 15, 2026) — type: GitHub issue (user reports on first-party repo)
- Verbatim: "In the desktop app a session cannot start a normal session by itself: `mcp__ccd_session__spawn_task` makes a chip, and the user must click it. No `start_session` or `hand_off_to_session` tool is exposed, although the descriptions of `detach_session`, `stop_session`, `set_session_model`, `set_session_effort`, `open_session_in` and `list_sessions` all refer to them."
- Verbatim (comment, evytheodoruas, Oct 13, 2026): "The desktop build already ships `start_session`, `hand_off_to_session` and `list_start_targets` (other ccd tools reference them), but our sessions only get `spawn_task`, and calls return 'Starting sessions is not enabled here.' No local setting controls it, so it looks like a remote feature gate (the desktop 'side sessions' flag)."
- Tier: **Plausible** (multiple independent users, consistent details, first-party repo; no official tool reference page exists for these app-internal MCP tools)

**F1.4 — Where it is NOT documented: no dedicated "nested sessions" docs page, no CLI changelog entry.**
- Source: https://code.claude.com/docs/llms.txt (full docs index, read) + https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md (full changelog through v2.1.301, grepped for spawn_task/side session/child session/nested session/ccd_session/hand_off — zero hits) — type: vendor doc/changelog
- The docs index's "What's new" weekly digest only runs through Week 37 (Sep 7–11, 2026); the Oct 14 desktop update is not yet in it. The CLI changelog covers the `claude` CLI; the desktop app ships its own bundled Claude Code copy and is versioned separately (e.g., desktop 2.31226.1.0 with Claude Code 2.1.296, per issue #100913 comments).
- Tier: **Verified** (absence confirmed by direct read/grep)

### 2. Trigger: user-initiated, agent-initiated, or both?

**F2.1 — Agent-initiated is the core mode.** Claude calls the spawn tool itself.
- Source: https://code.claude.com/docs/en/desktop#work-across-sessions (vendor doc) — "When it notices something worth fixing that's out of scope for the current task, it offers the work as a task chip in the chat."
- Source: https://pasqualepillitteri.it/en/news/24032/claude-code-desktop-nested-sessions-environments (blog/news, 15/10/2026) — "Nested sessions are child sessions that **Claude Code opens on its own** when asked to run several tasks in parallel, one per task. Each child session works independently and, once done, reports its result back to the main session."
- Source: https://github.com/anthropics/claude-code/issues/80238 (GitHub issue) — "The Claude Desktop app's Code tab has an `mcp__ccd_session__spawn_task` tool that lets **Claude proactively flag an out-of-scope issue as a 'Suggested task' chip**, one click away from spinning off an autonomous background session."
- Tier: **Verified** (docs) / **Plausible** (issues)

**F2.2 — Two initiation modes exist on `start_session`: `user_asked` (starts immediately) and `own_initiative` (proposal only).**
- Source: https://github.com/anthropics/claude-code/issues/100913 (GitHub issue, comment by JimMcBubbles, Oct 15, 2026)
- Verbatim: "That's reasonable for `initiation: \"user_asked\"`, which starts a session immediately. But the tool's own description says `own_initiative` only proposes one — 'the user sees a card and nothing runs until they start it'. A chip starts nothing; the click does."
- Tier: **Plausible** (single detailed user report quoting the tool's own description)

**F2.3 — User-initiated also works in plain language.**
- Source: https://code.claude.com/docs/en/desktop (vendor doc, "Continue in another surface" / sessions-from-dispatch context) — "A task can end up as a Code session in two ways: you ask for one directly, such as 'open a Claude Code session and fix the login bug', or Dispatch decides the task is development work and spawns one on its own."
- Tier: **Verified**

**F2.4 — Gate: unattended sessions cannot start sessions.**
- Source: https://github.com/anthropics/claude-code/issues/100913 (GitHub issue)
- Verbatim: "From a session started by the scheduler (a routine), `mcp__ccd_session__start_session` returns: 'Starting sessions requires a user at the keyboard; this session runs unattended (scheduled or remotely dispatched).'"
- Tier: **Plausible** (detailed repro by one user)

### 3. Payload: what is passed to the new session?

**F3.1 — `spawn_task` payload: `title`, `prompt`, `tldr`.**
- Source: https://github.com/anthropics/claude-code/issues/53494 (GitHub issue, Apr 26, 2026)
- Verbatim: "In an active session, the agent calls `mcp__ccd_session__spawn_task` with `title`, `prompt`, `tldr`. A chip appears in the UI. User clicks the chip — task spawns to a fresh worktree."
- Tier: **Plausible** (user report; matches screenshot structure: title → session title "Report the Nomad jobs in the services section"; prompt → "Aufgabe" section; tldr/context → "Kontext" section)

**F3.2 — `start_session` payload: prompt, model, effort, cwd/worktree, permission_mode.**
- Source: https://github.com/anthropics/claude-code/issues/100913 (GitHub issue, feature request body)
- Verbatim: "Expose a tool, for example `start_session`, with these inputs: `prompt` (first user message); `model` and `effort`; `cwd` or worktree option; `permission_mode`. It should create an ordinary top-level session in the sidebar under the same project, with no click." (Request text; per comment by garrysanders the tool existed and "worked as expected" for some users Oct 8–14, 2026.)
- Tier: **Plausible**

**F3.3 — Screenshot mapping (inference from F3.1 + observed UI).** The new session's first message is rendered as structured sections: "Aufgabe" (Task) = the detailed work instruction (the `prompt`), "Kontext" (Context, collapsed) = background context (the `tldr`/context payload). Header "Von Claude gestartet aus Sitzung ohne Titel" = "Started by Claude from [parent session title]" — i.e., the parent session's title is recorded and displayed. Environment line "Dieser Computer · Pius · Als Umgebung speichern" = local environment on machine "Pius" + the new "Save as environment" affordance from the same Oct 14 update.
- Tier: **Speculative** (mapping of payload fields to UI sections is inferred; the app's exact field names are not published)

### 4. Execution: where does the new session run?

**F4.1 — Full independent session with its own history, linked to the parent.**
- Source: https://github.com/anthropics/claude-code/issues/99393 (GitHub issue, Oct 4, 2026)
- Verbatim: "One remote Code-tab session created several background-task chips with `mcp__ccd_session__spawn_task`, and the user clicked each one to start it. … `mcp__ccd_session_mgmt__get_session` on any of the started sessions returns `\"parentSessionId\": \"<first session's id>\"` and `\"detached\": false`."
- Verbatim (same issue): the `list_sessions` tool describes `linked: true` as listing "this session's linked family: the session that started it, the sessions it or they started"; "It says linked sessions are ones 'Claude started from another with start_session'."
- Tier: **Plausible** (user report with concrete tool output)

**F4.2 — Runs on the same machine by default; own git worktree is the default isolation for chip-spawned sessions.**
- Source: https://code.claude.com/docs/en/desktop (vendor doc) — "Click the chip to start that work in a new session with its own worktree."
- Source: https://github.com/anthropics/claude-code/issues/52243 (GitHub issue) — "The `mcp__ccd_session__spawn_task` tool (used by Cowork 'chips' to launch a fresh Claude Code session in a new git worktree) always creates the new worktree from the repo's default branch, regardless of the parent session's current branch."
- Source: https://github.com/anthropics/claude-code/issues/72915 (GitHub issue) — "The desktop app's 'Suggested task' popup chips (the `mcp__ccd_session__spawn_task` suggestions, with 'Start with worktree')…"
- Tier: **Verified** (docs) / **Plausible** (issues)

**F4.3 — Sidebar visibility: nested under the parent.**
- Source: https://www.mindstudio.ai/blog/claude-code-3-0-parallel-sessions (blog, Oct 2026)
- Verbatim: "The nested sessions themselves still appear in the sidebar, nested under the parent task, so you can open any of them individually to see the full detail if you need it."
- Tier: **Plausible** (secondary blog; consistent with screenshot showing the new session as a normal sidebar entry)

**F4.4 — Child sessions carry a `CLAUDE_CODE_CHILD_SESSION` env marker (technical detail).**
- Source: https://github.com/anthropics/claude-code/issues/101386 (GitHub issue)
- Verbatim: "Record the parent session id for every Claude Code process that a session's tools start: the claude CLI, npx-launched Claude Code, and Agent SDK launches. The carrier must not change the child's own behavior (see v2.1.173 regression: TUI writes no transcript records when CLAUDE_CODE_CHILD_SESSION is inherited from a parent claude session…)."
- Tier: **Plausible**

**F4.5 — Cloud spawning also exists (older behavior, bug-reported).**
- Source: https://github.com/anthropics/claude-code/issues/53494 (GitHub issue) — "A task spawned via `mcp__ccd_session__spawn_task` and started by the user becomes invisible… The task runs to completion silently…" (closed as not planned, May 2026; visibility later improved per F4.3)
- Tier: **Plausible**

### 5. Reporting: how does the result get back to the parent?

**F5.1 — Official behavior: child reports its result back to the parent/main session when done; intermediate work stays in the child.**
- Source: https://alphasignal.ai/news/anthropic-s-claude-code-now-runs-nested-sessions-and-saves-dev-environments (news, Oct 2026)
- Verbatim: "A parent session can now split parallel work into nested child sessions. Each child handles its assigned task and **reports the result to the parent when finished**, keeping most intermediate tool calls out of the main transcript."
- Source: https://x.com/WesRoth/status/2110513483833921828 (Anthropic employee, X, 2026-10-14) — "Parallel tasks open in nested sessions and **report their results back to the main conversation**."
- Source: https://pasqualepillitteri.it/en/news/24032/claude-code-desktop-nested-sessions-environments (blog) — "Each child session works independently and, once done, reports its result back to the main session. … Anthropic justifies the choice on readability grounds. The main thread does not fill up with the work of every task and stays the place where the project's history is read."
- Tier: **Plausible** (announcement wording via secondary sources; the X thread itself is not directly readable)

**F5.2 — Likely mechanism: the cross-session messaging / "work across sessions" surface (message injected into the parent as a card), plus `ccd_session_mgmt` polling.**
- Source: https://code.claude.com/docs/en/desktop#work-across-sessions (vendor doc) — "When Claude messages another session through this surface, Claude Code shows it there as a card labeled with the sending session's title and a link back… If the receiving session is mid-task, Claude Code holds the message and Claude reads it once the current work finishes. The receiving Claude can reply, and Claude Code delivers the reply back through this surface."
- Source: https://code.claude.com/docs/en/cross-session-messaging.md (vendor doc) — "Claude discovers the target with `ListAgents` and sends with `SendMessage`… The receiving Claude reads the message between tool calls during an active turn… When the receiving session is idle, Claude Code starts a new turn with the message." (CLI-side mechanism; the desktop surface is the app-internal equivalent.)
- Tier: **Verified** (docs for the messaging surface) / **Speculative** (that the nested-session report specifically rides this exact channel is inferred; Anthropic has not published the internal delivery path)

### 6. Model selection

**F6.1 — Spawned session can use a different model/effort; escalation above the caller's own asks the user.**
- Source: https://github.com/anthropics/claude-code/issues/100913 (GitHub issue)
- Verbatim: "Expose a tool, for example `start_session`, with these inputs: `prompt` (first user message); `model` and `effort`… Approval can follow the existing rules: a model or effort above the caller's own asks the user first." (Requested spec; per garrysanders comment the shipped tool "worked as expected" Oct 8–14, 2026.)
- Tier: **Plausible**

**F6.2 — Known bug: chip-spawned sessions start at medium effort regardless of parent/settings.**
- Source: https://github.com/anthropics/claude-code/issues/99862 (GitHub issue)
- Verbatim: "…I start a background task via a card (spawn_task chip) and I click it, the new local session always starts with effort medium." (ignores `effortLevel` in settings.json and the parent session's effort)
- Tier: **Plausible**

### 7. Availability: plans, platforms, limits

**F7.1 — Claude Desktop app, Code tab; Pro/Max/Team/Enterprise; macOS + Windows, Linux beta.**
- Source: https://code.claude.com/docs/en/desktop (vendor doc) — download cards for macOS/Windows/Linux (beta); "Verify that you have an active paid subscription: Pro, Max, Team, or Enterprise."
- Source: https://pasqualepillitteri.it/en/news/24032/claude-code-desktop-nested-sessions-environments (blog) — "You need the Claude desktop app with a Pro, Max, Team or Enterprise plan (macOS and Windows, with a Linux beta). Update the app, open the Code tab and start a new session."
- Tier: **Verified** (docs) / **Plausible** (blog)

**F7.2 — Feature-gated server-side ("side sessions" flag); rollout was partial and changed during Oct 2026.**
- Source: https://github.com/anthropics/claude-code/issues/100913 (GitHub issue)
- Verbatim (evytheodoruas, Oct 13): "…our sessions only get `spawn_task`, and calls return 'Starting sessions is not enabled here.' No local setting controls it, so it looks like a remote feature gate (the desktop 'side sessions' flag)."
- Verbatim (garrysanders, Oct 15): "We're seeing the same on macOS (Claude desktop 2.26454.2, Claude Code 2.1.293), with one difference that might help. `start_session` and `hand_off_to_session` were offered to our Code tab sessions from 8 to 14 October and worked as expected. From 15 October they're gone for new and existing sessions alike, with 'Its MCP server ccd_session is connected but does not offer this tool here.' There was no app or Claude Code update in between, so by the looks of it this could be a server-side switch."
- Tier: **Plausible** (multiple consistent user reports)

**F7.3 — Kill switch for the chips: `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`.**
- Source: https://github.com/anthropics/claude-code/issues/72915 (GitHub issue)
- Verbatim: "The desktop app's 'Suggested task' popup chips (the `mcp__ccd_session__spawn_task` suggestions, with 'Start with worktree') are intrusive and I want them off. The problem: the only lever I can find is `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, which per the changelog 'disable[s] all background task…'"
- Tier: **Plausible**

**F7.4 — Limits: no documented max concurrent spawned sessions; cost is per-session plan usage.**
- Source: https://pasqualepillitteri.it/en/news/24032/claude-code-desktop-nested-sessions-environments (blog) — "Four active sessions use up the plan faster than one does. The five-hour limit… is therefore reached sooner." / "Anthropic does not put a number on it."
- Source: https://www.mindstudio.ai/blog/claude-code-3-0-parallel-sessions (blog) — "The update is built for people running many sessions in parallel, which means it leans hard on usage limits, and Anthropic has not announced any changes to those limits alongside this release."
- Tier: **Plausible** (absence of a documented cap = verified absence in docs read; cost behavior is secondary reporting)

### 8. Difference from subagents (and from agent teams)

**F8.1 — Subagents: ephemeral, in-process, in one session; result returns to caller.**
- Source: https://code.claude.com/docs/en/agent-teams (vendor doc, comparison table)
- Verbatim: "Subagents report results back to the main agent. In agent teams, teammates share a task list, claim work, and communicate directly with each other." Table: Subagents — "Own context window; results return to the caller" / "Lower: results summarized back to main context".
- Source: https://code.claude.com/docs/en/agents.md (vendor doc) — "Subagents: Delegated workers inside one session that do a side task in their own context and return a summary."
- Tier: **Verified**

**F8.2 — Agent teams: CLI-only, experimental, disabled by default; NOT available in Desktop.**
- Source: https://code.claude.com/docs/en/desktop (vendor doc, "What's not available in Desktop")
- Verbatim: "**Agent teams**: coordinated teams, where Claude as the team lead assigns tasks to teammates from a shared task list, are available in the CLI, not in Desktop. For multi-agent work inside one session, use dynamic workflows, which run in Desktop; Claude can also message and manage your other sessions directly."
- Source: https://code.claude.com/docs/en/agent-teams (vendor doc) — "Agent teams are experimental and disabled by default. Enable them by setting `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`… Each teammate is a full, independent Claude Code session."
- Tier: **Verified**

**F8.3 — The spawned-session mechanism is distinct from both: a visible, persistent, parent-linked top-level session.**
- Synthesis of F1.2, F4.1, F5.1: subagents never appear in the sidebar as sessions and have no `parentSessionId`; agent teams are a CLI-only coordination layer with mailboxes/shared task lists; nested sessions are ordinary desktop sessions (same sidebar, same panes, same archive/rename semantics) created by another session's tool call, with a parent link and a report-back contract.
- Tier: **Verified** (each component verified; the synthesis is direct comparison of official docs)

---

## Timeline (verified dates)

| Date | Event | Source |
|---|---|---|
| 2026-04-26 | `mcp__ccd_session__spawn_task` (chip: title/prompt/tldr) already in use; visibility bug reported | GitHub issue #53494 |
| 2026-10-04 | `parentSessionId` / `linked` family semantics observed via `ccd_session_mgmt` | GitHub issue #99393 |
| 2026-10-08…14 | `start_session` / `hand_off_to_session` offered to some desktop users; "worked as expected" | GitHub issue #100913 (garrysanders) |
| 2026-10-09 | Feature request: zero-click `start_session` (prompt, model, effort, cwd/worktree, permission_mode) | GitHub issue #100913 |
| 2026-10-14 | **ClaudeDevs announces desktop update: nested sessions, saved environments, new session screen, sidebar status, /btw, one-click follow-ups** | ClaudeDevs X thread 2110445844675838148; Wes Roth X post (23:30 UTC) |
| 2026-10-15 | `start_session`/`hand_off_to_session` withdrawn server-side for some users | GitHub issue #100913 (garrysanders) |
| 2026-10-15 | News coverage (pasqualepillitteri.it, AlphaSignal, MindStudio) | blogs |
| 2026-10-16 | Peter's screenshot: spawned session "Report the Nomad jobs in the services section" | user evidence |

## Screenshot evidence → feature mapping

| Screenshot element (German) | English equivalent | Feature element |
|---|---|---|
| Sidebar entry "Report the Nomad jobs in the services section" | session title | `spawn_task`/`start_session` `title` payload |
| Header "Von Claude gestartet aus Sitzung ohne Titel vor 18 Minuten" | "Started by Claude from [session without title], 18 minutes ago" | parent-session attribution (`parentSessionId` link) |
| Body section "Aufgabe" | "Task" | the `prompt` (detailed work instruction) |
| Body section "Kontext" (collapsed) | "Context" | the `tldr`/context payload |
| "Dieser Computer · Pius" | "This Computer · Pius" | local environment (machine name Pius) |
| "Als Umgebung speichern" | "Save as environment" | saved environments feature (same Oct 14 update) |

## Relevance to Hermes (for the parent report)

- Hermes has no direct equivalent of agent-spawned *visible top-level sessions* with a parent link and report-back. Closest Hermes primitives: `delegate_task` (subagent-style, ephemeral, result returns to caller — analogous to Claude *subagents*), and the kanban boards (work-queue items, not sessions). Claude's "nested sessions" sit between subagents and independent user sessions: they are real sessions in the sidebar with a parent-child link and a report-back contract.
- The Claude mechanism is app-internal (MCP server `ccd_session` bundled with the desktop app), not part of the public Agent SDK/CLI surface — so it is not reproducible via the Claude Agent SDK; it is a desktop-app product feature.

## Searched, found nothing

- Query: `"Claude Desktop" spawn session` / `Claude Code "spawn" new session feature` / `"parallel sessions" Claude Code` / `Claude Code changelog sessions 2026` / `site:reddit.com Claude Desktop "new session" spawn` / `"Claude Code" "child sessions" OR "sub-sessions" OR "session spawning"` / `Claude Desktop "tasks" agent spawn` / `site:news.ycombinator.com Claude Desktop spawn session` / `Claude Code "worktree" session spawn` / `Anthropic "Claude Desktop" release notes 2026` (web_search) — no dedicated official "nested sessions" docs page, no HN thread, no Reddit thread specifically documenting the Oct 14 feature; community corroboration came from GitHub issues (first-party repo) and tech blogs instead.
- Direct fetch of https://x.com/ClaudeDevs/status/2110445844675838148 and https://x.com/WesRoth/status/2110513483833921828 (X/Twitter) — blocked (scrape failed); content obtained via secondary citations (pasqualepillitteri.it quotes the ClaudeDevs post; search snippets carry the Wes Roth wording).
- Grep of full Claude Code CLI CHANGELOG.md (through v2.1.301) for `spawn_task|side session|child session|nested session|report back|ccd_session|hand_off|start_session` — no hits (feature is desktop-app-side, not in the CLI changelog).
- No official documentation of a maximum number of concurrent spawned sessions, or of the exact internal delivery channel for the child→parent report (see F5.2 tier note).
- No official English UI string reference for "Started by Claude from …" / "Task" / "Context" sections (app UI strings, not published in docs); German docs use "Task-Chip" for the chip mechanism.

## Source inventory

| # | URL | Type | Used for |
|---|---|---|---|
| 1 | https://code.claude.com/docs/en/desktop | vendor doc (read in full) | task chip, work across sessions, plans, worktrees, "not available in Desktop" |
| 2 | https://code.claude.com/docs/de/desktop | vendor doc (German, read) | German terminology "Task-Chip", "neue Sitzungen" |
| 3 | https://code.claude.com/docs/en/agent-teams | vendor doc (read in full) | subagent vs agent-team comparison; CLI-only teams |
| 4 | https://code.claude.com/docs/en/agents.md | vendor doc (read) | five parallel-work approaches; subagent definition |
| 5 | https://code.claude.com/docs/en/cross-session-messaging.md | vendor doc (read) | ListAgents/SendMessage mechanism, delivery semantics |
| 6 | https://code.claude.com/docs/llms.txt | vendor doc index (read in full) | docs structure; whats-new coverage ends w37 |
| 7 | https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md | changelog (read/grepped in full) | absence of spawn_task entries; agent.spawn mod hooks (CLI) |
| 8 | https://github.com/anthropics/claude-code/issues/100913 | GitHub issue (read in full) | spawn_task vs start_session, initiation modes, side-sessions gate, model/effort, unattended gate |
| 9 | https://github.com/anthropics/claude-code/issues/99393 | GitHub issue (read in full) | parentSessionId, linked family, get_session/list_sessions |
| 10 | https://github.com/anthropics/claude-code/issues/53494 | GitHub issue (read in full) | spawn_task payload (title/prompt/tldr), worktree spawn, visibility bug |
| 11 | https://github.com/anthropics/claude-code/issues/80238 | GitHub issue (snippet) | "Suggested task" chip, proactive out-of-scope flagging |
| 12 | https://github.com/anthropics/claude-code/issues/72915 | GitHub issue (snippet) | "Start with worktree" option; CLAUDE_CODE_DISABLE_BACKGROUND_TASKS |
| 13 | https://github.com/anthropics/claude-code/issues/52243 | GitHub issue (snippet) | chip spawns fresh session in new git worktree |
| 14 | https://github.com/anthropics/claude-code/issues/99862 | GitHub issue (snippet) | chip-spawned session effort bug |
| 15 | https://github.com/anthropics/claude-code/issues/101386 | GitHub issue (snippet) | CLAUDE_CODE_CHILD_SESSION env var |
| 16 | https://alphasignal.ai/news/anthropic-s-claude-code-now-runs-nested-sessions-and-saves-dev-environments | news/blog (read in full) | "nested sub-sessions that report results back to the main thread"; saved environments; plans/platforms |
| 17 | https://pasqualepillitteri.it/en/news/24032/claude-code-desktop-nested-sessions-environments | blog (read in full) | Oct 14 date; ClaudeDevs quote; nested-session definition; task-chip docs cross-reference |
| 18 | https://www.mindstudio.ai/blog/claude-code-3-0-parallel-sessions | blog (read in full) | sidebar nesting under parent; demo example; usage-limit impact |
| 19 | https://x.com/WesRoth/status/2110513483833921828 | X post (search snippet; direct fetch blocked) | "Parallel tasks open in nested sessions and report their results back to the main conversation" |
| 20 | https://x.com/ClaudeDevs/status/2110445844675838148 | X thread (direct fetch blocked; quoted in #17) | official announcement, Oct 14, 2026 |
