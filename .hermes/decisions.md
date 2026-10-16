# Design Decisions — hermes-spawn-session

Decisions from the spec Q&A session (2026-10-16). Basis: `.hermes/research/`.
Reference model: Claude Desktop "nested sessions" (see screenshot in research).

| # | Topic | Decision |
|---|---|---|
| D1 | Visibility of child session B | B is a real, visible **top-level session tab** in Hermes Desktop (Option B: desktop plugin, plus Python backend using gateway RPC `session.create`). Subagent-only (Option A) rejected: not interactive, not persistent. |
| D2 | Who initiates | **Both**: user via ⌘K palette / button, and agent via tool `spawn_session` (backend creates the session). |
| D3 | Agent-initiated flow | Mirrors Claude `user_asked` / `own_initiative`: if the user explicitly asked for a handover, B starts immediately; if the agent proposes it on its own, A shows a **card** (title, task, context, model) and B starts only after the user clicks. |
| D4 | Completion + report-back | **Explicit completion**: user triggers `/report` or button in B, or B's agent calls tool `report_back`. B writes a structured report (result, changes, open items, artifacts: paths/commits/branches). Delivered to A as a message that **triggers a turn** in A. B stays open afterwards. |
| D5 | Persistence | **File + message**: each handover is a file `.hermes/handovers/YYYY-MM-DD-<slug>.md` with frontmatter (parent/child session IDs, model, status), task, context; the report is appended as a "Report" section to the same file. B receives the content as first message; A receives the report as message. Survives restarts/compaction and A being inactive. |
| D6 | Model / effort | **Default = A's model**, overridable by user (⌘K / card) and agent (`model`, `provider`, `effort` params). Agent choosing a **more expensive** model than A always requires user confirmation. Always `provider:model` syntax (billing trap #132117). |
| D7 | Working directory + project context | **Default = A's cwd**; optional `worktree: true` creates a git worktree + branch `spawn/<slug>`, report lists branch/commits. B also **inherits A's Hermes Desktop project** (workspace) and its associated repo and Kanban board, if available in A. (Open: how a plugin assigns a project to a new session — `session.create` only has `cwd`; verify docs-first in spec phase.) |
| D8 | Report delivery when A is busy/closed | **Queue**: if A is mid-turn, deliver the report as a new turn after it finishes. If A is closed / process gone, the report stays in the handover file with status `reported`; when A is reopened the plugin shows "1 open report" and delivers on click. |
| D9 | Sidebar / UI presentation | **Like Claude**: B nested under A in the sidebar; header in B "Started by Hermes from **‹A title›**" (link to A) with collapsible "Task" and "Context" blocks; status card in A (running / reported / open). If the desktop plugin API cannot nest sidebar rows (verify docs-first), fallback = `↳` title prefix. |
| D10 | Nesting / concurrency | **One level only**: a spawned session (B) may NOT spawn further sessions (`spawn_session` tool unavailable / refused in child sessions; ⌘K spawn from B also blocked). Parallel children of A: **max 3 running agent-initiated** children (configurable); a 4th agent spawn asks the user first. User-initiated spawns (⌘K) are unlimited. |

## Open questions

(Tracked in the Q&A session; appended as decided.)
