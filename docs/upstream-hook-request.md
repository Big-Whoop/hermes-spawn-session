# Draft: upstream "request a public hook" issue (NOT filed)

Status: draft only. Kanban card t_d28ed43c asked for the text, not for filing.
Filing it on NousResearch/hermes-agent is the user's decision (see Q2 in
`docs/catalog-contribution.md`).

---

**Title:** Plugin API: public seams for (1) the calling session in slash-command handlers and (2) creating a visible session from a plugin

**Body:**

We maintain `spawn-session` (https://github.com/Big-Whoop/hermes-spawn-session),
a Desktop plugin that lets an agent (or the user) start a new, visible
top-level session B from session A. A gets a handover file, and B reports back
into A. `hermes plugins validate` (v0.22.2) warns under catalog rule 9 about
two private core imports. We found no documented replacement for either, so
we'd like to ask for public seams.

1. **Calling session inside a slash-command handler.**
   `ctx.register_command()` handlers receive only `raw_args: str`. Tool
   handlers get `session_id` as an injected kwarg, but command handlers have
   no documented way to learn which session invoked them. Today we call
   `gateway.session_context.get_session_env("HERMES_SESSION_KEY")`. The TUI
   gateway (`_run_plugin_command`) and the messaging gateway already bind that
   context around plugin commands precisely so handlers can read it, but the
   module is not in the documented set.
   *Ask:* either forward context kwargs to command handlers the same way tool
   dispatch does (signature-inspected, e.g. `session_id`, `session_key`,
   `platform`), or document a public read accessor such as
   `ctx.current_session()`.

2. **Creating a session from the Python half.**
   Our `spawn_session` tool creates the child with `session.create` (title, cwd
   with `cwd_explicit`, model, provider, reasoning_effort, parent_session_id,
   idempotency_key, source). It then calls `prompt.submit` (seed message),
   `session.title` and `session.archive`. It does this through
   `tui_gateway.server.handle_request`, in-process. The Desktop SDK exposes
   the same RPCs to the renderer as `host.request`, but the Python half has
   no equivalent. `POST /api/sessions` on the API server needs a separately
   enabled server and a key. It only inserts a row (no cwd and no live
   runtime session), so the Desktop doesn't show it as a live tab.
   *Ask:* a documented in-process RPC door for plugins, e.g.
   `ctx.gateway_request(method, params)` (returning `None` or raising when no
   gateway runs in the process), or a narrower `ctx.create_session(...)` /
   `ctx.submit_prompt(session_id, text)`.

Both imports are guarded today: an import failure degrades to a clean,
JSON-returned error (or an `os.environ` read for #1). We'd rather switch to a
public seam than keep listing them as disclosed internals.
