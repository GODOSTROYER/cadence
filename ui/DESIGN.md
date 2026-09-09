# Cadence — UI design brief

**Cadence** is the dashboard and playground for an evaluated AI support agent built on @SpotifyCares
conversations. Its job: let a sceptical reviewer (a Hiver engineer) understand in two minutes what the
agent does, how well it does it, and where it fails — and then poke at it.

## Direction: "editorial mission control"

Quiet, dark, precise. A music magazine's typography meeting an observability console. The honesty of the
evaluation is the product, so the design foregrounds numbers *and their caveats* with equal weight.
Anti-references: generic SaaS admin templates, purple gradients, glassmorphism everywhere, bouncy emoji UI,
"AI sparkles". No stock illustrations.

## Tokens (CSS custom properties on `:root`, dark only)

```
--bg:        #0B0C0F   page ground (near-black, faint blue)
--surface:   #12141A   panels
--surface-2: #191C24   hover / nested
--border:    rgba(255,255,255,0.08)   hairlines everywhere instead of drop shadows
--text:      #ECEDEF
--muted:     #8B8F98
--faint:     #5B5F69
--green:     #1ED760   auto_handle, success, primary CTA  (Spotify green, used sparingly)
--amber:     #F5B841   escalate, warnings
--rose:      #FF5C77   failures, reject, missed escalations
--sky:       #6CB6FF   judge / information
--violet:    #A78BFA   baselines
--grain:     subtle SVG noise overlay at 3–4% opacity on the page ground
```
Intent colours: assign each intent id a stable hue from a muted 11-step palette (defined once in `src/lib/intents.ts`).

## Typography (Google Fonts, with real fallbacks)

- Display: **Instrument Serif** (regular + italic) — page titles, section headers, and the big metric numerals.
  Italic for the product name and for "voice" moments (the tagline, the misleading-numbers callout title).
- UI/body: **Geist** (fallback Inter, system-ui) — 14px base, 1.5 line-height.
- Mono: **Geist Mono** (fallback JetBrains Mono, ui-monospace) — ids, intent ids, thread ids, timestamps, code, numbers in tables.
- Scale: 12 / 13 / 14 / 16 / 20 / 28 / 40 / 64 / 96. Letter-spacing −0.01em on ≥28px.

## Layout

- Left sidebar (240px, collapses to 64px icon rail under 1100px, drawer under 768px): logo wordmark "Cadence" in italic serif,
  nav items with lucide icons, footer status chips (API key: live / cache-only / static; agent model; judge model).
- Top of each page: eyebrow label (mono, muted) + serif title + one-sentence description.
- Content max-width 1280px, 32px padding, 24px grid gaps. Prefer hairline-bordered regions over floating cards.
- Tables: sticky header, mono numerals, row hover `--surface-2`, zebra off.

## Components (in `src/components/`)

MetricTile (serif numeral 64px, label, CI or delta subtitle, optional sparkline), IntentBadge (dot + mono id + name),
DecisionPill (green auto_handle / amber escalate + reason on hover), ConfidenceBar, TweetBubble (customer message
styled like a tweet: avatar circle, "@customer", relative date), ReplyPreview (280-char tweet composer look, char
counter, copy button, "/AI" signature), EvidenceCard (customer text → brand reply, BM25 score, thread id, resolved
links, "cited" marker), StepTimeline (rules → retrieve → LLM → decide with ms and status), ConfusionMatrix (heatmap
cells with hover tooltip: gold→pred count and examples), F1Bars (per-intent horizontal bars with CI whiskers),
ScoreDistribution (stacked 1–5 bars per system, per dimension), AgreementScatter (human vs judge with jitter +
identity line), ThresholdChart (recall vs auto-handle rate line with the chosen threshold marked), DataTable
(sortable/filterable, keyboard rows), Drawer (right-side detail panel), Callout (the "misleading" box: amber
hairline, italic serif title), Kbd, Toast, EmptyState, Skeleton.

## Motion (framer-motion, honour `prefers-reduced-motion`)

