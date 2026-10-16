"""spawn-session — Hermes plugin: agent-spawned visible child sessions.

Agent half (this package): registers the ``spawn_session`` and
``report_back`` tools (SPEC.md sections 4.1/4.2), the ``/report``,
``/abandon``, ``/detach`` and ``/spawn-cleanup`` slash commands (4.3), plus a
``pre_tool_call`` guard enforcing the child-session toolset restrictions
(D10/D12). Report delivery into the parent uses ``ctx.inject_message`` and
needs ``plugins.entries.spawn-session.allow_gateway_injection: true``. The desktop half lives in
``desktop/plugin.js`` (⌘K "Spawn session with report" + proposal confirmation
cards) and talks to the REST backend in ``dashboard/plugin_api.py``.

Install: place this folder at ``$HERMES_HOME/plugins/spawn-session/`` (or a
profile's ``plugins/`` root), run ``hermes plugins enable spawn-session`` and
accept the Python dependency consent (PyYAML, declared in ``pyproject.toml``),
then restart the gateway. The tool is registered on every surface but refuses to
act outside Desktop sessions (D13).
"""

from __future__ import annotations

from .spawn_session import delivery
from .spawn_session.commands import COMMANDS
from .spawn_session.tools import (
    REPORT_BACK_SCHEMA,
    SPAWN_SESSION_SCHEMA,
    report_back_handler,
    spawn_session_handler,
    toolset_guard,
)


def register(ctx) -> None:
    """Plugin entry point (see developer-guide/plugins docs)."""
    # inject_message (report delivery into the parent, SPEC Q4) needs the context.
    delivery.set_plugin_context(ctx)
    ctx.register_tool(
        name="report_back",
        toolset="spawn-session",
        schema=REPORT_BACK_SCHEMA,
        handler=report_back_handler,
        description=REPORT_BACK_SCHEMA["description"],
        emoji="📨",
    )
    if hasattr(ctx, "register_command"):
        for name, (handler, description, args_hint) in COMMANDS.items():
            ctx.register_command(name, handler, description=description, args_hint=args_hint)
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
