# Lane 4 — Community & Practice: Mixing Cheap (Local) and Expensive (API) Models in Long-Running Agent Projects

Research date: 2026-10-16. Sources: Reddit (r/ClaudeCode, r/ClaudeAI, r/hermesagent, r/MachineLearning), Hacker News, vendor blogs/docs, arXiv.
Tier key: **Plausible** = community report / multi-source / official docs; **Speculative** = single-anecdote claim.

---

## 1. Patterns practitioners actually use (with quality/cost reports)

### 1.1 Dominant pattern: expensive orchestrator + cheap subagents

**F1.** The most-repeated working setup in r/ClaudeCode is a frontier orchestrator that delegates all execution to cheap subagents.
- Source: https://www.reddit.com/r/ClaudeCode/comments/1ruuzdg/opus_as_the_orchestrator_with_aggressive/ (reddit)
- Quote (PrintfReddit): "Opus as the orchestrator with aggressive delegation to Sonnet and Haiku is probably the most efficient way to use the models. This isn't just about token efficiency, it's also about time efficiency. Opus doesn't get lost, and uses subagents to actually do the execution."
- Quote (kellstheword): "I have 20+ agent definitions, all with tight scopes and roles. Just Haiku agents alone are 11... I run sessions with a Sonnet orchestrator, delegating all execution tasks to subagents."
- Quote (mcouthon): "One conductor/orchestrator to rule them all, memory via specifically formatted MD files, and heavy delegation to other dedicated subagents. This is the way."
- Tier: Plausible (multiple independent users, same thread)

**F2.** The mechanism behind the savings: subagent file reads/search outputs stay in the subagent's own context; only a summary returns to the orchestrator, so the expensive context grows slowly.
- Source: https://www.reddit.com/r/ClaudeAI/comments/1x1buac/how_much_more_effectivebetter_is_using_opus_55/ (reddit, 101 upvotes)
- Quote (kenthesaint): "Most of the savings come from the subagent's file reads and search outputs staying in their own context, with only a summary coming back, so the Opus context grows much more slowly."
- Thread consensus: "using Haiku as subagents is far more efficient and cheaper."
- Tier: Plausible

**F3.** Per-task quality/cost data from a self-run 6-task benchmark (single user, but measured):
- Source: https://www.reddit.com/r/ClaudeCode/comments/1x1e7ts/i_tested_haiku_55_sonnet_55_and_opus_55_as/ (reddit, 231 upvotes)
- Quote (emarkosov): "Code search: Haiku found 44/48 files, $0.44 vs Opus 45/48, $6.17 — same quality, so Haiku wins on price. Web research: Haiku had 10 wrong facts, Opus had 1. Fact-checking: Haiku had 30 false positives... What I use now: Haiku for code search, Opus for research and fact-checking, Sonnet when small mistakes are acceptable."
- Tier: Plausible (self-reported benchmark; single user)

**F4.** Counterpoint: frontier orchestrators can trust cheap subagent reports blindly.
- Source: https://www.reddit.com/r/ClaudeCode/comments/1ruuzdg/opus_as_the_orchestrator_with_aggressive/ (reddit)
- Quote (Caibot): "Opus is really good at following instructions, and believes things in the context without verification. If a Sonnet/Haiku subagent reports something clearly false, I'm pretty sure Opus will also get it wrong."
- Tier: Plausible (community report)

**F5.** Pitfall: orchestrators default to their own model for subagents, defeating the tiering.
- Source: r/ClaudeCode thread "Opus 5 REALLY loves to use Opus 5 subagents all the time, even when subagents are overkill or Haiku would be more than enough for codebase exploration" (reddit, ~1 month old)
- Tier: Plausible (community report)

**F6.** Pitfall: the orchestrator/subagent split can burn more tokens than expected if subagents are poorly scoped.
- Source: r/ClaudeCode thread "My Opus-orchestrator / Sonnet-subagent Claude Code setup is burning way more tokens and time than I expected" (reddit, ~3 months old)
- Tier: Plausible (community report)

**F7.** Historical pitfall: Claude Code once had a hardcoded instruction discouraging Opus 5 from using subagents.
- Source: r/ClaudeCode thread "Claude Code has a hardcoded instruction telling Opus 5 not to use subagents" (reddit, ~3 months old, 428 upvotes)
- Tier: Plausible (community report)

