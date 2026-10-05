"""Pipeline entry point: `python -m radar.cli <step> [options]`.

Every step reads the previous step's output from data/work/, writes its own,
is safe to rerun, and prints a one-line summary.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from radar import emergence, ingest, templating
from radar.config import Settings, get_settings
from radar.schemas import EmergenceResult


def step_dir(settings: Settings, as_of: str | None) -> Path:
    """Default runs write to data/work/; as-of runs to data/work/asof_<YYYY-MM>/."""
    path = settings.work_dir / f"asof_{as_of}" if as_of else settings.work_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_complaints(settings: Settings) -> pd.DataFrame:
    path = settings.complaints_path
    if not path.exists():
        sys.exit(f"missing {path}. Run: python -m radar.cli ingest")
    return pd.read_parquet(path)


def load_emergence(settings: Settings, as_of: str | None) -> EmergenceResult:
    path = step_dir(settings, as_of) / "emergence.json"
    if not path.exists():
        sys.exit(f"missing {path}. Run: python -m radar.cli emergence")
    return EmergenceResult.model_validate_json(path.read_text())


# ---------- steps ----------


def cmd_ingest(args: argparse.Namespace, settings: Settings) -> None:
    if args.from_dir:
        source = Path(args.from_dir)
        paths = sorted(source.glob("*.zip")) + sorted(source.glob("*.csv"))
    else:
        paths = ingest.download(ingest.select_exports(args.exports), settings.raw_dir)
    if not paths:
        sys.exit("no export files found")
    df = ingest.load(paths)
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(settings.complaints_path, index=False)
    full = ingest.complete_months(df)
    span = f"{full[0]}..{full[-1]}" if full else "none"
    print(
        f"ingest: {len(df):,} unique complaints from {len(paths)} files, "
        f"{df['narrative'].ne('').mean():.0%} with narratives, complete months {span}"
    )


def cmd_emergence(args: argparse.Namespace, settings: Settings) -> None:
    result = emergence.compute(load_complaints(settings), month=args.month, as_of=args.as_of)
    out = step_dir(settings, args.as_of) / "emergence.json"
    out.write_text(result.model_dump_json(indent=1))
    print(
        f"emergence: month {result.month}, {len(result.clusters)} clusters with >= "
        f"{emergence.MIN_RECENT_AVG:.0f}/mo, baseline {len(result.baseline_months)} months -> {out}"
    )
    print(f"  {'rank':>4}  {'velocity':>8}  {'recent/mo':>9}  {'base/mo':>8}  cluster")
    for c in result.clusters[: args.top]:
        print(
            f"  {c.rank:>4}  {c.velocity:>7.2f}x  {c.recent_monthly_avg:>9,.0f}  "
            f"{c.baseline_monthly_avg:>8,.0f}  {c.product} / {c.issue}"
        )


def cmd_templating(args: argparse.Namespace, settings: Settings) -> None:
    df = emergence.filter_as_of(load_complaints(settings), args.as_of)
    result = load_emergence(settings, args.as_of)
    marked = templating.mark_templated(df)
    shares = templating.templated_shares(marked, result)
    out_dir = step_dir(settings, args.as_of)
    marked.to_parquet(out_dir / "fingerprints.parquet", index=False)
    (out_dir / "templating.json").write_text(json.dumps(shares, indent=1))
    high = sum(share >= 0.2 for share in shares.values())
    print(
        f"templating: {marked['templated'].mean() if len(marked) else 0:.1%} of "
        f"{len(marked):,} narratives templated; {high} of {len(shares)} clusters >= 20% "
        f"-> {out_dir / 'templating.json'}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="radar", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="download, load, normalize, dedupe")
    p.add_argument("--exports", default="recent", help="recent, all, or comma-separated keys")
    p.add_argument("--from-dir", help="load every zip/csv in this directory instead")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("emergence", help="rank accelerating clusters (no AI)")
    p.add_argument("--month", help="analysis month YYYY-MM (default: last complete month)")
    p.add_argument("--as-of", help="ignore all data after this month YYYY-MM")
    p.add_argument("--top", type=int, default=10, help="rows to print")
    p.set_defaults(func=cmd_emergence)

    p = sub.add_parser("templating", help="detect copy-paste narratives (no AI)")
    p.add_argument("--as-of", help="match the emergence run's --as-of")
    p.set_defaults(func=cmd_templating)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args, get_settings())


if __name__ == "__main__":
    main()
