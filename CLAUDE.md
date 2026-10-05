# Complaint Radar: build instructions for Claude Code

Read this whole file before writing code. It is the source of truth for the project.
Work through the milestones in order, verify each one before starting the next, and
keep this file updated if a decision changes.

## 1. What we are building

Complaint Radar is an AI-native early-warning system for consumer finance risk. It reads
real consumer complaints about financial companies, finds issues that are accelerating
before they become regulatory or reputational problems, explains the likely root cause,
and has a skeptic agent reject weak signals.

It is a portfolio prototype for a Deloitte AI interview (financial services sector,
risk and regulatory advisory). The deliverable is a GitHub repo, a deployed demo, and a
3-minute recording. Optimize for: a memorable visual, real data, visible AI reasoning,
honest evaluation, and clean code a reviewer can read.

### The story the demo tells

In August 2026 the CFPB stopped publishing complaint narratives and visualizations in
its public Consumer Complaint Database. It still collects complaints and shares them
with regulators, and it published an archive of complaints received from December 1,
2011 through August 14, 2026. Banks have lost the public early-warning view but
regulators have not. Complaint Radar shows what that view revealed, and how a bank could
run the same radar on its own complaints.

Describe this change neutrally and factually everywhere it appears. The project takes
no position on the policy. Its argument works either way: banks benefit from seeing
their own risks early.

## 2. Hard rules

- **Never fabricate data or results.** Every number in the UI must come from the
  pipeline. If a step has not run, show an empty state that says which command to run.
- **Complaints are unverified allegations.** All copy and prompts call them claims or
  signals, never findings of wrongdoing.
- **Normalize for company size.** Never rank companies by raw complaint count alone.
- **Paraphrase, don't publish narratives.** The UI shows AI-written one-sentence
  summaries plus the CFPB complaint ID, not raw narrative text.
- **Coding style: do not use `break` statements** in any language. Use loop conditions,
  early returns, comprehensions, `iter(callable, sentinel)`, `find`/`some`, or helper
  functions instead.
- Keep secrets in `.env`. Commit `.env.example` only.
- Python 3.11+, type hints everywhere, small modules. TypeScript strict mode.

## 3. Repo layout

```
complaint-radar/
  CLAUDE.md
  README.md                  # pitch, screenshots, how to run, evaluation results
  .env.example
  Makefile                   # make data, make pipeline, make api, make web, make test
  data_spike/                # existing exploration script; keep it, reuse its logic
  backend/
    pyproject.toml
    radar/
      config.py              # settings, model ids, paths (env-overridable)
      llm.py                 # Claude client: structured output, caching, batches
      ingest.py              # download + load + normalize (port from data_spike)
      emergence.py           # statistical acceleration detection
      templating.py          # copy-paste / form-letter detection
      extract.py             # per-narrative AI extraction
      themes.py              # AI consolidation of root causes into themes
      agents/
        analyst.py           # writes the issue brief per cluster
        skeptic.py           # challenges each brief, keep or reject
      lens.py                # per-company view vs peers
      backtest.py            # as-of replay
      evaluate.py            # metrics on extraction and skeptic quality
      export.py              # writes static JSON for the frontend
      api.py                 # FastAPI app
      cli.py                 # `python -m radar.cli <command>`
    tests/
      fixtures.py            # synthetic CFPB-format data generator
      test_*.py
  frontend/
    (Next.js 14 app router, TypeScript)
  data/                      # gitignored: raw/, work/, cache/
  public_data/               # committed: small precomputed JSON for the deployed demo
```

## 4. Data source

- Archive page: https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/
- Files are zips at `https://files.consumerfinance.gov/f/documents/<name>.zip`. The full
  list of export file names is in `data_spike/spike.py` (`EXPORTS`). Reuse it.
- Default window: the `RECENT` exports (September 2025 to August 2026). Backtesting
  needs older exports via `--exports all`.
