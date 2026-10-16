# Lane 3 — Hermes Agent source-code behavior verification

Repo: github.com/NousResearch/hermes-agent, branch `main` (tree sha `27f73cb51ddc833c1e442480849fce35fb1fdfe4`, read 2026-10-16).
Note: `main` is ahead of the user's installed v0.22.2 (2026-10-15); line refs are to `main`.
Method: raw.githubusercontent.com single-file fetches, local grep/read. Tiers: **Verified** = read the actual code; **Plausible** = inferred from adjacent code / provider-side behavior.

---

## Q1 — `/model` at runtime

### 1.1 `/model` swaps the model IN PLACE; conversation history is kept
**Verified.** `agent/agent_runtime_helpers.py` L2464-2470 (`switch_model`):
```python
def switch_model(
    agent, new_model, new_provider, api_key='', base_url='', api_mode='', capabilities=None
):
    """Switch the model/provider in-place for a live agent (rebuild clients, caching flags,
    compressor). Mirrors ``_try_activate_fallback()`` but also updates ``_primary_runtime`` so
    the change persists across turns. A failed swap/rebuild rolls back to the pre-switch
    snapshot and re-raises (callers catch)."""
```
The CLI path never retires the agent for a plain switch — `hermes_cli/cli_model_switch_mixin.py` `_stage_and_swap_model` L702-754 stages CLI fields then calls `self.agent.switch_model(...)`; `_retire_agent` is only used by the `/moa` one-shot (L999). History lives in `cli.conversation_history` / the session DB and is untouched by the swap.

### 1.2 The switch note is prepended to the NEXT USER MESSAGE, not inserted as a system message
**Verified.** `hermes_cli/cli_model_switch_mixin.py` L119-135:
```python
    """Record the next-turn switch note and print the "Model switched" block.

    The note is prepended to the next user message (a mid-history system message would break
    providers and prompt caching). ``strict_context``: the typed /model path lets
    context-resolution errors propagate; the picker path swallows them.
    """
    ...
    cli._pending_model_switch_note = (
        f"[Note: model was just switched from {_display_old} to {_display_new} "
        f"via {result.provider_label or result.target_provider}. "
        f"{'This override applies to the next turn only. ' if one_turn else ''}"
        f"Adjust your self-identification accordingly.]")
```
Consumed at `hermes_cli/cli_chat_turn_mixin.py` L304-310:
```python
        # One-shot /model and /reload-skills notes; _prepend_note_to_message also handles
        # multimodal content-part lists (string concat raised TypeError with an image).
        for _note_attr in ("_pending_model_switch_note", "_pending_skills_reload_note"):
            _note = getattr(self, _note_attr, None)
            if _note:
                agent_message = _prepend_note_to_message(agent_message, _note)
                setattr(self, _note_attr, None)
```
L317-319: "Notes and voice prefix are API-local: the staged input stays the durable transcript value" — the persisted transcript keeps the clean message. So the history PREFIX is byte-identical; only the newest user message (context tail) changes.

### 1.3 The system prompt IS invalidated and rebuilt on the next turn — and it embeds the model name
**Verified.** `agent/agent_runtime_helpers.py` L2513-2514 (inside `switch_model`):
```python
    # Invalidate the cached system prompt so it rebuilds next turn.
    agent._cached_system_prompt = None
```
The rebuilt prompt contains the model identity: `agent/system_prompt.py` L511-513:
```python
    trailer = (("Session ID", agent.session_id if agent.pass_session_id else None), ("Model", agent.model),
               ("Provider", agent.provider), ("Platform", agent.platform))
    return timestamp_line + "".join(f"\n{label}: {value}" for label, value in trailer if value)
```
Plus model-gated guidance blocks that change with model family, `agent/system_prompt.py` L572-578:
```python
    if _model_gate(agent._tool_use_enforcement, agent.model, TOOL_USE_ENFORCEMENT_MODELS):
        parts.append(TOOL_USE_ENFORCEMENT_GUIDANCE)
        if any(g in (agent.model or "").lower() for g in ("gemini", "gemma")):
            parts.append(GOOGLE_MODEL_OPERATIONAL_GUIDANCE)
    if _model_gate(getattr(agent, "_execution_guidance", "auto"), agent.model, EXECUTION_GUIDANCE_MODELS):
```
Consequence: after a model switch the system-prompt bytes differ (new model name in the trailer, possibly different gated blocks) → the Anthropic cache prefix changes → the prompt cache is invalidated by the switch itself (see Q3).

