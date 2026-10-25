# Upstream "request a public hook" issue (filed)

- **Title:** Plugin API: public seams for (1) the calling session in
  slash-command handlers and (2) creating a visible session from a plugin
- **URL:** https://github.com/NousResearch/hermes-agent/issues/140199
- **Filed:** 2026-10-17 by Big-Whoop
- **Status:** open (part 1 resolved upstream, part 2 still open)

The issue asks for public replacements for the two private imports that
`hermes plugins validate` warns about under catalog rule 9
(`gateway.session_context.get_session_env` and
`tui_gateway.server.handle_request`). The per-call reasons are in SPEC.md §3.1.
The GitHub issue holds the authoritative text. This file only links to it.

## Progress

- **Part 1, calling session in slash-command handlers: resolved.** Hermes
  v0.22.5 (#140997, merge 5f274827ffc) passes `session_id`, `session_key`,
  `platform` and `source` to command handlers that declare them (developer
  guide, "Register slash commands → Calling-session context"). The plugin
  switched to these keywords and now requires `>=0.22.5`;
  `gateway.session_context.get_session_env` is no longer imported.
- **Part 2, creating a visible session from Python: still open.**
  `spawn_session/gateway.py` still uses `tui_gateway.server.handle_request`.