**F8.** Single-anecdote successes of strict cheap-worker setups.
- Source: https://www.reddit.com/r/ClaudeCode/comments/1ruuzdg/opus_as_the_orchestrator_with_aggressive/ (reddit)
- Quote (rehtorical): "I have a system that strictly runs haiku workers and an opus orchestrator thread, fully functional, called Aesop on npm, and I wrote a paper called the haiku wager."
- Quote (WishboneOk305): "Haiku is stupidly cheap, I can run about 7 subagents for 5 hours straight and not use 30% of my limit."
- Tier: Speculative (single anecdotes)

### 1.2 Cheap orchestrator + expensive specialist (minority, with caveats)

**F9.** Cheap-orchestrator plans exist but are usually framed as experiments, and cheap "judge" models are criticized for under-escalation.
- Source: https://www.reddit.com/r/ClaudeCode/comments/1x0kzbh/haiku_55_is_40x_cheaper_than_opus_55_your_explore/ (reddit)
- Quote (imsahoamtiskaw): "My next plan is to have Haiku orchestrate and use Fable as a worker."
- Source: https://www.reddit.com/r/ClaudeAI/comments/1x1nnkn/i_made_a_claude_code_mod_that_uses_haiku_55_or/ (reddit)
- Quote (-WhateverDude): "Using Haiku as a judge seems like a bad idea. It can't reliably pick the cheapest model/effort that can comfortably handle the job, and if it underestimates, you end up spinning your wheels with a weak answer."
- Tier: Speculative (plan, not report) / Plausible (critique)

**F10.** Gatekeeper/cascade pattern: cheap model screens, expensive model handles the hard remainder.
- Source: https://www.reddit.com/r/ClaudeAI/comments/1ry7ad1/how_i_use_haiku_as_a_gatekeeper_before_sonnet_to/ (reddit, 195 upvotes)
- Quote (gzoomedia): "Haiku as a gate filters 85% of input, Sonnet handles 15%... Tuning the Haiku prompt to be more specific was far more effective than trying to fine-tune a confidence-score threshold."
- Quote (redishtoo): "Haiku screens incoming mail and if a VIP is identified, passes it to sonnet."
- Tier: Plausible (community report with numbers) / Speculative (mail anecdote)

**F11.** Stage-based pipelines mixing tiers per stage.
- Source: https://www.reddit.com/r/ClaudeAI/comments/1rb1ohn/haiku_vs_opussonnet_is_there_a_reason_to_use_more/ (reddit)
- Quote (Jdizza12): "Haiku for rough draft → Haiku for prompt refinement → Sonnet/Opus for strategic pass (limited) → Haiku for execution → Haiku for stress test → Sonnet/Opus only when needed for stubborn issues."
- Quote (Substantial-Reward70): "I use a tool called autospec, which has 4 stages: specify, plan, tasks, implementation. I use Opus 4.6 High effort for everything except implementation. Implementation is always done with Haiku, and honestly it works fine for me."
- Tier: Speculative (single anecdotes)

**F12.** Escalation-on-failure ("cheap first, expensive when stuck") is endorsed.
- Source: https://www.reddit.com/r/ClaudeAI/comments/1sw4bl6/how_do_you_decide_which_claude_code_tasks_to_run/ (reddit)
- Quote (Bitter-Law3957): "Escalating to Opus after Sonnet hits a wall is exactly the right pattern."
- Tier: Plausible

### 1.3 Role-based multi-agent (Hermes-specific)

**F13.** Role-based model assignment per agent profile is the standard Hermes practice: PM/coordinator on cheap, architect/engineer on expensive.
- Source: https://www.reddit.com/r/hermesagent/comments/1u0xpb6/looking_for_a_costeffective_ai_setup_for_hermes/ (reddit)
- Quote (VladShwartz23): "Biggest lesson: big tasks fail, small tasks succeed... using an expensive model for project management is mostly a waste. The Flash model is more than capable of: planning, reading reports, creating tasks, managing kanban boards, coordinating agents, summarizing progress. Pro models are only used where they actually matter: architecture, implementation, debugging, code review. This significantly reduced costs."
- Tier: Plausible (community report)

