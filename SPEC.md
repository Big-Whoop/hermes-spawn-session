# hermes-spawn-session — Specification

Status: v1 spec (card t_225e6046), 2026-10-16.
Source of truth: `.hermes/decisions.md` (D1–D13). Research: `.hermes/research/`.
Doc verification: official Hermes docs fetched 2026-10-16 (URLs cited inline as [Dn]
where "Dn" below refers to the doc list in §11, not to decisions; decisions are
written as **D1–D13**).

## 1. Goal

From an active Hermes Desktop session **A**, spawn a visible top-level session **B**
(own model/effort), seeded with task + context, that later reports a structured
result back into A as a message that triggers a real agent turn in A.
Reference model: Claude Desktop "nested sessions".

## 2. Open questions — docs verification (docs-first)

Docs consulted (all fetched 2026-10-16): desktop-plugin-sdk [S1], user-guide/desktop
[S2], developer-guide/plugins [S3], programmatic-integration [S4],
user-guide/features/plugins [S5], user-guide/sessions [S6],
user-guide/features/kanban [S7], subagent-lifecycle-api [S8]. Hermes source was
NOT read for the original card (Q1 was later corrected from source, see Q1); source-derived facts come from the existing research
archive (`REPORT-spawn-with-report-de.md`, refs [58]–[62]) and are marked as such.

### Q1 — Assign A's Desktop project / repo / Kanban board to B

