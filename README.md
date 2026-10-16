# hermes-spawn-session

A Hermes Agent plugin for **Hermes Desktop**. From the session you are working
in (A), it starts a new, visible session (B) with its own model and reasoning
effort. B gets a task and context, works on its own, and then **reports back
into A**. The report arrives in A as a message, and A runs a turn on it.

The idea comes from the "nested sessions" feature in Claude Desktop (screenshot:
[`.hermes/research/2026-10-16-spawn-with-report/claude-desktop-spawn-with-report-ui.png`](.hermes/research/2026-10-16-spawn-with-report/claude-desktop-spawn-with-report-ui.png)).
One reason to use it: send a routine task to a cheaper model, or a hard task to
a stronger one, without switching the model of your current chat. Switching
throws away the prompt cache.

```
A (your chat) ──spawn──▶ B "↳ Fix flaky test"  (own model/effort, same project)
      ▲                         │
      └──── report message ◀────┘  /report or report_back
```

## Requirements

- **Hermes Desktop.** The plugin only works in Desktop sessions (decision
  D13). In CLI, TUI-only or messaging sessions, the tool refuses and suggests
  something else.
- **Hermes v0.22.2.** This is the version the plugin was built and tested
  against.
- **Python dependencies.** These are declared in `pyproject.toml`: currently
  only `PyYAML>=6,<7`. Hermes provides `fastapi` (used by the dashboard
  backend) and its own modules, so they are not declared.
- **git** (optional). Needed only for the worktree option.

## Installation

1. Put the repository in your plugins folder as `spawn-session`. You can clone
   it there or symlink it:

   ```sh
   git clone https://github.com/Big-Whoop/hermes-spawn-session ~/.hermes/plugins/spawn-session
   # or: ln -s /path/to/hermes-spawn-session "$HERMES_HOME/plugins/spawn-session"
   ```

   The repository is one package. It contains the agent half (`__init__.py`,
   `spawn_session/`), the REST backend (`dashboard/`) and the desktop half
   (`desktop/plugin.js`).

2. Enable the plugin and accept the **dependency consent** prompt:

   ```sh
   hermes plugins enable spawn-session
   ```

   Hermes installs the dependencies declared in `pyproject.toml` only after
   you consent. If you added `spawn-session` to `plugins.enabled` by hand,
   Hermes skipped that step. Run this to trigger it:

   ```sh
   hermes plugins disable spawn-session && hermes plugins enable spawn-session
   ```

3. Allow report delivery. Reports reach A through `ctx.inject_message`, which
   needs this setting in `config.yaml`:

   ```yaml
   plugins:
     entries:
       spawn-session:
         allow_gateway_injection: true
   ```

4. **Restart the gateway / dashboard.** The agent half and the REST backend
   (`/api/plugins/spawn-session/`) are only loaded at startup.

5. In Desktop, go to **Capabilities → Plugins** and enable **Spawn session**.
   Desktop plugins are opt-in. If the plugin is not listed, click **Rescan**.

6. Check that it loaded:
   - `agent.log` and `gui.log` contain no `Failed to load plugin spawn-session`
     line.
   - The ⌘K palette shows **Spawn session with report**.

### Uninstall

1. Run `hermes plugins disable spawn-session`. You can also remove the plugin
   from `plugins.enabled` and delete `plugins.entries.spawn-session`.
2. Disable **Spawn session** under Desktop **Capabilities → Plugins**.
3. Delete `~/.hermes/plugins/spawn-session` (or remove the symlink), then
   restart the gateway.
4. Optional: delete the leftover data. This is the state index in
   `$HERMES_HOME/spawn-session/` and the handover files in
   `<project>/.hermes/handovers/`. Child sessions are normal sessions and
   stay in your history.

## Usage

### Starting a child session

- **⌘K → Spawn session with report.** This opens a dialog with *Title*, *Task*,
  *Context* (optional), *Model* and *Effort*. Model and effort start with A's
  values. **Start** creates B right away and opens it in a tab. Spawns you
  start yourself have no limit.
- **Ask the agent.** For example: "hand this over to a new session with a
  cheaper model". The agent calls the `spawn_session` tool with
  `initiation: user_asked`, and B starts right away and opens as a tab.
