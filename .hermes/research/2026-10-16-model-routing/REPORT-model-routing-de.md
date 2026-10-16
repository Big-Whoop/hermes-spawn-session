# Modell-Mixing in langen Projekten — Deep-Research-Report

**Frage:** Wie setze ich in langen Projekten teurere Modelle (Claude) für komplexe Aufgaben im Orchestrating-Chat ein, **ohne** den Modellwechsel in bestehenden Chats vorzunehmen (teurer Prefill, unterschiedliche Kontextlängen)?

**Setup (lokal verifiziert, 2026-10-16):** Hermes Agent v0.22.2 · Default `claude-opus-5-5` via CLIProxyAPI (Provider `cpa`, ~18 Claude-Modelle) · lokal `Qwen3.8-27B-FP8` (Provider `ryzen`, 262144 ctx, SGLang/llama-swap) und `qwen38vl-27b-kvu` (Provider `llm`) · `prompt_caching.cache_ttl: 1h` · Kompression aktiv (Schwelle 0.75) · `delegation` ohne Modell-Pin.

**Methode:** 5 parallele Research-Lanes (offizielle Docs, GitHub-Issues/PRs, Quellcode-Verifikation, Community/Praxis, Kosten-Mechanik), 38 registrierte Quellen, gestufte Konfidenz (Verified / Plausible / Speculative). Lane-Dateien: `research-model-routing/lane1…lane5`.

---

## TL;DR — Empfehlung

Dein Instinkt ist korrekt und datenbestätigt: Ein Modellwechsel in einem bestehenden Chat bedeutet **100 % Prompt-Cache-Verlust + komplettes Re-Prefill der gesamten Historie** [1][12]. Gemessen in Hermes: 309k-Token-Session nach Switch 220,7 s kalt vs. 8–25 s warm [12]; die Maintainer betrachten die Kosten als inhärent, nicht als Bug [13].

Das von Hermes offiziell empfohlene — und community-seitig bestätigte — Muster ist: **ein Modell pro Chat für dessen Lebensdauer; Arbeit wird über frische Kontexte zum passenden Modell geroutet**:

1. **Subagents (`delegate_task`) mit gepinntem Modell** — `delegation.model`/`delegation.provider` → Massenarbeit läuft auf lokalem Qwen (kostenlos), der Orchestrator-Chat bleibt unangetastet [2][11].
2. **Kanban per-task Model Override** — der einzige native Per-Task-Pin: harte Karten explizit auf `claude-opus-5-5 --provider cpa` [3][37].
3. **Auxiliary-Slots** (Kompression, web_extract, Titel, Kanban-Decomposer, …) → lokal [1][11].
4. **Neuer Chat auf dem passenden Modell + Handover-Datei** — für interaktive komplexe Aufgaben: 5–10k Handover auf Opus ≈ $0,04–0,08, das sind 5–20× günstiger als ein 100k-Chat umzuprefillen [5][21][22].

Konkreter Config-Vorschlag für dein Setup: Abschnitt 4.1 (**nicht angewendet — braucht deine Bestätigung**).

---

## 1. Warum Umschalten teuer ist (Mechanik + Zahlen)

### 1.1 Mechanik

- Der Anthropic-Prompt-Cache ist **content-addressed** (Hash des Präfixes bis zum `cache_control`-Breakpoint) und **modell-spezifisch**: der gecachte KV-State gehört zu den Gewichten des Modells, ein für Opus geschriebener Eintrag ist für Sonnet nicht lesbar [21]. (Dass „Modellwechsel" selbst als Invalidierungsgrund gilt, steht nicht wörtlich in der Anthropic-Tabelle — die Mechanik ist schlüssig abgeleitet; die Hermes-Docs bestätigen explizit, dass Caches „keyed to the model" sind [1].)
- Hermes **rebuildet beim `/model`-Switch den System-Prompt** (Modellname im Trailer + modellabhängige Guidance-Blöcke) → die Präfix-Bytes ändern sich → kompletter Cache-Miss im nächsten Turn, obwohl die Historie unverändert bleibt [1][12].
- Ein **Provider-Wechsel** (z. B. `cpa` → OpenRouter) wechselt zusätzlich in einen anderen Cache-Store überhaupt [13].
- Seit v0.17.0 sitzt der volatile Identity-Block (`Model:`/`Provider:`) in den letzten ~86 Zeichen des System-Prompts, direkt vor der Historie — jede Byte-Änderung invalidiert den Cache für die **gesamte** nachfolgende Historie [12].