**F14.** Per-profile model assignment with tiered routing by task type.
- Source: https://www.reddit.com/r/hermesagent/comments/1u6b0dd/how_do_you_configure_hermes_to_autoswitch_between/ (reddit)
- Quote (BHTAelitepwn): "chatgpt5.5 is the standard model. Deepseek v4 pro is backup... Easy/repetitive tasks are routed to gemini 2.5 flash. Opus 4.8 picks up critical tasks/infrastructure decisions." + "You can also minimize tools and skills on high-end profiles to reduce token bloat."
- Quote (Tha_Reaper): "My main profile uses qwen3.6 35b. My coder subagent uses qwen3.6 27b. My writer subagent uses Gemma... For subagents that do less tool-calling or simpler tasks, I use a faster/cheaper model."
- Tier: Plausible

**F15.** Prompt-level "defer to local" pattern: the expensive model is instructed to hand off routine tasks to a local model instead of answering.
- Source: https://www.reddit.com/r/hermesagent/comments/1u6b0dd/how_do_you_configure_hermes_to_autoswitch_between/ (reddit)
- Quote (L0cut15, SOULD.MD pattern): "Before answering, ask: could a competent 30B local model handle this just as well? If yes, don't answer. Reply only with: → defer:local '<one-line restatement of the task>'" — "This lets me get by with a local model for everyday stuff."
- Tier: Plausible (community report)

**F16.** Different models for main vs cron/delegation; one known breakage: don't use a different model for approvals.
- Source: https://www.reddit.com/r/hermesagent/comments/1sfvp3o/model_switching_on_subagent_delegation/ (reddit)
- Quote (Final-Department2891): "I use GLM for main and MiniMax for cron/delegate agents. The only thing I've noticed that really breaks is using a different model for approvals — don't do that."
- Quote (Pcorajr): "You can set the delegation model in the config. In my setup I have it set to use my local Gemma 4 model."
- Tier: Plausible

**F17.** Real Hermes local+API hybrid configurations (self-reported):
- Source: https://www.reddit.com/r/hermesagent/comments/1valiwr/what_provider_and_model_do_you_actually_use_with/ (reddit)
- Quote (marcel_One_8763): "Hermes3.6-35B-A3B (Q6) on 3060 Ti for web research/cron/ComfyUI/pentest, Qwen 3.6 27B (Q6) on 5070Ti+5060Ti for coding. Cost: electricity."
- Quote (iChrist): "Gemma4-31b for 90% of tasks, sometimes Qwen3.6-27B... when I don't send a message for 8 minutes the model is unloaded from the GPU."
- Quote (yarcsi): "DeepSeek V4 Pro for main, flash for basic stuff and cron, GLM 5 Turbo for agentic tool calls, Gemini 3.5 flash lite for file search sometimes."
- Quote (PracticlySpeaking): "A separate hermes instance running checks for important news... delegates search and selection processes to local models... GPT-5.5 $20 Plus... Gemma-4... what I don't like: agent cron... not that great."
- Tier: Plausible (multiple independent users)

**F18.** Multi-agent "named agents that talk to each other" pattern in Hermes.
- Source: https://www.reddit.com/r/hermesagent/comments/1wr5jka/what_models_are_you_guys_actually_using_with/ (reddit)
- Quote (RPG-Nerd): "I started with just basic profiles. Each agent has a name and a set of responsibilities. You start talking about a bug in some code and Gopher will ask 'Want me to tell Neo?'... This is nice because they can verify back and forth."
- Tier: Plausible

**F19.** Cost reality check from heavy Hermes usage: cheap models aren't always reliable enough for deep agent work, and router behavior can inflate bills.
- Source: https://www.reddit.com/r/hermesagent/comments/1wr5jka/what_models_are_you_guys_actually_using_with/ (reddit)
- Quote (Severe-Cap1333, OP): "I also managed to burn through $1,500+ on OpenRouter in under 4 weeks 😅... What surprised me is that I actually liked Sonnet more than Luna. On paper Luna looked really interesting because it's so much cheaper, but in my actual Hermes usage I felt like Sonnet was more reliable for some of the deeper reasoning / agent stuff."
- Quote (same thread, on caching): "Hermes resends the whole context on every tool call, so caching is most of the bill in long loops, better to work on that first. openrouter spreads calls so your agent context lands on a new provider each time and re bills at full price rather than hitting cache. $1500 is partly the router as well."
- Tier: Plausible (community report; caching quote is from thread comments as indexed by search)

**F20.** Hermes overhead itself consumes tokens before user input.
- Source: https://www.reddit.com/r/hermesagent/comments/1valiwr/what_provider_and_model_do_you_actually_use_with/ (reddit)
- Quote (humblingman): "deepseek flash has lots of errors... deepseek pro is great... the only problem is that token usage is very high... I think the hermes overhead system is already using a lot of tokens before my input."
- Tier: Plausible (community report)