- **Agent proposals.** If the agent decides on its own that a handover makes
  sense (`own_initiative`), nothing starts yet. A **Proposed session** card
  appears above A's composer. It shows the title, the model, the task and
  context (collapsed), and the reason it needs your confirmation. Your
  options:
  - **Start**: creates B.
  - **Edit**: opens the dialog with the proposal filled in, so you can change
    it before starting.
  - **Dismiss**: marks the proposal `abandoned`. No session is created.

### Model, effort and confirmation

- Models are written as `provider:model`. Bare model names are rejected, so a
  session cannot end up billed to the wrong provider.
- If you don't pick a model or effort, B uses A's.
- Sometimes the agent asks for a model that is **more expensive** than A's.
  In that case the spawn always becomes a proposal card, even if you asked
  for the handover. Cost is decided by the `cost_rank` setting (see below).
  Models not listed there count as most expensive. If neither model is
  listed, they count as equal.

### Working directory, worktree, project, Kanban

- B starts in A's working directory.
- **Worktree.** When the agent passes `worktree: true`, the plugin creates a
  git worktree `<repo>/.worktrees/<slug>` on branch `spawn/<slug>`, and B
  works there. For a proposal, the worktree is only created when you click
  Start. The ⌘K dialog has no worktree option yet.
- **Project.** B joins A's Hermes Desktop project. Hermes works out a session's
  project from its working directory. If B's directory is outside the project
  (for example, a worktree outside every project folder), B's first message
  tells it to run `desktop_project switch` first.
- **Kanban board.** B uses the board bound to A's project. If there is none,
  it uses `HERMES_KANBAN_BOARD` or the current board. The board is named in B's
  first message. No global setting is changed.
- **Toolsets.** The agent can limit B to fewer toolsets with
  `allowed_toolsets`. It can only take tools away, never give B more than A
  has. B never gets `spawn_session`.

### Working in B

B's first message holds the task, the context, the worktree and Kanban hints,
and an instruction to call `report_back` when done. Above B's composer, a
header reads **"Started by Hermes from ‹A›"**. Clicking it opens A. The header
also shows B's status and has collapsible **Task** and **Context** blocks.

### Reporting back

- Type **`/report [note]`** in B. This asks B's agent to call `report_back`
  with a full report. Any note you add is passed along as guidance.
- B's agent can also call **`report_back`** on its own when it finishes. A
  report has `result` (required), plus `changes`, `open_items` and
  `artifacts`. Artifacts are paths, commits, branches, URLs or PRs.

The report is added to the handover file. A receives it as a user message that
starts with `[spawn-session report: <title> (<handover_id>)]`, followed by the
report and the paths to the child session and the handover file.

- If A is idle, it runs a turn on the report right away.
- If A is busy, the report is handled after the current turn finishes.

The status changes to `delivered` only once the message shows up in A's
history, not just when it was accepted.

B stays open after reporting. Every later `report_back` adds a "Report (n)"
section and is delivered again.

### When A is closed: "open report"

If A is not live, the report stays `reported` in the handover file. When you
open A again, a **"1 open report"** notice (or "N open reports") appears above
the composer. Click **Deliver** to send it. Abort and detach notices that
could not be delivered are kept and sent the same way.

### Status cards in A

A shows one card per active child (`running`, `reported` or `delivered`). Each
card shows the status, the title and the number of reports, with these
buttons:

- **Open**: opens B in a tab.
- **Abort**: only while the child is `running`.
- **Detach**: asks you to confirm, because it can't be undone.

Abandoned and detached children no longer get a card.

### Abort and detach

- **`/abandon [reason]`** in B, or **Abort** on A's card.
  - The status becomes `abandoned`.
  - A gets a short abort report: the reason and the state so far.
  - B is archived, not deleted.
  - If B had a worktree, uncommitted changes are saved first as a WIP commit
    and pushed if a remote exists. Then you are asked whether to remove the
    worktree and branch. Answer with `/spawn-cleanup <handover_id> yes|no`.
    Nothing is ever deleted automatically.
- **`/detach confirm`** in B, or **Detach** on A's card.
  - The status becomes `detached`, and this cannot be undone.
  - B continues as an independent session and sends no more reports.
  - A gets a one-line notice.
  - B's title changes to `↳ Detached: <title>`.
  - A plain `/detach` without `confirm` only explains what detaching does.

