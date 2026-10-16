# Lane 5 — COST MECHANICS: why "do not switch the model of an existing chat"

Research date: 2026-10-16. Scope: prefill cost, prompt-caching invalidation, context-window differences, fresh-session-with-handover comparison.
Environment facts (verified locally, not vendor docs): Hermes default model `claude-opus-5-5` via CLIProxyAPI (OpenAI-compatible proxy in front of Anthropic); local `Qwen3.8-27B-FP8` with 262144-token ctx, free; config `prompt_caching.cache_ttl: 1h`; long project chats accumulate 50k–200k+ tokens.

---

## F1. Anthropic prompt caching mechanism
- **Claim:** Caching works on prompt *prefixes*: a `cache_control` breakpoint writes one cache entry = cryptographic hash of everything up to and including that block (up to 4 breakpoints). On the next request the system computes the prefix hash and walks back at most 20 blocks looking for a prior write. Cache writes happen ONLY at breakpoints. Automatic caching (top-level `cache_control`) places the breakpoint on the last cacheable block and advances it as the conversation grows.
- **Source:** https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching (vendor doc, read in full)
- **Quote:** "Cache writes happen only at your breakpoint. Marking a block with `cache_control` writes exactly one cache entry: a hash of the prefix ending at that block. … The lookback window is 20 blocks." / "Cache keys are generated using a cryptographic hash of the prompts up to the cache control point. This means only requests with identical prompts can access a specific cache."
- **Tier:** Verified

## F2. Cache price multipliers (per-model table)
- **Claim:** 5-minute cache writes cost 1.25x base input; 1-hour cache writes cost 2x base input; cache reads cost 0.1x base input (standard), 0.05x on Claude Opus 5.5 / Sonnet 5.5, 0.025x on Fable 5.1 / Mythos 5.1. Current per-MTok prices: **Opus 5.5** input $4 / output $20, 5m write $5, 1h write $8, read $0.20. **Sonnet 5.5** input $2 / output $10, 5m write $2.50, 1h write $4, read $0.10. **Haiku 5.5** input $0.10 (≤100k) / $0.50 (>100k), output $0.50 (≤100k) / $2.50 (>100k), 5m write $0.125 / $0.625, 1h write $0.20 / $1.00, read $0.01 / $0.05.
- **Source:** https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching (Pricing table) + https://www.anthropic.com/pricing (vendor docs, both read)
- **Quote:** "5-minute cache writes cost 25% more than base input tokens, 1-hour cache writes cost 2x base input tokens, and cache hits cost a fraction of the base input token price" / "Cache hits and refreshes on Claude Opus 5.5 and Claude Sonnet 5.5 are priced at 0.05x the base input price. All other models use the standard 0.1x multiplier."
- **Tier:** Verified

## F3. TTL options and refresh semantics
- **Claim:** Default TTL 5 minutes; optional 1-hour TTL via `"cache_control": {"type":"ephemeral","ttl":"1h"}`. "The cache is refreshed for no additional cost each time the cached content is used" — lifetime is measured from the start of the request that writes OR reads the entry, so an actively used 1h cache stays alive indefinitely at read prices. No manual cache clearing exists.
- **Source:** https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching (vendor doc, read)
- **Quote:** "By default, the cache has a 5-minute lifetime. The cache is refreshed for no additional cost each time the cached content is used." / "You can specify a 1-hour TTL at 2x the base input token price: { \"cache_control\": { \"type\": \"ephemeral\", \"ttl\": \"1h\" } }"
- **Tier:** Verified

## F4. Exactly what invalidates the cache (vendor table)
- **Claim:** Hierarchy is `tools` → `system` → `messages`; a change at a level invalidates that level and all later levels. **Tool definition change (names/descriptions/params) invalidates the ENTIRE cache** (tools+system+messages). Web-search/citations/speed toggles modify the system prompt → invalidate system+messages. `tool_choice`, images, thinking params, and `output_config.effort` always invalidate message blocks (tools/system model-specific). Any content change at or before a breakpoint changes the cumulative hash → no hit.
- **Source:** https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching, "What invalidates the cache" (vendor doc, read)
- **Quote:** "Modifying tool definitions (names, descriptions, parameters) invalidates the entire cache" / "Changes at each level invalidate that level and all subsequent levels." / "Because the hash is cumulative, covering everything up to and including the breakpoint, changing any block at or before the breakpoint produces a different hash on the next request."
- **Tier:** Verified

