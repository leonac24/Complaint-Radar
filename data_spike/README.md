# Complaint Radar: data spike

Answers one question before you build anything: is the CFPB complaint archive good
enough to power the radar?

## Run it

```bash
cd data_spike
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

python spike.py all
```

`all` downloads about 12 months of archive exports (September 2025 to August 2026),
which are large zips, so expect a long first download. Every step caches its output in
`work/`, so you can rerun any single step:

| Step | What it does | Output |
|---|---|---|
| `download` | Fetches exports from the CFPB narratives archive | `raw/*.zip` |
| `load` | Unzips, normalizes column names, removes duplicates | `work/complaints.parquet` |
| `profile` | Volumes, narrative coverage, top products and companies, templating | `work/profile.md` |
| `emerge` | Finds issues accelerating against their own baseline. Statistics only, no AI | `work/emerging.json` |
| `extract` | Claude reads sampled narratives and pulls out root cause, harm, severity | `work/extractions.jsonl` |
| `contract` | Assembles the file the frontend will be designed around | `work/radar_sample.json` |

Useful options: `--exports all` for the full history back to 2011 (needed for
backtesting), `--top-clusters 25`, and `--sample-per-cluster 40`. Set `SPIKE_MODEL`
to change the extraction model.

The default extraction run is 15 clusters x 20 narratives = 300 short Haiku calls.

## What to look for

Go or no-go signals, in rough order of importance:

1. **Narrative coverage** in `profile.md`. If too few recent complaints carry narratives,
   the AI has little to read and the radar leans on CFPB's form categories instead.
2. **Real acceleration** in `emerge`. You want a handful of clusters with velocity
   well above 1.0 and meaningful volume, not just noise.
3. **Extraction quality.** Open `extractions.jsonl` and read 20 rows next to their
   narratives. Are the root causes more specific and useful than CFPB's issue labels?
   This is the core claim of the project, so check it honestly.
4. **Templating.** Clusters with a high `templated_share` are likely driven by
   credit-repair form letters. That is exactly what your skeptic agent should catch.
5. **Company lift.** `lift` above 1 means a company is overrepresented in a cluster
   relative to its overall complaint volume. That is the size-normalized signal.

## Notes

- The final month (August 2026) is partial because the archive stops at
  August 14, so `emerge` leaves it out.
- Narratives are unverified consumer allegations, and the extraction prompt says so.
- `radar_sample.json` leaves `brief` and `skeptic` empty. The analyst and skeptic
  agents fill those in during the real build.