**F21.** Model switching is not seamless in Hermes; users route via profiles, skills, or external proxies instead.
- Source: https://www.reddit.com/r/hermesagent/comments/1u9k0p9/abandoning_model_switcher_and_just_using_a_skill/ (reddit)
- Quote (Jonathan_Rivera): "5090: primary model Qwen 27B // 5070 - OSS 20B for auxiliary tasks, compression, summarization... /model switcher only switches the primary model. If I'm using Codex gpt 5.5 and my aux is pointing at the primary model, my budget gets blown. Aux can't be left local because gpt's context length budget is way bigger. Switching the main provider, aux provider, and agent provider is a pain." (He abandoned the model switcher in favor of a skill that switches primary/aux/agents in plain text.)
- Source: https://www.reddit.com/r/hermesagent/comments/1u6b0dd/how_do_you_configure_hermes_to_autoswitch_between/ (reddit)
- Quote (rj_rad): "Hermes isn't fast or seamless enough to be the right surface for this. Better to run a configurable proxy/middleware like LiteLLM where you can set up failover rules or custom routes."
- Quote (CarbonMaxxer): "Feels like this feature is a huge missing feature."
- Tier: Plausible

**F22.** Local-model serving mechanics: llama-swap for fast model swaps; llama.cpp built-in model router for per-task aliases.
- Source: https://www.reddit.com/r/hermesagent/comments/1tyyyry/is_there_any_way_to_switch_local_models_quicker/ (reddit)
- Quote (mgithens1): "llama-swap is what you're looking for."
- Quote (wayofTzu): "llama.cpp now has a built-in model router... I set up one fast model for delegate tasks and one slow model for planning and subagent invocation. I haven't yet figured out how to intelligently map models to task difficulty, but in hermes I just point various tasks (like delegates) at the aliases defined in the models.ini file."
- Tier: Plausible

**F23.** Agents can fabricate calls to other models (hallucinated delegation).
- Source: https://www.reddit.com/r/hermesagent/comments/1u6b0dd/how_do_you_configure_hermes_to_autoswitch_between/ (reddit)
- Quote (x_MASE_x): "He fabricated all of this and MedGemma_27B_Text was never called."
- Tier: Plausible (community report)

---

## 2. Switching models mid-conversation: cost, cache, quality

**F24.** Vendor technical explanation: a mid-session model switch triggers a full cache miss (entire history re-processed at full price) plus out-of-distribution context problems (style drift, lost implicit context, instruction ambiguity, reasoning discontinuity).
- Source: https://www.mindstudio.ai/blog/why-not-switch-models-mid-conversation-ai-coding-agents (blog)
- Quote: "The moment you switch models mid-conversation, you trigger a full cache miss... Every single token — every line of code you shared, every explanation, every file you pasted — gets re-processed from scratch at full inference cost."
- Tier: Plausible (vendor blog; technically consistent with community reports)

**F25.** Community confirmation that cache is per-model, so escalation re-reads the whole context at full input price.
- Source: https://www.reddit.com/r/ClaudeAI/comments/1x1nnkn/i_made_a_claude_code_mod_that_uses_haiku_55_or/ (reddit)
- Quote (-WhateverDude): "The cache is per-model, so when it escalates to Opus, the entire context gets re-read at full input price instead of cache price. Effort-only switching avoids that, but model switching doesn't."
- Quote (tomas_f): "What about cold cache when switching models, lol?"
- Tier: Plausible

**F26.** Measured cost structure of a long-running agent session: cache reads dominate, which is why switching is expensive.
- Source: https://www.reddit.com/r/ClaudeCode/comments/1x19b2c/i_built_a_claude_code_mod_on_haiku_55_or_jev_that/ (reddit)
- Quote (effortless mod OP): "Across roughly 80k of my own requests, cache reads were about 76% of cost, output only 8%. Effort mostly changes how many tool calls a prompt makes, not how long the answer is. Switching effort preserves the cache on Opus 5.5 and Sonnet 5.5. On Fable 5.1 and older Opus it rewrote 56–100% of it, so Auto pauses there."
- Tier: Plausible (self-reported benchmark)