## F5. Model change ⇒ total cache loss (mechanism, not explicitly documented)
- **Claim:** Anthropic's invalidation table covers request-level changes only; it does NOT list "model change" as an invalidator. However, the cache key is a hash of prompt *content*, and the cached artifact is the model's KV cache, which is inherently model-specific (different weights ⇒ different activations). A cache entry written for Opus 5.5 cannot be read by Sonnet 5.5 (or vice versa); per-model minimum-cacheable-lengths and per-model pricing in the same doc are consistent with per-model cache namespaces. Therefore switching models on an existing conversation = 100% cache loss + full-history re-prefill at the new model's input price.
- **Source:** https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching (invalidation table + "Cache storage and sharing", read) — absence of explicit statement; mechanism inference
- **Quote (closest vendor text):** "Cache hits require 100% identical prompt segments, including all text and images up to and including the block marked with cache control." (no model-change row exists in the table)
- **Tier:** Plausible (sound mechanism, not on-target documented)

## F6. Context windows: all current Claude models are 1M by default
- **Claim:** Claude Fable 5.1, Mythos 5.1, Opus 5.5, Opus 5, Opus 4.8/4.7/4.6, Sonnet 5.5, Sonnet 5, Sonnet 4.6, Haiku 5.5 all have a **1M-token context window, and 1M is the default** (no beta header needed), billed at standard pricing except Haiku 5.5 where prompts >100k tokens cost more. Max output 128k. Older models (e.g. Sonnet 4.5) are 200k. So in 2026 the "200k standard / 1M beta" distinction is gone for the current lineup.
- **Source:** https://docs.anthropic.com/en/docs/build-with-claude/context-windows + https://docs.anthropic.com/en/docs/about-claude/models/overview (vendor docs, both read)
- **Quote:** "For every model with a 1M-token context window, 1M is the default: you don't need a beta header, and long-context requests are billed at standard pricing, except on Claude Haiku 5.5, where prompts over 100,000 tokens cost more." / Model overview table: Context window "1M tokens" for Fable 5.1 / Opus 5.5 / Sonnet 5.5 / Haiku 5.5, "Max output 128K tokens".
- **Tier:** Verified

## F7. Behavior when history exceeds the new model's window (vendor-documented)
- **Claim:** If the input alone exceeds the model's context window, the API returns **400 `invalid_request_error` ("prompt is too long")** on every model — no silent truncation. On Claude 4.5+ models, if input + `max_tokens` exceeds the window, the request is accepted and generation stops with `stop_reason: "model_context_window_exceeded"`. Cached prefixes still occupy the window ("prompt caching changes what you pay for those tokens, not whether they count"). Anthropic's recommended strategy for long conversations is server-side compaction (beta, 4.6+).
- **Source:** https://docs.anthropic.com/en/docs/build-with-claude/context-windows, "Context window overflow behavior" (vendor doc, read)
- **Quote:** "If the input alone already exceeds the model's context window, the API returns a 400 `invalid_request_error` (\"prompt is too long\") on every model. On Claude 4.5 models and newer, if input tokens plus `max_tokens` exceeds the context window size, the API accepts the request. If generation then reaches the context window limit, it stops with `stop_reason: \"model_context_window_exceeded\"`."
- **Tier:** Verified
- **Implication for this setup:** Claude→Claude switches never hit a window problem (all 1M). Claude→Qwen3.8-27B (262144 ctx) is safe only while history+output stays under 256k; a 200k+ chat with thinking blocks can exceed it, and local servers (vLLM-class) reject over-limit requests with a 400 rather than truncating (local-deployment behavior, not vendor-documented here).

## F8. Qwen3.8-27B-FP8 context window
- **Claim:** Local Qwen3.8-27B-FP8 has 262144 (256k) context tokens and is free (no per-token cost).
- **Source:** user environment context (verified local fact, 2026-10-16); no vendor doc exists for this local deployment
- **Tier:** Verified (as an environment fact)

