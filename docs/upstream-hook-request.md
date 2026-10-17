# Upstream "request a public hook" issue (filed)

- **Title:** Plugin API: public seams for (1) the calling session in
  slash-command handlers and (2) creating a visible session from a plugin
- **URL:** https://github.com/NousResearch/hermes-agent/issues/140199
- **Filed:** 2026-10-17 by Big-Whoop
- **Status:** open

The issue asks for public replacements for the two private imports that
`hermes plugins validate` warns about under catalog rule 9
(`gateway.session_context.get_session_env` and
`tui_gateway.server.handle_request`). The per-call reasons are in SPEC.md §3.1.
The GitHub issue holds the authoritative text. This file only links to it.
