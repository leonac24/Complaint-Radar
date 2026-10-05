"""Complaint Radar data spike.

One script that answers: is the CFPB archive good enough to build the radar on?

    python spike.py all            # download -> load -> profile -> emerge -> extract -> contract
    python spike.py download       # fetch the archive exports (about 12 months by default)
    python spike.py load           # unzip, normalize columns, dedupe -> work/complaints.parquet
    python spike.py profile        # what is in the data -> work/profile.md
    python spike.py emerge         # find accelerating issues, no AI -> work/emerging.json
    python spike.py extract        # Claude reads sampled narratives -> work/extractions.jsonl
    python spike.py contract       # assemble the frontend handoff -> work/radar_sample.json

Options: --exports recent|all|<name,...>   --sample-per-cluster 20   --top-clusters 15
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
WORK = HERE / "work"
BASE = "https://files.consumerfinance.gov/f/documents/"

# From the CFPB narratives archive page (complaints received through Aug 14, 2026).
EXPORTS = {
    "2026-08": "CCDB_Export_21_August_2026.zip",
    "2026-07": "CCDB_Export_20_July_2026.zip",
    "2026-06": "CCDB_Export_19_June_2026.zip",
    "2026-05": "CCDB_Export_18_May_2026.zip",
    "2026-04": "CCDB_Export_17_April_2026.zip",
    "2026-03": "CCDB_Export_16_March_2026.zip",
    "2026-01_02": "CCDB_Export_15_January_2026_through_February_2026.zip",
    "2025-11_12": "CCDB_Export_14_November_2025_through_December_2025.zip",
    "2025-09_10": "CCDB_Export_13_September_2025_through_October_2025.zip",
    "2025-07_08": "CCDB_Export_12_July_2025_through_August_2025.zip",
    "2025-05_06": "CCDB_Export_11_May_2025_through_June_2025.zip",
    "2025-03_04": "CCDB_Export_10_March_2025_through_April_2025.zip",
    "2025-01_02": "CCDB_Export_9_January_2025_through_February_2025.zip",
    "2024-11_12": "CCDB_Export_8_November_2024_through_December_2024.zip",
    "2024-08_10": "CCDB_Export_7_August_2024_through_October_2024.zip",
    "2024-04_07": "CCDB_Export_6_April_2024_through_July_2024.zip",
    "2023-09_2024-03": "CCDB_Export_5_September_2023_through_March_2024.zip",
    "2022-11_2023-08": "CCDB_Export_4_November_2022_through_August_2023.zip",
    "2021-05_2022-10": "CCDB_Export_3_May_2021_through_October_2022.zip",
    "2018-05_2021-04": "CCDB_Export_2_May_2018_through_April_2021.zip",
    "2011-12_2018-04": "CCDB_Export_1_December_2011_through_April_2018.zip",
}
RECENT = ["2026-08", "2026-07", "2026-06", "2026-05", "2026-04", "2026-03",
          "2026-01_02", "2025-11_12", "2025-09_10"]

# Canonical column names, with the variants we might meet in the exports.
COLUMNS = {
    "complaint_id": ["complaint_id"],
    "date_received": ["date_received"],
    "product": ["product"],
    "sub_product": ["sub_product"],
    "issue": ["issue"],
    "sub_issue": ["sub_issue"],
    "narrative": ["consumer_complaint_narrative", "complaint_what_happened", "narrative"],
    "company": ["company"],
    "state": ["state"],
    "tags": ["tags"],
    "submitted_via": ["submitted_via"],
    "company_response": ["company_response_to_consumer", "company_response"],
    "timely": ["timely_response", "timely"],
}


def snake(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def canonical_map(columns: list[str]) -> dict[str, str]:
    lookup = {snake(c): c for c in columns}
    mapping = {}
    for canon, variants in COLUMNS.items():
        hits = [lookup[v] for v in variants if v in lookup]
        if hits:
            mapping[hits[0]] = canon
    return mapping


# ---------------------------------------------------------------- download
def cmd_download(names: list[str]) -> None:
    RAW.mkdir(exist_ok=True)
    for name in names:
        dest = RAW / EXPORTS[name]
        if dest.exists():
            print(f"  have {dest.name}")
            continue
        print(f"  downloading {dest.name}")
        tmp = dest.with_suffix(".part")
        with urllib.request.urlopen(BASE + EXPORTS[name]) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            for chunk in iter(lambda: resp.read(1 << 20), b""):
                out.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r    {done / total:5.1%} of {total / 1e6:,.0f} MB", end="", flush=True)
        tmp.rename(dest)
        print()


# ---------------------------------------------------------------- load
def read_tables(path: Path):
    """Yield DataFrame chunks from every CSV inside a zip (or a bare CSV)."""
    if path.suffix == ".csv":
        yield from pd.read_csv(path, dtype=str, chunksize=200_000, low_memory=False)
        return
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.namelist() if m.lower().endswith(".csv")]
        if not members:
            print(f"  warning: no CSV inside {path.name}: {archive.namelist()[:5]}")
        for member in members:
            with archive.open(member) as handle:
                yield from pd.read_csv(handle, dtype=str, chunksize=200_000, low_memory=False)


def cmd_load() -> pd.DataFrame:
    files = sorted(RAW.glob("*.zip")) + sorted(RAW.glob("*.csv"))
    if not files:
        sys.exit("No files in raw/. Run: python spike.py download")
    frames = []
    for path in files:
        rows = 0
        for chunk in read_tables(path):
            mapping = canonical_map(list(chunk.columns))
            chunk = chunk[list(mapping)].rename(columns=mapping)
            frames.append(chunk)
            rows += len(chunk)
        print(f"  {path.name}: {rows:,} rows")
    df = pd.concat(frames, ignore_index=True)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        print(f"  note: columns not found in exports: {missing}")
    df["date_received"] = pd.to_datetime(df["date_received"], errors="coerce")
    before = len(df)
    df = df.drop_duplicates(subset="complaint_id").dropna(subset=["date_received"])
    print(f"  {before:,} rows -> {len(df):,} unique complaints")
    WORK.mkdir(exist_ok=True)
    df.to_parquet(WORK / "complaints.parquet", index=False)
    return df


def load_df() -> pd.DataFrame:
    path = WORK / "complaints.parquet"
    if not path.exists():
        sys.exit("No work/complaints.parquet. Run: python spike.py load")
    return pd.read_parquet(path)


# ---------------------------------------------------------------- templating signal
def signature(text: str) -> str:
    """Rough fingerprint for spotting templated (copy-paste) complaints."""
    cleaned = re.sub(r"x{2,}", " ", str(text).lower())
    cleaned = re.sub(r"[^a-z ]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return hashlib.md5(cleaned[:400].encode()).hexdigest()


def add_template_flags(df: pd.DataFrame) -> pd.DataFrame:
    has = df["narrative"].notna() & (df["narrative"].str.len() > 0)
    df["has_narrative"] = has
    df["sig"] = None
    df.loc[has, "sig"] = df.loc[has, "narrative"].map(signature)
    counts = df.loc[has, "sig"].value_counts()
    df["templated"] = has & (df["sig"].map(counts).fillna(0) >= 5)
    return df


# ---------------------------------------------------------------- profile
def cmd_profile() -> None:
    df = add_template_flags(load_df())
    narr = df[df["has_narrative"]]
    lines = ["# Complaint data profile", ""]
    lines.append(f"- Complaints: {len(df):,} ({df['date_received'].min():%Y-%m-%d} to {df['date_received'].max():%Y-%m-%d})")
    lines.append(f"- With narratives: {len(narr):,} ({len(narr) / max(len(df), 1):.0%})")
    if len(narr):
        lengths = narr["narrative"].str.len()
        lines.append(f"- Narrative length: median {lengths.median():,.0f} chars, 90th pct {lengths.quantile(.9):,.0f}")
        lines.append(f"- Narratives that look templated (5+ near-identical copies): {narr['templated'].mean():.1%}")
    lines.append(f"- Companies: {df['company'].nunique():,}")

    def table(title: str, series: pd.Series, n: int = 12) -> None:
        lines.extend(["", f"## {title}", "", "| value | count |", "|---|---|"])
        lines.extend(f"| {k} | {v:,} |" for k, v in series.head(n).items())

    monthly = df.groupby(df["date_received"].dt.to_period("M")).size()
    table("Complaints per month", monthly.sort_index(ascending=False), 24)
    table("Top products", df["product"].value_counts())
    table("Top issues", df["issue"].value_counts())
    table("Top companies", df["company"].value_counts())
    if "tags" in df:
        table("Tags", df["tags"].value_counts(), 6)
    if len(narr):
        table("Most-copied narrative signatures", narr["sig"].value_counts(), 8)

    WORK.mkdir(exist_ok=True)
    (WORK / "profile.md").write_text("\n".join(lines))
    print("\n".join(lines[:8]))
    print(f"  full profile: {WORK / 'profile.md'}")


# ---------------------------------------------------------------- emerge
def cmd_emerge(top: int) -> list[dict]:
    """Find issues accelerating against their own baseline. Pure statistics, no AI."""
    df = add_template_flags(load_df())
    df["month"] = df["date_received"].dt.to_period("M")
    months = sorted(df["month"].unique())
    # The final month in the archive is partial (cut off Aug 14), so leave it out.
    months = months[:-1] if len(months) > 9 else months
    if len(months) < 6:
        sys.exit("Need at least 6 full months of data for emergence detection.")
    recent, base = months[-3:], months[-9:-3]

    df["cluster_key"] = df["product"].fillna("?") + " / " + df["issue"].fillna("?")
    counts = df[df["month"].isin(months)].groupby(["cluster_key", "month"]).size().unstack(fill_value=0)
    recent_avg = counts[recent].mean(axis=1)
    base_avg = counts[[m for m in base if m in counts.columns]].mean(axis=1)
    velocity = (recent_avg + 5) / (base_avg + 5)  # smoothed so tiny clusters don't explode

    company_share = df["company"].value_counts(normalize=True)
    clusters = []
    for key in velocity[recent_avg >= 30].sort_values(ascending=False).head(top).index:
        rows = df[(df["cluster_key"] == key) & df["month"].isin(recent)]
        top_companies = rows["company"].value_counts().head(5)
        product, issue = key.split(" / ", 1)
        clusters.append({
            "id": hashlib.md5(key.encode()).hexdigest()[:10],
            "product": product,
            "issue": issue,
            "velocity": round(float(velocity[key]), 2),
            "recent_monthly_avg": round(float(recent_avg[key]), 1),
            "baseline_monthly_avg": round(float(base_avg[key]), 1),
            "months": [{"month": str(m), "count": int(counts.loc[key, m])} for m in months],
            # Share of this cluster's narratives that are near-identical copies.
            "templated_share": round(float(rows.loc[rows["has_narrative"], "templated"].mean()), 3)
            if rows["has_narrative"].any() else 0.0,
            "narrative_count": int(rows["has_narrative"].sum()),
            # Lift > 1 means the company is overrepresented relative to its overall complaint volume.
            "companies": [
                {
                    "name": name,
                    "count": int(n),
                    "lift": round(float((n / len(rows)) / company_share.get(name, 1e-9)), 2),
                }
                for name, n in top_companies.items()
            ],
            "states": {k: int(v) for k, v in rows["state"].value_counts().head(15).items()},
        })
    WORK.mkdir(exist_ok=True)
    (WORK / "emerging.json").write_text(json.dumps(clusters, indent=1))
    for c in clusters:
        print(f"  {c['velocity']:>5.2f}x  {c['recent_monthly_avg']:>8,.0f}/mo  templated {c['templated_share']:.0%}  {c['product']} / {c['issue']}")
    return clusters


# ---------------------------------------------------------------- extract (Claude)
EXTRACT_SYSTEM = """You analyze consumer complaints about financial companies for a bank's
risk team. Read the narrative and extract what actually happened, beyond the form
category the consumer picked. Be literal: report only what the narrative supports.
Narratives are unverified allegations; describe them as claims. 'XXXX' marks redacted text."""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "root_cause": {"type": "string", "description": "Short phrase naming the underlying failure, e.g. 'dispute not investigated', 'fee charged after closure'"},
        "root_cause_family": {"type": "string", "enum": [
            "fees_and_charges", "disputes_and_errors", "fraud_and_scams", "access_and_service",
            "credit_reporting_accuracy", "collections_conduct", "servicing_process", "disclosure_and_terms", "other"]},
        "journey_stage": {"type": "string", "enum": [
            "account_opening", "everyday_use", "payment", "dispute", "collections", "closing", "other"]},
        "harm": {"type": "string", "description": "What the consumer says they lost or suffered"},
        "money_at_stake_usd": {"type": ["number", "null"]},
        "vulnerable_consumer": {"type": "boolean", "description": "Older adult, servicemember, hardship, disability, or similar is stated"},
        "severity": {"type": "integer", "minimum": 1, "maximum": 5},
        "summary": {"type": "string", "description": "One neutral sentence paraphrasing the claim; no names"},
        "looks_templated": {"type": "boolean", "description": "Reads like a form letter or credit-repair template"},
    },
    "required": ["root_cause", "root_cause_family", "journey_stage", "harm", "vulnerable_consumer",
                 "severity", "summary", "looks_templated"],
}


async def extract_one(client, sem, model: str, row: dict) -> dict:
    async with sem:
        resp = await client.messages.create(
            model=model,
            max_tokens=600,
            system=[{"type": "text", "text": EXTRACT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=[{"name": "submit", "description": "Submit the extraction.", "input_schema": EXTRACT_SCHEMA}],
            tool_choice={"type": "tool", "name": "submit"},
            messages=[{"role": "user", "content":
                       f"Product: {row['product']}\nIssue picked: {row['issue']}\n\nNarrative:\n{row['narrative'][:6000]}"}],
        )
    calls = [b for b in resp.content if b.type == "tool_use"]
    result = calls[0].input if calls else {"error": "no tool call"}
    return {"complaint_id": row["complaint_id"], "cluster_id": row["cluster_id"], **result}


async def run_extract(rows: list[dict], model: str) -> list[dict]:
    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()
    sem = asyncio.Semaphore(int(os.getenv("SPIKE_CONCURRENCY", "8")))
    return await asyncio.gather(*(extract_one(client, sem, model, r) for r in rows))


def cmd_extract(per_cluster: int) -> None:
    path = WORK / "emerging.json"
    if not path.exists():
        sys.exit("No work/emerging.json. Run: python spike.py emerge")
    clusters = json.loads(path.read_text())
    df = add_template_flags(load_df())
    df["cluster_key"] = df["product"].fillna("?") + " / " + df["issue"].fillna("?")
    rows = []
    for c in clusters:
        pool = df[(df["cluster_key"] == f"{c['product']} / {c['issue']}") & df["has_narrative"]]
        pool = pool.sort_values("date_received").tail(per_cluster * 10)
        picked = pool.sample(min(per_cluster, len(pool)), random_state=1)
        rows.extend({**r, "cluster_id": c["id"]} for r in picked[["complaint_id", "product", "issue", "narrative"]].to_dict("records"))
    model = os.getenv("SPIKE_MODEL", "claude-haiku-4-5-20251001")
    print(f"  extracting {len(rows)} narratives with {model}")
    results = asyncio.run(run_extract(rows, model))
    with open(WORK / "extractions.jsonl", "w") as out:
        out.writelines(json.dumps(r) + "\n" for r in results)
    families = Counter(r.get("root_cause_family") for r in results)
    print(f"  root cause families: {dict(families.most_common())}")
    print(f"  wrote {WORK / 'extractions.jsonl'}")


# ---------------------------------------------------------------- contract
def cmd_contract() -> None:
    clusters = json.loads((WORK / "emerging.json").read_text())
    ext_path = WORK / "extractions.jsonl"
    extractions = [json.loads(l) for l in ext_path.read_text().splitlines()] if ext_path.exists() else []
    by_cluster: dict[str, list] = {}
    for e in extractions:
        by_cluster.setdefault(e["cluster_id"], []).append(e)
    for c in clusters:
        mine = [e for e in by_cluster.get(c["id"], []) if "error" not in e]
        c["root_causes"] = dict(Counter(e["root_cause"] for e in mine).most_common(5))
        c["root_cause_families"] = dict(Counter(e["root_cause_family"] for e in mine).most_common())
        c["avg_severity"] = round(sum(e["severity"] for e in mine) / len(mine), 2) if mine else None
        c["vulnerable_share"] = round(sum(e["vulnerable_consumer"] for e in mine) / len(mine), 2) if mine else None
        c["examples"] = [{"complaint_id": e["complaint_id"], "summary": e["summary"]} for e in mine[:5]]
        c["brief"] = None     # filled later by the analyst agent
        c["skeptic"] = None   # filled later by the skeptic agent
    contract = {
        "source": "CFPB Consumer Complaint Database archive (complaints received through 2026-08-14)",
        "clusters": clusters,
    }
    (WORK / "radar_sample.json").write_text(json.dumps(contract, indent=1))
    print(f"  wrote {WORK / 'radar_sample.json'} with {len(clusters)} clusters")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["download", "load", "profile", "emerge", "extract", "contract", "all"])
    parser.add_argument("--exports", default="recent", help="recent, all, or comma-separated names from EXPORTS")
    parser.add_argument("--top-clusters", type=int, default=15)
    parser.add_argument("--sample-per-cluster", type=int, default=20)
    args = parser.parse_args()

    if args.exports == "recent":
        names = RECENT
    elif args.exports == "all":
        names = list(EXPORTS)
    else:
        names = args.exports.split(",")

    steps = {
        "download": lambda: cmd_download(names),
        "load": cmd_load,
        "profile": cmd_profile,
        "emerge": lambda: cmd_emerge(args.top_clusters),
        "extract": lambda: cmd_extract(args.sample_per_cluster),
        "contract": cmd_contract,
    }
    order = list(steps) if args.command == "all" else [args.command]
    for name in order:
        print(f"[{name}]")
        steps[name]()


if __name__ == "__main__":
    main()