- The final month is partial (archive stops August 14, 2026). Exclude partial months
  from rate calculations.
- Column names vary. Normalize with the `COLUMNS` alias map from `data_spike/spike.py`.
  Deduplicate on `complaint_id` because exports can overlap.
- Store the normalized table as Parquet in `data/work/complaints.parquet`.

## 5. Pipeline

Run as `python -m radar.cli <step>` or `make pipeline`. Every step reads the previous
step's output from `data/work/`, writes its own, and is safe to rerun. Each step prints
a one-line summary.

### 5.1 ingest
Port `download` and `load` from `data_spike/spike.py`. Stream downloads to disk with a
progress readout. Skip files already present.

### 5.2 emergence (no AI)
- A cluster is a `(product, issue)` pair.
- For the analysis month `M` (default: last full month), compute
  `velocity = (mean of last 3 months + 5) / (mean of prior 6 months + 5)`.
- Keep clusters with recent monthly average >= 30. Rank by velocity.
- Per cluster, store monthly counts for the full window, top states, narrative count,
  and top companies with **lift** = (company share of cluster) / (company share of
  all complaints). Lift > 1 means overrepresented relative to size.
- Accept an `--as-of YYYY-MM` flag so the same code powers backtesting. With `--as-of`,
  ignore all data after that month.

### 5.3 templating (no AI)
Fingerprint narratives: lowercase, remove `XX..` redactions, strip non-letters,
collapse whitespace, hash the first 400 characters. A narrative is templated if its
fingerprint appears 5+ times. Report `templated_share` per cluster over narratives only.

### 5.4 extract (AI, high volume)
- Model: `RADAR_MODEL_FAST` (default `claude-haiku-4-5-20251001`).
- Sample up to `--per-cluster` (default 40) recent narratives from each of the top
  `--clusters` (default 25) clusters.
- Use forced tool use for structured output. Schema (keep these exact field names):
  `root_cause` (short phrase), `root_cause_family` (enum: fees_and_charges,
  disputes_and_errors, fraud_and_scams, access_and_service, credit_reporting_accuracy,
  collections_conduct, servicing_process, disclosure_and_terms, other),
  `journey_stage` (enum: account_opening, everyday_use, payment, dispute, collections,
  closing, other), `harm`, `money_at_stake_usd` (number or null),
  `vulnerable_consumer` (bool), `severity` (1 to 5), `summary` (one neutral sentence,
  no names), `looks_templated` (bool).
- The system prompt must say narratives are unverified allegations and `XXXX` marks
  redactions. Mark it for prompt caching.
- **Cost controls:** cache every result in `data/cache/extractions.jsonl` keyed by
  `complaint_id` and never re-extract a cached ID. Support `--batch` to submit through
  the Message Batches API and poll until done. Support `--dry-run` that prints how many
  calls would be made. Support `--limit N`.

### 5.5 themes (AI)
- Model: `RADAR_MODEL_REASONING` (default `claude-opus-5-5`).
- Per cluster, send all extracted `root_cause` strings and summaries. Ask for 2 to 5
  consolidated themes, each with a label, a one-sentence description, and the
  complaint IDs that belong to it. This is the "AI sees more than the form categories"
  layer, so the UI must show these themes prominently.

### 5.6 analyst agent (AI)
- Model: `RADAR_MODEL_WRITER` (default `claude-sonnet-5-5`).
- Input: the cluster's statistics, lift table, templated share, themes, and sample
  summaries. Output schema: `headline` (plain language for a bank executive),
  `what_is_happening`, `who_is_affected`, `likely_root_cause` (framed as a hypothesis),
  `process_or_control_to_check` (where a bank should look internally),
  `regulatory_area` (a general area such as electronic fund transfer disputes or debt
  collection conduct; do not cite specific rule sections unless certain),
  `evidence` (list of quantified statements drawn only from the input), `confidence`
  (0 to 1).