**F27.** A built model-switching mod was pulled back to effort-only switching after benchmarks showed model switching didn't save much even accounting for cold cache.
- Source: https://www.reddit.com/r/ClaudeAI/comments/1x1nnkn/i_made_a_claude_code_mod_that_uses_haiku_55_or/ (reddit)
- Quote (OP): "It no longer switches models, it just offers it as an experimental setting, but for now it defaults to only changing effort. I ran some benchmarks, and even accounting for cold cache, it didn't save that much money. In my benchmarks, effort-only changes save an average of 20% if you're always using opus 5.5 medium."
- Tier: Plausible (self-reported benchmark)

**F28.** Code-level evidence that a model switch makes the new model pay a cold-cache prefill of the entire carried context.
- Source: https://github.com/workweave/router (PR: cost accounting for model switches)
- Quote: "When the router switches models, the newly serving model pays a cold-cache prefill of the entire carried context, reported as cache_creation tokens."
- Tier: Plausible (code-level evidence)

**F29.** HN skepticism that stateless routers increase cache misses (5-min TTL) and therefore cost.
- Source: https://news.ycombinator.com/item?id=48688700 (HN)
- Quote (stpedgwdgfhgdd): "The thing I don't get about these routers is that cache misses (5-min TTL) increase. And if there's one thing I've learned, it's that using the cache is crucial."
- Quote (ai_slop_hater): "Isn't this more expensive than always using the same model. Since, as I understand it, routing to different models means giving up the cache?"
- Tier: Plausible (community report)

**F30.** You cannot simply ask the agent to switch models mid-conversation in the chat window (Claude Code).
- Source: https://www.reddit.com/r/ClaudeAI/comments/1ry7ad1/how_i_use_haiku_as_a_gatekeeper_before_sonnet_to/ (reddit, mod TL;DR)
- Quote: "You can't just ask Claude to switch models mid-conversation in the chat window."
- Tier: Plausible

**F31.** In Hermes, the aux model silently following the primary model can blow the budget; context-length mismatch between API and local models is a real constraint on which roles can run locally.
- Source: https://www.reddit.com/r/hermesagent/comments/1u9k0p9/abandoning_model_switcher_and_just_using_a_skill/ (reddit)
- Quote (Jonathan_Rivera): "If I'm using Codex gpt 5.5 and my aux is pointing at the primary model, my budget gets blown. Aux can't be left local because gpt's context length budget is way bigger."
- Tier: Plausible

---

## 3. Claude Code model tiering (haiku/sonnet/opus): how it works + user reports

**F32.** Haiku 5.5 is ~40x cheaper than Opus 5.5 ($0.10/$0.50 vs $4/$20 per Mtok); Anthropic recommends it for subagents. Claude Code's built-in Explore subagent now runs on the main model (regression vs earlier Haiku default).
- Source: https://www.reddit.com/r/ClaudeCode/comments/1x0kzbh/haiku_55_is_40x_cheaper_than_opus_55_your_explore/ (reddit)
- Quote (OP): "Haiku 5.5 launched yesterday at $0.10/$0.50 per million tokens... versus $4/$20 for Opus 5.5. Anthropic recommends it as a subagent for Opus and Sonnet for coding work... Claude Code's built-in Explore subagent no longer runs on Haiku. It uses the main model, so on Opus 5.5 every Explore run goes through Opus."
- Tier: Plausible

**F33.** Per-agent model pinning via `model:` in agent frontmatter / `CLAUDE_CODE_SUBAGENT_MODEL` is the practical mechanism; users pin only research-type subagents to Haiku, not all.
- Source: https://www.reddit.com/r/ClaudeCode/comments/1x0kzbh/haiku_55_is_40x_cheaper_than_opus_55_your_explore/ (reddit)
- Quote (emarkosov): "I'm keeping the main session on Opus and trying Haiku for search-type subagents... 129 subagent spawns, only 2 were Explore. Most were implementation work I want to do on Opus, so FORCE would hurt me. Instead I'll move only the research subagents to Haiku with model: haiku."
- Quote (andreagrandi): "This way you are forcing every sub agent, even those which should use sonnet 5.5 (ie: implementer)"
- Tier: Plausible

**F34.** Counter-pattern: some power users just run everything on the top model and never switch.
- Source: https://www.reddit.com/r/ClaudeAI/comments/1sw4bl6/how_do_you_decide_which_claude_code_tasks_to_run/ (reddit)
- Quote (OP): "In practice I just default to whatever's set and never switch."
- Quote (Choose_ur_username1): "Everything runs on Opus 4.7 MAX."
- Quote (Zealousideal_Aside96): "Yeah, if I know I have plenty of buffer in the current session, I just run everything on opus regardless of the question or prompt"
- Tier: Speculative (single anecdotes) / Plausible (OP report)

