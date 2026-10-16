# Lane 1 — Hermes Agent Official Docs: native mechanisms for per-task model selection without switching an existing chat's model

- Research date: 2026-10-16 (Europe/Zurich)
- Scope: official docs only (hermes-agent.nousresearch.com/docs). No source code read.
- Question answered: "How do I use different (cheap/expensive) models for different tasks WITHOUT switching the model of an existing chat?"
- Method: web_extract of 12 doc pages (configuring-models, delegation, profiles, sessions, slash-commands, local-models, mixture-of-agents, kanban-worker-lanes, context-references, kanban, desktop, configuration, messaging, plugins/omh) + llms.txt index + targeted web_search.
- Confidence tiers: **Verified** = authoritative doc for this exact target; **Plausible** = sound general behavior not demonstrated on-target; **Speculative** = inferred.

---

## A. What /model does to an existing session (sub-question 1)

### A1. /model hot-swaps the model of the CURRENT session in place; the conversation is kept
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models (official docs)
- Quote: "Pick a model, hit **Switch**, and Hermes writes it to `~/.hermes/config.yaml` under the `model` section. **This applies to new sessions only** — any chat tab you already have open keeps running whatever model it started with. To hot-swap the current chat, use the `/model` slash command inside it."
- Quote (troubleshooting, same page): "Expected. The dashboard writes `config.yaml`, which new sessions read. The currently-open chat is a live agent process — it keeps whatever model it was spawned with. Use `/model <name>` inside the chat to hot-swap that specific session."
- **Verified**