### 1.2 Zahlen (100k-Token-Chat, Anthropic-Listenpreise [21][22])

| Aktion | Einmalkosten |
|---|---|
| Switch auf Sonnet 5.5 (Re-Prefill) | $0,20–0,40 |
| Switch auf Opus 5.5 | $0,40–0,80 |
| Switch auf Haiku 5.5 (>100k-Tarifstufe) | $0,50–1,00 |
| **Bleiben auf Opus 5.5, warmer 1h-Cache (deine Config)** | **≈ $0,02/Turn** |
| **Neue Session + 5–10k Handover auf Opus** | **$0,04–0,08** |

- Break-even Opus→Sonnet: **20–40 Turns** — kurzfristige Downgrades lohnen sich nie [21][22].
- Amüsantes Detail: Bei 100k Historie ist der Switch **aufwärts** auf Opus ($0,40–0,80) günstiger als **abwärts** auf Haiku ($0,50–1,00, wegen der >100k-Tarifstufe) [21][22].
- Community-Messung: Cache-Reads sind ≈ **76 % der Kosten** in langen Agent-Sessionen — der Cache ist der Kostentreiber, nicht der Token-Preis [32].

### 1.3 Kontextlängen

- Das aktuelle Claude-Lineup (5.x-Generation: Opus/Sonnet/Haiku 5.5, Opus 4.8 u. a.) hat **1M Kontextfenster als Default** [23][24] → Claude↔Claude-Switches haben kein Fenster-Problem.
- Qwen3.8-27B: **256k** (lokale Tatsache). Overflow → HTTP 400 „prompt is too long", **keine stille Trunkierung** [23]. Hermes reagiert mit **Preflight-Kompression** vor dem API-Call (quellcode-verifiziert, Lane 3); bei deaktivierter Kompression: Warnung + fail-closed.
- Fazit: Das Kontextlängen-Argument gegen Umschalten wirkt vor allem in Richtung **Claude→lokal (256k)** — und die Preflight-Kompression auf Opus wäre selbst ein Kostenfaktor (daher: Kompression auf lokal pinnen, s. 4.1).

---

## 2. Optionen-Matrix (alle machbaren Wege, gerankt)