**F35.** Hook-based model suggestion: a UserPromptSubmit hook classifies the prompt and suggests haiku/sonnet/opus triggers.
- Source: https://www.reddit.com/r/ClaudeAI/comments/1sw4bl6/how_do_you_decide_which_claude_code_tasks_to_run/ (reddit)
- Quote (Bitter-Law3957): "Once you start getting into agents for parts of your flow, you can define the right model for the task the agent is responsible for. Sadly, you can't have Claude change it for you in session."
- Tier: Plausible

**F36.** "Opus plan" hybrid: plan on Opus, execute on Sonnet, via `/model opusplan`.
- Source: https://howdoiuseai.com/blog/claude-code-model-switching-opus-sonnet-haiku (blog)
- Tier: Plausible (vendor blog)

**F37.** Official "advisor" strategy: Opus as advisor, Sonnet/Haiku as executor — now a platform feature.
- Source: https://www.reddit.com/r/ClaudeAI/comments/1sgy11x/ (reddit, 637 upvotes) — "We're bringing the advisor strategy to the Claude Platform"
- Source: https://www.reddit.com/r/ClaudeAI/comments/1sgyt6s/pair_opus_as_an_advisor_with_sonnet_or_haiku_as/ (reddit, 150 upvotes)
- Quote (TekintetesUr): "Even the official account claims a conservative 12% reduction."
- Community sentiment: "Opus 4.6 with 4.7 as an advisor might be the best option for many of us!" (315 upvotes); "Thanks to Haiku 5.5, I can run hundreds of agents without instantly blowing through my 20X sub" (194 upvotes); "Is Haiku 5.5 good enough to be your main coding agent, not just the cheap one?" (287 upvotes).
- Tier: Plausible (official + community)

**F38.** Community consensus on when Haiku-as-main is acceptable: search/reading-type work is a small fraction of real sessions, so losing detail there is not worth it for many.
- Source: https://www.reddit.com/r/ClaudeCode/comments/1x0kzbh/haiku_55_is_40x_cheaper_than_opus_55_your_explore/ (reddit)
- Quote (Evipicc): "search reading is like... 2% of what I do, so It's not worth the chance of losing an important detail to me."
- Quote (shout925): "Agree, dumb to implement Haiku for everything, quality of the code and work will degrade over time."
- Tier: Speculative (single anecdotes) / Plausible (shout925)

---

## 4. Router/cascade products: mechanism + real-world reports

**F39.** OpenRouter Auto Router: market-driven routing. Classifies each prompt into ~30 task types, then ranks models by aggregate community spend for that task type (trailing 7-day window); `cost_tier` (low/medium/high/xhigh/max) picks a band; no extra fee.
- Source: https://openrouter.ai/docs/guides/routing/routers/auto-router (official docs)
- Quote: "The Auto Router automatically selects the best model for your prompt. It is powered by the market: the aggregate spend of millions of people using OpenRouter, measured over a trailing 7-day window for each task type." / "You pay the standard rate for whichever model is selected. There is no additional fee for using the Auto Router."
- Tier: Plausible (official docs)

**F40.** OpenRouter Auto Router has session stickiness specifically to keep multi-turn conversations coherent (and cache-friendly): it remembers the model a conversation landed on and prefers it on later turns, re-ranking from scratch each turn.
- Source: https://openrouter.ai/docs/guides/routing/routers/auto-router (official docs)
- Quote: "To keep multi-turn conversations coherent, it remembers the model a conversation landed on and prefers it on later turns... The router still ranks candidates from scratch on each turn, and it reuses the remembered model only while that model is still one of the top candidates for the new prompt."
- Tier: Plausible (official docs)

**F41.** OpenRouter `:floor` routes to the cheapest available provider for a given model (provider-level, not model-level).
- Source: https://openrouter.ai/docs/guides/routing/provider-selection (official docs, via search snippet)
- Quote: "OpenRouter :floor is a special router that always routes to the cheapest available provider for a model."
- Tier: Plausible (official docs)

**F42.** LiteLLM Router: load balancing (round-robin, least-busy, latency-based, cost-based, simple-shuffle); [Beta] Auto Routing classifies requests into 4 complexity tiers and routes to the cheapest model that can handle the tier; [BETA] Adaptive Router learns per-request-type performance over time (first ~10 requests per model rely on declared tiers).
- Source: https://docs.litellm.ai/docs/routing (official docs, via search snippets)
- Tier: Plausible (official docs)