### Sidebar

Desktop cannot nest sidebar rows. Child sessions are marked by a `↳ <title>`
title prefix and a small `↳` badge in front of the row (`⤳` once detached).
The plugin does not reorder your Recents list.

### Limits

- **One level only.** B, including a detached B, cannot spawn further
  sessions. The tool refuses, and ⌘K is blocked while B is focused.
- At most **3 running agent-started children** per parent (`max_children`).
  If the agent starts a 4th, it becomes a proposal marked "limit reached".
  Spawns you start with ⌘K have no limit.

### Handover files

Each spawn writes a file `<A's cwd>/.hermes/handovers/YYYY-MM-DD-<slug>.md`.
If that folder is not writable, the file goes to
`$HERMES_HOME/spawn-session/handovers/` instead. The file has YAML
frontmatter (session ids, model, effort, cwd, worktree, project, board, status
history), plus the Task, the Context, and every Report. It is the
authoritative record. The index in `$HERMES_HOME/spawn-session/state.json` is
rebuilt from these files.

## Configuration

Settings go under `plugins.entries.spawn-session` in `config.yaml`:

| Key | Default | Meaning |
|---|---|---|
| `max_children` | `3` | Max running agent-started children per parent |
| `worktree_dir` | `.worktrees` | Worktree folder, relative to the repo root |
| `branch_prefix` | `spawn/` | Branch prefix for worktrees |
| `title_prefix` | `↳ ` | Title prefix for child sessions |
| `detached_prefix` | `Detached: ` | Added after `title_prefix` when a child is detached |
| `cost_rank` | `{}` | Map of `provider:model` to an integer; higher means more expensive |
| `delivery_confirm_timeout_s` | `120` | How long to wait for a report to appear in A's history |
| `allow_gateway_injection` | not set | Hermes permission for `inject_message`; set it to `true` |

Example:

```yaml
plugins:
  entries:
    spawn-session:
      allow_gateway_injection: true
      max_children: 3
      cost_rank:
        "custom:qwen-local": 1
        "anthropic:claude-sonnet": 5
        "anthropic:claude-opus": 10
```

`handover_dir` is listed in SPEC.md §8, but the code does not read it yet.
Handover files always go to `.hermes/handovers`.

## Troubleshooting

- **"Spawn session" is not listed in Capabilities → Plugins.** Click
  **Rescan**. Check that the folder is named `spawn-session` and contains
  `desktop/plugin.js`, then restart the dashboard.
- **`Failed to load plugin spawn-session` / `No module named 'yaml'`.** The
  dependency consent was skipped. Run
  `hermes plugins disable spawn-session && hermes plugins enable spawn-session`,
  accept the prompt, and restart the gateway.
- **⌘K says "spawn-session backend unavailable".** The REST backend is only
  mounted when `spawn-session` is in `plugins.enabled` and the gateway was
  restarted after that.
- **The report never arrives in A.**
  - Check `allow_gateway_injection: true`.
  - If A was closed, open it and click **Deliver** on the open-report notice.
  - A status that stays `reported` means the message was not found in A's
    history within `delivery_confirm_timeout_s`.
  - The handover file always contains the report.
- **The tool refuses in the CLI, Telegram or another messaging surface.** This
  is intended (D13: Desktop only). Use `delegate_task` or a Kanban card
  instead.
- **"Not available in a spawned session".** You are in a child session, and
  only one level of nesting is allowed. Ask the parent to coordinate.

## Known limitations

- Sidebar nesting is shown with the `↳` prefix and a badge only, because the
  desktop SDK has no API for nested rows.
- Desktop sessions only. CLI and messaging surfaces are not supported (D13).
- The ⌘K dialog has no worktree toggle.
- `handover_dir` is not read yet (see Configuration).
- The full end-to-end check in a live Desktop is still pending (Kanban card
  `t_787f6427`). Automated tests cover the Python half, the REST routes and a
  Node smoke test of the desktop half.

## More

- Specification: [SPEC.md](SPEC.md)
- Design decisions D1–D13: [.hermes/decisions.md](.hermes/decisions.md)
- Research archive (German): [.hermes/research/](.hermes/research/)
- Contributing / coding agents: [AGENTS.md](AGENTS.md)

## License

MIT — see [LICENSE](LICENSE).
