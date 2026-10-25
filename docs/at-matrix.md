# Acceptance-test matrix (SPEC.md §9 → tests)

One row per acceptance test of [SPEC.md §9](../SPEC.md#9-cards-and-acceptance-tests).
Coverage was taken from the test code itself (grep for AT ids, REST routes
in `dashboard/plugin_api.py`, and the handlers in `spawn_session/tools.py`,
`commands.py`, `lifecycle.py`, `delivery.py`), not from file names. State: 2026-10-21, base `691e7dd`; backend rows completed on 2026-10-22.

Tiers:

- unit: pytest seam test in `tests/` (gateway, injection and history faked).
- backend-e2e: `e2e/specs/backend.api.spec.ts`. Runs against an isolated
  `hermes serve --port 0` and a mock LLM, in the sandbox and in CI.
- desktop-e2e: `e2e/specs/desktop.ui.spec.ts` (Electron). It is only
  typechecked in the sandbox and runs in the hermes-e2e k8s Job.
- smoke: `scripts/smoke_desktop_plugin.mjs` (Node, registration only).
- live-only: no automated harness can reach it (see the justification).
- MISSING: the planned location is in the last column.

Desktop testability: every element a desktop spec clicks or asserts carries a
stable `data-spawn-session-*` attribute (list in the header of
`desktop/plugin.js`). Desktop specs run first in the hermes-e2e Job.

Abbreviations: `rules` = `tests/test_spawn_rules.py`, `rb` =
`tests/test_report_back.py`, `dt` = `tests/test_desktop.py`, `ui` =
`tests/test_desktop_ui.py`, `be` = backend spec, `de` = desktop spec.

## Matrix

| AT | D | Mechanism under test | Current coverage | Tier | Planned test (layer: file → test) |
|---|---|---|---|---|---|
| AT2.1 | D2, D3, D5 | `spawn_session_handler` with `user_asked`: writes the handover file, calls `session.create`, seeds B with the file body | rules `TestUserAskedHappyPath::test_creates_running_handover_and_child_session`, `test_state_index_registers_child_ids`, `test_broadcasts_child_created`; `tests/test_handover.py::test_create_writes_file_with_frontmatter`, `test_child_first_message_has_no_frontmatter`; be `⌘K spawn: child starts…` (user path); be `AT2.6 allowed_toolsets…` (A's agent calls `spawn_session` with `user_asked` in a real mock-LLM turn in the serve) | unit + backend-e2e | — |
| AT2.2 | D6 | Default model, provider and effort are A's; overrides go into the `session.create` frame | rules `TestModelDefaults::test_default_model_is_parent_model`, `test_explicit_model_and_effort_override`; dt `TestUserSpawn::test_spawn_uses_parent_model_by_default`, `test_model_and_effort_override`; be `⌘K spawn: child starts…` (card `model`) | unit + backend-e2e | — |
| AT2.3 | D6 | A bare model name is rejected; a more expensive model gives `proposed` (`cost_rank`, unknown = expensive) | rules `TestModelRules::test_bare_model_name_rejected`, `test_more_expensive_model_requires_confirmation`, `test_cheaper_model_starts_immediately`, `test_unknown_child_model_counts_as_expensive`, `test_two_unknown_models_are_equal`; be `⌘K spawn: validation errors are 400` (bare model, REST); be `AT2.3 cost rule: a more expensive model is a proposal…` (helper `spawn --model custom:mock-e2e-pricey` → `proposed` + note in `/proposals`, `/confirm` starts B; same model starts at once); de `AT2.3: cost-limited proposal card shows the note and Start works` (`ensureCostRank` in `e2e/support/desktop.ts`) | unit + backend-e2e + desktop-e2e | — |
| AT2.4 | D1, D7, Q1/Q2 | B is a sidebar row, `cwd` = A's cwd, appears under A's project with Group by → Projects | rules `test_creates_running_handover_and_child_session` (`cwd` param); `tests/test_spawn_project.py` `TestAssignment::test_cwd_inherits_project_and_board`, `TestDesktopPaths::*`; be `waitForChildRow` (state.db row exists); de `status card in A, ↳ sidebar badge` (row visible) | unit + backend-e2e + desktop-e2e | Desktop: `desktop.ui.spec.ts` → `AT2.4: Group by Projects lists B under A's project` (project registered with `hermes project create` in the isolated HERMES_HOME; the host "Group by" selectors are unverified until the first hermes-e2e Job run). |
| AT2.5 | D7 | `worktree: true` creates `spawn/<slug>` and B's cwd is the worktree | rules `TestWorktree::test_worktree_true_creates_branch_and_sets_cwd` (fake `_create_worktree`), `test_no_worktree_for_proposed_handover`, `test_worktree_false_keeps_parent_cwd`; `tests/test_spawn_worktree.py::test_create_worktree` (real git); dt `test_worktree_created_only_on_start`; `tests/test_spawn_project.py::test_confirm_with_worktree_replans_assignment`; rules `TestWorktree::test_worktree_true_real_git` (handler + real git); be `AT2.5 worktree: true creates spawn/<slug>…` (tool and ⌘K path, git `projectDir` with a bare `origin`) | unit + backend-e2e | — |
| AT2.6 | D12 | `allowed_toolsets` narrows B's tools (`pre_tool_call` guard); `spawn-session` is stripped; superset rejected | rules `TestAllowedToolsets::*` (recorded, stripped, unknown name rejected), `TestToolsetGuard::test_narrowed_child_blocks_foreign_toolset`, `test_report_back_allowed_in_child`, `TestAllowedToolsets::test_superset_of_parent_rejected`, `test_narrowing_within_composite_parent_toolset_accepted`, `test_unknown_parent_toolsets_refuse_narrowing`; be `AT2.6 allowed_toolsets: B is narrowed…` (A's agent spawns B with `[file, spawn-session]`, `spawn-session` stripped, a `terminal` call in B's real turn is blocked by the guard; unknown name rejected), be `AT2.6 allowed_toolsets: a superset of A's toolsets is rejected…` (A pinned to `file,web`: `[file, terminal]` rejected naming `terminal`, `[file, spawn-session]` accepted as `[file]`) | unit + backend-e2e | — (superset check: `tools._check_toolset_superset` compares against A's enabled toolsets from `tools.list`; a toolset counts as covered when all its tools are in A's enabled toolsets; unknown A toolsets → refused) |
| AT3.1 | D10 | `spawn_session` refused in B, in a detached B and in a compressed continuation of B | rules `TestNestingAndConcurrency::test_spawn_inside_child_refused`, `test_spawn_in_compressed_continuation_of_child_refused`, `TestToolsetGuard::test_spawn_blocked_in_child`, `test_guard_enforced_in_compressed_continuation`; rb `TestAbandon::test_abandon_notifies_and_archives` and `TestDetach::test_detach` (index keeps the ban); dt `test_refused_inside_child`; be `D10: nested spawn from B is refused`; de `child header in B and nested-spawn refusal`; rb `TestDetach::test_spawn_refused_after_detach`; be `AT7.3 /detach in B…` and `Detach: needs confirm=true…` (propose from a detached B refused) | unit + backend-e2e + desktop-e2e | — |
| AT3.2 | D10 | The 4th running agent child gives `proposed` "limit reached"; user spawns are unlimited | rules `test_fourth_agent_child_is_proposed`, `test_cap_after_spawns_through_handler`, `test_two_id_children_counted_once`, `test_user_initiated_children_do_not_count`, `test_max_children_configurable`, `test_non_running_children_do_not_count`; dt `test_user_spawns_are_not_capped`; be `AT3.2 D10 cap: the 4th running agent spawn is a "limit reached" proposal…`; de `AT3.2: limit-reached proposal card after three running agent children` | unit + backend-e2e + desktop-e2e | — |
| AT3.3 | D13 | CLI, Telegram and other non-desktop sources refused with the `delegate_task`/Kanban hint | rules `test_non_desktop_surface_refused[cli,kanban,telegram,tui,cron]`; dt `test_refused_on_non_desktop`; be `D13: a non-desktop parent cannot spawn` | unit + backend-e2e | — |
| AT4.1 | D4, D5 | `report_back` appends the Report section; status `reported` | rb `TestReportGeneration::*`, `TestReportBack::test_appends_report_and_delivers`, `test_refused_outside_child`, `test_works_from_compression_continuation`; `tests/test_handover.py::test_append_report_and_follow_up`; be `report: B reports…`, `report_back outside a child session is refused` | unit + backend-e2e | — |
| AT4.2 | D8 | A idle → report injected, a turn runs in A, then `delivered` (confirmed from A's history) | rb `test_appends_report_and_delivers` (fake inject + history), `test_history_contains_follows_continuations` (real sqlite); be `report: B reports…` (accepts delivered or open); `scripts/live_report_test.py` (real gateway + real LLM turn); be `AT4.2 report to an idle live A is delivered…` (A live via the gateway WS, B's agent calls `report_back` in a mock-LLM turn, status `delivered`, marker in A's history and in the mock's requests) | unit + backend-e2e + live script | — |
| AT4.3 | D8 | A mid-turn → accepted into the queue, delivered as the next turn | rb `test_accepted_but_unconfirmed_stays_reported`, `test_redelivery_is_idempotent` (fake: "accepted but not yet in history"); `scripts/live_report_test.py` (queued behind A's turn); be `AT4.3 report while A is mid-turn…` (20 s mock reply in A; `reported` during the turn, `delivered` after, report persisted after A's finished turn) | unit + backend-e2e + live script | — |
| AT4.4 | D8 | A not live → stays `reported`; after reopen, deliver-on-click delivers | rb `test_parent_not_live_keeps_reported`, `test_deliver_pending_after_reopen`; ui `TestOpenReports::test_reported_while_parent_closed_counts_as_open`, `test_deliver_on_click`, `test_parent_still_closed_keeps_report`; be `report: B reports…` (`POST /deliver` shape only); de `report: open-report notice in A and Deliver` (either branch); be `AT4.4 A not live: report stays reported, reopen + Deliver delivers`; de `AT6.2 / AT4.4: closed A shows N open report(s) and Deliver delivers` (forces the notice branch) | unit + backend-e2e + desktop-e2e | — |
| AT4.5 | D4 | `/report [note]` in B injects a `report_back` request into B | rb `TestCommands::test_report_command_injects_prompt_into_b`, `test_commands_refused_outside_child`; be `AT4.5 /report in B makes B's agent call report_back` (`command.dispatch` over the gateway WS) | unit + backend-e2e | — |
| AT4.6 | D4 | A follow-up report gives a "Report (2)" section, delivered again | rb `test_follow_up_report`, `test_follow_up_while_still_reported`; `tests/test_handover.py::test_append_report_and_follow_up`; be `AT4.6 follow-up report: Report (2) is appended and delivered again` (two persisted report turns in A, `reports=2`, `# Report (2)` in the file) | unit + backend-e2e | — |
| AT5.1 | D2 | ⌘K palette command creates B (user-initiated) and opens it as a tab | dt `TestUserSpawn::*`; be `⌘K spawn: child starts…`; smoke (palette registered); de `⌘K spawn dialog starts a child B` | unit + backend-e2e + desktop-e2e | Desktop: done, `AT5.1: ⌘K spawn dialog starts a child B and focuses its tab` (B's header renders only for the focused session). |
| AT5.2 | D1 | An agent-created B opens as a tab via the `child.created` event | rules `test_broadcasts_child_created` (event emitted); smoke (listener registered) | unit + smoke | Desktop: `desktop.ui.spec.ts` → `AT5.2: an agent-created B opens as a tab (child.created event)`. The agent proposal is started via REST `/confirm` so the event comes from the serve process the Desktop listens to (a helper-process broadcast reaches no client); initiator stays `agent`. |
| AT5.3 | D3 | `own_initiative` gives a proposed card; Start creates B; Decline/Dismiss gives `abandoned` | rules `TestOwnInitiative::*`; dt `TestProposals::*`; rb `test_decline_proposal`; be both `own_initiative proposal…` tests; de `proposal card: Dismiss, Edit, Start` | unit + backend-e2e + desktop-e2e | — |
| AT5.4 | D9 | B header: parent link and collapsible Task / Context | ui `TestChildHeader::*`; be `⌘K spawn…` (`/child` payload); de `child header in B and nested-spawn refusal` | unit + backend-e2e + desktop-e2e | Desktop: done, `AT5.4: the parent link in B's header focuses A`. |
| AT5.5 | D10 | ⌘K spawn blocked while a child is focused | dt `TestDefaults::test_child_session_cannot_spawn`; be `D10: nested spawn…` (`can_spawn:false`); de `child header in B and nested-spawn refusal` | unit + backend-e2e + desktop-e2e | Desktop: dedicated `AT5.5: ⌘K spawn is blocked while a child is focused` (notice shown, no dialog, no new child in `/children`). |
| AT5.6 | — | No hardcoded colours; loads without an error toast | smoke (hex/rgb/black/white scan, imports); de `theme switch…`; be `plugin loads…` | smoke + backend-e2e + desktop-e2e | Desktop: done, `AT5.6: plugin loads without an error toast`. |
| AT6.1 | D9, Q3 | `↳ ` title prefix and leading badge (Recents order is not changed, SPEC §7) | rules `test_creates_running_handover_and_child_session` (`↳` title); ui `TestSidebarTree::*`; be `⌘K spawn…` (`/tree`); smoke (`sessionRow.leading`); de `status card in A, ↳ sidebar badge` | unit + backend-e2e + desktop-e2e | — |
| AT6.2 | D8 | Reopening A with `reported` children shows the banner; Deliver works | ui `TestOpenReports::*`; de `report: open-report notice…` (either branch) | unit + desktop-e2e | Desktop: done, `AT6.2 / AT4.4: closed A shows N open report(s) and Deliver delivers` (banner → Deliver → `delivered`). |
| AT7.1 | D11 | `/abandon` or Abort → `abandoned`, A gets the abort report, B archived | rb `TestAbandon::test_abandon_notifies_and_archives`, `test_abort_notice_persisted_when_parent_closed`, `test_cannot_abandon_reported`, `TestCommands::test_abandon_command`, `test_backend_actions_by_handover_id`; ui `test_abort_from_card`, `test_abort_after_report_refused`; be `Abort: running child becomes abandoned`; de `Abort and Detach from the status card`; be `AT7.1 Abort from A…` and `AT7.1 /abandon in B…` (abort report persisted in A, B `archived` in state.db) | unit + backend-e2e + desktop-e2e | — |
| AT7.2 | D11 | A dirty worktree is WIP-committed and pushed before the removal prompt; nothing is deleted without a yes | rb `test_dirty_worktree_banked_and_kept` (real git + bare remote), `test_cleanup_yes_removes` (`/spawn-cleanup … yes`); be `AT7.2 abort with a dirty worktree banks WIP (pushed)…` (WIP commit on the branch and on `origin`, worktree kept, `/spawn-cleanup … no` keeps it) and `AT7.2 /spawn-cleanup yes removes…` | unit (real git) + backend-e2e | — |
| AT7.3 | D11 | `/detach` → `detached`, one-line notice, title `↳ Detached: …`, `report_back` refused, spawn ban kept, no re-attach | rb `TestDetach::*`, `TestReportBack::test_refused_after_detach`, `TestCommands::test_detach_requires_confirm`; ui `test_detach_requires_confirm`, `test_detach_retitles_and_keeps_nesting`; be `Detach: needs confirm=true…`; de `Abort and Detach from the status card`; be `AT7.3 /detach in B…` (confirm prompt, `/detach confirm`, one-line notice in A, title `↳ Detached: …` in state.db, `report_back` and spawn refused) and `Detach: needs confirm=true…` (same checks on the REST path); de `AT7.3: Detached: title, Detached marker and report_back refusal` | unit + backend-e2e + desktop-e2e | — |

## Live-only

No AT row has to stay live-only. Two checks remain manual on the e2e card
(they need things outside any harness):

- The user's packaged Desktop build on his workstation, as opposed to the
  Electron build in the hermes-e2e Job: packaging and auto-update differ, and
  no harness runs on his desktop.
- His real project and real provider billing (AT2.3 cost note with real
  `cost_rank`, AT4.2/4.3 with a paid model): the harness uses a mock LLM and
  must not spend real credits.

`scripts/live_test.py` and `scripts/live_report_test.py` stay as optional live
checks (real gateway + local LLM). The planned backend-e2e tests above replace
them for gating.

## SPEC mismatches

None open. (AT2.6 "superset rejected" was resolved by implementing the check.)

## Backend harness (how the backend-e2e rows run)

- `e2e/support/gateway.ts`: a JSON-RPC client on the serve's `/api/ws` (the
  Desktop's socket, session token as `?token=` on loopback). It keeps A and B
  live (`session.resume` with `eager_build`), runs turns (`prompt.submit`) and
  dispatches plugin slash commands (`command.dispatch`).
- `e2e/support/mock-llm.ts`: replies can carry `match` (only for a turn whose
  last user message contains it), `delayMs` (a slow turn) and a tool call.
  Plugin tools are deferred behind `tool_call`, so scripted agent calls use
  `tool_call` with `{name: "report_back" | "spawn_session", arguments}`.
- `tests/e2e_support/hermes_helper.py`: `spawn` (any initiation, `--model`,
  `--worktree`, `--allowed-toolset`) and `session` (state.db row + messages);
  `seed-parent` seeds A with `custom:mock-e2e` so D6 can rank A's model.
- `e2e/support/backend.ts`: `cost_rank` for the two mock models and a
  project repo with one commit and a bare `origin`.

## Helper additions the planned tests need

Done for the backend lane (see above); the desktop lane still needs them for
its own specs.


- `tests/e2e_support/hermes_helper.py spawn --session-id A --title … --task … [--initiation user_asked|own_initiative] [--model p:m] [--worktree]`
  calls the registered `spawn_session` handler. Needed by AT2.1, AT2.3, AT3.2 and AT5.2.
- A slash-command dispatch into a session (`/report`, `/abandon`, `/detach`)
  for AT4.5, AT7.1 and AT7.3 (AT7.3 uses it for `/detach` and `/detach confirm`).
- `e2e/support/backend.ts` `configYaml()`: add a `cost_rank` map ranking the
  parent `custom:mock-e2e` (e.g. 1) below a child `custom:mock-e2e-pricey`
  (e.g. 5). Needed by AT2.3 in both the backend and the desktop lane.
- `e2e/support/global-setup.ts`: make `projectDir` a git repo with a bare
  remote, for AT2.5 and AT7.2.
- `e2e/support/mock-llm.ts`: a delayed reply (AT4.3) and a scripted
  `report_back` tool call (AT4.5).