**F43.** workweave/router (HN, 216 points, 113 comments): cache-aware model router for coding agents. Claims 40% savings vs always-frontier; uses subscription pricing when available; subagents (fresh context) are routed independently.
- Source: https://news.ycombinator.com/item?id=48688700 (HN)
- Quote (adchurch, OP): "That's exactly why we built the router to be cache-aware! Once it starts using one model, the threshold for switching to another model becomes higher. That's because the additional cost of a cache miss has to be worth the cost savings or quality improvement. This is the key point that other routers we've seen miss: they're stateless, so in coding agent use cases you end up spending more money due to all the cache misses."
- Quote (adchurch): "experimentally this solves the problem (as I said, we ourselves saved 40% compared to what we would otherwise have paid)."
- Quote (adchurch): "If you have a Claude/Codex subscription, we use that (and account for the subsidized price accordingly when making routing decisions)... in practice, a lot of people are using this to stretch their Claude sub limits further!"
- Quote (alansaber): "Interesting, so in practice you end up routing between only 2 models"
- Quote (adchurch): "I'd say a typical main agent loop uses 1–3 models… but when there are subagents, since they have a fresh context window, they can be routed independently, so there's a lot more freedom there."
- Quote (_pdp_, skeptic): "But I still don't get how this saves money… small LLMs tend to stop before finishing, throw errors, and produce loops."
- Quote (adchurch): "It saves money because some agent sessions can be handled entirely by a smaller model (related: subagents use a fresh context window, so even if the main agent needs a frontier model, a subagent with a simple task can be routed to a smaller model). And you're totally right about small LLMs. That's why we trained this on real agent sessions… there are also guardrails that have a bigger model 'rescue' a smaller model."
- Tier: Plausible (vendor claims + active community discussion; 40% figure is vendor-reported)

**F44.** Artifact-based handoff as a cache-friendly alternative to model switching: expensive model writes a plan/summary file, cheap model executes in its own session (99.9% cache hits reported), expensive model reviews the artifact.
- Source: https://news.ycombinator.com/item?id=48688700 (HN)
- Quote (port11): "Artifact-based workflows solve this problem… I still have Claude Code because Opus makes good plans, but I hand the plan to M3 on Pi, and I get 99.9% cache hits on long sessions. Beautiful. Then Pi writes a summary file that Opus can use to review the code/context."
- Tier: Plausible (community report)

**F45.** Harness matters: the same model behaves differently in different agent harnesses, so "model routing" decisions can't be made on model name alone.
- Source: https://news.ycombinator.com/item?id=48688700 (HN)
- Quote (devmor): "Opus via Copilot CLI behaves completely differently from Opus via Claude Code, which behaves differently from Opus via OpenCode or Pi."
- Tier: Plausible (community report)

**F46.** Foreman: self-hosted LLM gateway for cost-aware model routing (HN, 15 points).
- Source: HN (Show HN: Foreman)
- Tier: Plausible (vendor)

**F47.** Local-model "router" pattern from the self-hosting blogosphere: keep a small model always loaded to classify every request and answer the easy ones.
- Source: https://medium.com (The Model Router: Running a Team of Local LLMs Instead of One Big One)
- Quote: "Keep the small model always loaded — it costs 8GB and does two jobs: classifying every request and answering the general ones."
- Tier: Plausible (blog)