Correction (card t_eec9aafd): the earlier answer ("unresolved, infer project
from the repository") was wrong. Hermes has first-class **Desktop Projects**
(tool `desktop_project`, toolset `project`, actions create/switch/list [S9];
CLI `hermes project create|list|show|use|bind-board` — "State is per-profile"
[S10]; Kanban boards bind to a project [S7]). The docs do not say how a plugin
assigns a project to *another* session, so — with user approval — Hermes source
(/opt/hermes, read-only, Hermes v0.22.2) was consulted:

Findings (source):
- Projects live in the per-profile SQLite `$HERMES_HOME/projects.db`, tables
  `projects` (id, slug, name, `board_slug`, `primary_path`, archived, …) and
  `project_folders` (project_id, path, is_primary)
  [`hermes_cli/projects_db.py:23-60`].
- **There is no per-session project field.** A session's project is *derived
  from its cwd*: `project_for_path(conn, path)` returns the non-archived project
  whose folder equals or is an ancestor of the path, innermost folder wins
  [`hermes_cli/projects_db.py:462-477`]. The same lookup feeds
  `desktop_project list` (`_calling_session_project_id`,
  [`tools/project_tools.py:74-85`]), session.info / status bar
  (`_project_info_for_cwd`, [`tui_gateway/server.py:2296-2310`]) and the RPC
  `projects.for_cwd` [`tui_gateway/methods_projects.py:123-130`].
- `desktop_project switch` resolves the project and only **re-anchors the live
  session's cwd** to the project's primary path via the GUI-gateway callback
  [`tools/project_tools.py:135-145`, `:40-46`] →
  `_apply_project_workspace` sets `cwd`/`explicit_cwd`, persists it and emits
  session.info [`tui_gateway/agent_callbacks.py:194-221`, wired at `:258`].
  Outside a GUI session it moves the profile-global `active_id` pointer instead
  [`hermes_cli/projects_db.py:390-400`] — which must not be touched for B.
- The project's bound board is `projects.board_slug` (`hermes project
  bind-board`, [`hermes_cli/projects_cmd.py:212-216`]).

Answer (implemented in `spawn_session/project.py` + `tools.py`):
1. **Resolve A's project** = `project_for_path(A.cwd)` (read-only re-implementation
   of the Hermes lookup on `projects.db`, opened `mode=ro`).
2. **Assign to B by cwd**: `session.create` with `cwd` (A's cwd or a worktree
   inside it, `cwd_explicit=true`) — the exact state `desktop_project switch`
   produces. The plugin re-checks `project_for_path(B.cwd) == A.project`; then
   `project.assignment = cwd`.
3. **Fallback** when B's cwd is not owned by A's project (e.g. a worktree dir
   outside every project folder): `project.assignment = seed_switch`; B's seed
   message starts with an instruction to call `desktop_project` action=switch
   name=`<A project id>`; `project` is added to a narrowed `allowed_toolsets`
   (A, a desktop session, has it — never exceeds A's rights, D12).
4. **Kanban board**: the project's `board_slug` if bound, else
   `HERMES_KANBAN_BOARD` → `kanban/current` (as before). Passed by name in the
   frontmatter (`kanban_board`) and seed message; no global mutation.
5. The handover frontmatter records `project: {id, slug, name, board,
   primary_path, assignment}` (null when A has no project).

### Q2 — Is a session from `session.create` visible as a top-level tab/row without a desktop plugin?

Findings:
- Session pickers hide only sources `oneshot`, `kanban`, `tool` [S6 §Session
  Sources]; `session.create` supports a `hidden` flag (research [58]). A
  non-hidden gateway-created session is therefore a stored, listable session
  (sidebar row in the session list).
- Opening it as a **tab** is a client action. The desktop SDK documents
  `host.openSession(id, { intent: 'tab' })` [S1 §host].
- A Python backend runs inside the gateway process and can push events to the
  desktop half via `broadcast_plugin_event(plugin_id, event, payload)` →
  `plugin.<id>.<event>` on `host.onEvent` [S1 §Pushing events to your desktop half].

Answer: **Row: yes (docs-implied, verify in card 2). Tab: no — requires the
desktop half.** Design: backend creates B, broadcasts `plugin.spawn-session.child.created`;
the desktop half calls `host.openSession(childId, { intent: 'tab' })`. If no
Desktop window is connected, the broadcast is a logged no-op [S1] and B is
reachable from the sidebar row.

### Q3 — Can a desktop plugin nest a sidebar row under its parent?

Findings: `SESSION_ROW_AREAS.leading/trailing` only decorate existing rows;
`host.sessions.pin/reorder/reorderPinned/setColor` change order/pin/colour
[S1 §Session rows — decorations + the session list API]. No parent/child or
indent API is documented.

Answer: **No. `↳` fallback confirmed.** B's title = `↳ <title>` (via
`session.title`), a `SESSION_ROW_AREAS.leading` badge with the parent's
colour, and `host.sessions.reorder()` placing B directly after A in Recents
where a manual order exists. Detached children: `↳ Detached: <title>`.

### Q4 — Deliver a message into A that triggers a real turn (queued if busy, persisted if closed)

Findings: `ctx.inject_message(content, role="user", session_key=...)`. For the
TUI/Desktop host: "Pass the session's durable `session_key` (the `ses_…` id) …
Hermes queues the text on that session's prompt queue: a busy session keeps the
message for the next turn, an idle session starts one. A key that is not a live
TUI session is left for the messaging gateway … and is never rerouted" [S5
§Injecting Messages]. Injected text is conversational only (no slash commands /
approvals) [S5]. Return value `True` = accepted, not completed [S5].

Answer: **Resolved for live A** via `ctx.inject_message(report_text,
session_key=A.durable_id)`. **Closed/not-live A** is not persisted by Hermes;
the plugin persists: handover status stays `reported`, and on A's reopen the
desktop half shows "1 open report" and delivers on click (D8). Delivery is
marked `delivered` only after the injected message appears in A's history
(`session.history` poll), not on the `True` return value. Secondary fallback
(desktop only): `host.composer.submit(A, text)` which fails closed when A has no
visible surface [S1 §composer].

### Q5 — Detect "running inside a spawned child session" (D10)

Findings: tool handlers receive injected context kwargs incl. `session_id`
[S3 §Step 4 handler rules]; `pre_tool_call` hooks can veto with
`{"action":"block"}` [S3 §Hook reference]; `on_session_start` receives
`session_id, model, platform` [S3]. `check_fn` takes no session context [S3].

Answer: **Resolved via plugin-owned registry.** The plugin records every child
session id (and its compression lineage root) in its state index (§6). The
`spawn_session` handler looks up `kwargs["session_id"]`; if it maps to a child
(any status incl. `detached`), it returns an error JSON ("spawn_session is not
available in a spawned session (one level only)"). The desktop half hides/blocks
the ⌘K command when the focused stored session id is a known child. D13 surface
check uses the same kwargs/platform: non-Desktop platforms refuse with a hint.

## 3. Component layout

```
hermes-spawn-session/                 (installed as ~/.hermes/plugins/spawn-session/)
├── plugin.yaml                       name: spawn-session, kind: tool
├── __init__.py                       register(ctx): tools, command, hooks
├── spawn_session/
│   ├── tools.py                      spawn_session, report_back handlers
│   ├── commands.py                   /report, /abandon, /detach
│   ├── handover.py                   file read/write, frontmatter, report section
│   ├── state.py                      state index + state machine
│   ├── gateway.py                    session.create / title / history calls
│   ├── delivery.py                   inject_message + delivery confirmation
│   └── worktree.py                   git worktree create / WIP-bank / remove
├── dashboard/
│   ├── manifest.json                 { "name": "spawn-session", "api": "plugin_api.py" }
│   └── plugin_api.py                 REST: /children, /spawn, /confirm, /deliver, /abandon, /detach
└── desktop/spawn-session/plugin.js   ESM desktop half (copied to $HERMES_HOME/desktop-plugins/)
```

- Python plugin must be in `plugins.enabled`; backend is imported only then [S1].
- `plugins.entries.spawn-session.allow_gateway_injection: true` is documented as
  required for gateway injection [S5]; the install doc tells the user to set it
  (Desktop/TUI host path is verified in card 4).
- Desktop half: ⌘K command `Spawn session…`, status cards in A, header block in
  B, row decorations, open-report banner; talks to backend via `ctx.rest` with
  polling fallback (`ctx.socket` is a no-op on OAuth remotes) [S1].

### 3.1 Private Hermes seams (catalog rule 9)

`hermes plugins validate` warns about two imports. Both were audited on
2026-10-17 (card t_d28ed43c). Neither has a documented public replacement, so
both stay behind their guarded fallbacks. The upstream hook request is drafted
in `docs/upstream-hook-request.md` (not filed).

| Call | Why it's needed | Public candidates checked | Why they don't fit | Fallback |
| --- | --- | --- | --- | --- |
| `gateway.session_context.get_session_env` (`spawn_session/commands.py:35`) | Slash-command handlers (`/report`, `/abandon`, `/detach`, `/spawn-cleanup`) must know which session invoked them | Injected `session_id` kwarg [S3]; `ctx.profile_name`; `ctx.dispatch_tool` | `register_command` handlers receive only `raw_args` (no context kwargs); `profile_name` is not a session; `dispatch_tool` forwards kwargs into the tool but cannot read the caller's session | `os.environ` `HERMES_SESSION_KEY` / `HERMES_SESSION_ID`; empty means a clean "cannot determine the current session" error |
| `tui_gateway.server.handle_request` (`spawn_session/gateway.py:47`): `session.create`, `prompt.submit`, `session.title`, `session.archive` | Create the visible child B with title/cwd/model/provider/parent/seed (D1, D2, D7, D11) | `ctx.dispatch_tool`; Desktop SDK `host.request` [S1]; API server `POST /api/sessions` | No tool creates sessions; `host.request` exists only in the renderer, but the agent-initiated `spawn_session` tool runs in Python with no desktop round-trip; `POST /api/sessions` needs a separately enabled, keyed API server and only inserts a row (no cwd, no live runtime session, no seed turn) | `GatewayUnavailable`, so the tool returns a JSON error (D13: Desktop/TUI host only) |

Tool handlers already use the public `session_id` kwarg (`tools.py:275`,
`:599`, `:629`).

## 4. Tool schemas

### 4.1 `spawn_session` (agent-initiated, D2/D3/D6/D7/D10/D12/D13)

```json
{
  "name": "spawn_session",
  "description": "Spawn a visible child session for a self-contained task. It reports back here when done.",
  "parameters": {
    "type": "object",
    "properties": {
      "title":      {"type": "string", "maxLength": 80},
      "task":       {"type": "string", "description": "Detailed instructions for the child."},
      "context":    {"type": "string", "description": "Short background summary (TL;DR)."},
      "initiation": {"type": "string", "enum": ["user_asked", "own_initiative"]},
      "model":      {"type": "string", "description": "provider:model; default = parent's model"},
      "effort":     {"type": "string", "enum": ["low", "medium", "high", "xhigh"]},
      "worktree":   {"type": "boolean", "default": false},
      "allowed_toolsets": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["title", "task", "initiation"]
  }
}
```

Rules:
- Refuse in child sessions (Q5) and on non-Desktop surfaces (D13, hint:
  `delegate_task` or a Kanban card).
- `model` must be `provider:model` (billing trap #132117); bare names rejected.
- More expensive model than A → always `proposed` (user confirmation), even when
  `user_asked`. Cost rank comes from config `cost_rank` (§8); unknown = expensive.
- `own_initiative` → status `proposed`, card in A; no session created yet.
- `user_asked` → created immediately unless the cost rule or the concurrency cap
  applies (4th running agent child → `proposed` with "limit reached" note).
- `allowed_toolsets` may only narrow A's toolsets; `spawn_session` is always removed.
- Returns `{"ok":true,"handover_id","status","child_session_id"|null,"handover_path"}`.

### 4.2 `report_back` (child-only, D4)

```json
{
  "name": "report_back",
  "parameters": {
    "type": "object",
    "properties": {
      "result":     {"type": "string"},
      "changes":    {"type": "array", "items": {"type": "string"}},
      "open_items": {"type": "array", "items": {"type": "string"}},
      "artifacts":  {"type": "array", "items": {"type": "object",
                     "properties": {"kind": {"enum": ["path","commit","branch","url","pr"]},
                                    "value": {"type": "string"}}, "required": ["kind","value"]}}
    },
    "required": ["result"]
  }
}
```

Refuses outside a running child (not a child, or status ≠ `running`). Repeat
calls after `reported`/`delivered` append a new "Report (n)" section (follow-up
reports allowed; B stays open).

### 4.3 Slash commands (in B)

- `/report [note]` — asks B's agent (via injected user message) to call
  `report_back` with a full structured report; `note` is passed as guidance.
- `/abandon [reason]` — D11 abort.
- `/detach confirm` — D11 detach (bare `/detach` only explains; irreversible).
- `/spawn-cleanup <handover_id> yes|no` — the user's answer to the D11
  "remove worktree + branch?" question after an abort (never automatic).

Implementation notes (card 4): plugin slash commands receive only the raw
argument string; the calling session is read from the gateway-bound session
context (`HERMES_SESSION_KEY`). `/report` injects the request into B itself via
`inject_message`. Undeliverable abort/detach notices are kept in the handover
frontmatter (`pending_notices`) and retried with the reports by the backend
action `deliver_pending(parent)` (the desktop "open reports" banner, card 6).
Backend actions for A's card buttons: `action_abandon`, `action_detach`,
`action_deliver_pending` in `spawn_session/commands.py`.

## 5. Handover file format (D5)

Path: `<A.cwd>/.hermes/handovers/YYYY-MM-DD-<slug>.md` (slug from title, de-duplicated
with `-2`, `-3`). If `<A.cwd>` is not writable, fallback
`$HERMES_HOME/spawn-session/handovers/`.

```markdown
---
handover_id: hs_20261016_ab12cd
parent_session_id: ses_…        # durable lineage root of A
child_session_id: ses_… | null
title: "Fix flaky test"
status: proposed|running|reported|delivered|abandoned|detached
initiation: user_asked|own_initiative
initiator: agent|user
model: anthropic:claude-…
effort: medium
cwd: /path
worktree: { path: /path/.worktrees/spawn-fix-flaky-test, branch: spawn/fix-flaky-test } | null
kanban_board: hermes-spawn-session | null   # project's bound board first
project: { id, slug, name, board, primary_path, assignment: cwd|seed_switch } | null
allowed_toolsets: [...] | null
created_at: 2026-10-16T16:00:00+02:00
updated_at: …
history:
  - { at: …, from: proposed, to: running, by: user }
---
# Task
…
# Context
…
# Report
## Result
## Changes
## Open items
## Artifacts
```

B's first message = the file body (Task + Context + Kanban/worktree hints +
"call `report_back` when done"). A receives the Report section as message,
prefixed `[spawn-session report: <title> (<handover_id>)]`.

## 6. State machine

```
proposed ──confirm──▶ running ──report──▶ reported ──inject ok──▶ delivered
   │                    │  │                  │                       │
   └─decline─▶ abandoned ◀┘  └─detach─▶ detached ◀─────── detach ──────┘
                (abort)                  (terminal)
```

- `proposed` → `running` (user confirms card) | `abandoned` (user declines).
- `running` → `reported` (`report_back`) | `abandoned` (`/abandon`, card button)
  | `detached` (`/detach`, card button).
- `reported` → `delivered` (report visible in A's history) | `detached`.
- `delivered` → `reported` (follow-up report) | `detached`.
- `abandoned`, `detached` are terminal. Abandon sends A a short abort report
  (reason + state so far); detach sends a one-line notice.
- Abandon/detach with worktree: uncommitted changes → WIP commit + push (if a
  remote exists), then ask the user whether to remove worktree + branch; never
  auto-delete. B's session is archived on abandon, never deleted.
- Index: `$HERMES_HOME/spawn-session/state.json` maps `child_session_id`,
  `parent_session_id` → `handover_path`; the handover file is authoritative and
  the index is rebuilt from handover files on startup.
- Concurrency: running agent-initiated children per parent ≤ `max_children`.

## 7. UI (desktop half, D9)

- B header (Contribute in B's workspace header): "Started by Hermes from
  **‹A title›**" (link → `host.openSession(A)`), collapsible Task and Context.
- A: status card per child (running / reported / delivered / abandoned /
  detached) with buttons Open, Abort, Detach; `proposed` card with title, task,
  context, model selector, Start / Decline.
- Sidebar: `↳` title prefix and leading badge (Q3). Ordering after A is NOT
  applied (card t_1f857d7f): `host.sessions.reorder()` replaces the whole manual
  Recents order and the SDK cannot read it, so reordering would clobber the
  user's own order.
- Reopen of A with `reported` children: banner "N open report(s)" → Deliver.

## 8. Config keys (`plugins.entries.spawn-session.*`)

| Key | Default | Meaning |
|---|---|---|
| `max_children` | `3` | Max running agent-initiated children per parent (D10) |
| `handover_dir` | `.hermes/handovers` | Relative to A's cwd |
| `worktree_dir` | `.worktrees` | Relative to repo root |
| `branch_prefix` | `spawn/` | Worktree branch prefix |
| `title_prefix` | `↳ ` | Child title prefix (Q3) |
| `detached_prefix` | `Detached: ` | Added after detach (D11) |
| `cost_rank` | `{}` | `provider:model` → integer; higher = more expensive (D6) |
| `delivery_confirm_timeout_s` | `120` | Wait for report to appear in A's history |
| `allow_gateway_injection` | user sets `true` | Hermes host permission [S5] |

## 9. Cards and acceptance tests

Card 2 — Backend core: `spawn_session` + session.create + handover file
- AT2.1 `user_asked` call in a Desktop session creates a handover file with
  valid frontmatter and a child session whose first message is the file body.
- AT2.2 Child session has `model`/`provider`/`effort` as requested; default = A's.
- AT2.3 Bare model name rejected; more expensive model → `proposed`.
- AT2.4 Child is visible as a sidebar row; `cwd` = A's cwd; with Group by →
  Projects it appears under A's project (Q1/Q2 empirical check; result recorded).
- AT2.5 `worktree: true` creates `spawn/<slug>` worktree and B's cwd is it.
- AT2.6 `allowed_toolsets` narrows B's toolsets; superset rejected.

Card 3 — Guards: nesting, concurrency, surfaces
- AT3.1 `spawn_session` inside B (incl. detached B) refuses with the D10 message.
- AT3.2 4th running agent-initiated child → `proposed` "limit reached"; user spawns unlimited.
- AT3.3 CLI / Telegram session: tool refuses with the D13 hint.

Card 4 — Report-back and delivery
- AT4.1 `report_back` in B appends Report section; status `reported`.
- AT4.2 A idle → report injected, a turn runs in A, status `delivered`.
- AT4.3 A mid-turn → report delivered as the next turn after A finishes.
- AT4.4 A not live → status stays `reported`; after reopen, deliver-on-click works.
- AT4.5 `/report` in B triggers a `report_back` call.
- AT4.6 Follow-up report → "Report (2)" section, delivered again.

Card 5 — Desktop half: ⌘K, tabs, cards, header
- AT5.1 ⌘K "Spawn session…" creates B (user-initiated) and opens it as a tab.
- AT5.2 Agent-created B opens as a tab via the `child.created` plugin event.
- AT5.3 `own_initiative` shows a proposed card in A; Start creates B, Decline → `abandoned`.
- AT5.4 B header shows parent link + collapsible Task / Context.
- AT5.5 ⌘K spawn is blocked while a child session is focused.
- AT5.6 No hardcoded colours; plugin loads without error toast.

Card 6 — Sidebar presentation and open-report banner
- AT6.1 Child title has `↳ ` prefix and leading badge; ordered after A.
- AT6.2 Reopening A with `reported` children shows the banner; Deliver works.

Card 7 — Abort / detach / cleanup
- AT7.1 `/abandon` or Abort button → `abandoned`, A gets abort report, B archived.
- AT7.2 Dirty worktree is WIP-committed (+pushed when a remote exists) before
  the removal prompt; nothing is deleted without confirmation.
- AT7.3 `/detach` → `detached`, A gets one-line notice, title `↳ Detached: …`,
  `report_back` refused afterwards, spawn ban still applies, no re-attach.

## 10. Non-goals (v1)

CLI / messaging surfaces (D13); multi-level nesting (D10); re-attach (D11);
sharing one handover across profiles.

## 11. Doc sources

- [S1] https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk
- [S2] https://hermes-agent.nousresearch.com/docs/user-guide/desktop
- [S3] https://hermes-agent.nousresearch.com/docs/developer-guide/plugins
- [S4] https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration
- [S5] https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins#injecting-messages
- [S6] https://hermes-agent.nousresearch.com/docs/user-guide/sessions#session-sources
- [S7] https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban#boards-multi-project
- [S8] https://hermes-agent.nousresearch.com/docs/developer-guide/subagent-lifecycle-api
- [S9] https://hermes-agent.nousresearch.com/docs/reference/tools-reference#project-toolset
- [S10] https://hermes-agent.nousresearch.com/docs/reference/cli-commands#hermes-project
- Research archive refs [58]–[62] (Hermes source, verified 2026-10-16 in the
  research phase): `tui_gateway/contracts/sessions.py` (`session.create` params
  incl. `cwd`, `title`, `parent_session_id`, `hidden`).
