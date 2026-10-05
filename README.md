# Complaint Radar

An early-warning radar for consumer finance risk. Complaint Radar reads real consumer
complaints about financial companies, finds issues that are accelerating before they
become regulatory or reputational problems, explains the likely root cause, and has a
skeptic agent reject weak signals.

## Why this exists

In August 2026 the CFPB stopped publishing complaint narratives and visualizations in
its public Consumer Complaint Database. It still collects complaints and shares them
with regulators, and it published an archive of complaints received from December 1,
2011 through August 14, 2026.

That archive shows what a public early-warning view could reveal. Complaint Radar runs
on it, and the same pipeline could run on a bank's own complaint data.

Complaints are **unverified allegations**. Everything here treats them as claims or
signals, never as findings of wrongdoing.

## Project status

| Milestone | Status |
|---|---|
| 1. Skeleton, fixtures, tests | Done |
| 2. Data: ingest, emergence, templating | Done, run on real data |
| 3. AI layer: extract, themes, analyst, skeptic | Done, run on real data |
| 4. Export and API | Done |
| 5. Frontend radar | Not started |
| 6. Bank lens, backtests, method page | Not started |
| 7. Evaluation | Not started |
| 8. Polish, screenshots, demo recording | Not started |

## How it works

```mermaid
flowchart LR
    A[CFPB archive zips] --> B[ingest<br/>normalize + dedupe]
    B --> C[emergence<br/>velocity + lift]
    B --> D[templating<br/>copy-paste detection]
    C --> E[extract<br/>Haiku 4.5, per narrative]
    D --> E
    E --> F[themes<br/>root causes beyond<br/>the form categories]
    F --> G[analyst agent<br/>writes the brief]
    G --> H[skeptic agent<br/>keeps or rejects]
    H --> I[export<br/>static JSON + API]
    I --> J[radar UI]
```

**No-AI steps**

- **Emergence.** A cluster is a `(product, issue)` pair. Velocity compares the last
  3 months with the 6 before them:
  `(recent mean + 5) / (baseline mean + 5)`. Clusters averaging fewer than 30
  complaints a month are dropped.
- **Lift.** A company's share of a cluster divided by its share of the same
  product. Lift above 1 means a company is over-represented among its peers, not just
  big. Companies are never ranked by raw count.
- **Templating.** Narratives are fingerprinted after stripping redactions and
  punctuation. A fingerprint seen 5 or more times marks a form letter or copy-paste
  campaign, which can fake a spike.

**AI steps**

- **Extract** (Claude Haiku 4.5, Message Batches API). Up to 40 recent narratives
  per cluster are turned into structured fields: root cause, harm, money at stake,
  severity, vulnerable consumer, and a one-sentence neutral summary. Results are cached
  by complaint ID, so nothing is paid for twice.
- **Themes.** Root causes in each cluster are consolidated into 2 to 5 labeled
  themes. This is where the AI sees more than the CFPB's form categories.
- **Analyst agent.** Writes a brief for a bank executive: what is happening, who is
  affected, the likely root cause (framed as a hypothesis), and which internal process
  or control to check.
- **Skeptic agent.** Reviews every brief against the same evidence with five checks:
  size (lift), templating, concentration, thin evidence, and seasonality. Rejected
  briefs stay in the data and are shown as rejected.

## Results so far

From the RECENT window (September 2025 to August 2026):

- 6,884,299 unique complaints, 90% of them about credit reporting.
- 79 clusters pass the volume floor. The fastest is accelerating at 1.77x.
- 35% of narratives are templated; 8 of 79 clusters are at least 20% templated.
- Narrative share falls toward the end of the window (16% in September 2025, 1.5% in
  July 2026), which is consistent with a publication lag. Recent samples are thinner.

**The skeptic at work.** Of the top three clusters by velocity, it kept one brief and
rejected two:

| Cluster | Verdict | Skeptic's note |
|---|---|---|
| Payday/advance loans: can't stop withdrawals | Rejected | Peaked in June 2026 and fell for two straight months (58, 39, 33) |
| Credit reporting: dispute investigations (specialty reporters) | Rejected | Fell from 922 to 299 after a June peak; 4 recent narratives, half templated |
| Credit reporting: dispute investigations (national bureaus) | Kept | Broad, sustained, market-wide rise with low templating |

Across all 25 clusters the skeptic **kept 15 and rejected 10**. The checks that
failed:

| Check | Briefs failing it |
|---|---|
| Seasonality (a single peak, or falling for two months) | 8 |
| Thin evidence | 3 |
| Templating (30% or more of recent narratives) | 2 |
| Size (lift) | 0 |
| Concentration (one state or one company) | 0 |

A brief can fail more than one check. Extraction accuracy and theme stability will be
added here once the evaluation step (milestone 7) has run.

## Running it

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), and an Anthropic API key
for the AI steps.

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY
make setup                    # install backend dependencies
make test                     # no network or API key needed
```

Real data:

```bash
make data                     # download + normalize the CFPB archive (recent window)
make dry-run                  # show how many AI calls extract would make, and the cost
make pipeline                 # emergence, templating, extract, themes, analyst, skeptic, export
make api                      # serve public_data/ at http://localhost:8000/api
```

Synthetic data, for development without a download:

```bash
make data-fixtures
```

Each step can also be run on its own: `cd backend && uv run python -m radar.cli <step>`.

### Cost

`extract` will not spend money without a confirmation or `--yes`, and `--dry-run`
prints the call count and estimated cost first.

The AI steps are one-time costs. Their outputs are saved to `data/`, extractions are
cached by complaint ID, and finished clusters are skipped on rerun. The deployed demo
reads precomputed JSON and makes no API calls.

Models are set in `.env`:

| Variable | Default | Used by |
|---|---|---|
| `RADAR_MODEL_FAST` | `claude-haiku-4-5-20251001` | extract |
| `RADAR_MODEL_WRITER` | `claude-sonnet-5-5` | analyst |
| `RADAR_MODEL_REASONING` | `claude-opus-5-5` | themes, skeptic |

Setting `RADAR_MODEL_REASONING=claude-sonnet-5-5` roughly halves the cost of a
25-cluster run.

## Repo layout

```
backend/radar/     pipeline steps, Claude client, agents, CLI
backend/tests/     synthetic CFPB-format fixtures and unit tests
data_spike/        original data exploration script
data/              downloaded and intermediate data (gitignored)
public_data/       precomputed JSON for the deployed demo
```

## Limitations

- **Unverified allegations.** Complaints are consumers' claims. A rising cluster is a
  signal to investigate, not evidence that a company did anything wrong.
- **Size normalization is relative.** Lift compares a company with others in the
  same product. It does not account for differences in customer mix within a product.
- **Templating.** Form letters and coordinated campaigns can inflate counts. They are
  detected and reported, not removed.
- **Sampling.** The AI reads up to 40 narratives per cluster, not every complaint.
  Themes and briefs describe that sample.
- **Narrative lag.** Fewer narratives are published for recent months, so the most
  recent signals have the least text behind them.
- **Label drift.** The CFPB uses near-duplicate issue labels, which can split one
  cluster in two.

## Demo script (planned)

1. Open on the radar sweeping in early 2026. Blips appear across sectors.
2. Drag the month slider forward; one cluster moves toward the rim. Click it.
3. Walk through the themes, then the skeptic's checks.
4. Show a rejected brief and why the skeptic rejected it.
5. Switch to a bank lens to show size-normalized lift.
6. Show a backtest result, whatever it was.
7. Reach August 2026 as the scope dims. Close on the method page and evaluation.

## Data source

[CFPB Consumer Complaint Database narratives archive](https://www.consumerfinance.gov/foia-requests/foia-electronic-reading-room/cfpb-consumer-complaint-database-narratives-archive/).
The UI shows AI-written one-sentence summaries with the CFPB complaint ID, not the raw
narrative text.