**F48.** Academic/secondary claims on cascades: MoT cascade (arXiv 2310.03094, ICLR'24) reports ~40% of the cost at comparable performance; a Stanford study (via neuraltrust) claims up to 98% cost reduction vs always-best-LLM with same output quality.
- Sources: https://arxiv.org/abs/2310.03094 (paper); neuraltrust.com (secondary)
- Tier: Plausible (academic / secondary citation — not independently verified here)

**F49.** r/MachineLearning prompt-routing discussion thread exists (1m2zrpr) — community discussion of routing prompts to different models.
- Source: https://www.reddit.com/r/MachineLearning/comments/1m2zrpr/ (reddit)
- Tier: Plausible (community discussion)

---

## 5. Hermes Agent-specific model-mixing threads (summary)

**F50.** Hermes has a `/switch` (numbered) model-switching mechanism and an open PR to restore/extend it; switching via messaging channels is reported buggy (users fall back to the `hermes model` command on the VPS).
- Sources: https://www.reddit.com/r/hermesagent/comments/1scs3k3/ (Model Switching), https://www.reddit.com/r/hermesagent/comments/1sp1b5i/ (reddit)
- Quote (1sp1b5i): "I had to use the Hermes model command on my VPS."
- Tier: Plausible

**F51.** Switching local models in Hermes requires re-pointing the custom endpoint and re-running; the community-recommended fast path is llama-swap (or llama.cpp's built-in model router with per-task aliases).
- Source: https://www.reddit.com/r/hermesagent/comments/1tyyyry/is_there_any_way_to_switch_local_models_quicker/ (reddit)
- Tier: Plausible

**F52.** Users report the model switcher only switches the primary model (not aux/agent models), and have built skills that switch primary/aux/agents together in plain text.
- Source: https://www.reddit.com/r/hermesagent/comments/1u9k0p9/abandoning_model_switcher_and_just_using_a_skill/ (reddit)
- Tier: Plausible

**F53.** The "autoswitch between models" feature request thread (1u6b0dd) is the central Hermes community thread on this topic: answers are per-profile models, per-subagent models, SOULD.MD defer-to-local prompts, LiteLLM proxy, and llama.cpp router aliases — no built-in automatic routing exists, and several users call it a missing feature.
- Source: https://www.reddit.com/r/hermesagent/comments/1u6b0dd/how_do_you_configure_hermes_to_autoswitch_between/ (reddit)
- Tier: Plausible

---

## 6. Synthesis: what practitioners actually do

1. **Fresh-context delegation beats mid-conversation switching.** The near-universal practitioner pattern is: keep ONE model per session (to preserve prompt cache), and move work to a different model by spawning subagents/fresh sessions (cheap workers) or by handoff artifacts (plan file → cheap executor → expensive reviewer). Nobody reports success from switching the model of an existing long conversation; every source that measures it (F26, F27, F28, F29) shows the switch costs a full cold prefill of the carried context.
2. **Expensive orchestrator + cheap subagents is the default that works**, with per-task pinning (research/search → cheap; implementation/architecture → expensive). Reported savings are real but the quality risk is the cheap model's false reports being trusted by the orchestrator (F4, F5, F6).
3. **Cheap orchestrator + expensive specialist is a minority pattern**, usually as a plan or for bounded tasks; the recurring criticism is that cheap judges under-escalate (F9).
4. **Role-based assignment (Hermes)**: PM/coordinator/cron on cheap (Flash-class or local), architect/engineer on expensive; per-profile and per-subagent model config is the actual mechanism people use (F13–F17, F22).
5. **Cache is the whole game**: with cache reads ~76% of spend (F26), practitioners optimize for cache hits (session stickiness, artifact handoffs, not switching) before optimizing for per-token price. Router products that are stateless are explicitly criticized for causing cache misses (F29, F43).
6. **Local models are used for**: cron/background jobs, web research, file search, summarization/compression, and "90% of tasks" for some users — with API models reserved for deep reasoning, architecture, and anything with long context (F17, F22, F15). Known breakages: approvals on a different model (F16), aux model silently following the expensive primary (F31), agents fabricating delegation calls (F23).
7. **Router products exist** (OpenRouter auto with session stickiness + cost tiers, LiteLLM auto/adaptive routing, workweave/router cache-aware, Foreman) but real-world adoption reports are thin; the strongest community-validated "router" is manual: profiles + subagent model pinning + defer-to-local prompts.

## 7. Searched, found nothing

- No community reports of a working **automatic** cheap→expensive escalation *inside a single Hermes conversation* (the feature-request thread 1u6b0dd confirms it doesn't exist; users use workarounds).
- No quantitative community benchmarks of **local (27B-class) vs API models on identical long-running agent tasks** in Hermes (only qualitative "cost: electricity" reports and one Claude Code 6-task benchmark, F3).
- No X/Twitter threads found with substantive practitioner data on model mixing (searches surfaced only vendor announcements).
- No conference-talk articles specifically on local+API model mixing in agent loops (closest: HN Show HN threads and vendor blogs).
- No user reports of **Anthropic's official model routing** feature in production agent use (the advisor strategy is documented, F37, but no community cost reports found).
- No data on **prompt-cache TTL differences across providers** beyond the 5-minute Anthropic figure mentioned in the HN thread (F29).