### A2. Mid-session model switch resets the prompt cache — one-time full-price re-read of the whole conversation
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models (official docs)
- Quote: "Prompt caches are keyed to the model serving the request, so any mid-conversation model change — an explicit `/model` switch, an automatic fallback, or a credential-pool rotation onto a different account — means the next message re-reads the entire conversation at full input-token price instead of the cached (~75–90% discounted) rate. On a long session this one-time re-read can dwarf the per-token difference between the two models. Switch when you need to, but prefer doing it early in a conversation or right after starting a fresh session."
- Same warning on the slash-commands page (https://hermes-agent.nousresearch.com/docs/reference/slash-commands): "**Cost note:** switching models mid-conversation resets the prompt cache — the cache key includes the model, so your next turn re-reads the entire conversation at full input price instead of the ~75%-discounted cached rate. Expected and unavoidable, but worth knowing on long sessions."
- **Verified**

### A3. /model rewrites the Model:/Provider: line in the system prompt (one-time cache miss, then byte-stable)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models (official docs)
- Quote: "An explicit `/model` switch also rewrites the `Model:` (and `Provider:`) line inside the system prompt so the agent knows what it is running on. That is a deliberate, one-time change: the first request after the switch misses the cached prefix once, and everything after the system prompt stays byte-identical. Automatic fallbacks rewrite the same line only in memory — the stored session keeps the primary's labels, so a restored primary replays a byte-identical prompt."
- **Verified**

### A4. Confirmation guard before mid-session switch in large contexts: `model.switch_context_confirm_tokens` (default 100,000)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models (official docs)
- Quote: "Because of that one-time re-read cost, Hermes asks for **explicit confirmation** before applying a mid-session switch when the live session already holds a large context (default: **100,000 tokens**, measured from the latest provider-billed prompt size). … Tune or disable it in `config.yaml`: `model: switch_context_confirm_tokens: 100000` … Re-selecting the model you're already on never prompts (the cache stays warm), and sessions with no measured context (fresh sessions, non-live surfaces) are exempt."
- **Verified**

### A5. Switching to a model with a smaller window can trigger preflight compression on the next message
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models (official docs)
- Quote: "When you switch models **inside an active session** (Herm TUI model picker, `hermes` CLI, or `/model` on Telegram/Discord), Hermes estimates whether your **next message** will run **preflight context compression** against the new model's window. If the session is already near or above that model's compression threshold … the switch reply includes a warning … The switch still applies immediately; compression runs on the **first user message after the switch**, before the model answers."
- **Verified**

### A6. `/model <name> --once` = one-turn model escalation with automatic restore (no persistence)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models (official docs, "Alternative methods → CLI slash command")
- Quote: "`/model claude-opus-4.6 --once` # next turn only, then auto-restores … `--once` switches for a single turn and restores the previous model afterward — on success, error, or interrupt alike. Nothing is persisted: a gateway restart mid-turn comes back on the original model. Useful for escalating one hard question to an expensive model (\"ask Opus just this once\") or dropping to a cheap model for a throwaway query."
- **Verified**

### A7. Documented cost caveat for `--once` in long cached sessions (double cache break)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models (official docs)
- Quote: "A one-turn switch breaks the provider's prompt-cache prefix twice (switching out and back). In a long session on a cached-prefix provider (Anthropic, OpenAI), the next turn re-pays full input cost — `--once` wins for short sessions or cheap→expensive escalation, but a quick side question inside a long expensive session can cost more than it saves."
- **Verified**

### A8. /model flags and scoping: `--global`, `--session`, `--once`, `--provider`, `--reasoning`; plain pick is session-only
- Source: https://hermes-agent.nousresearch.com/docs/reference/slash-commands (official docs)
- Quote: "Flags: `--global` persists the change to config.yaml; `--session` forces session-only; `--once` applies to the next turn only; `--refresh` re-fetches the provider's model list; `--provider <name>` switches backend (session-only unless `--global`); `--reasoning <level>` sets the reasoning effort … in the same step and with the same scope as the pick. A plain `/model <name>` is session-only unless `model.persist_switch_by_default: true` is set … **Note:** `/model` can only switch between already-configured providers. To add a new provider, exit the session and run `hermes model` from your terminal."
- Quote (same page, `--global` semantics, configuring-models): "`--global` does the same thing the dashboard's **Change** button does, plus it switches the running session in-place."
- **Verified**

### A9. Gateway chats: /model override is session-scoped and survives gateway restarts; /new clears it
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/messaging (official docs, "Persistent /model Overrides")
- Quote: "A `/model` switch in a gateway chat applies to that session and now **survives gateway restarts**: the model/provider choice is persisted to the session store and rehydrated on first use after a restart (credentials are re-resolved at load time and never written to disk). `/new` (or `/reset`) clears the override, and `/model <name> --global` writes it through to `config.yaml` instead. `/model <name> --once` applies for a single turn only."
- **Verified**

### A10. CLI/TUI keep a per-session model pin; resume restores the model that chat used
- Source: https://hermes-agent.nousresearch.com/docs/reference/slash-commands (official docs, messaging /model row)
- Quote: "a successful `--global` pick (typed or picker) also drops this chat's session-only override, so config.yaml alone decides the model after a gateway restart (a chat with a `channel_overrides` model keeps the override, since the channel setting would otherwise outrank config.yaml; the CLI/TUI deliberately keep their per-session pin so resume restores the model that chat used)."
- **Verified**

### A11. Config-file model changes never touch running sessions (deliberate cache protection)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models (official docs, "When does it take effect?")
- Quote: "CLI (`hermes chat`): next `hermes chat` invocation. Gateway (Telegram, Discord, Slack, etc.): next _new_ session. Existing sessions keep their model. Restart the gateway (`hermes gateway restart`) if you want to force all sessions to pick up the change. Dashboard chat tab (`/chat`): next new PTY. The currently-open chat keeps its model — use `/model` inside it to hot-swap. Changes never invalidate prompt caches on running sessions. That's deliberate: swapping the main model inside a session requires a cache reset (the system prompt contains model-specific content), and we reserve that for the explicit `/model` slash command inside chat."
- **Verified**

---

## B. Delegation: delegate_task children on a different (cheaper) model (sub-question 2)

### B1. `delegation.model` / `delegation.provider` route ALL subagents to a different model/provider; omit = inherit parent
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (official docs, "Model Override")
- Quote: "You can configure a different model for subagents via `config.yaml` — useful for delegating simple tasks to cheaper/faster models: `delegation: model: \"google/gemini-flash-2.0\" # Cheaper model for subagents; provider: \"openrouter\" # Optional: route subagents to a different provider`. If omitted, subagents use the same model as the parent."
- **Verified**

### B2. Granularity is profile-wide (config.yaml), NOT per-spawn: no per-task model parameter exists
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (official docs)
- Quote: "Note that the pin is global: `delegate_task` has no per-task model parameter, so every child in a batch runs on the configured delegation model. For quality-sensitive subtasks that need a stronger model, either leave `delegation.model` unset for that session or hand the task to the kanban board, which does support a per-task model override."
- **Verified** (documented negative: no per-task model on delegate_task)

### B3. Resolution order: base_url > provider > inherit; model applies in all cases
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (official docs)
- Quote: "Resolution order: `delegation.base_url` (direct endpoint) takes precedence, then `delegation.provider` (full credential bundle resolved via the runtime provider system), and when neither is set children inherit the parent's provider and credentials; `delegation.model` applies in all cases, and when it is empty children inherit the parent's model."
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuration (official docs, "Delegation")
- Quote: "**Precedence:** `delegation.base_url` in config → `delegation.provider` in config → parent provider (inherited). `delegation.model` in config → parent model (inherited). Setting just `model` without `provider` changes only the model name while keeping the parent's credentials (useful for switching models within the same provider like OpenRouter)."
- **Verified**

### B4. Full key list for delegation model routing (config.yaml)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuration (official docs, "Delegation")
- Quote: "delegation: # model: \"google/gemini-3-flash-preview\" # Override model (empty = inherit parent) # provider: \"openrouter\" # Override provider (empty = inherit parent) # base_url: \"http://localhost:1234/v1\" # Direct OpenAI-compatible endpoint (takes precedence over provider) # api_key: \"local-key\" # API key for base_url (falls back to OPENAI_API_KEY) # api_mode: \"\" # Wire protocol …"
- Additional keys documented on the same page: `delegation.fallback_providers` ("Set `delegation.fallback_providers` to give workers their own chain"), `delegation.request_overrides` ("a dict of request settings sent on every subagent API call"), `delegation.max_iterations` (default 250), `delegation.max_concurrent_children` (default 3), `delegation.max_spawn_depth` (1–3), `delegation.compression_threshold_tokens`.
- **Verified**

### B5. Subagent context is FRESH, not inherited — parent must pass everything via goal/context
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (official docs, "How Subagent Context Works")
- Quote: "Subagents start with a **completely fresh conversation**. They have zero knowledge of the parent's conversation history, prior tool calls, or anything discussed before delegation. The subagent's only context comes from the `goal` and `context` fields the parent agent populates when it calls `delegate_task`."
- Exception (same section): "when the parent has a resolved workspace directory, every subagent's system prompt embeds that workspace's **project context files** (`.hermes.md` > AGENTS.md chain > CLAUDE.md > `.cursorrules` …)."
- **Verified**

### B6. Docs explicitly endorse the "frontier planner, inexpensive workers" cost strategy
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (official docs, "Cost strategy: frontier planner, inexpensive workers")
- Quote: "Decomposing a problem into well-specified subtasks takes frontier-level judgment; executing a subtask that already comes with a clear goal, full context, and an output contract usually doesn't. Meanwhile the children are where the tokens go — a parallel batch of subagents typically burns the large majority of a run's total tokens, so the worker model is where the cost actually lives. Pinning `delegation.model` to an inexpensive model while your main session stays on a frontier model keeps the planning quality where it matters and cuts spend where the volume is."
- Example config (same section): "model: default: \"your-frontier-model\" # parent (planner) stays on the frontier model; delegation: model: \"your-inexpensive-model\" # all delegate_task children run on this; provider: \"openrouter\" # optional: route children to a different provider"
- **Verified**

### B7. The agent delegates automatically based on task complexity (no user prompt needed)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (official docs, tip at end of Configuration)
- Quote: "The agent handles delegation automatically based on the task complexity. You don't need to explicitly ask it to delegate — it will do so when it makes sense."
- **Verified**

### B8. `/review` reviewer model is separately pinnable via `auxiliary.review`
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation (official docs, "Review model")
- Quote: "By default the reviewer runs on your main model. To pin a dedicated review model, set `auxiliary.review` in `config.yaml`: `auxiliary: review: provider: openrouter; model: anthropic/claude-opus-4.6 # a strong reviewer model`. Credentials resolve exactly like a `delegation.provider` pin … `provider: auto` with an empty `model` means \"inherit the main agent's model\" — the default."
- **Verified**

---

## C. Auxiliary model slots (native per-task-type model offloading)

### C1. 11 auxiliary task slots, each independently overridable to a cheaper/faster model
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models (official docs, "Setting auxiliary models")
- Quote: "Hermes uses two kinds of model slots: **Main model** — what the agent thinks with. … **Auxiliary models** — smaller side-jobs the agent offloads. Context compression, vision (image analysis), web-page summarization, approval scoring, MCP tool routing, session-title generation, and skill search. Each has its own slot and can be overridden independently."
- Quote: "Every auxiliary task defaults to `auto` — meaning Hermes tries your main model for that job too. … Override a specific task when you want a cheaper or faster model for a side-job."
- **Verified**

### C2. Documented override patterns per task (compression, vision, approval, web extract, title gen, MCP, skills hub, triage specifier)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models (official docs, "Common override patterns")
- Quote (table rows): "**Title Gen** — … Pin a known-good flash model, or set `auxiliary.title_generation.prefer_fast_model: true` … **Vision** — … Point it at `google/gemini-2.5-flash` or `gpt-4o-mini`. **Compression** — When you're burning reasoning tokens on Opus/M2.7 just to summarize context. A fast chat model does the job at 1/50th the cost. **Approval** — For `approval_mode: smart` — a fast/cheap model (haiku, flash, gpt-5-mini) decides whether to auto-approve low-risk commands. Expensive models here are waste. **Web Extract** — When you use `web_extract` heavily. Same logic as compression — summarization doesn't need reasoning. … **Triage Specifier** — Routes the Kanban triage specifier (`hermes kanban specify`) … A cheap, capable model works well."
- **Verified**

### C3. Auxiliary config shape: `auxiliary.<task>.provider/model/base_url/api_key/timeout/extra_body` + per-task `fallback_chain`
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models (official docs, "What gets written to config.yaml")
- Quote: "auxiliary: vision: provider: openrouter; model: google/gemini-2.5-flash; base_url: ''; api_key: ''; timeout: 120; extra_body: {}; download_timeout: 30 … `provider: auto` with `model: ''` tells Hermes to use the main model for that task, while still honoring fallback policy … Optional task-specific fallback chains live under the same auxiliary task: auxiliary: title_generation: provider: auto; model: ''; fallback_chain: - provider: openrouter; model: inclusionai/ring-2.6-1t:free"
- **Verified**

### C4. Compression specifically: override to a cheaper model than the main chat model
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuration (official docs, Context Compression)
- Quote: "Uses your main provider and main model. Override per-task (e.g. `auxiliary.compression.provider: openrouter` + `model: google/gemini-2.5-flash`) if you want compression on a cheaper model than your main chat model."
- **Verified**

### C5. Per-task reasoning effort for auxiliary slots (`auxiliary.<task>.reasoning_effort`)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuration (official docs)
- Quote: "This is the per-task counterpart of the global `agent.reasoning_effort`: run compression at `low` or vision at `none` to cut side-task latency and cost when your main model is an expensive reasoning model, without touching your main chat behavior."
- **Verified**

### C6. Delegation entry in the auxiliary picker persists to `delegation.*`, not `auxiliary.*`
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuration (official docs, Auxiliary models)
- Quote: "The **Delegation** entry is special: it routes the model used by `delegate_task` subagents and persists to the top-level `delegation.*` section (`delegation.provider` / `delegation.model`) rather than `auxiliary.*`, because subagents are full child agents, not side-LLM calls. Its `auto` means \"inherit the parent agent's provider, model, and credentials.\""
- **Verified**

---

## D. Profiles: different default models per profile (sub-question 3)

### D1. Each profile has its own config.yaml with its own model/provider
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/profiles (official docs, "Configuring profiles")
- Quote: "Each profile has its own: **`config.yaml`** — model, provider, toolsets, all settings; **`.env`** — API keys, bot tokens; **`SOUL.md`** — personality and instructions."
- Example (same section): "coder config set model.default anthropic/claude-sonnet-4"
- **Verified**

### D2. Run a task in another profile: `hermes -p <name>` (any position) and one-shot `-q`
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/profiles (official docs)
- Quote: "hermes -p coder chat; hermes --profile=coder doctor; hermes chat -p coder -q \"hello\" # works in any position"
- **Verified**

### D3. Profiles auto-become commands (`coder chat`, `coder setup`, `coder gateway start`)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/profiles (official docs)
- Quote: "When you create a profile, it automatically becomes its own command. Create a profile called `coder` and you immediately have `coder chat`, `coder setup`, `coder gateway start`, etc."
- **Verified**

### D4. Desktop: per-profile global default model; each profile keeps its own default
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/desktop (official docs, "Choosing a model")
- Quote: "**Set the default in Settings → Model.** That \"main\" model is your **per-profile global default** — it's what new chats, crons, subagents, and auxiliary tasks start from, and it's the only place that writes it. Each profile keeps its own default."
- **Verified**

---

## E. Desktop app: per-chat model selection UI (sub-question 4)

### E1. Composer model picker; switching in a live chat is scoped to THAT chat only
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/desktop (official docs, "Choosing a model")
- Quote: "The model picker lives in the **composer**, just left of the microphone. Click it to switch the model; hover a model row for its options (thinking, effort, fast)."
- Quote: "**The composer picker is sticky UI state and never touches your default.** It's remembered locally (per device) and **follows** across new chats and restarts instead of snapping back to the default — pick a model once and the next `Cmd/Ctrl+N` opens on it. With a live chat, switching models scopes the change to that **current chat**; either way the selection rides along when the session is created/switched and is **never** written to the profile [default]."
- **Verified**

### E2. Desktop documents the same prompt-cache cost for mid-chat switches, and recommends a fresh chat on long sessions
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/desktop (official docs)
- Quote: "**Mid-chat switches reset the prompt cache.** Switching the model inside a live chat means the next message re-reads the whole conversation at full input price (provider prompt caches are keyed to the model). Fine occasionally; on a long chat, a fresh chat on the new model is often cheaper than bouncing back and forth."
- **Verified**

### E3. Per-model effort/fast presets and favorites in the desktop picker
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/desktop (official docs)
- Quote: "**Per-model effort/fast presets.** Each model remembers its own reasoning effort and fast-mode choice in the desktop app, re-applied to the session whenever you pick that model. These presets are a desktop convenience and don't change crons or subagents."
- **Verified**

---

## F. Context transfer to a new session on another model (sub-question 5)

### F1. Context references (@-syntax) inject files/diffs/URLs into a message — CLI feature
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/context-references (official docs)
- Quote: "Type `@` followed by a reference to inject content directly into your message. Hermes expands the reference inline and appends the content under an `--- Attached Context ---` section." Supported: `@file:path`, `@file:path:10-25`, `@folder:path`, `@diff`, `@staged`, `@git:N`, `@url:…`.
- Caveat (same page): "Context references are primarily a **CLI feature**. … In **messaging platforms** (Telegram, Discord, etc.), the `@` syntax is not expanded by the gateway — messages are passed through as-is."
- **Verified**

### F2. `session_search` tool: full-text recall across ALL past sessions (no LLM calls)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/sessions (official docs, "Session Search Tool")
- Quote: "The agent has a built-in `session_search` tool that performs full-text search across all past conversations using SQLite's FTS5 engine — and lets the agent scroll through any session it finds. It makes no LLM calls and returns views of actual messages from the DB rather than generating summaries."
- **Verified**

### F3. Session resume: `hermes -c` / `--resume <id|title|latest>` / `--in <dir>`; messaging `/resume [name]`; sessions store model name+config
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/sessions (official docs)
- Quote: "Resume previous conversations from the CLI using `--continue` or `--resume`: hermes --continue … hermes --resume 20250305_091523_a1b2c3d4 … hermes --resume \"refactoring auth\" … hermes --resume latest … Pass `--in <dir>` to change into a directory before starting or resuming."
- Quote (session metadata): "The SQLite database stores: … Model name and configuration … System prompt snapshot … Full message history (role, content, tool calls, tool results) … Parent session ID (for compression-triggered session splitting)."
- **Verified**

### F4. `/handoff <platform>` moves a LIVE conversation to another surface with the same session id
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/sessions (official docs, "Cross-Platform Handoff")
- Quote: "Use `/handoff <platform>` from a CLI session to transfer the live conversation to a messaging platform's home channel. The agent picks up exactly where the CLI left off — same session id, full role-aware transcript, tool calls and all."
- **Verified**

### F5. Kanban parent link = structured context handoff from a completed card to a new card (works across models/profiles)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban (official docs, "Handing context to follow-up cards (the parent link)")
- Quote: "A parent link is not just a scheduling gate — it is the context handoff channel from a **completed** card to a new one. When you create a card with `--parent <done-card-id>`, two things happen: 1. It's immediately eligible. … 2. **The parent's handoff rides along.** The worker context assembled for the child … contains a `## Parent task results` section with each parent's completion `summary` and `metadata`, verbatim."
- **Verified**

### F6. `/bg <prompt>` (messaging): separate background session, isolated context, inherits current model/provider
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/messaging (official docs, "Background Sessions")
- Quote: "Each `/bg` prompt spawns a **separate agent instance** that runs asynchronously: **Isolated session** — the background agent has its own session with its own conversation history. It has no knowledge of your current chat context and receives only the prompt you provide. **Same configuration** — inherits your model, provider, toolsets, reasoning settings, and provider routing from the current gateway setup."
- **Verified**

### F7. `/btw <question>` (messaging): side question about the current conversation without interrupting the running turn
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/messaging (official docs, Chat Commands table)
- Quote: "`/btw <question>` | Ask a side question about the current conversation without interrupting it"
- **Verified**

---

## G. Mixture of Agents (sub-question 6)

### G1. MoA presets CAN mix different providers and models (explicit provider/model pairs per slot)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents (official docs, "Configure presets")
- Quote: "The config stores explicit provider/model pairs, so you can mix providers and use multiple models from the same provider: moa: presets: default: reference_models: - provider: openai-codex; model: gpt-5.5; - provider: openrouter; model: deepseek/deepseek-v4-pro; aggregator: provider: openrouter; model: anthropic/claude-opus-4.8"
- **Verified**

### G2. MoA is a virtual provider selectable like any model (via /model, hermes model, dashboard, desktop dropdown)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents (official docs)
- Quote: "Mixture of Agents is a virtual model provider. Each named MoA preset appears as a selectable model under the `moa` provider. … MoA presets are selectable on **every Hermes surface**, because MoA is a normal provider in the model system: **CLI / gateway / TUI `/model`** — `/model <preset> --provider moa` … **Desktop GUI app** — the model dropdown shows an `MoA presets` section."
- **Verified**

### G3. Aggregator is the acting/billed model; references advise once per user turn by default (cheapest cadence)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents (official docs)
- Quote: "The **aggregator is billed for the whole run**: it runs every step of the tool loop, so almost all of a preset's cost lands on the aggregator's provider. References only advise once per user turn (with the default `fanout`). … By default the advisors run **once per user turn** (`fanout: user_turn`) … This is the cheapest cadence: advisor cost does not multiply with the number of tool calls in a turn."
- **Verified**

### G4. `/moa` one-shot runs a prompt through the default preset, then RESTORES the previous model
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents (official docs, "Slash command shortcut")
- Quote: "`/moa` is one-shot convenience sugar. It runs a single prompt through the **default** MoA preset, then restores whatever model you were on … `/moa` is deliberately not a model switch, so a normal prompt can never accidentally change your model."
- **Verified**

### G5. MoA does NOT break the main conversation's prompt cache (unlike a plain /model switch)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents (official docs, "Prompt caching")
- Quote: "MoA is built so the **main conversation's prompt cache is never broken**. Selecting a MoA preset is a normal model selection: it does not mutate past context, swap toolsets, or rebuild the system prompt mid-conversation. … Switching to or away from a MoA preset costs the same cache invalidation as any other `/model` switch — no more. … Its only real cost is the extra reference calls (once per user turn with the default `fanout`) — you pay for multiple model perspectives, not for broken caches."
- **Verified**

### G6. MoA can serve as a fallback entry
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents (official docs, Notes)
- Quote: "A preset can be a fallback entry (`fallback_providers: [{provider: moa, model: <preset>}]`). When the primary fails, Hermes activates the preset itself — references and aggregator, with `moa://local` as the virtual endpoint."
- **Verified**

---

## H. Kanban: workers on different models/profiles than the orchestrator (sub-question 7)

### H1. Kanban workers are spawned as `hermes -p <assignee>` — each worker reads ITS OWN profile's model config
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes (official docs, "2. A spawn mechanism")
- Quote: "For Hermes profile lanes, the dispatcher's `_default_spawn` runs `hermes -p <assignee> chat -q <prompt>` (or the equivalent module form when the `hermes` shim isn't on `$PATH`) inside the task's pinned workspace …"
- **Verified**

### H2. Per-task model override: `--model`/`--provider` at create, `hermes kanban set-model` later, dashboard dropdown
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban (official docs, "Per-task model override")
- Quote: "Pin a task's worker to a specific model (and optionally provider), independent of the assignee profile's default: `hermes kanban create \"hard refactor\" --assignee coder --model claude-opus-4.6 --provider anthropic` # Or later — takes effect on the next dispatch `hermes kanban set-model t_abcd claude-opus-4.6 --provider anthropic`; `hermes kanban set-model t_abcd none` # clear the override. The dispatcher spawns the worker with the pinned model (`--provider <name>` is passed when set; `--provider` requires a model). The dashboard's per-task model dropdown drives the same `model_override` field. With no override, the worker uses its profile's configured model."
- **Verified**

### H3. Docs explicitly endorse "frontier orchestrator, inexpensive workers" via per-profile configs
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban (official docs, "Cost strategy: frontier orchestrator, inexpensive workers")
- Quote: "Kanban's per-profile configs make the planner/worker cost split natural. Decomposing a project into well-scoped cards takes frontier-level judgment; executing a card that already carries a clear goal, context, and handoff evidence usually doesn't — and the workers are where the vast majority of tokens are spent, so the worker model is where the cost lives. Run your orchestrator/dispatcher profile on a frontier model and point worker profiles at inexpensive models. Each profile has its own `config.yaml` under `~/.hermes/profiles/<name>/`, and the dispatcher injects the profile-scoped `HERMES_HOME` when it spawns `hermes -p <assignee>`, so each worker reads its own profile's model settings."
- Example (same section): "# ~/.hermes/config.yaml (orchestrator / dispatcher profile) model: default: \"your-frontier-model\"; # ~/.hermes/profiles/coder/config.yaml (worker profile) model: default: \"your-inexpensive-model\""
- **Verified**

### H4. Kanban decomposer model is separately pinnable: `auxiliary.kanban_decomposer`
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban (official docs, config table)
- Quote: "`auxiliary.kanban_decomposer` | Model that produces the task graph (called by Decompose). Set `provider`/`model` to override the main chat model."
- Related (same page): "`kanban.orchestrator_profile` does not load that profile's prompt, skills, or custom logic into the decomposition call. It controls who owns the root/orchestration task after fan-out. To change the decomposer's model/provider, configure `auxiliary.kanban_decomposer`."
- **Verified**

### H5. Kanban vs delegate_task: named persistent profiles vs anonymous subagents; durable audit trail
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban (official docs, "Kanban vs. `delegate_task`")
- Quote (table): "Child identity: Anonymous subagent | Named profile with persistent memory. Resumability: None — failed = failed | Block → unblock → re-run; crash → reclaim. Audit trail: Lost on context compression | Durable rows in SQLite forever."
- **Verified**

### H6. Orchestrator profile lane = kanban toolset without terminal/file/code/web (decompose-only role)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes (official docs, "Orchestrator profile lane")
- Quote: "A specialisation of the profile lane: an orchestrator is a Hermes profile whose toolset includes `kanban` but excludes `terminal` / `file` / `code` / `web` for implementation. Its job is decomposing a high-level goal into child tasks via `kanban_create` + `kanban_link` and stepping back."
- **Verified**

---

## I. Gateway per-channel model overrides (bonus — directly on-target for "different model per chat")

### I1. `channel_overrides` under a platform: different model (and system prompt) per channel from ONE gateway
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/messaging (official docs, "Per-Channel Model & System Prompt Overrides")
- Quote: "Different channels can run different models and personas from a **single gateway** — e.g. a cheap fast model in `#daily` and a frontier model with a specialist prompt in `#dev`. Configure `channel_overrides` under the platform in `~/.hermes/config.yaml`: platforms: discord: enabled: true; channel_overrides: \"123456789012345678\": model: anthropic/claude-sonnet-4.6; provider: anthropic; system_prompt: \"You are the #dev channel code-review specialist.\"; \"987654321098765432\": model: openai/gpt-5-mini"
- Quote (resolution): "All three keys are optional — set only `model`, only `system_prompt`, or any combination. Unset fields fall back to the global defaults. Lookup order is exact channel/thread id first, then the **parent** channel/forum id — so Discord threads inherit their parent channel's override automatically. Resolution priority for the model is: session `/model` override → `channel_overrides` → global config. A user running `/model` in a chat still wins over the channel default."
- **Verified**

---

## J. Supporting mechanisms

### J1. Custom model aliases for fast switching (`model_aliases:` full form, `model.aliases.<name>: provider/model` short form)
- Source: https://hermes-agent.nousresearch.com/docs/reference/slash-commands (official docs, "Custom model aliases")
- Quote: "Define your own short names for models you use often, then reach them with `/model <alias>` in a running session, `hermes chat --model <alias>` at startup, or any messaging platform. … `model_aliases: fav: model: claude-sonnet-4.6; provider: anthropic; … ollama-qwen: model: qwen3-coder:30b; provider: custom; base_url: http://localhost:11434/v1`"
- **Verified**

### J2. `hermes model` = canonical interactive picker; writes `model.provider` + `model.default`; auxiliary picker per task
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models (official docs, "Alternative methods → hermes model subcommand")
- Quote: "hermes model # Interactive provider + model picker (the canonical way to switch defaults) … The choice is written to `model.provider` and `model.default` in `~/.hermes/config.yaml`. … **Configure auxiliary models...** opens the per-task side-model picker (vision, compression, approval, delegation, …)."
- **Verified**

### J3. Local models (llama.cpp managed runtime) as a free/cheap model source; `model.provider: llamacpp`
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/local-models (official docs)
- Quote: "Hermes can run open models entirely on your own machine. … Selecting a local model as your main model uses the standard `model.provider: llamacpp` + `model.default` settings." Also: "If a llama-server is already running on your machine, Hermes detects it and uses it instead of starting its own. Point a custom endpoint at any OpenAI-compatible server for full manual control."
- **Verified**

### J4. REST API for programmatic model switching (dashboard endpoints)
- Source: https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models (official docs, "REST API")
- Quote: "curl -X POST … -d '{\"scope\":\"main\",\"provider\":\"openrouter\",\"model\":\"anthropic/claude-opus-4.7\"}' http://localhost:PORT/api/model/set # Override [auxiliary] …"
- **Verified**

### J5. Non-native (plugin catalog): "omh" (oh-my-hermes) plugin adds per-lane model routing for delegated work
- Source: https://hermes-agent.nousresearch.com/docs/plugins/omh (official plugin catalog page; third-party plugin, NOT a native mechanism)
- Quote: "**Mixture-of-Models Routing** — each delegated lane is routed onto a category (ultrabrain, deep, quick, writing, visual-engineering, …) whose model and reasoning effort are applied per dispatch; every activity row carries its `category:name(model:effort)` so the routing is visible, and rejected routes fall back along the category chain."
- Quote: "It starts here, at routing: every request is scored before dispatch … A rename scores light and goes to the quick lane. \"Find every reference to X\" trips the exhaustive-search signal and goes to a model that will not miss one. Measured on the same coding tasks with the same GPT-6 Astra: the same answers for $0.66 instead of $4.29, in 5 minutes instead of 23."
- **Plausible** (documented in the official catalog, but it is a third-party plugin; behavior not independently verified; requires separate install `omh setup`)

---

## K. Searched, found nothing

| Query / target | Source type searched | Result |
| --- | --- | --- |
| "model routing" as a named native feature (automatic per-turn model routing of the MAIN model by task complexity) | web_search `site:hermes-agent.nousresearch.com "model routing" OR "route tasks to different models"` + full-text scan of configuring-models, configuration, delegation, kanban pages | No native per-turn model router for the main model exists in the docs. Only hits: "provider-routing warnings" (data-training tiers, configuring-models), "model routing all behave per-profile" (multi-profile-gateways, i.e. per-profile config), and the third-party `omh` plugin (per-lane routing for delegated lanes). The native equivalents are: agent-judged `delegate_task` (B7), auxiliary slots (C1), kanban per-task override (H2), MoA (G). |
| Per-task model parameter on `delegate_task` | delegation page (official docs) | Documented NEGATIVE: "delegate_task has no per-task model parameter" (B2). |
| Per-chat model selection UI in the classic CLI | slash-commands, cli, tui pages (official docs) | No per-chat UI in the classic CLI; the mechanism is the session-scoped `/model` pin (A8/A10). (TUI has a model picker mentioned in configuring-models: "Herm TUI model picker" — session-scoped, same cache caveats.) |
| "cheap model subagent" config keys other than `delegation.model`/`delegation.provider`/`delegation.base_url` | configuration + delegation pages (official docs) | None — those three (plus `api_key`, `api_mode`, `request_overrides`, `fallback_providers`) are the complete documented set. |
| MoA as a per-TASK router (only expensive model for hard sub-steps within one turn) | mixture-of-agents page (official docs) | MoA is a model SELECTION (whole session/turn runs through the preset), not a per-task router; `fanout` controls advisor cadence, not task routing. |
| Per-session model override in `config.yaml` (static, per session id) | configuration page (official docs) | No such key. Per-session model state is runtime (session store / session pin), set via `/model`, not config. |
| "different model per session" static config for CLI sessions | configuration, sessions, slash-commands pages (official docs) | No static per-session config; sessions record the model they ran with (sessions page: "Model name and configuration" stored in state.db) and resume restores it (A10). |

---

## L. Synthesis: native mechanisms that answer the user's question (ranked by fit)

1. **`delegation.model` / `delegation.provider` (B1–B7)** — the docs' own "frontier planner, inexpensive workers" pattern: main chat stays on expensive Claude; all `delegate_task` children run on a cheap model (e.g. local Qwen via `delegation.base_url` or `delegation.provider: ryzen`). Children get fresh context (goal/context fields), so no prefill cost on the parent chat; parent chat's model and cache are never touched. Limitation: global pin, no per-task model (B2).
2. **Kanban per-task model override + per-profile worker models (H1–H4)** — the only NATIVE per-TASK model pin: `--model`/`--provider` at create or `hermes kanban set-model` later; workers run under their own profile's model config; orchestrator profile stays on frontier model. Durable, resumable, human-in-the-loop; context handoff via parent links (F5). Heavier machinery than delegation.
3. **Auxiliary slots (C1–C6)** — offload side-jobs (compression, vision, web extract, approval, titles, kanban decomposer, /review) to cheap models while the main chat stays on the expensive model. Zero impact on the chat's model/cache.
4. **Desktop composer picker (E1–E3)** — per-chat model selection UI; switching in a live chat is scoped to that chat only and never writes the profile default. Caveat: mid-chat switch resets that chat's prompt cache (E2).
5. **`/model --once` (A6–A7)** — one-turn escalation to an expensive model with auto-restore; documented double-cache-break cost in long sessions.
6. **Profiles (D1–D4)** — separate profile per model tier; run work via `hermes -p <profile> chat -q "…"` one-shots; each profile keeps its own default model.
7. **`channel_overrides` (I1)** — per-channel model for gateway chats (cheap model in one chat, frontier in another) from a single gateway.
8. **MoA (G1–G6)** — mix providers/models per preset; selectable per session; `/moa` one-shot restores previous model; cache-safe.
9. **Context transfer for fresh-session-on-cheap-model pattern (F1–F7)** — @-references, session_search, resume, /handoff, kanban parent links, /bg, /btw.
10. **Non-native: `omh` plugin (J5)** — per-lane model routing for delegated work (third-party, plugin catalog).