### 1.4 The toolset is NOT changed by a model switch
**Verified (by exhaustive read of `switch_model`, `agent/agent_runtime_helpers.py` L2464-2528).** The function touches: credential pool, model/provider/base_url/api_mode/api_key, client rebuild, `_use_prompt_caching`/`_use_native_cache_layout`, `context_compressor` (model + context length), `reasoning_config`, `_cached_system_prompt`, `runtime_capabilities`, `_primary_runtime`. It never touches `valid_tool_names`, `tools`, `enabled_toolsets`, or `disabled_toolsets`. (The session's tool pin is a separate, persisted thing: `hermes_state_sessions.py` L699-709 `update_session_tool_names` — "Persist the session's ``tools[]`` pin … so a rebuilt AIAgent sends the same bytes".)

### 1.5 Where the session's model is stored: PER-SESSION in state.db, not per-profile
**Verified.** The `sessions` table has `model` and `model_config` columns; `hermes_state_sessions.py` L711-739:
```python
    def update_session_model(
        self, session_id: str, model: str, provider: Optional[str] = None, *,
        base_url: Optional[str] = None, api_mode: Optional[str] = None,
    ) -> None:
        """Set the model after a mid-session /model switch (unconditionally) and drop any Browser
        runtime lock (lineage markers survive).
        ...
        """
        ...
        patch: dict[str, Any] = {"browser_model_lock": None}
        if model:
            patch["model"] = model
        if provider:
            route = {"provider": provider, "base_url": base_url or None, "api_mode": api_mode or None}
            patch.update(route, gateway_runtime=route)
        self._write_model_config_patch(
            session_id, patch, "UPDATE sessions SET model = ?, model_config = ? WHERE id = ?",
            lambda merged: (model, merged, session_id),
        )
```
and L679-687:
```python
    def update_session_meta(
        self, session_id: str, model_config_json: str, model: Optional[str] = None,
    ) -> None:
        """Update model_config and (COALESCE) optionally model."""
        self.flush_token_counts()  # barrier against queued token deltas — see update_session_model
        self._write_sql(
            "UPDATE sessions SET model_config = ?, model = COALESCE(?, model) WHERE id = ?",
            (model_config_json, model, session_id),
        )
```
The CLI writes the row on every non-`--once` switch, `hermes_cli/cli_model_switch_mixin.py` L422-457 (`_persist_model_switch_to_session`):
```python
        route = {
            "provider": _heal_bare_custom_provider(
                result.target_provider, base_url=result.base_url, model=result.new_model,
            ) or None,
            ...
            "base_url": result.base_url or None,
            "api_mode": result.api_mode or None}
        try:
            db.update_session_model(sid, result.new_model)
            db.patch_session_model_config(sid, {"gateway_runtime": route, **route})
```
`config.yaml` is written ONLY for `--global` (or `model.persist_switch_by_default: true` / first-ever pick). `hermes_cli/model_switch.py` L510-545 (`resolve_persist_behavior`):
```python
    """Decide whether a ``/model`` switch should persist to ``config.yaml``.

    Order: ``--once`` / ``--session`` -> False; ``--global`` -> True; no default configured yet
    (neither ``model.default`` nor ``model.provider`` — a fresh install's first pick) -> True, ...
    ``model.persist_switch_by_default`` -> True (the user's explicit opt-in to persistence);
    ``--provider`` without a persist flag -> False (exploratory). ...
    """
    if is_once or is_session:
        return False
    if is_global:
        return True
```
Resume restores the stored per-session route: `hermes_cli/cli_model_switch_mixin.py` L459-544 (`_restore_session_model`) and L49-80 (`stored_session_route`).

### 1.6 `/model --once` = one-turn override with automatic restore
**Verified.** `hermes_cli/cli_model_switch_mixin.py` L261-295 (`_commit_model_switch`): `snapshot = cli._snapshot_model_runtime() if one_turn else None`, and L288-295: `--once` "is restored after one turn and never touches the [session DB] row". Restore: `_restore_model_runtime_snapshot` L622-667 (restores `_RUNTIME_FIELDS` = model/provider/api_key/base_url/api_mode/reasoning_config and the agent's `_primary_runtime`).

---

## Q2 — `delegation.model` / `delegation.provider`

### 2.1 They are profile-wide config keys; resolution: config override > parent inherit
**Verified.** Defaults at `hermes_cli/config_defaults.py` L1330+:
```python
    "delegation": {
        "model": "",  # e.g. "google/gemini-3-flash-preview" (empty = inherit parent)
        "provider": "",  # e.g. "openrouter" (empty = inherit parent provider + credentials)
        ...
        "base_url": "",  # direct OpenAI-compatible endpoint for subagents
        "api_key": "",  # key for delegation.base_url (falls back to OPENAI_API_KEY)
        ...
```
Resolution in `tools/delegate_tool_config.py` L421-440 (`_resolve_delegation_credentials`):
```python
    """Child credential bundle from the ``delegation`` config section. Three branches: ``base_url`` set → direct
    endpoint (``api_key`` None means inherit the parent's key, so providers keyed outside OPENAI_API_KEY work);
    ``provider`` set → full bundle via the runtime provider system (same path as CLI/gateway startup); neither →
    None values, child inherits everything. ``request_overrides`` is honored on every branch. ..."""
    values = {k: str(cfg.get(k) or "").strip() or None for k in ("model", "provider", "base_url", "api_key")}
```
and L487-512 (`_resolve_child_runtime`): `effective_model = model or parent_agent.model`; provider/base_url are "one bundle: all from the override, or all from the parent".

### 2.2 NOT overridable per `delegate_task` call — the tool schema exposes no model/provider parameter
**Verified.** `tools/delegate_tool.py` L696-776 (`DELEGATE_TASK_SCHEMA`): per-task properties are exactly `goal`, `context`, `output_schema`, `images`, `group`; top-level: `tasks`, `action` (spawn/list/steer/stop), `subagent_id`, `message`. No `model`/`provider`/`base_url` anywhere. All children of one call share one credential bundle: L437-442:
```python
            child = _build_child_preserving_parent_tools(
                task_index=i, goal=t["goal"], context=_child_context,
                toolsets=None,  # always inherit the parent's toolsets
                model=creds["model"], max_iterations=max_iterations, task_count=len(task_list),
                parent_agent=parent_agent, role=_normalize_role(t.get("role") or top_role), **overrides,
            )
```
where `creds = _resolve_delegation_credentials(cfg, parent_agent)` (config-derived). (The `override_*` parameters of `_build_child_agent` exist for internal callers like `/review` with `auxiliary.review`, not for model-facing calls.)

### 2.3 Children start with a FRESH context — no parent history
**Verified.** `tools/delegate_tool.py` L279-292 (`_build_child_agent`):
```python
            child = AIAgent(
                **rt, max_iterations=max_iterations, prefill_messages=getattr(parent_agent, "prefill_messages", None),
                enabled_toolsets=child_toolsets, disabled_toolsets=child_disabled_toolsets, quiet_mode=True,
                ephemeral_system_prompt=child_prompt, log_prefix=f"[subagent-{task_index}]", platform="subagent",
                side_agent=True,
                skip_context_files=True, skip_memory=True, clarify_callback=None,
                ...
                session_db=child_session_db, parent_session_id=parent_sid, request_overrides=request_overrides,
                ...
                iteration_budget=None,  # fresh budget per subagent
            )
```
`child_prompt` is built from goal+context only (`_build_child_system_prompt(goal, context, ...)` L246-249). The tool description tells the model the same: L718-727:
```python
                        "goal": _p(
                            "string",
                            "What this subagent should accomplish. Be specific and self-contained — it knows "
                            "nothing about your conversation history.",
                        ),
                        "context": _p(
                            "string",
                            "Background THIS child needs: file paths, error messages, constraints. Each child "
                            "sees only its own context — repeat shared background in every task that needs it.",
                        ),
```
The child gets its own session row (dedicated SessionDB handle, `parent_session_id` lineage, `_delegate_from` marker L319-320). `prefill_messages` is a constructor-level static prefill (empty in normal chats; `agent/agent_init.py` L2378 "Prefilled conversation turns") — not the parent's conversation history.

### 2.4 Child prompt-cache TTL is clamped to 5m; toolsets inherited
**Verified.** `tools/delegate_tool.py` L151-157:
```python
def _apply_child_cache_ttl(child) -> None:
    """A delegated child never uses the 1h cache tier. The tier is priced for a person who steps
    away between turns (2x write vs 1.25x for 5m, #14971); a subagent calls every few seconds for
    minutes and is gone, so it pays the 2x on every tool result and never collects the retention.
    Caching itself stays exactly as configured (disabled stays disabled)."""
    if getattr(child, "_cache_ttl", None) == "1h":
        child._cache_ttl = "5m"
```
Toolsets: L439 `toolsets=None,  # always inherit the parent's toolsets`.

---

## Q3 — `prompt_caching.cache_ttl`

### 3.1 It selects the Anthropic `cache_control` TTL tier: "5m" (default) or "1h" (or "auto" / off)
**Verified.** `agent/prompt_caching.py` L102-104:
```python
def _build_marker(ttl: str) -> dict[str, str]:
    """Build a cache_control marker dict for the given TTL ('5m' or '1h')."""
    return {"type": "ephemeral", "ttl": "1h"} if ttl == "1h" else {"type": "ephemeral"}
```
Config read at `agent/agent_init.py` L668-702 (`_init_prompt_cache_config`):
```python
    # cache_ttl: "5m" (default), "1h" (2x write cost; pays off with >5-minute pauses) or "auto"
    # (1h when a person paces the session, 5m when a machine does); unknown values keep "5m". A falsy/off value disables caching entirely (OAuth plans
    # billing cache writes, proxies adding their own cache_control); the disable survives
    # /model switches and fallback re-derivation.
    # Anthropic supports "5m" (default) and "1h" cache TTL tiers. Read from config.yaml under
    # prompt_caching.cache_ttl; unknown values keep "5m". 1h tier costs 2x on write vs 1.25x for 5m, but
    # amortizes across long sessions with >5-minute pauses between turns (#14971). ...
    agent._cache_ttl = "5m"
    ...
        _ttl = _pc_cfg.get("cache_ttl", "5m")
        if _ttl in {"5m", "1h"}:
            agent._cache_ttl = _ttl
        elif _ttl == AUTO_CACHE_TTL:
            ...
            agent._cache_ttl = auto_cache_ttl_for_source(session_source_for(getattr(agent, "platform", None)))
        elif cache_ttl_means_disabled(_ttl):
            agent._use_prompt_caching = False
            agent._use_native_cache_layout = False
            agent._cache_ttl = None
            agent._cache_disabled = True
```
Default config: `hermes_cli/config_defaults.py` L702: `"prompt_caching": {"cache_ttl": "5m"}`.
So: it is the **server-side retention window of the Anthropic prompt cache** (how long a written cache entry stays warm after the last write), NOT a local cache. The user's `cache_ttl: 1h` means cache entries survive up to 1h of idle time (at 2x write cost).

### 3.2 "auto" = 1h for human-paced sessions, 5m for machine-paced sources
**Verified.** `agent/prompt_caching.py` L139-146:
```python
AUTO_CACHE_TTL = "auto"
MACHINE_PACED_SOURCES = frozenset({"subagent", "cron", "oneshot", "webhook", "kanban", "api", "tool", "batch"})


def auto_cache_ttl_for_source(source: str | None) -> str:
    """The tier ``auto`` resolves to for a session source: ``5m`` for machine-paced sources,
    ``1h`` for everything a human types into (cli, tui, desktop, messaging platforms)."""
    return "5m" if (source or "").strip().lower() in MACHINE_PACED_SOURCES else "1h"
```

### 3.3 Route clamping: Qwen/Alibaba routes drop the 1h tier to 5m
**Verified.** `agent/prompt_caching.py` L149-160:
```python
def effective_cache_ttl(ttl: str | None, *, model: str = "", provider: str = "") -> str:
    """Clamp a requested cache TTL to what the destination route supports (``None`` → ``5m``).

    Qwen/Alibaba routes drop ``1h`` (→ ``5m``) except on ``MEASURED_1H_PROVIDERS`` minus
    ``NO_1H_TIER_MODELS``; that check runs BEFORE the generic Qwen clamp, which would swallow it.
    """
    if ttl != "1h":
        return ttl or "5m"
    provider_lower = (provider or "").lower()
    if provider_lower in MEASURED_1H_PROVIDERS:
        return "5m" if _flat_model(model) in NO_1H_TIER_MODELS else "1h"
    return "5m" if is_qwen_model(model) or provider_lower in ALIBABA_FAMILY_PROVIDERS else "1h"
```
Relevant to the user: the local `ryzen` (Qwen3.8-27B-FP8) route would be clamped to 5m if it ever used Anthropic-style markers (it uses chat_completions; see 3.5).

### 3.4 What invalidates the cache: any prefix-byte change or TTL expiry; the cache is content-addressed
**Verified (code statement).** `agent/prompt_cache_scope.py` L174-183:
```python
def is_slot_keyed_cache_route(provider: Any, model: Any, base_url: Any = "") -> bool:
    """True when the cache key selects ONE server-side slot per conversation.

    xAI (``xai``/``xai-oauth``, ``api.x.ai``, or Grok via OpenRouter ``x-ai/grok-*``) pins its
    prompt cache to the server picked by ``x-grok-conv-id`` / ``prompt_cache_key``: two divergent
    request streams under one key evict each other. Anthropic, DeepSeek and Gemini caches are
    content-addressed and OpenAI's ``prompt_cache_key`` only routes over a prefix match, so the
    shared scope (#109964) stays a win there. ...
    """
```
Breakpoint layout, `agent/prompt_caching.py` L1-6:
```python
"""Anthropic prompt caching strategy — pure functions, no AIAgent dependency.

Default layout: 4 cache_control breakpoints — the static system prefix, the end of the
system prompt, and the last 2 non-system messages (without a static prefix: one system
breakpoint plus the last 3 messages). All markers share one TTL (5m or 1h).
"""
```
So invalidation = (a) TTL expiry after last write (5m/1h), (b) ANY change to the cached prefix bytes (system prompt, tools array, or earlier messages), (c) model change — a different model is a different cache (provider-side; **Plausible**, standard Anthropic behavior, not stated in Hermes code). Concretely for `/model`: the system prompt is rebuilt with the new model name (Q1.3) → prefix bytes change → full cache miss on the next turn even though history is untouched.

### 3.5 Which routes get caching at all (policy), re-resolved on every switch
**Verified.** `agent/agent_runtime_helpers.py` L2497-2499 (inside `switch_model`):
```python
    agent._use_prompt_caching, agent._use_native_cache_layout = agent._anthropic_prompt_cache_policy(
        provider=new_provider, base_url=agent.base_url, api_mode=api_mode, model=new_model
    )
```
Policy grants (L1778-1895, abridged): native Anthropic (Claude) → `(True, True)`; Claude/Kimi via OpenRouter/Nous Portal on the OpenAI wire → `(True, False)` envelope layout; third-party `anthropic_messages` gateways with Claude → `(True, True)`; custom providers can opt in/out via per-model `prompt_caching` capability; MiniMax-M3 → `(False, False)` (server-side auto caching); Qwen/Alibaba on OpenCode/DashScope → `(True, False)`. For the user's `cpa` (CLIProxyAPI) custom provider: caching applies only if the custom-provider model capability `prompt_caching` is set (L1836-1852) — otherwise no markers. **Plausible** for the user's exact setup (depends on their `custom_providers` config, which I did not read).

---

## Q4 — Desktop app: per-chat model override

### 4.1 Yes — the desktop stores a per-chat (per-session) model override, sent as a gateway RPC
**Verified.** `apps/desktop/src/app/session/hooks/use-model-controls.ts` L359-365 (`selectModel`):
```typescript
      const requestSwitch = (confirmExpensiveModel = false) =>
        requestGateway<ModelSwitchResponse>('config.set', {
          session_id: liveSessionId,
          key: 'model',
          value: `${selection.model} --provider ${selection.provider}${scope}`,
          ...(confirmExpensiveModel ? { confirm_expensive_model: true } : {})
        })
```
L246-250: "The composer model is plain UI state: with no live session it's just stored (and shipped on the next session.create); with one it's scoped to that session via config.set. It NEVER writes the profile default — that lives in Settings → Model". L343-357: secondary chat tiles always send `--session`; only the primary tile lets the gateway decide persistence.

### 4.2 Backend: the override lands in the session (in-memory `model_override` + state.db row), never in process-global env
**Verified.** `tui_gateway/methods_config_set.py` L111-145 (`_set_model` → `_apply_model_switch`), and `tui_gateway/model_switch.py` L364-373:
```python
    # PER-SESSION override so a rebuild of THIS session (/new, resume) re-derives the model.
    # Deliberately NOT written to process-global env (HERMES_MODEL & co.): the desktop hosts
    # every same-profile session in one process, so os.environ would leak the switch to all.
    if pin_session_override and isinstance(session, dict) and not one_turn:
        session["model_override"] = {
            "model": result.new_model, "provider": result.target_provider,
            "base_url": result.base_url, "api_key": result.api_key, "api_mode": result.api_mode}
    if persist_global:
        from hermes_cli.model_switch import persist_model_selection
        persist_model_selection(result)
```
Persistence to the session DB row: `tui_gateway/agent_factory.py` L212-233 (`_persist_live_session_runtime`):
```python
def _persist_live_session_runtime(session: dict | None) -> None:
    """Persist active session runtime so future resumes restore the same footer."""
    ...
        if hasattr(db, "update_session_meta"):
            db.update_session_meta(session_key, json.dumps(model_config), model or None)
        elif model and hasattr(db, "update_session_model"):
            db.update_session_model(session_key, model)
```
Mid-turn picks are deferred: `tui_gateway/methods_config_set.py` L73-95 (`_stash_pending_model_switch`, "No live swap while a turn streams") — applied at next turn start. Same in-place `agent.switch_model` as the CLI (Q1.1), so the same cache-invalidation behavior applies.

---

## Q5 — Context exceeds the new model's window after a switch

### 5.1 The switch re-resolves the context length and re-points the compressor
**Verified.** `agent/agent_runtime_helpers.py` L2353-2384 (`_update_switch_compressor`):
```python
def _update_switch_compressor(agent, custom_providers, effective_context_length, snapshot) -> None:
    """Point the context compressor at the new model (rolls back the switch on failure)."""
    ...
        new_context_length = get_model_context_length(
            agent.model, base_url=agent.base_url, api_key=ctx_api_key, provider=agent.provider,
            config_context_length=effective_context_length, custom_providers=custom_providers,
        )
        agent.context_compressor.update_model(
            model=agent.model,
            context_length=new_context_length,
            ...
        )
```
Context length resolution honors the `model.context_length` pin, custom-provider metadata, and provider catalogs (`_resolve_switch_context_length` L2311-2350; `agent/context_pin.py` L1-5: "``model.context_length`` is an explicit pin: it wins over provider metadata").

### 5.2 At switch time you get a preflight warning if the next turn will compress
**Verified.** `hermes_cli/context_switch_guard.py` L53-115 (`merge_preflight_compression_warning`):
```python
    new_threshold = _threshold_tokens(cc, result.new_model, new_ctx, result.target_provider)
    if estimate < new_threshold:
        return
    ...
    parts: list[str] = []
    if old_ctx and new_ctx < old_ctx:
        parts.append(f"Context window shrinks ({old_ctx:,} → {new_ctx:,}). ")
    parts.append(
        f"Session is ~{estimate:,} tokens; "
        f"{result.new_model} allows {new_ctx:,} "
        f"(auto-compress at ~{new_threshold:,}). "
        f"Your next message will run preflight compression before the model replies.")
    _append_warning(result, "".join(parts))
```
Wired into the CLI switch path: `hermes_cli/cli_model_switch_mixin.py` L99-116 (`_merge_preflight_warning`).

### 5.3 Runtime behavior: COMPRESSION before the API call — not truncation, not an error
**Verified.** Turn start runs the preflight gate: `agent/conversation_loop.py` L1663 `_pg = _run_phase(run_preflight_gate, agent, s)`; `agent/turn_preflight_gate.py` L90-100 → `run_preflight_compression`; `agent/turn_preflight.py` L96-150:
```python
    if (
        _eligible
        and not _review_fork_first_request_pending(agent)
        and (not v._preflight_compression_blocked or provider_overflow_preflight)
        and (not defer_preflight(request_pressure_tokens) or provider_overflow_preflight)
        and not _compression_cooldown
        and compressor.should_compress(request_pressure_tokens)
    ):
        # Managed local runtime: grow the context window before compressing (last
        # resort). Only for a llamacpp provider at the supervised base_url.
        _grown_window = _maybe_grow_local_window(agent, compressor, request_pressure_tokens)
        if _grown_window:
            ...
            return _done("continue")
        ...
        v.messages, v.active_system_prompt = agent._compress_context(
            v.messages, system_message, approx_tokens=request_pressure_tokens,
            task_id=effective_task_id, trigger="pre_api",
        )
```
`_eligible` requires `agent.compression_enabled` (L88-92). So with compression enabled (the user's case), an oversized session after a switch to a smaller-window model is auto-compacted at the start of the next turn, before the model call.

### 5.4 If compression is disabled: warning only, request goes out as-is
**Verified.** `agent/turn_preflight.py` L212-219:
```python
    elif not agent.compression_enabled and len(v.messages) > 1:
        # Uncompressed session guard: compression is disabled, so warn (deduped) when
        # the request exceeds the context window; the turn-context preflight re-arms.
        _ctx_len = getattr(getattr(agent, "context_compressor", None), "context_length", None)
        if isinstance(_ctx_len, int) and _ctx_len > 0 and request_pressure_tokens > _ctx_len:
            _warn_fn = getattr(agent, "_warn_uncompressed_context_overflow", None)
            if callable(_warn_fn):
                _warn_fn(request_pressure_tokens, _ctx_len)
```

### 5.5 If the provider reports overflow: forced preflight retries, then FAILS CLOSED (no silent truncation)
**Verified.** `agent/turn_preflight.py` L192-224:
```python
    elif provider_overflow_preflight and _compression_cooldown:
        # Provider proved the request cannot fit and the compressor is unavailable:
        # don't resend; let the next user turn retry after cooldown.
        ...
    elif provider_overflow_preflight and v.compression_attempts >= max_compression_attempts:
        # All recovery passes consumed and still over threshold: fail closed —
        # llama.cpp may silently truncate an oversized retry.
        return _done("return", _exhausted_result())
    ...
    if provider_overflow_preflight:
        # Any other gate blocking the forced preflight (e.g. uncompressible one-
        # message request) must fail closed: the request is proven not to fit.
        return _done("return", _exhausted_result())
```
And the docstring L62-68: "A forced provider-overflow preflight that any gate blocks fails closed (llama.cpp may silently truncate)."

---

## Searched, found nothing

- **Exact `CREATE TABLE sessions` DDL**: not located in the files fetched (`hermes_state_schema.py`, `hermes_state_local.py`, `hermes_state_dbfile.py`, `hermes_state.py` all lack it — the DDL lives in a module I did not fetch). The `sessions.model` / `sessions.model_config` columns are nonetheless proven by the `UPDATE sessions SET model = ?, model_config = ?` statements in `hermes_state_sessions.py` (Q1.5).
- **Any per-call model/provider parameter for `delegate_task`**: searched the full tool schema (`tools/delegate_tool.py` L696-776) and the registry handler (L799-813) — none exists; `_MODEL_HIDDEN_TASK_FIELDS = {"acp_command", "acp_args"}` (L790) is the only per-task override surface, and it is trusted-config-only, not model-facing.
- **Any "truncate history to fit" path in the main loop**: searched `agent/conversation_loop.py`, `agent/turn_preflight.py`, `agent/turn_preflight_gate.py`, `agent/context_compressor.py` for truncation-on-overflow — none; the only overflow handling is compression, window growth (managed local runtimes), warnings, and fail-closed exhaustion.
- **`prompt_caching` keys other than `cache_ttl`**: searched `hermes_cli/config_defaults.py` — the `prompt_caching` section is exactly `{"cache_ttl": "5m"}` (L702); no separate enable/disable key (disable is expressed via falsy `cache_ttl`).
- **`agent/prompt_caching.py` on first fetch**: transient HTTP 429 from raw.githubusercontent.com; retried successfully (HTTP 200).
