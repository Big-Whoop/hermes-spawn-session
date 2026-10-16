# Contributing spawn-session to the official Hermes plugin catalog

Kanban card: t_e6a4c01f. Research date: 2026-10-17. Hermes checked: v0.22.2
(2026.9.24, upstream d923a5eb). Repo state checked: `main` at `e7d756a`
(PR #10 docs/readme-agents is merged, so the README and AGENTS.md are included).

Research and gap analysis only. Nothing was submitted upstream and no plugin
code was changed. Source ids like [S1] point to the Sources section at the end.

## TL;DR

- Getting into the catalog takes one PR to `NousResearch/hermes-agent` that adds
  a single file, `plugin-catalog/spawn-session.yaml`. The file pins our public
  repo to a full 40-hex commit SHA. Catalog CI runs `hermes plugins validate` at
  that commit and a maintainer reviews and merges it by hand. There is no form,
  no self-serve registry and no automated ingestion [S1][S2].
- Tiers: `official` means maintained by NousResearch; we would be `community`.
  There are no other badges or verification tiers. Being listed is itself the
  trust signal [S2][S3].
- We are not ready yet. `hermes plugins validate .` on Hermes v0.22.2 fails 3
  of its checks (output below):
  1. the declared tools are missing (`capabilities.provides_tools`);
  2. the declared hooks are missing (`provides_hooks`);
  3. the security scan rates German research files under `.hermes/research/`
     as `dangerous`.
  It also warns about two private core imports. Those are a rule 9 risk and
  the most likely reason a reviewer would push back.
- Smaller gaps: there is no `requires_hermes` floor, no `license` field in
  `plugin.yaml`, no screenshots, no disclosure section, no CI and no release
  tag. The desktop half does not set `defaultEnabled: false`.

## Validator run (evidence)

Command: `/opt/hermes/bin/hermes plugins validate .` (run on the worktree;
`main` has the same tree). Without `--install-deps`, so dependency resolution
inside Hermes's core constraints is still unverified:

    ✓ manifest — plugin.yaml parses
    ✓ manifest fields — name, version, description present
    ✓ requires_hermes — not declared
    ✓ config schema — not declared
    ✓ requires_env — all entries UPPER_SNAKE
    ✓ loadable — entry: __init__.py, desktop/plugin.js
    ✓ python dependencies — 1 requirements from pyproject
    ✓ capability probe — register() ran in isolation
    ✗ declared tools — undeclared tools registered (not in provides_tools): report_back, spawn_session
    ✗ declared hooks — undeclared hooks registered (not in provides_hooks): pre_tool_call
    ✓ declared middleware — matches registrations
    ✓ built-in tool collisions — no collisions
    ✗ security scan — dangerous: agent_config_mod_shell (lane1-hermes-docs.md:101),
      context_exfil (lane2-hermes-native-session-spawning.md:266), sys_prompt_override (lane1-hermes-docs.md:316)
    ✓ no core override — no runtime rebinds of Hermes core
    ✓ desktop surface — stays inside the plugin SDK surface
    ⚠ private core imports (catalog rule 9): spawn_session/commands.py:33
      gateway.session_context.get_session_env; spawn_session/gateway.py:46
      tui_gateway.server.handle_request.
    ◆ Isolation — runs in the plugin host (plugins.isolation: host)
      · dashboard backend API is served through the plugin host (buffered responses)
    Validation failed.

Other local checks on the same tree: `pytest` gives 202 passed and 4 skipped.
`node scripts/smoke_desktop_plugin.mjs` gives "smoke ok: 6 contributions, 4
event listeners".

## Process steps

1. Prepare the plugin repo (gaps G1–G12 below). Then pick the commit to pin.
2. At that commit, run `hermes plugins validate <checkout> --install-deps`. It is
   the same check catalog CI runs. Fix every failure and read every warning [S1].
3. Fork `NousResearch/hermes-agent` and add exactly one file,
   `plugin-catalog/spawn-session.yaml`, following the entry schema [S2]. `sha`
   must be the full 40-hex commit and `version` must be quoted [S1].
4. The PR description must say what the plugin does, which Hermes surfaces it
   uses, and everything rule 13 asks to disclose. Add screenshots, since the
   plugin has a UI [S1]. Precedent: merged PR #138521 (kanban-graph) follows the
   repo PR template and states owner, license and pin [S7].
5. Wait for the catalog CI job to go green. It clones our repo at the pin and
   runs validate [S1].
6. A maintainer reviews the pinned tree and then merges, requests changes or
   declines. Rule 3 and rule 9 problems are declines, not fix requests [S1].
   Precedent: session-flow was declined under rule 8 in PR #134760 and was
   listed after a compliant resubmission [S6][S5].
7. After the merge, `/docs/plugins/spawn-session` is generated from the entry
   and from our README at the pinned SHA. Updating means a new SHA-bump PR with
   `version` bumped, and the reviewer re-reads the commit range [S1][S2].
8. Promote the plugin in the Nous Discord `#plugins-skills-and-skins` channel
   (optional) [S4][S8].

Who may submit: only the repo owner or a major contributor (rule 5). Big-Whoop
owns the repo, so this is met. A submission by the agent would need the user's
explicit go-ahead, and this card forbids it.

## Requirements checklist

Status values: MET, NOT MET, UNCLEAR, N/A. "Rule n" refers to the admission
rules in [S1]/[S2].

| # | Requirement | Source | Status | Evidence |
|---|---|---|---|---|
| R1 | Public https repo (GitHub/GitLab) | [S1] Before you submit | MET | github.com/Big-Whoop/hermes-spawn-session is public (card body); `plugin.yaml:9` homepage |
| R2 | `plugin.yaml` plus an entrypoint at the pin | [S1] | MET | `plugin.yaml:1-9`, `__init__.py:32`, `desktop/plugin.js:550`; validator "loadable ✓" |
| R3 | Manifest `name`, `version`, `description` | [S3 dev-guide] / validator | MET | `plugin.yaml:1-7`; validator "manifest fields ✓" |
| R4 | Catalog name `[a-z0-9_-]{1,64}`, no name conflict | [S2] Entry schema, Names | MET | `spawn-session`; no `plugin-catalog/spawn-session.yaml` in the upstream listing (checked 2026-10-17 via GitHub contents API) |
| R5 | `requires_hermes` is a SemVer floor, not newer than the current release (rule 14) | [S2] rule 14 | NOT MET (optional in schema, but strongly expected) | not in `plugin.yaml`; README.md:25-26 says "built and tested against v0.22.2". Every precedent entry sets one [S5][S9] |
| R6 | `version` matches the pinned code, quoted in the entry (rule 14) | [S1][S2] | MET (keep in sync) | `plugin.yaml:2` = `pyproject.toml` version = `dashboard/manifest.json` version = 0.1.0 |
| R7 | `license` (SPDX) in the manifest, compatible license | [S3] Manifest v2 reference | NOT MET (field optional) | `LICENSE` is MIT and README.md:305-307 says MIT; `plugin.yaml` has no `license:` field |
| R8 | `manifest_version` (optional; absent = v1, supported forever) | [S3] Manifest v2 reference | N/A | v1 manifest is fine; set `manifest_version: 2` only if we adopt v2 fields |
| R9 | Declared capabilities match registrations (rule 6) | [S2] rule 6 | NOT MET | `__init__.py:36-60` registers tools `report_back`, `spawn_session` and the `pre_tool_call` hook. The entry must list them; the validator fails both checks |
| R10 | Install security scan: no `dangerous` (rule 7) | [S2] rule 7 | NOT MET | flagged: `.hermes/research/2026-10-16-model-routing/lane1-hermes-docs.md:101,316`, `.hermes/research/2026-10-16-spawn-with-report/lane2-hermes-native-session-spawning.md:266` (quoted docs and prompts, not code, but the scanner reads the whole tree) |
| R11 | Desktop half stays inside the SDK (rule 8) | [S2] rule 8; [S10] | MET | validator "desktop surface ✓"; imports only `@hermes/plugin-sdk`, `react`, `react/jsx-runtime` (`desktop/plugin.js:33-55`) |
| R12 | Desktop: theme variables only, no hardcoded colours | [S10] "Style with theme variables" | MET | a grep for `#hex` / `rgb(` in `desktop/plugin.js` finds no hits |
| R13 | Desktop: `defaultEnabled: false` for opt-in plugins | [S10] (optional; default `true`) | UNCLEAR (not a catalog rule) | `desktop/plugin.js:550` exports no `defaultEnabled`, so the desktop half is on as soon as it is installed. The Python half is already opt-in via `plugins.enabled` [S3 user-guide]. Decision needed (Q3) |
| R14 | No runtime overrides of core (rule 9) | [S2] rule 9 | MET | validator "no core override ✓" |
| R15 | Only public surfaces; private core imports are warned (rule 9) | [S2] rule 9; [S1] Before you submit | UNCLEAR, likely reviewer pushback | `spawn_session/commands.py:33` imports `gateway.session_context.get_session_env`; `spawn_session/gateway.py:46` imports `tui_gateway.server.handle_request` (the session RPC door for creating child B). A warning, not a failure. Precedent plan-mode was listed with a disclosure of "eight groups of internal Hermes seams … each guarded with a documented fallback" [S9] |
| R16 | Dependency policy: oldest compatible floor plus upper bound (rule 10) | [S2] rule 10; [S3] Dependency security policy | MET | `pyproject.toml` `PyYAML>=6,<7` |
| R17 | Deps resolve under core constraints (`--install-deps`) (rule 14) | [S1][S2] | UNCLEAR | not run with `--install-deps` here; PyYAML is very likely already a core dependency |
| R18 | Host modules not declared as deps | [S3] Python dependencies | MET | `pyproject.toml` header comment; `tests/test_dependencies.py` |
| R19 | Credentials only through Hermes; no `.env`/`auth.json` reads (rule 11) | [S2] rule 11 | MET | a grep finds no `.env`/`auth.json` access. `os.environ` reads are only `HERMES_SESSION_*`/`HERMES_HOME`/`HERMES_KANBAN_BOARD` (`commands.py:37`, `parent.py:56`, `tools.py:88`), which are not secrets |
| R20 | Approvals and unattended runs respected; no YOLO-inheriting children (rule 12) | [S2] rule 12 | UNCLEAR | own-initiative spawns need user approval (D3; `tools.py:318`) and the tool refuses outside Desktop (D13), so cron/gateway are not reachable. Not verified: whether a spawned child B inherits A's approval mode/YOLO. To check and disclose |
| R21 | Risky behaviour disclosed in README and PR (rule 13) | [S2] rule 13 | NOT MET | no disclosure section in README.md. Behaviours to disclose: `git` subprocess (`spawn_session/worktree.py:26`, worktree option); writes outside plugin data (`<cwd>/.hermes/handovers`, `spawn_session/handover.py:3`; `$HERMES_HOME/spawn-session/state.json`, `state.py:211`); `inject_message` into the parent (needs `allow_gateway_injection`, `__init__.py:8`); creating new sessions with other models (cost) |
| R22 | No self-updating code (rule 3) | [S2] rule 3 | MET | no updater or remote loader (manual review; validator found nothing) |
| R23 | No binaries, `.pyc` or opaque archives (rule 17) | [S2] rule 17 | MET with caveat | `.gitignore` excludes `__pycache__/`. The tree tracks `.hermes/research/.../claude-desktop-spawn-with-report-ui.png` (an image, not executable) |
| R24 | Not a fork or skin of a bundled or listed plugin (rules 15/16) | [S2] | MET | original design (`.hermes/research/2026-10-16-plugin-existence-search-de.md`); nearest listed relatives `hermes-teammates`, `protean-subagent-viewer` do in-process subagents or a read-only viewer, not visible top-level sessions [S9] |
| R25 | Dashboard backend import boundary (GHSA-mcfc-hp25-cjv7) | [S10] "Python side" | MET by design | the advisory page needs login [S11]. Per [S10], `plugin_api.py` is imported only when the plugin is in `plugins.enabled`. Our `dashboard/manifest.json` + `plugin_api.py` follow the documented layout. Validator: "dashboard backend API is served through the plugin host" |
| R26 | README renders on the catalog page at the pin | [S2] Entry schema (`readme: true`) | MET with caveat | README.md exists and is English, but it links to German `.hermes/research/` (README.md:298-303); fine, but worth labelling |
| R27 | Screenshots for anything with a UI | [S1] Opening the PR | NOT MET | no screenshots in the repo; `image`/`screenshots` must be `raw.githubusercontent.com` URLs pinned to the SHA [S2] |
| R28 | Tests / CI | not a catalog rule; [S3] recommends own CI with `uv --exclude-newer` | UNCLEAR (recommended) | `tests/` is pytest (202 pass); there is no `.github/workflows/` |
| R29 | Versioning / tags / releases | [S2] rule 2: only the SHA counts; tags rejected as pins | MET (tags optional) | no git tags; precedent kanban-graph tagged `v0.2.1` alongside the SHA [S7] |
| R30 | Category, tier, platforms metadata | [S2] Entry schema | MET (to choose) | proposed `tier: community`, `category: desktop` or `automation`, `platforms: []` |
| R31 | Portable Agent Plugins v1 packaging | [S3] Portable Agent Plugins | N/A | native `plugin.yaml` + `register(ctx)` plugin; portable format only covers skills/MCP |
| R32 | Third-party-product plugins ship standalone | [S4][S3] | MET | standalone repo; listing through the catalog, not merged into core |
| R33 | Plugin data in the profile-scoped data dir (`plugin_data_dir()`) | [S3] "Keep state across updates" (recommendation) | NOT MET (recommendation) | `state.py:211` uses `$HERMES_HOME/spawn-session/state.json`, not `plugin_data_dir()` |

## Gaps and follow-up card proposals

Not implemented on this card. Each item is one suggested follow-up card.

- **G1 (blocker): capabilities in the entry.** Draft
  `capabilities.provides_tools: [spawn_session, report_back]` and
  `provides_hooks: [pre_tool_call]`. Validate locally with a draft entry. The
  validator's "declared tools" check reads the catalog entry or manifest; also
  mirror the block in `plugin.yaml` if the validator reads it from there
  (verify).
- **G2 (blocker): security-scan failures from `.hermes/research/`.** Options:
  (a) move the research archive out of the plugin tree (a separate repo or
  branch, or a `docs/` path the scanner skips, if any), (b) point the catalog
  `subdir` at a plugin-only directory, or (c) ask upstream whether
  documentation files are exempt. This touches the source-of-truth rules in
  AGENTS.md (`.hermes/research/` is read-only), so it needs a user decision
  (Q1).
- **G3 (high, rule 9): private core imports.** `gateway.session_context` and
  `tui_gateway.server.handle_request`. Check whether a public ctx API now
  covers creating a session and reading the session key, e.g.
  `ctx.dispatch_tool`, session-key kwargs on hooks or SDK RPCs. If none does:
  keep the guarded fallbacks, disclose them like plan-mode did, and/or open an
  upstream "asking for a hook" issue (user decision; not from this card).
- **G4: add `requires_hermes: ">=0.22.2"`** (or the oldest release actually
  tested) to `plugin.yaml` and the entry. Add `license: MIT`, plus optionally
  `manifest_version: 2` and `tags`.
- **G5: README "Disclosure" section** covering everything listed in R21, plus
  the private-seam disclosure from G3. Also reuse it as the entry
  `description` disclosure line.
- **G6: rule 12 audit.** Verify that a spawned child B does not inherit YOLO or
  approval-off from A, and document the result. Add a test if possible.
- **G7: screenshots and banner.** Capture them during the live e2e card
  t_787f6427: ⌘K dialog, proposal card, child header, status cards, sidebar
  badge. Store them under `docs/media/` and use pinned raw URLs; the banner
  must be 2:1.
- **G8: decide on `defaultEnabled: false`** for `desktop/plugin.js` (Q3).
- **G9: CI.** A GitHub Actions workflow running pytest, the Node smoke test
  and, if feasible, `hermes plugins validate --install-deps`, with
  `uv --exclude-newer "3 days"` as [S3] recommends.
- **G10: move state into `plugin_data_dir()`** (survives `hermes plugins
  update`/`remove`, follows the active profile). This changes SPEC.md and
  `state.py`. Optional for listing.
- **G11: release hygiene.** Tag `v0.1.0` (or `v1.0.0` after e2e) at the pinned
  commit and keep `plugin.yaml`, `pyproject.toml` and
  `dashboard/manifest.json` versions in lockstep.
- **G12: draft the entry and PR text** (`spawn-session.yaml` plus a PR body
  following the kanban-graph precedent) inside our repo, e.g.
  `docs/catalog-entry-draft.yaml`, for the user to submit manually.

Suggested order: finish e2e t_787f6427 → G2 → G1/G4 → G3 → G5/G6 → G7 → G9 →
G11 → G12 → user submits.

## Open questions for the user

- Q1: How should the `.hermes/research/` scanner failures be handled: move the
  research out of the plugin tree, use a `subdir` layout, or ask upstream?
- Q2: Should we open an upstream issue asking for a public seam for session
  creation and session-key lookup (rule 9), or list with a disclosure as
  plan-mode did?
- Q3: Should the desktop half ship with `defaultEnabled: false`?
- Q4: Which category: `desktop` or `automation`? And which `requires_hermes`
  floor: only 0.22.2, or test older releases too?
- Q5: Should we submit only after the live e2e card t_787f6427 passes and a
  1.0 tag exists? (Recommended.)
- Q6: Who opens the upstream PR? Rule 5 says owner or major contributor, so
  Peter under Big-Whoop.

## Sources

- [S1] Submitting to the Plugin Catalog: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission
- [S2] plugin-catalog/README.md (canonical admission rules, entry schema, names): https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md
- [S3] Build a Hermes Plugin (capabilities, manifest v2, Python deps, dependency security policy, portable plugins): https://hermes-agent.nousresearch.com/docs/developer-guide/plugins ; Plugins user guide (opt-in, `--ref` pins): https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins ; Plugin catalog user guide (tiers, entry fields): https://hermes-agent.nousresearch.com/docs/user-guide/features/plugin-catalog
- [S4] CONTRIBUTING.md, "Submitting a Plugin to the Catalog": https://github.com/NousResearch/hermes-agent/blob/main/CONTRIBUTING.md
- [S5] session-flow catalog page and entry: https://hermes-agent.nousresearch.com/docs/plugins/session-flow ; https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/session-flow.yaml
- [S6] session-flow decline (rule 8): https://github.com/NousResearch/hermes-agent/pull/134760
- [S7] Merged precedent kanban-graph: https://github.com/NousResearch/hermes-agent/pull/138521 (others: #138443, #139143, #137528, #136874)
- [S8] Catalog index (client-rendered, needs JS): https://hermes-agent.nousresearch.com/docs/plugins/
- [S9] Related entries: https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/plan-mode.yaml , .../hermes-teammates.yaml , .../protean-subagent-viewer.yaml
- [S10] Desktop Plugin SDK (defaultEnabled, theme variables, imports, dashboard backend, GHSA note): https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk
- [S11] GHSA-mcfc-hp25-cjv7 (page not readable without login; content taken from [S10]): https://github.com/NousResearch/hermes-agent/security/advisories/GHSA-mcfc-hp25-cjv7
- Local: `hermes plugins validate .` output on Hermes v0.22.2 (above); repo files cited inline at `main` e7d756a.