### 5.7 skeptic agent (AI)
- Model: `RADAR_MODEL_REASONING`.
- Reviews every brief against the same evidence. It must explicitly test:
  1. Size: is the signal explained by a company's overall volume (check lift)?
  2. Templating: is a high `templated_share` driving the spike?
  3. Concentration: is it one state or one company only?
  4. Thin evidence: are there too few narratives to support the root cause?
  5. Seasonality or a known one-off: does the monthly series look like a single blip?
- Output per brief: `verdict` (kept or rejected), `checks` (each check with pass or
  fail and a one-sentence reason), `note` (one sentence for the UI).
- Rejected briefs stay in the data and are shown in the UI as rejected. Showing the
  skeptic at work is a key part of the demo.

### 5.8 lens
For a selected company, compute its clusters with lift and velocity relative to peers
(all other companies). Precompute for the 15 companies with the most complaints.

### 5.9 backtest
- `python -m radar.cli backtest --as-of YYYY-MM --cluster "<product> / <issue>"`
  reruns emergence, extract (cached), analyst, and skeptic using only data up to
  `--as-of`, then reports the cluster's rank and whether a kept brief existed.
- Do **not** choose an enforcement action or claim a result. Store cases in
  `backend/radar/backtest_cases.yaml` with fields `name`, `public_date`, `as_of`,
  `cluster`, `source_url`, and leave the file with one commented example. The user
  will add real cases from the CFPB enforcement actions page and verify them.
- Report outcomes honestly, including misses.

### 5.10 evaluate
- **Extraction check:** export 50 random extractions with their narratives to
  `data/work/review_sheet.csv` with blank columns for a human rating (accurate,
  partially, wrong). `evaluate` reads the filled sheet and reports accuracy.
- **Skeptic check:** report kept and rejected counts and the most common failed checks.
- **Stability check:** rerun themes on one cluster twice and report label overlap.
- Write results to `data/work/evaluation.json`. The UI and README read from there.

### 5.11 export
Write `public_data/` with small JSON files the frontend can serve statically:
`radar_<YYYY-MM>.json` for each month in the window, `cluster_<id>.json`,
`lens_<company-slug>.json`, `backtests.json`, `evaluation.json`, and `meta.json`
(source, window, generated time, model ids). Keep the total under 20 MB.

## 6. Data contract

`radar_<YYYY-MM>.json`:
```json
{
  "month": "2026-07",
  "clusters": [{
    "id": "a1b2c3d4e5",
    "product": "Money transfer, virtual currency, or money service",
    "issue": "Fraud or scam",
    "product_family": "payments",
    "velocity": 2.9,
    "recent_monthly_avg": 415,
    "baseline_monthly_avg": 140,
    "severity": 3.8,
    "templated_share": 0.04,
    "vulnerable_share": 0.21,
    "narrative_count": 1210,
    "themes": [{"label": "...", "description": "...", "share": 0.42}],
    "top_companies": [{"name": "...", "count": 947, "lift": 2.1}],
    "states": {"CA": 120},
    "months": [{"month": "2025-09", "count": 130}],
    "brief": {"headline": "...", "confidence": 0.8},
    "skeptic": {"verdict": "kept", "note": "..."}
  }]
}
```
`cluster_<id>.json` holds the full brief, all skeptic checks, themes with example
summaries and complaint IDs, and the state map data. Define matching TypeScript types
in `frontend/lib/types.ts` and Pydantic models in `backend/radar/schemas.py`. Keep
them in sync.

`product_family` maps CFPB products into 6 to 8 radar sectors: banking (checking,
savings), cards, credit_reporting, debt_collection, lending (mortgage, auto, personal,
student), payments (money transfer, prepaid, virtual currency), other.

## 7. API

