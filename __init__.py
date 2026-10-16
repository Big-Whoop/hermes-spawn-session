"""spawn-session — Hermes plugin: agent-spawned visible child sessions.

Agent half (this package): registers the ``spawn_session`` tool
(SPEC.md section 4.1) plus a ``pre_tool_call`` guard enforcing the
child-session toolset restrictions (D10/D12). The desktop half lives in
``desktop/plugin.js`` (⌘K "Spawn session with report" + proposal confirmation
cards) and talks to the REST backend in ``dashboard/plugin_api.py``.

Install: place this folder at ``$HERMES_HOME/plugins/spawn-session/`` (or a
profile's ``plugins/`` root) and add ``spawn-session`` to ``plugins.enabled``
in the profile config. The tool is registered on every surface but refuses to
act outside Desktop sessions (D13).
"""

from __future__ import annotations

from .spawn_session.tools import SPAWN_SESSION_SCHEMA, spawn_session_handler, toolset_guard


def register(ctx) -> None:
    """Plugin entry point (see developer-guide/plugins docs)."""
    ctx.register_tool(
        name="spawn_session",
        toolset="spawn-session",
        schema=SPAWN_SESSION_SCHEMA,
        handler=spawn_session_handler,
        description=(
            "Spawn a visible child session for a self-contained task. It reports back here when done."
        ),
        emoji="🔀",
    )
    # D10/D12: block spawn_session/report_back inside spawned children and
    # enforce per-child allowed_toolsets narrowing (defense in depth; the
    # handler re-checks nesting on every call).
    ctx.register_hook("pre_tool_call", toolset_guard)