## F9. Worked example — cost of SWITCHING a 100k-token chat (one-time re-prefill)
- **Claim:** Switching models loses the whole cache (F5) and re-prefills 100k at the new model's input price:
  - → **Sonnet 5.5:** uncached 100k×$2 = **$0.20**; with 5m cache write 100k×$2.50 = **$0.25**; with 1h write 100k×$4 = **$0.40**
  - → **Opus 5.5:** uncached 100k×$4 = **$0.40**; 5m write 100k×$5 = **$0.50**; 1h write 100k×$8 = **$0.80**
  - → **Haiku 5.5:** 100k+ falls in the >100k tier: uncached 100k×$0.50 = **$0.50**; 5m write 100k×$0.625 = **$0.625**; 1h write 100k×$1.00 = **$1.00** (switching DOWN to Haiku is MORE expensive than switching to Sonnet at this history size)
  - Subsequent turns within TTL then read at: Sonnet $0.01 / Opus $0.02 / Haiku $0.005 per 100k.
- **Source:** computed from F2 vendor prices (https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching, https://www.anthropic.com/pricing)
- **Tier:** Verified (inputs) / computed

## F10. Worked example — cost of STAYING on Opus 5.5 with warm 1h cache (user's config)
- **Claim:** With `cache_ttl: 1h` and an active conversation, each turn reads the 100k history at the 0.05x read price: 100k×$0.20/MTok = **$0.02/turn**, plus the new delta written at the 1h rate (e.g. 2k×$8/MTok = $0.016). Total ≈ **$0.03–0.04/turn** before output tokens. The 1h TTL refreshes on every read (F3), so an active chat never re-prefills.
- **Source:** computed from F2/F3 vendor prices
- **Tier:** Verified (inputs) / computed

## F11. Worked example — FRESH session with compact handover vs switching
- **Claim:** A fresh session on Opus 5.5 with a 5–10k-token handover summary costs: 5k → $0.02 uncached / $0.025 (5m write) / $0.04 (1h write); 10k → $0.04 / $0.05 / **$0.08**. That is **5–20x cheaper** than re-prefilling a 100k chat onto Opus ($0.40–$0.80) and 2.5–10x cheaper than switching onto Sonnet ($0.20–$0.40). Trade-off: only the handover content survives; full history is dropped.
- **Source:** computed from F2 vendor prices
- **Tier:** Verified (inputs) / computed

## F12. Break-even: Opus→Sonnet switch is rarely economical
- **Claim:** Opus 5.5 → Sonnet 5.5 on a 100k chat: one-time $0.20–$0.40 (F9) vs per-turn read-price saving of $0.02−$0.01 = **$0.01/turn** → break-even at **20–40 turns** of continued use at that history size, before counting delta-write differences. For short-term model downgrades the switch cost is a sunk loss; the cheaper route is a fresh session with handover (F11) or staying on Opus with the warm cache (F10, $0.02/turn).
- **Source:** computed from F2/F9/F10
- **Tier:** Verified (inputs) / computed

## F13. CLIProxyAPI: cache_control IS passed through / auto-injected (third-party project)
- **Claim:** CLIProxyAPI's translator layer is *pure pass-through* (intentional architecture: "preserves client-supplied fields"), but the Claude **executor** auto-injects `cache_control` breakpoints when the client sends none — last tool definition, last system element, second-to-last user turn — enforces Anthropic's 4-breakpoint limit, and for OAuth credentials upgrades breakpoints to `ttl: "1h"` (`upgradeClaudeCacheControlTTL()`), auto-adding the `extended-cache-ttl-2025-04-11` beta header. So Hermes (OpenAI-protocol client) gets prompt caching on the Claude path without sending cache_control itself.
- **Source:** https://github.com/router-for-me/CLIProxyAPI/issues/5557 (third-party project issue tracker; maintainer/collaborator comment, read)
- **Quote:** "In CLIProxyAPI's architecture, the pass-through behavior in `internal/translator/` is intentional. … Origination and lifecycle management of Claude prompt caching breakpoints are handled downstream in the executor layer" / "`injectMessagesCacheControl()` places a rolling breakpoint on the latest cacheable message in the conversation history" / "For OAuth credentials, `upgradeClaudeCacheControlTTL()` upgrades these breakpoints to `\"ttl\": \"1h\"`."
- **Tier:** Verified (read primary project sources; caveat: third-party project, behavior is version-dependent)

## F14. CLIProxyAPI 1h-TTL reliability was a real bug, fixed (third-party project)
- **Claim:** Issue #3398 (opened 2026-05-14, closed via PR #4731): injected default `cache_control` blocks stayed 5m and `normalizeCacheControlTTL()` could downgrade later `ttl:"1h"` blocks, so the 1h cache path was not reliably used. After the fix, a user (2026-09-12) confirms: "I can confirm the 1h TTL does come through on my ooauth cc v2.1.101 setup by default w/o any special config flags." Related known bug #2419: `usage.prompt_tokens_details.cached_tokens` was not translated into the OpenAI chat-completions response, so OpenAI-protocol clients could not see cache hits (status not confirmed fixed from sources read).
- **Source:** https://github.com/router-for-me/CLIProxyAPI/issues/3398, https://github.com/router-for-me/CLIProxyAPI/issues/2419 (third-party project issue trackers, read)
- **Quote:** "CLIProxyAPI already injects and repairs Anthropic `cache_control` breakpoints for Claude requests, but the current behavior does not reliably preserve the 1-hour prompt cache path."
- **Tier:** Verified (read primary project sources; caveat: third-party, version-dependent)

## F15. OpenRouter reference (user does NOT use OpenRouter — context only)
- **Claim:** Via OpenRouter, Anthropic caching = 5m write 1.25x, 1h write 2x, read 0.1x (note: OpenRouter's docs state 0.1x reads, while Anthropic's own pricing says 0.05x for Opus 5.5/Sonnet 5.5 — OpenRouter figure appears simplified/stale for the 5.5 generation; verify against live page for current models). OpenRouter uses provider sticky routing (10-min inactivity expiry, per conversation hash or `session_id`) to keep caches warm, and translates `cache_control` ↔ OpenAI `prompt_cache_breakpoint` between dialects — "TTLs are not translated".
- **Source:** https://openrouter.ai/docs/guides/best-practices/prompt-caching (vendor doc, read)
- **Quote:** "Cache writes (5-minute TTL): charged at 1.25x the price of the original input pricing … Cache reads: charged at 0.1x" / "Sticky sessions expire after 10 minutes of inactivity."
- **Tier:** Verified (read; discrepancy with Anthropic pricing flagged)

---

## Bottom line for "do not switch the model of an existing chat"
1. Switching = 100% cache loss (F5) + full-history re-prefill at the new model's input price: $0.20–$1.00 one-time for 100k tokens (F9).
2. Staying on the current model with a warm 1h cache costs ~$0.02/turn for 100k reads on Opus 5.5 (F10) — the switch cost is 10–40x a single cached turn and takes 20–40 turns to amortize (F12).
3. If a different model is genuinely needed for a task, a fresh session with a 5–10k handover on the expensive model ($0.04–$0.08 on Opus 5.5) is 5–20x cheaper than re-prefilling 100k (F11), and leaves the original chat's cache intact.
4. Window risk is asymmetric: Claude→Claude is safe (all current models 1M, F6); Claude→local Qwen3.8-27B (256k) errors out with a 400 once history+output exceeds 256k (F7/F8) — no silent truncation.
5. On the user's exact stack (CLIProxyAPI + `cache_ttl: 1h`), caching is active on the Claude path via executor-side injection with 1h TTL (F13/F14), so the "stay put" option is actually cheap; verify cache hits via Anthropic-side usage fields, since OpenAI-protocol `cached_tokens` translation had a known bug (F14).

## Searched, found nothing
- No explicit Anthropic-doc statement that "changing the model invalidates the cache" — the invalidation table covers request-level changes only (hence F5 is Plausible, not Verified).
- No dedicated OpenRouter docs page on per-model context limits was fetched (context_length is listed per model on OpenRouter model pages, not on the prompt-caching page).
- No vendor documentation for the local Qwen3.8-27B-FP8 deployment (262144 ctx is an environment fact; overflow behavior of the local server not vendor-documented here).
- No Anthropic doc treating "switching models mid-conversation" as a named scenario with its own cost guidance.