| # | Option | Mechanismus | Konfidenz | Trade-offs |
|---|---|---|---|---|
| O1 | **Subagents mit gepinntem Delegation-Modell** | `delegation.model/provider/base_url` in config.yaml; alle `delegate_task`-Kinder laufen auf dem Pin mit **frischem Kontext** (nur goal+context, keine Parent-Historie) [2][11] | Verified (Docs + Quellcode + Community) | Globaler Pin, **kein Per-Task-Parameter** [2][14]; Kinder-Cache-TTL auf 5m geklemmt (Quellcode); Orchestrator muss gute goal/context-Briefs schreiben |
| O2 | **Kanban per-task Model Override** | `hermes kanban create … --model X --provider Y` oder `hermes kanban set-model`; Worker spawnen als `hermes -p <assignee>` mit eigenem Profil-Modell [3][37] | Verified | Einziger **nativer Per-Task-Pin**; schwerere Maschinerie (Board, Worktree, PR); durable/resumable/auditierbar [3] |
| O3 | **Neuer Chat auf dem passenden Modell + Handover** | Desktop-Composer-Picker pro neuem Chat (schreibt nie das Profil-Default) [5]; Kontext via Handover-Datei, @-References (CLI) [9], `session_search` [10] | Verified | Nur der Handover-Inhalt überlebt; 5–10k Prefill statt 100k [21][22]; Docs empfehlen explizit: „on a long chat, a fresh chat on the new model is often cheaper" [5] |
| O4 | **Auxiliary-Slots auf billige Modelle** | 11 Slots (compression, vision, web_extract, approval, title_generation, kanban_decomposer, triage_specifier, …), jeder unabhängig übersteuerbar [1][11] | Verified | Kein Einfluss auf Chat-Modell/Cache; Side-Jobs kosten dann Bruchteile [1] |
| O5 | **Profile pro Modell-Tier** | Eigenes `config.yaml` + Modell pro Profil; `hermes -p <name> chat -q „…"` One-Shots [4] | Verified | Volle Isolation (eigene Sessions/Memory/Skills); mehr Verwaltung; gut für dauerhafte „Opus-Workspace"-Profile |
| O6 | **`/model --once` (One-Turn-Eskalation)** | Ein-Turn-Switch mit Auto-Restore, nichts persistiert [1][6] | Verified (mit Caveats) | **Doppelter Cache-Break** (hin und zurück) [1]; offener Bug: veraltete Identity-Note nach Restore [18]; nur für kurze Sessions / cheap→expensive Eskalation sinnvoll [1] |
| O7 | **MoA-Presets (Mixture of Agents)** | Benannte Presets mischen Provider/Modelle (Reference-Modelle + Aggregator); `/moa` One-Shot restauriert das vorherige Modell; bricht den Haupt-Chat-Cache nicht [8] | Verified | Mehrere Modelle pro Turn = höherer Kosten pro Turn; Nische („zweite Meinung"), kein Task-Router [8] |
| O8 | **`channel_overrides` (Gateway)** | Pro Channel anderes Modell/System-Prompt aus einem Gateway (z. B. Telegram-Channel lokal, anderer Channel Opus); Priorität: Session-`/model` > Channel > Global [7] | Verified | Nur für Gateway-Chats, nicht für Desktop-Chats |
| O9 | **Nicht-nativ: Plugins/Router** | `omh` (per-lane Routing), `hermes-advisor` (billiger Executor + Opus-Advisor, **kein Modellwechsel**, Cache bleibt warm) [33], LiteLLM/llama.cpp-Router-Aliases [29]; OpenRouter Auto-Router mit Session-Stickiness als Referenz [34] | Plausible (Drittanbieter, nicht unabhängig verifiziert) | Kein nativer Per-Turn-Router in Hermes: `smart_model_routing` wurde entfernt, PRs offen/needs-decision [19]; `/expert`-Preset wurde abgelehnt („not planned") [20] |
| O10 | **`/model` mitten im Chat (Anti-Option)** | In-place-Swap, Konversation bleibt erhalten [1] | Verified | 100 % Cache-Loss + volles Re-Prefill [1][12]; gemessen 220,7 s vs. 8–25 s bei 309k [12]; Maintainer: inhärent [13]; bei >100k Kontext fragt Hermes ohnehin um Bestätigung (`model.switch_context_confirm_tokens`, Default 100k) [1] |

**Ranking für dein Szenario:** O1 + O2 + O4 als Grundgerüst (konfigurierbar, dauerhaft), O3 für interaktive Spitzenaufgaben, O5 optional für dauerhafte Tier-Trennung, O6 nur in kurzen Sessions, O7/O8/O9 situativ.

---

## 3. Was die Community in der Praxis macht

- **Dominantes Muster: teurer Orchestrator + billige Subagents.** „Opus as the orchestrator with aggressive delegation to Sonnet and Haiku is probably the most efficient way to use the models" [25]. Spar-Mechanik: Datei-Reads/Search-Outputs der Subagents bleiben in ihrem eigenen Kontext, nur die Summary kommt zurück — der teure Kontext wächst langsam [26].
- **Gemessener 6-Task-Benchmark** (Einzeluser, aber gemessen): Code-Search — Haiku 44/48 Dateien für $0,44 vs. Opus 45/48 für $6,17 (gleiche Qualität, 14× günstiger); Web-Research/Fact-Checking dagegen klar Opus [27].
- **Artifact-Handover** als cache-freundliche Alternative zum Umschalten: teures Modell schreibt Plan-Datei, billiges Modell führt in eigener Session aus (99,9 % Cache-Hits berichtet), teures Modell reviewt das Artefakt [31].
- **Hermes-spezifisch:** Rolle-basierte Modell-Zuweisung — PM/Koordinator/Cron auf billig (Flash-Klasse oder lokal), Architekt/Engineer auf teuer: „using an expensive model for project management is mostly a waste" [28]; Mechanismen der Leute: Per-Profil-Modelle, Per-Subagent-Modelle, „defer to local"-Prompt im SOUL.md, LiteLLM-Proxy, llama.cpp-Router-Aliase [29]. Bekannte Bruchstellen: **Approvals auf anderem Modell** („The only thing I've noticed that really breaks") [30], **Aux-Modell folgt still dem teuren Primary** und bläst das Budget [38].
- **Router-Produkte:** OpenRouter Auto-Router (Task-Klassifikation + **Session-Stickiness**, um Multi-Turn-Consistency und Cache zu halten) [34]; workweave/router (cache-aware, 40 % Ersparnis Vendor-Claim, Subagents mit frischem Kontext werden unabhängig geroutet) [31]; hermes-advisor (Opus-Advisor auf harten Turns, **ohne Modellwechsel**, Cache bleibt warm) [33]. In Hermes selbst existiert **kein** nativer Per-Turn-Router [19].
- **Konsens:** Niemand berichtet Erfolg vom Umschalten eines bestehenden langen Chats; alle Messungen zeigen, dass der Switch ein volles Cold-Prefill der mitgeführten Historie kostet [25][31][32].

---

## 4. Konkrete Empfehlung für dein Setup

### 4.1 Config-Vorschlag (VORSTELLUNG — nicht angewendet, braucht deine Bestätigung)

```yaml
delegation:
  model: model        # Modell-ID deines ryzen-Providers (Qwen3.8-27B-FP8)
  provider: ryzen     # lokal, kostenlos
  max_iterations: 250

auxiliary:
  compression:
    provider: ryzen
    model: model
  web_extract:
    provider: ryzen
    model: model
  title_generation:
    provider: ryzen
    model: model
  kanban_decomposer:
    provider: ryzen
    model: model
  triage_specifier:
    provider: ryzen
    model: model
```

Begründung und Randbedingungen:

- **`delegation` → lokal:** Alle `delegate_task`-Kinder laufen dann kostenlos auf Qwen mit frischem Kontext; der Chat-Modell und Cache bleiben unangetastet [2][11]. Das ist exakt das von den Docs sanktionierte Muster „frontier planner, inexpensive workers" [2].
- **`auxiliary.compression` → lokal:** Kompression auf Opus „burnt reasoning tokens … just to summarize context — 1/50th the cost" auf einem schnellen Modell [1]. Bei dir aktuell `auto` = Main-Modell = Opus → das ist ein echter Kosten-Leak.
- **`auxiliary.vision`** ist bereits auf ryzen gerichtet (beibehalten).
- **`auxiliary.review`** (Reviewer für `/review`) bewusst **nicht** auf lokal pinnen — Qualitätstor bleibt auf dem Main-Modell [2]; und **Approvals** nicht auf ein anderes Modell (Community-Bruchstelle) [30].
- Alternative für `delegation`: Provider `llm` (`qwen38vl-27b-kvu`) — je nachdem, welches lokale Modell du für Subagent-Arbeit lieber hast.

### 4.2 Workflow für lange Projekte

| Aufgabenart | Wo | Modell |
|---|---|---|
| Planung, Architektur, Review, hartes Debugging | **Opus-Chat** (neuer Chat, Composer-Picker) | `claude-opus-5-5` |
| Tagesgeschäft, Recherche, Zusammenfassungen, Execution | **Lokaler Chat** (wie dieser) | Qwen3.8-27B |
| Parallele/durable Arbeit | Kanban-Karten | günstig: lokal; hart: `--model claude-opus-5-5 --provider cpa` [3] |
| Massen-Subtasks (Recherche, Datei-Scans, Tests) | `delegate_task` | lokal (gepinnt) [2] |
| Seltenes hartes Subtask im lokalen Chat | Kanban-Karte mit Opus-Pin **oder** neuer Opus-Chat + Handover-Datei | Opus [3][5] |

- **Kontextübergabe:** Handover-Dateien (dein bestehendes `HANDOVER-orchestrator-*.md`-Muster), @-References in der CLI [9], `session_search` für Recall über alle Sessions [10], Kanban-Parent-Links tragen die Parent-Summary automatisch in die Child-Karte [3].
- **Reasoning-Effort als cache-sicherer Hebel:** `reasoning_effort` lässt sich ohne Modellwechsel ändern; Community-Messung: effort-only-Switching erhält den Cache auf 5.5-Modellen (Ø 20 % Ersparnis) [32]. Caveat: die Anthropic-Invalidierungstabelle listet `output_config.effort` als Message-Block-Invalidator [21] → möglicher teilweiser Verlust; Plausible.
- **Warum nicht einfach „Opus-Chat als Default behalten"?** Geht auch (das ist die O1-Variante mit Opus-Orchestrator) — aber dein Default ist bereits Opus und du hast diesen Chat bewusst auf lokal gestellt; der obige Workflow nutzt beides: Opus nur dort, wo Urteil zählt, Volumen auf lokal.

### 4.3 Wann `/model --once` trotzdem sinnvoll ist

One-Turn-Eskalation mit Auto-Restore („ask Opus just this once") [1][6] — aber: doppelte Cache-Break (hin und zurück) [1] und offener Identity-Note-Bug nach Restore [18]. In einem langen, gecachten Chat kann der Side-Question **mehr kosten als sparen** [1]. Nur für kurze Sessions oder bewusste cheap→expensive-Eskalation verwenden.

---

## 5. Fallstricke (dein Setup)

1. **Bare-Name-`/model` = Billing-Gefahr** (Issue #132117, offen, P2): Wechselt ein konfigurierter Provider dasselbe Modell-ID wie ein OpenRouter-Slug zu deklarieren, wird der Switch **stillschweigend auf OpenRouter (abgerechnet) umgeleitet** — ohne Warnung. Dein `ryzen`-Provider hat exakt die Form des Reproduktionsfalls (Qwen3.8, `context_length: 262144`). → Immer `provider:model`-Syntax verwenden [16].
2. **Caching auf dem cpa-Pfad verifizieren:** CLIProxyAPI injiziert `cache_control`-Breakpoints executor-seitig (Pass-through-Architektur), OAuth-Credentials werden auf 1h-TTL upgraded [35]. Aber Issue #2419: `cached_tokens` wird **nicht** in die OpenAI-Usage-Response übersetzt → Cache-Hits sind im OpenAI-Protokoll unsichtbar [36]. Historisch waren Custom-Provider sogar komplett vom Caching ausgeschlossen (#8294, gefixt) [17]. → Cache-Hits auf der Anthropic-Seite (Usage-Felder) prüfen.
3. **Orchestrator vertraut Subagent-Reports blind:** „If a Sonnet/Haiku subagent reports something clearly false, I'm pretty sure Opus will also get it wrong" [25]. Wichtige Claims verifizieren; `/review` auf Opus lassen [2].
4. **`delegate_task` hat keinen Per-Task-Modell-Parameter** — in Docs und Quellcode verifiziert; ~10 Issues, 6+ unmerged PRs (inkl. einem Branch von teknium1), Maintainer zu einigen Shapes: „We do not want this" [2][14][15]. Bis dahin: Kanban-Pin (O2) oder neuer Chat (O3).
5. **256k-Fenster lokal:** Lange lokale Chats können overflowen → 400 statt Trunkierung [23]; die Preflight-Kompression fängt es — deshalb gehört Kompression auf lokal gepinnt (4.1).
6. **`context_length`-Pins sind eine bekannte Mine** über Switches hinweg (Bug-Familie: #130318 offen, #15779 gefixt — Details in `lane2-github.md`): die pro-Modell-Deklaration unter `custom_providers[].models.<id>.context_length` (wie bei dir) ist der unterstützte Weg.

---

## 6. Was auf deinem exakten Target ungetestet bleibt

- **Echte Cache-Hits auf dem cpa-Pfad** — nicht gemessen; Sichtbarkeits-Bug #2419 [35][36].
- **Qualität von Qwen3.8-27B-FP8 für agentische Subagent-Arbeit** — kein gemessener Benchmark für dein Modell (der 6-Task-Benchmark ist Haiku 5.5) [27]; Community-Erfahrungen mit 27B-Klasse sind qualitativ positiv („Cost: electricity") [29].
- **Quellcode-Verifikation lief auf `main`** (vor deinem v0.22.2); Verhalten kann minimal abweichen (Lane 3).
- **„Modellwechsel invalidiert den Cache"** steht nicht wörtlich in den Anthropic-Docs (Mechanismus-Ableitung) [21]; die Hermes-Docs und die Messung bestätigen den Effekt [1][12].

---

## Methodik & Lane-Dateien

| Lane | Datei | Inhalt |
|---|---|---|
| 1 | `lane1-hermes-docs.md` | 40+ Findings aus offiziellen Docs (Modell-Wechsel, Delegation, Kanban, Profile, Desktop, MoA, Context-Transfer) |
| 2 | `lane2-github.md` | Issues/PRs: Switch-Kosten (#126068), Per-Task-Modell-Cluster, Cache-Bugs, Context-Length-Bug-Familie, Router-Features |
| 3 | `lane3-source.md` | Quellcode-Verifikation: `/model`-In-place-Swap, System-Prompt-Rebuild, Session-Modell in state.db, Delegation-Resolution, Cache-TTL-Policy, Preflight-Kompression |
| 4 | `lane4-community.md` | 53 Findings: Reddit/HN/Blogs — dominante Muster, Benchmarks, Hermes-spezifische Praxis, Router-Produkte |
| 5 | `lane5-cost-mechanics.md` | 15 Findings: Anthropic-Caching-Mechanik, Preise, Kontextfenster, Worked Examples, CLIProxyAPI-Caching |

Tier-Schema: **Verified** = autoritative Quelle gelesen (Docs/Vendor/Code) · **Plausible** = schlüssige Mechanik oder Community-Report · **Speculative** = Einzel-Anekdote.
## Sources

[1] https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models — Hermes Docs: Configuring Models
[2] https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation — Hermes Docs: Delegation
[3] https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban — Hermes Docs: Kanban Multi-Agent
[4] https://hermes-agent.nousresearch.com/docs/user-guide/profiles — Hermes Docs: Profiles
[5] https://hermes-agent.nousresearch.com/docs/user-guide/desktop — Hermes Docs: Desktop
[6] https://hermes-agent.nousresearch.com/docs/reference/slash-commands — Hermes Docs: Slash Commands
[7] https://hermes-agent.nousresearch.com/docs/user-guide/messaging — Hermes Docs: Messaging
[8] https://hermes-agent.nousresearch.com/docs/user-guide/features/mixture-of-agents — Hermes Docs: Mixture of Agents
[9] https://hermes-agent.nousresearch.com/docs/user-guide/features/context-references — Hermes Docs: Context References
[10] https://hermes-agent.nousresearch.com/docs/user-guide/sessions — Hermes Docs: Sessions
[11] https://hermes-agent.nousresearch.com/docs/user-guide/configuration — Hermes Docs: Configuration
[12] https://github.com/NousResearch/hermes-agent/issues/126068 — Issue #126068: Model switch forces full cold re-read
[13] https://github.com/NousResearch/hermes-agent/pull/128757 — PR #128757: say what a model switch costs
[14] https://github.com/NousResearch/hermes-agent/issues/111545 — Issue #111545: per-role delegation profiles / per-task model status
[15] https://github.com/NousResearch/hermes-agent/issues/10995 — Issue #10995: per-task model selection (closed)
[16] https://github.com/NousResearch/hermes-agent/issues/132117 — Issue #132117: bare-name model switch hijacked to OpenRouter
[17] https://github.com/NousResearch/hermes-agent/issues/8294 — Issue #8294: prompt caching for custom Anthropic-compatible providers
[18] https://github.com/NousResearch/hermes-agent/issues/127879 — Issue #127879: /model --once stale identity note
[19] https://github.com/NousResearch/hermes-agent/issues/123388 — Issue #123388: pluggable per-turn model router
[20] https://github.com/NousResearch/hermes-agent/issues/20249 — Issue #20249: Model Presets /expert (not planned)
[21] https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching — Anthropic Docs: Prompt Caching
[22] https://www.anthropic.com/pricing — Anthropic Pricing
[23] https://docs.anthropic.com/en/docs/build-with-claude/context-windows — Anthropic Docs: Context Windows
[24] https://docs.anthropic.com/en/docs/about-claude/models/overview — Anthropic Docs: Model Overview
[25] https://www.reddit.com/r/ClaudeCode/comments/1ruuzdg/opus_as_the_orchestrator_with_aggressive — Reddit r/ClaudeCode: Opus orchestrator + aggressive delegation
[26] https://www.reddit.com/r/ClaudeAI/comments/1x1buac/how_much_more_effectivebetter_is_using_opus_55 — Reddit r/ClaudeAI: Opus 5.5 subagent savings
[27] https://www.reddit.com/r/ClaudeCode/comments/1x1e7ts/i_tested_haiku_55_sonnet_55_and_opus_55_as — Reddit r/ClaudeCode: 6-task Haiku/Sonnet/Opus benchmark
[28] https://www.reddit.com/r/hermesagent/comments/1u0xpb6/looking_for_a_costeffective_ai_setup_for_hermes — Reddit r/hermesagent: cost-effective setup
[29] https://www.reddit.com/r/hermesagent/comments/1u6b0dd/how_do_you_configure_hermes_to_autoswitch_between — Reddit r/hermesagent: autoswitch between models
[30] https://www.reddit.com/r/hermesagent/comments/1sfvp3o/model_switching_on_subagent_delegation — Reddit r/hermesagent: model switching on subagent delegation
[31] https://news.ycombinator.com/item?id=48688700 — HN: workweave/router cache-aware model routing
[32] https://www.reddit.com/r/ClaudeCode/comments/1x19b2c/i_built_a_claude_code_mod_on_haiku_55_or_jev_that — Reddit r/ClaudeCode: cache reads 76% of cost
[33] https://github.com/superlowburn/hermes-advisor — GitHub: hermes-advisor (cheap executor + Opus advisor)
[34] https://openrouter.ai/docs/guides/routing/routers/auto-router — OpenRouter Docs: Auto Router
[35] https://github.com/router-for-me/CLIProxyAPI/issues/5557 — CLIProxyAPI #5557: cache_control injection
[36] https://github.com/router-for-me/CLIProxyAPI/issues/2419 — CLIProxyAPI #2419: cached_tokens not translated
[37] https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban-worker-lanes — Hermes Docs: Kanban worker lanes
[38] https://www.reddit.com/r/hermesagent/comments/1u9k0p9/abandoning_model_switcher_and_just_using_a_skill — Reddit r/hermesagent: abandoning model switcher / aux follows primary