Page enter: fade + 8px rise, 200ms. Lists: stagger 30ms. Metric numerals: count-up 600ms ease-out on first view.
Agent run: StepTimeline steps light up sequentially; the reply types in at ~8ms/char (click to skip).
Hover states: 120ms color transitions only, no scale bounces.

## Pages

1. **Overview `/`** — hero (italic serif "Cadence", tagline "An evaluated AI support agent for @SpotifyCares",
   dataset facts line); four headline MetricTiles (intent macro-F1 with CI, escalation recall, auto-handle rate,
   judge overall vs nearest-neighbour baseline); directly beneath, the Callout **"What is misleading about these numbers"**
   with 4–5 bullets pulled from results; a baseline comparison strip (agent vs trivial vs simple per task); CTA to the playground.
2. **Agent Playground `/agent`** — tweet composer textarea (280 counter), six example chips (real golden messages,
   varied intents), Run button. Result grid: left = decision header (IntentBadge + ConfidenceBar, sentiment chip,
   DecisionPill with reason sentence, rule flags as mono tags), ReplyPreview, grounding notes; right = EvidenceCards
   (cited ones highlighted), StepTimeline with latencies, model/cached chips. Static mode: chips replay recorded runs,
   free text disabled with an explanatory EmptyState.
3. **Evaluation `/eval`** — tabs Intent / Escalation / Reply quality / Judge agreement. Intent: system switcher
   (agent + 4 baselines), ConfusionMatrix, F1Bars, per-class table. Escalation: per-system PR tiles, ThresholdChart,
   the list of *missed escalations* (rose) with text and gold reason. Reply quality: ScoreDistribution per dimension,
   ship-rate tiles, flag-rate table, pairwise win-rate. Judge agreement: κ / ρ / exact / within-1 tiles,
   AgreementScatter, per-dimension table, protocol note.
4. **Golden Explorer `/golden`** — DataTable (id, text preview, gold intent, predicted intent ✓/✗, gold vs predicted
   decision, judge overall, split) with filters (intent, split, correct/incorrect, decision) + search (⌘K). Row →
   Drawer: full text, historical brand reply + thread, gold labels with annotator A/B and adjudication note,
   agent output (reply, evidence, reason), judge rationale per system.
5. **Failure Modes `/failures`** — five numbered editorial sections: title, count/share, hypothesis, 2–3 real
   examples (TweetBubble + gold vs predicted + what went wrong), proposed fix.
6. **Rate `/rate`** — blind human rating flow: one (message, reply, evidence) at a time; system identity hidden;
   five 1–5 segmented controls (keyboard 1–5 + Tab), three flag toggles, verdict, rationale; progress "12 / 60";
   POST to `/api/ratings`. Static mode: explain the protocol, disabled.
7. **Decisions `/decisions`** — numbered decision log, decision in text colour, "why" in muted.
8. **Method `/method`** — data facts, pipeline diagram (inline SVG: message → rules → BM25 retrieval → Gemini →
   decision), intent taxonomy table, escalation policy table, judge rubric, reproduce-in-15-minutes steps.

## Data layer

`src/lib/types.ts` mirrors CONTRACT.md §6–§9. `src/lib/api.ts` exposes `getHealth, getResults, getFailures, getGolden,
getGoldenById, handle(text), getRatingQueue, postRating, getDecisions`. Static mode when
`import.meta.env.VITE_STATIC === '1'`: fetch `${import.meta.env.BASE_URL}data/<name>.json`; `handle()` resolves from
`golden_merged.json` by exact text match, otherwise throws a typed `StaticModeError`.
`public/data/*.json` ships **realistic mock data that matches the schema exactly** so the UI is complete before
real results exist (real Spotify-style messages; no lorem ipsum). The export script overwrites them later.

## Accessibility & quality bar

WCAG AA contrast, visible focus rings (2px green), every chart has a table alternative or aria-label summary,
keyboard-navigable tables and rating flow, no layout shift on data load (skeletons sized like content),
`npm run build` clean with zero TypeScript errors, Lighthouse a11y ≥ 95.
