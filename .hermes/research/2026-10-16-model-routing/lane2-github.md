# Lane 2 — GitHub Issues / PRs / Discussions: model switching & per-task model selection

Repo: github.com/NousResearch/hermes-agent · Researched 2026-10-16 · Method: web_search + web_extract of issue/PR pages (gh CLI not authenticated in sandbox).
Tiers: **Verified** = full issue/PR page read, state + quote confirmed. **Plausible** = search snippet or cross-reference only, state not independently confirmed. **Speculative** = inference.
User context: v0.22.2, default model claude-opus-5-5 via custom provider `cpa` (CLIProxyAPI, ~18 Claude models), local providers `ryzen` (Qwen3.8-27B-FP8, 262144 ctx) and `llm` (qwen38vl-27b-kvu); delegation section has no model/provider pinning.

---

## 1. Model switching mid-session: what happens, bugs, fixes

### 1.1 #126068 — Model switch on a large-context session forces full cold re-read (prefix cache destroyed) — OPEN (P3, relabelled from P0)
- URL: https://github.com/NousResearch/hermes-agent/issues/126068
- Claim: Since v0.17.0, every mid-session model/provider switch rebuilds the stored system prompt; the volatile identity block (`Conversation started / Model: / Provider:`) sits in the LAST ~86 chars of the system prompt, immediately before the conversation history, so any byte change invalidates the provider's prefix cache for the ENTIRE history. A switch is therefore always a full-context cold prefill.
- Verbatim: "Since v0.17.0, switching model/provider mid-session rebuilds the stored system prompt. Because the volatile identity block (`Conversation started / Model: / Provider:`) sits in the LAST ~86 characters of the system prompt — immediately before the conversation history — any byte change there invalidates the provider's prefix cache for the ENTIRE history that follows."
- Verbatim (measured): "309K-token request, cache 0% (after a model switch): **220.7 s** to complete" vs "Same-size requests with a warm prefix cache: **8–25 s**"
- History: v0.15.x/0.16.0 reused the stored prompt verbatim (switches byte-stable and free, but `Model:`/`Provider:` lines went stale); v0.17.0 added `_stored_prompt_matches_runtime()` rebuild-on-mismatch; v0.18.0 additionally nulls `system_prompt` on switch (per #48173/#48248); v0.19.0 same.
- Proposed fixes: Option A = move identity block to end of request (out of cached prefix); Option B = v0.15-style stable prompt + in-band identity note (reporter's local workaround: reuse stored prompt verbatim, stop nulling `system_prompt` — "Restoring v0.15 cache behavior on a 300K-token session turns switch latency from minutes back into seconds").
- Tier: **Verified**

### 1.2 PR #128757 — "fix(agent): say what a model switch costs on a large session" — OPEN (changes requested; Related to #126068, deliberately NOT Closes)
- URL: https://github.com/NousResearch/hermes-agent/pull/128757
- Claim: The PR does NOT make switches fast; it only makes the `/model` switch summary name the re-read cost. The prompt-reuse mechanism it originally carried was withdrawn after teknium1's CHANGES_REQUESTED (guidance bytes are model-dependent, not just the identity trailer).
- Verbatim: "This PR does neither, and does not make model switches fast. It ships the triaged UX half: the `/model` switch summary now names the re-read cost, so the stall is explained where the user already reads the switch cost instead of looking like a hang."
- Verbatim (key triage statement): "A switch X→Y on a 300K session is a cold prefill on Y regardless of the bytes Hermes sends, and a provider switch moves to a different cache store entirely; this is why #100336 was withdrawn by its reporter and why #126068 was relabelled P0→P3"
- Implication: maintainers accept the cold-prefill cost as inherent (correctness of identity + per-model guidance bytes), not a bug to fix; UX disclosure is the shipped direction.
- Tier: **Verified**

### 1.3 #5999 — Feature: Add /model command to switch models within an active session — CLOSED (completed, May 24 2026, labelled duplicate)
- URL: https://github.com/NousResearch/hermes-agent/issues/5999
- Claim: Requested in-session `/model` (v0.7.0 era). Resolved as already supported.
- Verbatim (comment, fffonion): "This is already supported"
- Tier: **Verified**

### 1.4 #4808 — [Feature]: Ability to change model / provider mid session in CLI — CLOSED (not planned, Jun 10 2026, label `sweeper:implemented-on-main`)
- URL: https://github.com/NousResearch/hermes-agent/issues/4808
- Claim: Mid-session provider/model switch in CLI (Claude-Code-style, per-session model memory). Closed because the behavior is already on main.
- Verbatim (label): "Sweeper: behavior already present on current main"
- Tier: **Verified**

### 1.5 #4289 — [FEATURE] Add /model slash command to CLI chat — state not confirmed (v0.6.0 era request)
- URL: https://github.com/NousResearch/hermes-agent/issues/4289
- Claim: Early request for in-CLI-chat `/model`; snippet shows "The Hermes Agent CLI supports the command to switch models, but there's no equivalent slash command available within the interactive chat session". Superseded by #5999/#4808 outcomes.
- Tier: **Plausible**

### 1.6 #127879 — One-turn `/model --once` leaves a stale "model was just switched" note; weaker models keep claiming the temporary model — OPEN (P2; fix PR #128221 open)
- URL: https://github.com/NousResearch/hermes-agent/issues/127879
- Claim: After `/model <x> --once`, the prepended identity note stays in persisted history with no counterpart note on restore; routing is correct but a weaker primary model keeps identifying as the temporary model for the rest of the session. Reproduced on v0.21.5 (Telegram gateway; primary qwen3.5-9b via lmstudio, one-shot switch to claude-haiku).
- Verbatim: "The note stays in the persisted history, and when the one-turn override is restored no counterpart note is added. Routing is correct, but a weaker primary model then keeps claiming to be the temporary model for the rest of the session."
- Root cause (reporter): `gateway/slash_commands_model.py` builds the note; `_claim_one_turn_restore`/`_restore_session_model_override` add nothing on restore; CLI mixin builds the same note. Related: #124170 (same note restated after compaction).
- Relevance: this is the known wart of the `--once` cheap→expensive escalation pattern in long sessions.
- Tier: **Verified**

### 1.7 #132117 — [Bug]: bare-name model switch is hijacked to OpenRouter when a configured provider declares the same model id (silently billed) — OPEN (P2; fix PR #132148 open)
- URL: https://github.com/NousResearch/hermes-agent/issues/132117
- Claim: `/model <bare-name>` / TUI-dashboard picker / `switch_model()` silently routes to OpenRouter (metered) when a configured provider declares that exact model id AND the id matches the bare part of an OpenRouter slug. User picks a local/free model, gets billed to OpenRouter, no warning.
- Verbatim: "A bare-name model switch (`/model <name>`, the TUI/dashboard picker, or `switch_model()` itself) is silently hijacked to **OpenRouter** — a metered, billed provider — when a _configured_ provider (`providers.<slug>.models`) declares that exact model id and the id also matches the **bare part** of an OpenRouter slug (`vendor/<name>`). The user picks a local/free model and the turn is billed to OpenRouter, with no warning and no error."
- Measured repro uses `providers.llama-server` with `models: {qwen3.8-flash: {context_length: 262144}}` — i.e. exactly the shape of the user's `ryzen` provider (Qwen3.8, 262144 ctx). ~$0.20 of accidental OpenRouter spend + upstream 429s.
- Tier: **Verified**

### 1.8 #132648 — model switch pairing lost on agent rebuild at websocket reattach — OPEN (per snippet)
- URL: https://github.com/NousResearch/hermes-agent/issues/132648
- Claim: Sibling of #47828 (fixed in #60985, which covers the in-place switch_model path); the switch itself resolves correctly but the pairing is lost on agent rebuild at websocket reattach. hermes-agent 3294d683 (2026-09-30), TUI.
- Verbatim: "This is a sibling of #47828 (fixed in #60985, which covers the in-place switch_model path) — the switch itself resolves correctly; the pairing is lost on the agent rebuild at websocket reattach, a path #60985 does not touch."
- Tier: **Plausible**

### 1.9 #126707 — [Feature] Error-toast "Switch model" should open the in-chat picker (Desktop) — OPEN (per snippet)
- URL: https://github.com/NousResearch/hermes-agent/issues/126707
- Claim: The "Switch model" action in the error toast routes to the global provider settings page instead of the in-chat model picker, so the fix for the immediate problem is not reachable where the problem occurred.
- Verbatim: "The 'Switch model' action in the error toast routes the user away to the global provider settings page (/settings/providers) instead of opening the in-chat model picker, so the fix for the immediate problem is not reachable where the problem..."
- Tier: **Plausible**

### 1.10 #48173 / #48248 — stale Model/Provider in persisted system prompt; billing_provider write-once — referenced, state not confirmed
- URLs: https://github.com/NousResearch/hermes-agent/issues/48173 · https://github.com/NousResearch/hermes-agent/issues/48248
- Claim: #48173 "Mid-session model switch leaves stale Model/Provider in persisted system prompt"; #48248 "[Bug]: `billing_provider` / `billing_base_url` are write-once via COALESCE — mid-session `/model` switch leaves stale provider in session DB and misleads dashboard model cards". These are the correctness bugs that motivated v0.18.0's deliberate `system_prompt = NULL` on switch (which is what causes the #126068 cache break).
- Tier: **Plausible**

### 1.11 #100336 — withdrawn by reporter
- URL: https://github.com/NousResearch/hermes-agent/issues/100336
- Claim: A model-switch/caching-related issue withdrawn by its reporter; cited in PR #128757 as evidence the cold-prefill-on-switch is considered inherent, not fixable.
- Tier: **Plausible**

---

## 2. Per-session / per-chat model selection (esp. desktop)

### 2.1 Desktop: per-chat model switching exists; Settings→Models only changes default for new chats
- Source: website/docs/user-guide/desktop.md (in-repo docs; corroborating, docs lane owns)
- Verbatim (search snippet): "Switch provider — for provider, endpoint, auth, and billing failures, opens the composer's live model menu so you can move this chat to another provider/model right away (Settings → Models only changes the default for new chats)."
- Claim: The desktop composer has a live per-chat model menu; per-chat selection is a supported desktop surface.
- Tier: **Plausible** (docs snippet; not in tracker)

### 2.2 Third-party clients with per-session model pickers (community)
- aritsulynn/hermes-chat (web + Android client for the gateway): "Chat — token-by-token streaming ... per-session model picker; slash commands ... Agent configuration — Models: the resolved main model with context/capability badges, plus every auxiliary task slot." — https://github.com/aritsulynn/hermes-chat — Tier: **Plausible**
- ahrazzle/hermes-group-model-sync: "Per-member model & reasoning selector for Bot Mode group chats in Hermes Desktop + agent-wide model sync" — "Hermes Desktop switches a model per session, and the Dashboard switches one profile's default. Nothing shows what each agent in a group chat is running, nothing pushes one configuration to every session of an agent..." — https://github.com/ahrazzle/hermes-group-model-sync — Tier: **Plausible**

### 2.3 #67347 — [Feature]: Guided picker for Subagent Model + Provider in Advanced Settings (Desktop + Dashboard) — state not confirmed (snippet)
- URL: https://github.com/NousResearch/hermes-agent/issues/67347
- Claim: For users who want a different model for subagents, the config surface is trial-and-error; requests a guided picker in Desktop + Dashboard.
- Verbatim: "For users who want a different model for subagents (the common case — a cheaper or faster model than the main agent), this is a trial-and-error configuration surface."
- Tier: **Plausible**

---

## 3. delegation.model / delegation.provider: bugs, limitations, per-spawn override

### 3.1 Current state (v0.22.2): config-level pin works; NO per-task model parameter
- Source: official docs, features/delegation "Model Override" + "Cost strategy: frontier planner, inexpensive workers" (read in full from hermes-agent.nousresearch.com)
- Verbatim: "You can configure a different model for subagents via `config.yaml` — useful for delegating simple tasks to cheaper/faster models: `delegation: model: "google/gemini-flash-2.0"  # Cheaper model for subagents / provider: "openrouter"  # Optional: route subagents to a different provider`. If omitted, subagents use the same model as the parent."
- Verbatim (decisive limitation): "Note that the pin is global: `delegate_task` has no per-task model parameter, so every child in a batch runs on the configured delegation model. For quality-sensitive subtasks that need a stronger model, either leave `delegation.model` unset for that session or hand the task to the [kanban board](.../features/kanban#per-task-model-override), which does support a per-task model override."
- Verbatim (the sanctioned cost pattern — directly matches the user's goal): "Pinning `delegation.model` to an inexpensive model while your main session stays on a frontier model keeps the planning quality where it matters and cuts spend where the volume is: `model: default: "your-frontier-model"  # parent (planner) stays on the frontier model / delegation: model: "your-inexpensive-model"  # all delegate_task children run on this`"
- Resolution order (docs): `delegation.base_url` (direct endpoint) > `delegation.provider` (full credential bundle) > inherit parent; `delegation.model` applies in all cases; empty = inherit parent model. `delegation.request_overrides` honored on all branches.
- Tier: **Verified**

### 3.2 #11999 — delegate_task ignores subagent model config — always inherits parent model — CLOSED (completed, Apr 30 2026, P1)
- URL: https://github.com/NousResearch/hermes-agent/issues/11999
- Claim: On v0.10.0, `delegation.model`/`delegation.provider` were ignored; subagents always ran on the parent model, persisting across /reset and config reloads.
- Verbatim: "The delegation model config is ignored. Subagents always run on the parent model regardless of config. This persists across `/reset` commands and config reloads."
- Fix: "Fix landed in 9423fda (`feat: configurable subagent provider:model with full credential resolution`, 2026-03-11) which added `_resolve_delegation_credentials()` and the `override_provider/base_url/api_key/api_mode` plumbing through `_build_child_agent`." Verified fixed on v0.11.x by reporter. Root cause per triage (PR #12105): "in delegate_tool.py always takes CLI_CONFIG branch because default keys make dict truthy."
- Workaround noted: "Spawning a subagent profile via terminal (`iris chat -q "..."`) correctly uses the configured model."
- Tier: **Verified**

### 3.3 #10653 — [Bug]: delegation config doesn't work (delegation.provider ignored) — CLOSED (completed, May 4 2026, fixed in commit 8308077)
- URL: https://github.com/NousResearch/hermes-agent/issues/10653
- Claim: On v0.9.0, subagents used the parent's provider + delegation.model; delegation.provider had no effect (verified via provider billing dashboards).
- Verbatim: "when execute tasks with parallel sub agents,sub agents use the model.provider and delegation.model(if configed) to do tasks"
- Fix: commit 8308077 "fix(delegation): honor provider override for subagents".
- Tier: **Verified**

### 3.4 Per-task (per-spawn) model override: requested ~10 times, implemented in multiple UNMERGED PRs, maintainer said "We do not want this" for the profile/extension shapes
- #10995 — feat: delegate_task should support per-task model selection — CLOSED (completed, Jul 5 2026). teknium1 (Collaborator): **"We do not want this"**. URL: https://github.com/NousResearch/hermes-agent/issues/10995 — Tier: **Verified**
  - Verbatim (problem): "When the parent runs on an expensive model (e.g. claude-opus), all subagents inherit that model even for trivial tasks like writing template files or running searches. This wastes tokens/cost and causes timeouts on tasks that a smaller model could handle faster."
  - Verbatim (workaround that does NOT work natively): "The `acp_args` workaround (`['--acp', '--stdio', '--model', 'claude-sonnet-4']`) only works for ACP subprocess children and does not affect native Hermes subagents."
- #46880 — Feature: Dual Sub-Agent Model Configuration (per task-type) — CLOSED (completed, Jul 5 2026; teknium1: "We do not want this"; duplicate of #9459). URL: https://github.com/NousResearch/hermes-agent/issues/46880 — Tier: **Verified**
  - Verbatim (contradicts current docs — claims the per-task param shipped): "The per-task `model` override (from Feature: Per-sub-agent provider/model selection in delegate_task #24263) works but requires remembering to set it every time — a config-level default per task type is more reliable" and "Use the `model` parameter per delegate_task call (merged in #24263)".
  - Note: the "merged in #24263" claim is contradicted by (a) current official docs ("delegate_task has no per-task model parameter") and (b) #111545's Oct 10 2026 comment (below). Treat "shipped" as false for v0.22.2.
- #24263 — Feature: Per-sub-agent provider/model selection in delegate_task — CLOSED (completed, May 12 2026, labelled duplicate). URL: https://github.com/NousResearch/hermes-agent/issues/24263 — Tier: **Verified**
  - Verbatim (alt-glitch): "Duplicate of #14974 — same feature request for per-task provider/model overrides in delegate_task. Implementing PR already exists at #17756."
- #14974 — [Feature]: delegation-per-task-endpoint-overrides — CLOSED (completed, May 30 2026). URL: https://github.com/NousResearch/hermes-agent/issues/14974 — Tier: **Verified**
  - Verbatim (alt-glitch): "Related to open PR #12794 which already adds model/provider overrides to delegate_task. The base_url/api_key additions requested here extend that same feature surface."
- #111545 — Feature request: per-role delegation profiles (delegation.profiles.<role>.model) — OPEN (P3). URL: https://github.com/NousResearch/hermes-agent/issues/111545 — Tier: **Verified**
  - Verbatim (problem): "`delegate_task` children all resolve credentials from the top-level `delegation.model` / `delegation.provider` only. There is no way to route different kinds of subagents to different models... Today the only workaround is flipping `delegation.model` between dispatches, which is racy with concurrent children and easy to forget to revert."
  - Verbatim (kesudh, Oct 10 2026 — the most recent authoritative status): "Per-task _model_ selection is already implemented, unmerged, in three places: `7ba55aa7935` on branch `kilocode-port/per-task-delegation-model` (by teknium1) — the `delegation.allow_model_selection` variant, routed through the existing `model_switch` resolution with the schema field built in `_build_dynamic_schema_overrides()` so prompt caching stays valid. **PR #85228** 'feat(delegation): allow safe per-task model selection' (OldKrab, open since Aug 13, +622/-13) — same opt-in shape, with an AI review flagging an `api_mode` family-compatibility bug and no human review yet. Plus **PR #129546**, **PR #112741**"
  - Triage note: "this sits in the per-task delegate model-override cluster (#107937, #97653, #96014, #94887, #88891). The named `delegation.profiles.<role>` approach is a distinct shape (config-side presets vs per-call `model`/`provider` params), so tracking it separately; whichever lands first should probably subsume the other."
  - Guardrail detail: "A profile pinning a provider must be able to declare `fallback_providers`, or it silently becomes fallback-less"; "A profile with `base_url` but no `api_key` raises `ValueError` rather than sending the parent's key to a custom endpoint".
- Duplicate/cluster issues (all per-task model override requests, states not individually confirmed): #3719 (closed per #10995 reference), #6306, #15789, #18591, #34764, #41814, #61622, #9459 (named subagent profiles; #46880 dup of it).
  - #18591 verbatim: "Currently the only workaround is to change delegation.model globally before each delegation, which is impractical." — https://github.com/NousResearch/hermes-agent/issues/18591 — Tier: **Plausible**
  - #9459 verbatim: "The current delegate_task model is useful, but it still feels like 'spawn an anonymous child copy of the parent with a different task'. What would make Hermes much more powerful is to make subagents first-class, named, reusable, declarative units" — https://github.com/NousResearch/hermes-agent/issues/9459 — Tier: **Plausible**
- Competing PRs (all unmerged as of Oct 2026 per 3.1 docs + 3.4 #111545):
  - PR #17756 — "feat(delegate): add per-call model/provider/base_url overrides" (mddragon18, Apr 30 2026). Adds `model`, `provider`, `base_url` to `delegate_task` top-level + per-task; precedence "per-task > top-level per-call > delegation config > parent inherit"; `api_key` excluded from schema ("to prevent LLM secret leakage"). State: not confirmed merged; current docs say the param does not exist → treat as unmerged. URL: https://github.com/NousResearch/hermes-agent/pull/17756 — Tier: **Plausible**
  - PR #12794 — "feat(delegate_task): per-subagent model/provider overrides + model observability plugin" (thesunofdog, Apr 20 2026). Also adds a `model_observability` plugin that "verifies that requested models actually reach the subagent. Surfaces ground-truth routing data (requested vs actual model, mismatch warnings...)". Unmerged per docs. URL: https://github.com/NousResearch/hermes-agent/pull/12794 — Tier: **Plausible**
  - PR #7586 — "Feat/delegate model parameter" (Labhund) — cited by #7929 as "foundation: per-task model parameter on delegate_task". State unconfirmed. URL: https://github.com/NousResearch/hermes-agent/pull/7586 — Tier: **Plausible**
  - PR #85228 — "feat(delegation): allow safe per-task model selection" (OldKrab, open since Aug 13 2026, +622/-13; AI review flagged an `api_mode` family-compatibility bug; no human review). URL: https://github.com/NousResearch/hermes-agent/pull/85228 — Tier: **Plausible**
  - PR #112741 — "feat(delegate): per-task model, provider, reasoning_effort and toolsets"; PR #129546 — "feat(delegate): per-task model, provider and reasoning_effort". Both open per #111545. URLs: https://github.com/NousResearch/hermes-agent/pull/112741 · https://github.com/NousResearch/hermes-agent/pull/129546 — Tier: **Plausible**
  - teknium1's own unmerged branch: `kilocode-port/per-task-delegation-model` (commit 7ba55aa7935) — `delegation.allow_model_selection` opt-in variant, schema built in `_build_dynamic_schema_overrides()` "so prompt caching stays valid". — Tier: **Plausible** (via #111545 comment)

### 3.5 Sanctioned per-task model override that DOES exist: kanban board
- Source: official docs (delegation page, see 3.1 quote) — "hand the task to the kanban board, which does support a per-task model override" (link: features/kanban#per-task-model-override).
- Claim: The only shipped per-task model override surface is the kanban board, not delegate_task.
- Tier: **Verified** (docs quote read in full)

---

## 4. Prompt-caching invalidation on model switch (and adjacent cache-breakers)

### 4.1 #126068 + PR #128757 — see 1.1/1.2 (the core model-switch cache break; open, accepted as inherent)
- Tier: **Verified**

### 4.2 Docs corroboration (configuring-models.md, in-repo; docs lane owns)
- Verbatim (search snippet): "An explicit /model switch also rewrites the Model: (and Provider:) line inside the system prompt so the agent knows what it is running on. That is a deliberate, one-time change: the first request after the switch misses the cached prefix once..."
- Verbatim (search snippet, on --once): "A one-turn switch breaks the provider's prompt-cache prefix twice (switching out and back). In a long session on a cached-prefix provider (Anthropic, OpenAI), the next turn re-pays full input cost — --once wins for short sessions or cheap→expensive escalation, but a quick side question inside a long expensive session can cost more than it saves."
- Tier: **Plausible** (snippet)

### 4.3 #8294 — [Bug]: Prompt caching not enabled for custom Anthropic-compatible providers (api_mode: anthropic_messages) — CLOSED (fixed; commit "fix(anthropic): complete third-party Anthropic-compatible provider su..." references it)
- URL: https://github.com/NousResearch/hermes-agent/issues/8294
- Claim: Prompt caching was gated on provider NAME, not capability: `is_native_anthropic = self.api_mode == "anthropic_messages" and self.provider == "anthropic"` — so any custom provider (ZenMux, corporate proxies, and by extension CLIProxyAPI-style relays) using `api_mode: anthropic_messages` got zero caching even for Claude models.
- Verbatim: "This means any named custom provider using `api_mode: anthropic_messages` is excluded from prompt caching unless the provider name is literally `anthropic`."
- Verbatim (measured impact, corporate Anthropic proxy, v0.9.0): "47 API calls, 2.9M cumulative input tokens, 11K output tokens · `cache_read_tokens: 0`, `cache_write_tokens: 0` — caching completely disabled · ~99.7% of input tokens were cacheable prefix ... With caching enabled: estimated ~¥10 CNY — **90% reduction**"
- Verbatim (one-line fix verified by commenter): `is_native_anthropic = self.api_mode == "anthropic_messages"`
- Relevance: the user's `cpa` provider is a custom provider; if it serves Claude via `api_mode: anthropic_messages`, caching behavior depends on whether this fix is in v0.22.2 (issue closed → likely yes, but verify in the user's actual cache stats).
- Tier: **Verified**

### 4.4 #104414 — [Bug]: Surface switch (desktop↔TUI) makes stored system prompt 'stale' → full rebuild → 100% prompt-cache miss (200K+) — CLOSED (P0; PR #105844 closed)
- URL: https://github.com/NousResearch/hermes-agent/issues/104414
- Claim: Switching a live session between surfaces (desktop ↔ TUI) or resuming after a dashboard restart on a different surface triggers a full system-prompt rebuild → 100% cache miss, because `_stored_prompt_matches_runtime` compares the volatile `Platform:`/CWD lines byte-for-byte.
- Verbatim: "Switching a live session between surfaces (desktop ↔ TUI), or resuming it after a dashboard restart on a different surface, triggers a **full system-prompt rebuild**, which turns every subsequent request into a **100% prompt-cache miss** (`cached_tokens ≈ 0-1.5K` on a 220K-prompt session; ~218-366K tokens re-prefilled per occurrence)."
- Telemetry: "09:21:28 (pre-restart, last warm call) in=240287 cache=240000/240287 (100%) → 09:24:27 (first call after dashboard restart + TUI resume) in=219861 cache=1536/219861 (1%) ← 100% miss, 218K re-prefill"
- Tier: **Verified**

### 4.5 #13631 — [Bug]: Honcho auto-injected context rebuilds cached system prompt every N turns, invalidating KV cache on every prefix-caching backend — state not confirmed (snippet)
- URL: https://github.com/NousResearch/hermes-agent/issues/13631
- Verbatim: "Every `contextCadence` / `dialecticCadence` tick rewrites Layer 3 of the cached system prompt. Observed on Gemma 4 31B 8-bit (MLX) served via a `vllm-mlx` fork with PagedAttention prefix caching: ... With `contextCadence: 1` every user turn is a full prefill."
- Tier: **Plausible**

### 4.6 #128817 — [Bug]: Follow-up turns re-prefill because tool schemas change between turns — state not confirmed (snippet)
- URL: https://github.com/NousResearch/hermes-agent/issues/128817
- Verbatim: "Hermes rebuilds the tool list between turns in a way that changes bytes ahead of the conversation, so the cache misses."
- Tier: **Plausible**

### 4.7 #27339 — [Bug]: Prompt Cache / KV Cache Invalidation on Follow-Up Messages Due to Dynamic Tool Shuffling — state not confirmed (snippet)
- URL: https://github.com/NousResearch/hermes-agent/issues/27339
- Verbatim: "The system is then penalized with a full re-prefill of over 37,000 tokens entirely due to a structural mismatch in the tool definitions array." (llama.cpp server, Qwen 3.6)
- Tier: **Plausible**

### 4.8 #124170 — the switch note restated after compaction (related to #127879) — state not confirmed
- URL: https://github.com/NousResearch/hermes-agent/issues/124170 — Tier: **Plausible**

---

## 5. Context-length mismatch when switching models

### 5.1 #130318 — [Bug]: `hermes model` keeps the previous model's `model.context_length` pin, so the new model inherits its window — OPEN (P2; fix PR #130319 open)
- URL: https://github.com/NousResearch/hermes-agent/issues/130318
- Claim: `/model --global` and the dashboard drop the pin on route change, but the `hermes model`/`hermes setup` writers never do. After an Azure gpt-4.1 (1,047,576-token window) setup, switching to a ~40K model keeps the 1M window.
- Verbatim: "`model.context_length` applies to the configured default route, so a pin carried over to another model becomes that model's context window. ... after an Azure `gpt-4.1` (1,047,576-token window) setup, switching to a ~40K model keeps the 1M window: compression never fires before the provider rejects the request."
- Pre-flight summary of the whole bug family: "fix(agent): clear stale config context_length on model switch #24724 (merged) fixed only the in-memory value on live /model; fix: clear stale _config_context_length when switching providers #24079 / fix: sync context_length on model switch and show updated limit #17269 closed; #116467 closed via #117631; fix: clear stale global context length on model switch #26900 (@hubdev4, open, stranded on moved files) is the salvage candidate."
- Tier: **Verified**

### 5.2 #116467 — [Bug] Desktop/CLI model changes can silently discard the effective context ceiling — CLOSED (P2; via PR #117631 "fix(context): live model/provider switches and Desktop config round-trips keep the configured context ceiling (#116467, salvage #116661)")
- URL: https://github.com/NousResearch/hermes-agent/issues/116467
- Verbatim: "Hermes can silently stop honoring a configured context ceiling after a provider/model is added or selected through `hermes model` while Hermes Desktop remains open, and after some Desktop or live `/model` configuration round-trips. ... The result can be a 256K fallback or a catalog value around 1M even though the user intended a lower limit."
- Tier: **Verified**

### 5.3 #24493 — [Feature]: Per-model overrides for `model.context_length` and `provider_routing` — OPEN (P2)
- URL: https://github.com/NousResearch/hermes-agent/issues/24493
- Claim: `model.context_length` and `provider_routing.{only,order,ignore,sort}` are profile-global but should vary per active model; the flat pin "applies to whatever model is active. Switch models and the override now applies to the wrong model."
- Verbatim: "So `/model` switching becomes an error-prone manual coordination, and sporadic tool-call failures appear when the harness's check runs with the wrong model's expectations."
- Covers cluster: #24140 (P1 "context window below minimum 64K"), #24000 (P2 nous fallback to 32K), #24072 (P2 context_length persists across /model switches).
- Tier: **Verified**

### 5.4 #24072 — `model.context_length` persists across `/model` provider switches — state not confirmed (snippet)
- URL: https://github.com/NousResearch/hermes-agent/issues/24072
- Verbatim: "After switching to a provider with context_length: 8192, the context window should reflect 8192. The context window remains at 1,000,000 — the stale _config_context_length from startup shadows the new provider's value."
- Tier: **Plausible**

### 5.5 #15779 — Bug: /model switch to named custom provider ignores custom_providers model context_length — CLOSED (P2; PR #15844)
- URL: https://github.com/NousResearch/hermes-agent/issues/15779
- Claim: Mid-session `/model` switch to a named custom provider ignored `custom_providers[].models.<model>.context_length` and fell back to 128,000, while the startup path honored it (two different resolution paths).
- Verbatim: "When a running gateway session switches to a **named custom provider** via `/model`, Hermes ignores the per-model `context_length` configured under `custom_providers[].models.<model>.context_length` and falls back to the default `128,000` token window."
- Relevance: same class as the user's cpa/ryzen custom providers — per-model context_length under custom_providers is the supported way to declare e.g. 262144 for Qwen3.8.
- Tier: **Verified**

### 5.6 #41944 — [Desktop] Model picker clears model.context_length when switching models in a fresh session — state not confirmed (snippet)
- URL: https://github.com/NousResearch/hermes-agent/issues/41944
- Verbatim: "Any model that depends on a specific context_length (> 64000 for Hermes' minimum check) is now unreachable · Switching models should preserve the existing model.context_length value"
- Tier: **Plausible**

### 5.7 #40979 — model.context_length global config override is not re-read after /model switch — state not confirmed (snippet)
- URL: https://github.com/NousResearch/hermes-agent/issues/40979
- Verbatim: "Step 0 (config_context_length): Always None after switch, so the global model.context_length is lost. Step 0b (custom_providers per-model): Works correctly — the config file is re-read and custom_providers[i].models.<model>.context_length is honored."
- Tier: **Plausible**

### 5.8 #24140 — All models rejected with "context window below minimum 64,000 tokens" — state not confirmed (snippet)
- URL: https://github.com/NousResearch/hermes-agent/issues/24140
- Verbatim: "Model MiniMax-M2.7 has a context window of 32,768 tokens, which is below the minimum 64,000 required by Hermes Agent. Choose a model with at least 64K context, or set model.context_length in config.yaml to override."
- Relevance: Hermes enforces a 64K minimum context window; relevant when considering small local models.
- Tier: **Plausible**

### 5.9 #15962 — Feature: auto-scale context-dependent config from active model context — state not confirmed (snippet)
- URL: https://github.com/NousResearch/hermes-agent/issues/15962
- Verbatim: "context-dependent configuration should be automatically derived from the resolved model context window and kept in sync. ... Resolve the active model context window during setup, model selection/switching, and session startup."
- Tier: **Plausible**

### 5.10 #10157 — Feature: Warn on context_length mismatch after /model --global switch — state not confirmed (snippet)
- URL: https://github.com/NousResearch/hermes-agent/issues/10157
- Verbatim: "In the --global persistence block (CLI _handle_model_switch, _apply_model_switch_result, and gateway _handle_model_command): Resolve the new model's actual context_length from ModelSwitchResult.model_info.context_window or get_model_context_length() (without config override)"
- Tier: **Plausible**

### 5.11 #24268 — Wrong context length for kimi-k2.6 family: OpenRouter returns 32K, overrides correct hardcoded 256K default — referenced from #24493
- URL: https://github.com/NousResearch/hermes-agent/issues/24268 — Tier: **Plausible**

### 5.12 Direct 262k-local-vs-200k-Claude mismatch reports: NOT FOUND
- No issue specifically reports "switching from a 262144-ctx local model to a 200K Claude model breaks/under-reports the window" as a distinct bug. The general mechanism (stale/flat context_length pins across switches) is covered by 5.1–5.11. The 262144 figure appears only in #132117's repro config (local qwen3.8-flash).
- Tier: **Verified** (negative finding from searches)

---

## 6. Model-routing / model-escalation features in the tracker

### 6.1 #123388 — [Feature]: Pluggable per-turn model router (smart routing) with a classifier-agnostic controller — OPEN (P3, needs-decision)
- URL: https://github.com/NousResearch/hermes-agent/issues/123388
- Claim: No supported way to pick the model per turn. `smart_model_routing` was REMOVED (PR #12732; leftover config key tracked in #98835). `pre_llm_call` hook can only add context; `llm_request` middleware can rewrite `model` but not client/base_url/api_mode (single endpoint only).
- Verbatim: "Today there is no supported way to do this. `smart_model_routing` was removed in #12732 (its leftover config key is tracked in #98835), the `pre_llm_call` hook can only add context, and the `llm_request` middleware can rewrite `model` but not the client / base_url / api_mode, so it can only switch within a single endpoint."
- Verbatim (switching cost acknowledged): "Each model change rebuilds the agent and invalidates the prompt cache, and a smaller-window target triggers pre-request compression. An optional hysteresis setting (e.g. require the confidence margin to exceed X before leaving the current route) would avoid flapping between two routes on alternating turns."
- Verbatim (limitation of the router PR): "`anthropic_messages` targets are rejected. `_target_route` only accepts `chat_completions` / `responses` / `codex_responses`, so a custom provider with `transport: anthropic_messages` can't be a route target."
- Convergence points per comments: PR #118645 (implementation) and PR #98703 ("feat: add safe pre-agent turn routing middleware — generic pre-agent `turn_route` plugin surface; plugin selects public model/provider identity, Hermes retains credential/client/runtime ownership"). Related: #106740 (task-based routing + failover), #114212 (time-based switching), #83894 (per-input-type routing), PR #133753 (plugin-catalog kfchow-llm-value-router; "per-turn model routing resolved from the KFChow value leaderboard" — a P1 was raised against it re: route persistence across tool follow-ups).
- Tier: **Verified**

### 6.2 PR #118645 — feat(router): add fail-closed per-turn model routing — OPEN (needs-decision)
- URL: https://github.com/NousResearch/hermes-agent/pull/118645
- Verbatim: "Add opt-in, fail-closed per-turn model routing through a local Laya controller. Keep provider/model/credentials/runtime mapping in Hermes allowlisted policy; Laya returns only semantic route labels. Cover CLI, Gateway, Desktop, background and secondary paths with policy-bound fallbacks, loopback/no-proxy/no-redirect transport, redaction, and turn-local restore."
- Safety: "Invalid controller output, low confidence, controller failures, and unsupported targets resolve to the configured allowlisted fallback route." 40 targeted tests passed.
- Tier: **Verified**

### 6.3 PR #98703 — feat: add safe pre-agent turn routing middleware — OPEN (per #123388 comment)
- URL: https://github.com/NousResearch/hermes-agent/pull/98703
- Verbatim (from #123388 comment): "generic pre-agent `turn_route` plugin surface; plugin selects public model/provider identity, Hermes retains credential/client/runtime ownership."
- Tier: **Plausible**

### 6.4 #7929 — feat: delegation model tiers + list_models tool — CLOSED (not planned, Jul 12 2026, sweeper:not-planned)
- URL: https://github.com/NousResearch/hermes-agent/issues/7929
- Claim: Named tiers (`delegation.model_tiers: small/medium/large`) + a `list_models` tool so the agent can route subagents by tier without knowing deployment-specific model ids.
- Verbatim (why heuristics failed in production): "We deployed and tested `smart_model_routing` (message-length heuristic) in production and disabled it (see #7905). Short messages like 'yes' or 'go ahead' can trigger the most complex operations — message length is a terrible proxy for task complexity. **Model-directed delegation is fundamentally better**: the model has full context, knows the task complexity, and chooses the right model for each subagent."
- Tier: **Verified**

### 6.5 #20249 — Model Presets: per-turn expert-on-demand model escalation — CLOSED (not planned, sweeper:not-planned)
- URL: https://github.com/NousResearch/hermes-agent/issues/20249
- Claim: `model_presets` config + `/expert` one-shot escalation to a strong model for a single turn, then snap back; plus implicit complexity auto-detection.
- Verbatim (problem framing): "If you're on a cheap/fast model ... and a turn comes up that genuinely needs Opus-level reasoning ... you have two bad options: 1. **/model** to a bigger model, take the hit on all subsequent turns (waste of tokens and money), then /model back manually. 2. Power through on the weak model, get a mediocre answer, then re-prompt with /retry."
- Verbatim (rejected alternatives in the issue): "delegate_task to the big model: That spawns a subagent with no conversation history. The point of /expert is to bring the full context to the powerful model. Just run Opus all the time: Expensive and slow for the 90% of turns that don't need it. Router middleware: Too heavy for v1."
- Tier: **Verified**

### 6.6 #125110 — [Feature]: Model autopilot — jointly route model and reasoning effort with quota/cache awareness — OPEN (P3, needs-decision, innovation)
- URL: https://github.com/NousResearch/hermes-agent/issues/125110
- Verbatim: "A useful 'model autopilot' should make **one joint decision per user turn**: which allowlisted model should handle the turn; what reasoning effort that model should use; **whether switching away from the current model is worth losing its warm prompt cache**."
- References #123388, #108770, #53306 (provider quota visibility), PR #89678.
- Tier: **Verified**

### 6.7 PR #89678 — feat: add cost-aware model routing and one-shot override — OPEN (prototype; awaiting maintainer approval of fork-PR CI)
- URL: https://github.com/NousResearch/hermes-agent/pull/89678
- Verbatim: "Adds automatic initial model selection that defaults to `gpt-5.4-mini` and can escalate hard/complex technical requests to `gpt-5.4`. Adds session-local, in-memory one-shot overrides: `/model strong`, `/model gpt-5.4`, and `/model auto`. Preserves explicit runtime model override precedence and clears a pending one-shot override only after a successful final response."
- Known limitations (author): "Model IDs are currently explicit ... rather than resolved through configurable model roles or a provider catalog. Current complexity signals are English-oriented ... Keyword-only escalation needs stricter intent matching to reduce false positives."
- Tier: **Verified**

### 6.8 #108770 — Feature Request: Automatic Dynamic Reasoning Effort Switching per Skill/Task — OPEN (P3)
- URL: https://github.com/NousResearch/hermes-agent/issues/108770
- Verbatim: "Add support for dynamic reasoning_effort (thinking mode) adjustment based on the active skill or task context. When executing heavy skills (such as academic research or thesis building), automatically shift reasoning effort to high for deep analysis, and revert upon completion."
- Comment: "Passing — large architectural scope touching core agent runtime and skills system. This is the kind of feature that benefits from maintainer design discussion first."
- Tier: **Verified**

### 6.9 Other routing/escalation feature requests (snippet-level, states not individually confirmed)
- #15176 — "[Feature]: Add fallback routing from local open-source models to closed-source models after repeated failures" — "Hermes Agent could start with a local/open-source model as the primary model, and automatically switch to a stronger cloud model after repeated failures or lack of progress." — https://github.com/NousResearch/hermes-agent/issues/15176 — Tier: **Plausible**
- #61371 — "[Feature] Agent-level model router: auto-route between local and cloud models" — proposed config: "model_router: enabled: true / local: provider: ollama model: llama3.2-3b for_tasks: [read_only, shell_commands] / cloud: provider: nous model: anthropic/claude-sonnet-4.6 for_tasks: [debugging, code_review, log_analysis]" — https://github.com/NousResearch/hermes-agent/issues/61371 — Tier: **Plausible**
- #30652 — "Feature Request: Dynamic model routing based on task complexity" — "Hermes Agent currently locks each session to a single model via config.yaml. ... There's no built-in way to route tasks to different models based on complexity, cost, or capability requirements." — https://github.com/NousResearch/hermes-agent/issues/30652 — Tier: **Plausible**
- #38954 — "[Feature]: Automatic Role-Based Model Routing" — "Hermes Agent currently requires manual model switching (/model) or subagent delegation to use different models for different tasks." (P3 label visible in snippet) — https://github.com/NousResearch/hermes-agent/issues/38954 — Tier: **Plausible**
- #157 — "Feature Request: User-Configurable Multi-Model Routing with Capability Categories and Evaluation Feedback" — "Enable end users to configure multiple LLMs across defined capability categories (e.g., speed, intelligence, uncensored, low-cost, reasoning-heavy), and allow tools to request models based on..." — https://github.com/NousResearch/hermes-agent/issues/157 — Tier: **Plausible**
- #344 — "Feature: Multi-Agent Architecture — Orchestration, Cooperation, Specialized Roles & Resilient Workflows" — "A cheap model (Sonnet-class) classifies tasks into complexity × type, routing to different agent team sizes. Uncertain cases escalate to an expensive..." — https://github.com/NousResearch/hermes-agent/issues/344 — Tier: **Plausible**
- #106740 (task-based routing + failover), #114212 (time-based switching), #83894 (per-input-type routing) — referenced from #123388 — Tier: **Plausible**
- #53306 — "feat(cli): show provider quota and rate-limit in status bar for all providers" — referenced from #125110 — Tier: **Plausible**
- #133753 — PR "Add plugin-catalog/kfchow-llm-value-router.yaml — per-turn model routing resolved from the KFChow value leaderboard" (P1 raised against it: route must persist for the whole turn incl. tool follow-ups) — https://github.com/NousResearch/hermes-agent/pull/133753 — Tier: **Plausible**
- #12732 — PR that REMOVED `smart_model_routing` — https://github.com/NousResearch/hermes-agent/pull/12732 — Tier: **Plausible**
- #98835 — leftover `smart_model_routing` config key tracking — https://github.com/NousResearch/hermes-agent/issues/98835 — Tier: **Plausible**
- #7905 — "is_local_endpoint misses Docker/Podman DNS names — stale timeout fires on local LLM proxies" (also where smart routing was disabled in production) — https://github.com/NousResearch/hermes-agent/issues/7905 — Tier: **Plausible**

### 6.10 Community routing workarounds (external repos, not in the tracker)
- superlowburn/hermes-advisor — "Advisor strategy for Hermes Agent: cheap executor, Opus advisor on hard turns, **no model switching (prompt cache stays warm)**. Optional Jev auto-escalation." — https://github.com/superlowburn/hermes-advisor — Tier: **Plausible**
- open-world-project/model-router — "Automatic cost-aware model routing for Hermes Agent. model-router classifies each turn, picks the cheapest tier that should work, and escalates only when the task needs more reasoning." — https://github.com/open-world-project/model-router — Tier: **Plausible**
- itsgurmailsingh-png/hermes-model-router — "Complexity-based model routing for Hermes Agent and Claude Code. Routes ALL LLM calls to the cheapest model tier that can handle the task — saving 30–45% on Claude API costs and significant latency on local Ollama calls." — https://github.com/itsgurmailsingh-png/hermes-model-router — Tier: **Plausible**
- kerpopule/hermes-jev-skills — "Jev-powered model routing ... `/jev routing on` switch models per turn ... The hermes-jev plugin uses only public plugin seams (pre_llm_call, transform_tool_result, the llm_request middleware, tools, a slash command), so hermes update does not break it and nothing in Hermes core is patched." — https://github.com/kerpopule/hermes-jev-skills — Tier: **Plausible**
- Lei-k/hermes-agent issue #25 — "perf(delegation): per-task model tier routing for delegate_task" (fork; proposes `delegation.tiers: {light, standard, heavy}`; suggests salvaging PR #49690 "feat(delegate): unbounded task queue + per-task model routing") — https://github.com/Lei-k/hermes-agent/issues/25 — Tier: **Plausible**
- PR #49690 — "feat(delegate): unbounded task queue + per-task model routing" (referenced; state unconfirmed) — https://github.com/NousResearch/hermes-agent/pull/49690 — Tier: **Plausible**

---

## 7. Cross-cutting observations for the user's scenario

1. **Mid-session model switching is supported but expensive by design**: every switch = system-prompt rebuild (identity + model-gated guidance bytes) = full cold prefill of the whole history (#126068, 220.7s on 309K vs 8–25s warm; PR #128757 confirms maintainers treat this as inherent). A provider switch additionally moves to a different cache store entirely. This directly validates the user's instinct to NOT switch the main chat's model.
2. **The sanctioned "expensive only where needed" pattern in the tracker/docs**: keep the frontier model in the main session; pin `delegation.model`/`delegation.provider` to a cheap model for all subagents ("frontier planner, inexpensive workers" — docs); for the rare quality-sensitive subtask that needs the strong model, leave `delegation.model` unset or use the **kanban board's per-task model override** (the only shipped per-task override surface).
3. **Per-task model override in delegate_task is the most-requested missing feature** (~10 issues, 6+ unmerged PRs incl. a teknium1 branch), but maintainers closed the profile/extension shapes with "We do not want this" (Jul 5 2026) and current docs explicitly state the parameter does not exist.
4. **Custom-provider caching**: #8294 (closed/fixed) shows caching was once broken for ALL custom `anthropic_messages` providers (90% cost impact measured); the user's `cpa` provider should be checked for actual cache hits.
5. **Context-length pins are a known minefield across switches** (#130318 open, #116467 closed, #15779 closed, #24072, #41944, #40979): a `model.context_length` pin can follow the wrong model across switches; per-model `custom_providers[].models.<id>.context_length` is the supported per-model declaration and is honored on startup but had mid-session switch bugs (fixed per #15779).
6. **Bare-name `/model` switching with local providers is a billing hazard** (#132117 open): if the user's `ryzen` model ids collide with OpenRouter slug bare parts, a bare-name switch can silently bill OpenRouter. Use explicit `provider:model` syntax.
7. **`/model --once` (one-turn escalation) exists** and is documented as the cheap→expensive escalation tool, but has an open identity-note bug (#127879) and the docs warn a one-turn switch breaks the cache prefix twice.
8. **No built-in per-turn model router exists** (smart_model_routing was removed; PRs #118645/#98703 open, needs-decision). Community plugins (hermes-jev-skills, model-router repos, hermes-advisor) fill the gap via public plugin seams; hermes-advisor's "no model switching, prompt cache stays warm" advisor pattern is the closest community analog to the user's goal.

---

## 8. Searched, found nothing

Queries run (web_search, all returned results above):
1. `site:github.com NousResearch hermes-agent "switch model"` — found issues (none "nothing")
2. `site:github.com hermes-agent "per-session model" OR "model per session" OR "model per chat"` — found #123388 + community repos
3. `site:github.com hermes-agent "delegation.model" OR "delegation provider"` — found delegation cluster
4. `site:github.com hermes-agent "different model" subagent OR delegate` — found delegation cluster
5. `site:github.com hermes-agent prefill OR "prompt caching" model switch` — found #126068, #104414, #8294, #13631, #128817, #27339
6. `site:github.com hermes-agent "context length" model switch OR "context window"` — found #24072, #24493, #41944, #130318, #15962, #24140, #40979, #15779, #10157
7. `site:github.com hermes-agent opus haiku routing OR escalation OR "cheap model"` — found #20249, #15080, #344 + community repos
8. `site:github.com hermes-agent "model routing" OR "model escalation" OR "auto model"` — found #38954, #15176, #125110, #61371, #30652, #157
9. `NousResearch hermes-agent pull 17756 merged per-call model provider base_url delegate_task` — no direct state confirmation (PR state banner not extractable)
10. `hermes-agent delegate_task "model" parameter per-task override documentation config.yaml` — found docs + #41814/#18591/#34764
11. `"NousResearch/hermes-agent" "17756" OR "12794" delegate_task model override closed OR merged OR open` — **empty result (found nothing)**

Gaps / not found:
- **No issue specifically about a 262144-ctx local model vs 200K Claude context-length mismatch on switch** (only the general stale-pin bug family; 262144 appears only in #132117's repro).
- **No merged PR for per-task delegate_task model selection** (all unmerged per docs + #111545).
- **No GitHub Discussions content** (Discussions tab not indexed by search; only issues/PRs covered).
- **PR #17756 / #12794 exact state** (open vs closed-unmerged) not directly confirmable from extracted pages; inferred unmerged from current docs + #111545.
- **No tracker issue found that endorses switching the main chat model as a recommended cost pattern** — all cost guidance points to delegation/kanban/auxiliary slots instead.