FastAPI in `backend/radar/api.py`. It serves the same shapes as `public_data/`.
- `GET /api/health`
- `GET /api/meta`
- `GET /api/radar?month=YYYY-MM`
- `GET /api/clusters/{id}`
- `GET /api/companies` (list for the lens picker)
- `GET /api/companies/{slug}`
- `GET /api/backtests`
- `GET /api/evaluation`

CORS for `http://localhost:3000`. The frontend uses `NEXT_PUBLIC_API_URL` when set and
otherwise reads `public_data/` (copied to `frontend/public/data/` at build time). The
deployed demo runs with static files only, so no API key is ever exposed.

## 8. Frontend

Next.js 14 (app router), TypeScript strict, plain CSS modules or a single tokens file.
No component kit. Render the radar in SVG for crisp text, with a canvas layer only if
performance requires it.

### Visual direction
The radar is one instrument sitting on a calm, light page. It is not a dark-mode
dashboard, and it must not use the cliché green phosphor look.
- Page: fog grey `#ECEFEE`, text ink `#1D2B33`, secondary text `#5A6B73`.
- Scope surface: deep teal ink `#102A35`, ring lines `rgba(204,226,224,0.18)`.
- Sweep arm: pale sea glass `#CCE2E0` fading to transparent.
- Severity scale for blips: `#9FC9C0` (low), `#E8B04A`, `#E5793B`, `#C8402F` (high).
- Rejected clusters: hollow grey outline `#8A979D`.
- Type: one sans family for UI (e.g. Instrument Sans) and one serif for brief prose
  (e.g. Source Serif 4), loaded from Google Fonts with system fallbacks. Sentence case.
  No all-caps labels.
- Spend motion in one place: the sweep. Everything else is still unless the user acts.

### Layout
```
+--------------------------------------------------------------+
| Complaint Radar           [ Bank lens: All companies v ]     |
+-------------------------------------+------------------------+
|                                     |  Brief panel           |
|            RADAR SCOPE              |  (cluster headline,    |
|        (square, max 640px)          |   themes, evidence,    |
|                                     |   skeptic checks,      |
|                                     |   state map, trend)    |
+-------------------------------------+------------------------+
|  Month slider  Sep 2025 ......................... Aug 2026   |
+--------------------------------------------------------------+
```
On narrow screens the brief panel becomes a sheet below the scope.

### The radar scope
- Sectors: one wedge per `product_family`, labeled at the rim.
- Radius encodes velocity: blips sit on a log scale from the center (velocity <= 1)
  to the outer ring (velocity >= 4). Accelerating issues literally move outward as
  the month slider advances. Animate position changes between months.
- Blip size encodes recent volume (sqrt scale). Fill color encodes severity.
- Kept briefs are filled; rejected briefs are hollow outlines.
- The sweep arm rotates continuously (one turn every 6 seconds). A blip brightens
  briefly as the sweep passes it.
- Hover shows the headline. Click selects and opens the brief panel.
- `prefers-reduced-motion`: no sweep, no animated transitions.
- Provide a "View as table" toggle with the same data, sortable, for accessibility and
  for interviewers who want numbers.

### Month slider and the August 2026 moment
The slider steps through each month in the window. When it reaches August 2026, the
scope dims and a short neutral note appears: "Public narrative publication ended in
August 2026. Regulators still receive complaints; banks can run this radar on their
own data." Keep the wording factual.

### Brief panel
Headline, then themes (the AI layer, shown as labeled bars by share), the brief
sections, evidence list, the skeptic's checks with pass or fail, a small state map
(simple SVG choropleth, no external tiles), a monthly trend sparkline, top companies
with lift, and 3 to 5 example summaries with their CFPB complaint IDs.

### Other views
- **Bank lens:** choosing a company recolors the scope to that company's clusters and
  shows lift against peers.
- **Backtests page:** for each case, a mini replay of the radar at `as_of` with the
  target cluster highlighted, and the result stated plainly, including misses.
- **Method page:** the pipeline as a simple diagram, model ids from `meta.json`, the
  evaluation results, and the limitations (unverified allegations, size normalization,
  templating, sampling).

### Quality floor
Keyboard focus visible, every blip reachable by keyboard (tab order by velocity),
AA contrast, works at 375px wide, no layout shift when the panel opens.

## 9. Testing

- `backend/tests/fixtures.py` generates synthetic CFPB-format CSV zips with planted
  patterns: one accelerating cluster dominated by one company, one cluster of
  copy-paste templated narratives, and stable background clusters.
- Unit tests: column normalization, dedupe, partial-month exclusion, velocity math,
  lift, templating detection, as-of filtering, contract schemas.
- Agent tests mock the Claude client and assert prompts include the required
  instructions and outputs validate against schemas.
- `make test` must pass with no network access and no API key.
- Frontend: `npm run build` and `tsc --noEmit` pass; render against
  `public_data/` produced from fixtures.

## 10. Milestones

Verify each milestone, then summarize what was done and anything the user must do.

1. **Skeleton.** Repo layout, Makefile, configs, `.env.example`, fixtures, tests passing.
2. **Data.** ingest, emergence, templating on fixtures; then on real data if the user
   has downloaded it. Print the top 10 clusters.
3. **AI layer.** extract (with cache, batch, dry run), themes, analyst, skeptic.
   Before running on real data, print the dry-run call count and stop for the user to
   confirm spend.
4. **Export and API.** `public_data/` files and endpoints matching the contract.
5. **Frontend.** Scope, slider, brief panel, table view, August 2026 moment.
6. **Lens, backtest, method pages.**
7. **Evaluation.** Review sheet, metrics, README results section.
8. **Polish.** README with pitch, screenshots, architecture diagram (Mermaid), run
   instructions, limitations, and a 3-minute demo script.

## 11. Demo script (for README)

1. Open on the radar sweeping in early 2026. Blips appear across sectors.
2. Drag the slider forward; one cluster moves toward the rim. Click it.
3. Walk through the themes (what the AI found beyond the form category), then the
   skeptic's checks.
4. Show a rejected brief and why the skeptic rejected it.
5. Switch to a bank lens to show size-normalized lift.
6. Show a backtest result, whatever it was.
7. Reach August 2026 as the scope dims. Close on the method page and evaluation.

## 12. Decisions log

- Lift uses company shares within the cluster's recent 3-month window (same period
  for numerator and denominator), not the whole archive.
- `ingest` keeps the `EXPORTS` dict (keyed by covered months) and `COLUMNS`/`snake()`
  matching from `data_spike/spike.py`; `--exports` accepts `recent`, `all`, or
  comma-separated keys. Dedupe prefers the copy of a complaint that has a narrative.
- Emergence needs at least one baseline month; months with fewer than 6 baseline
  months use what exists and record `baseline_months`.
- `--as-of` runs write to `data/work/asof_<YYYY-MM>/` so they never overwrite the
  default run.

### Findings from the real RECENT data (2026-10-05)

- 6,884,299 unique complaints; 90% are credit reporting. Dates run 2025-09-01 to
  2026-08-31 at normal daily volume, so August 2026 is **not** partial by date
  received. `complete_months` is data-driven and keeps it.
- Narrative share decays toward the end of the window (16% in Sep 2025, 1.5% in
  Jul 2026, ~0% in Aug 2026), consistent with a publication lag. Recent-month
  narrative samples are thin; the extract step must report how many it found.
- CFPB uses near-duplicate issue labels ("...existing issue" vs "...existing
  problem"), which split one cluster in two and can fake acceleration. Open question
  for the user: merge known label variants, or leave it for the skeptic.
- Top velocity is 1.77x; 35% of narratives are templated; 8 of 79 clusters >= 20%.

## 13. Out of scope

User accounts, real bank data, live CFPB API calls, chat interfaces, mobile apps,
predictions about specific companies' legal outcomes.
