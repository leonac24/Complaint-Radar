"""Pipeline entry point: `python -m radar.cli <step> [options]`.

Every step reads the previous step's output from data/work/, writes its own,
is safe to rerun, and prints a one-line summary.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from radar import backtest, emergence, evaluate, export, extract, ingest, templating, themes
from radar.agents import analyst, evidence, skeptic
from radar.config import Settings, get_settings
from radar.llm import LLM, ClaudeLLM, LLMError
from radar.schemas import (
    BacktestCase,
    BacktestsFile,
    Brief,
    EmergenceResult,
    Evaluation,
    ModelIds,
    SkepticReview,
    StabilityResult,
    ThemeOut,
)


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


def read_json(path: Path, default: object) -> object:
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=1))


def require(path: Path, command: str) -> Path:
    if not path.exists():
        sys.exit(f"missing {path}. Run: python -m radar.cli {command}")
    return path


def make_llm() -> LLM:
    return ClaudeLLM()


def extraction_cache_path(settings: Settings) -> Path:
    return settings.cache_dir / "extractions.jsonl"


def confirm_spend(calls: int, assume_yes: bool) -> bool:
    if assume_yes or calls == 0:
        return True
    if not sys.stdin.isatty():
        print("  not confirmed: rerun with --yes to make these calls")
        return False
    return input(f"  make {calls:,} API calls? [y/N] ").strip().lower() == "y"


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


def cmd_extract(args: argparse.Namespace, settings: Settings) -> None:
    df = emergence.filter_as_of(load_complaints(settings), args.as_of)
    result = load_emergence(settings, args.as_of)
    sampled = extract.sample(df, result, args.clusters, args.per_cluster)
    out_dir = step_dir(settings, args.as_of)
    index = extract.sample_index(sampled)
    write_json(out_dir / "extract_sample.json", index)

    cache_path = extraction_cache_path(settings)
    work = extract.plan(sampled, extract.load_cache(cache_path), args.limit)
    empty = min(args.clusters, len(result.clusters)) - len(index)
    model = settings.model_fast
    print(
        f"extract: {len(sampled):,} narratives sampled from {len(index)} clusters "
        f"({empty} top clusters had none); {work.cached:,} cached, {len(work.to_call):,} to call "
        f"with {model}{' via batch' if args.batch else ''}, "
        f"estimated ${work.estimate_usd(args.batch):,.2f}"
    )
    if args.dry_run or not confirm_spend(len(work.to_call), args.yes):
        return
    ok, failed = extract.run(make_llm(), model, work.to_call, args.batch)
    extract.append_cache(cache_path, ok, model)
    print(f"extract: {len(ok):,} new extractions cached, {failed:,} failed -> {cache_path}")


def _cluster_inputs(settings: Settings, as_of: str | None, limit: int):
    """Yield (cluster, sampled extractions) for clusters the extract step sampled."""
    out_dir = step_dir(settings, as_of)
    index = read_json(require(out_dir / "extract_sample.json", "extract"), {})
    cache = extract.load_cache(extraction_cache_path(settings))
    result = load_emergence(settings, as_of)
    by_id = {c.id: c for c in result.clusters}
    for cid in list(index)[:limit]:
        items = {x: cache[x] for x in index[cid] if x in cache}
        yield by_id[cid], items


def cmd_themes(args: argparse.Namespace, settings: Settings) -> None:
    out = step_dir(settings, args.as_of) / "themes.json"
    done: dict = read_json(out, {})
    llm, model = make_llm(), settings.model_reasoning
    stats = {"new": 0, "kept": 0, "thin": 0, "failed": 0}
    for cluster, items in _cluster_inputs(settings, args.as_of, args.clusters):
        if cluster.id in done and not args.force:
            stats["kept"] += 1
            continue
        try:
            found = themes.consolidate(llm, model, cluster, list(items.items()))
        except LLMError as exc:
            print(f"  {cluster.product} / {cluster.issue}: {exc}")
            stats["failed"] += 1
            continue
        stats["new" if found is not None else "thin"] += 1
        done[cluster.id] = (
            {"themes": [t.model_dump() for t in found]} if found is not None
            else {"skipped": f"fewer than {themes.MIN_EXTRACTIONS} extractions ({len(items)})"}
        )
        write_json(out, done)
    print(f"themes: {stats['new']} clusters themed with {model}, {stats['kept']} already done, "
          f"{stats['thin']} too thin, {stats['failed']} failed -> {out}")


def _themes_for(entry: dict | None) -> list[ThemeOut] | None:
    if not entry or "themes" not in entry:
        return None
    return [ThemeOut.model_validate(t) for t in entry["themes"]]


def cmd_analyst(args: argparse.Namespace, settings: Settings) -> None:
    out_dir = step_dir(settings, args.as_of)
    result = load_emergence(settings, args.as_of)
    shares: dict = read_json(require(out_dir / "templating.json", "templating"), {})
    theme_map: dict = read_json(require(out_dir / "themes.json", "themes"), {})
    briefs: dict = read_json(out_dir / "briefs.json", {})
    packages: dict = read_json(out_dir / "evidence.json", {})
    llm, model = make_llm(), settings.model_writer
    failed = 0
    for cluster, items in _cluster_inputs(settings, args.as_of, args.clusters):
        if cluster.id in briefs and not args.force:
            continue
        package = evidence.build(cluster, result, shares.get(cluster.id),
                                 _themes_for(theme_map.get(cluster.id)), items)
        try:
            brief = analyst.write_brief(llm, model, package)
        except LLMError as exc:
            print(f"  {cluster.product} / {cluster.issue}: {exc}")
            failed += 1
            continue
        packages[cluster.id] = package
        briefs[cluster.id] = brief.model_dump()
        write_json(out_dir / "evidence.json", packages)
        write_json(out_dir / "briefs.json", briefs)
    print(f"analyst: {len(briefs)} briefs with {model}, {failed} failed -> {out_dir / 'briefs.json'}")


def cmd_skeptic(args: argparse.Namespace, settings: Settings) -> None:
    out_dir = step_dir(settings, args.as_of)
    briefs: dict = read_json(require(out_dir / "briefs.json", "analyst"), {})
    packages: dict = read_json(out_dir / "evidence.json", {})
    reviews: dict = read_json(out_dir / "skeptic.json", {})
    llm, model = make_llm(), settings.model_reasoning
    failed = 0
    for cid, raw in briefs.items():
        if cid in reviews and not args.force:
            continue
        try:
            review = skeptic.review_brief(llm, model, Brief.model_validate(raw), packages[cid])
        except LLMError as exc:
            print(f"  {cid}: {exc}")
            failed += 1
            continue
        reviews[cid] = review.model_dump()
        write_json(out_dir / "skeptic.json", reviews)
    kept = sum(r["verdict"] == "kept" for r in reviews.values())
    print(f"skeptic: {kept} kept, {len(reviews) - kept} rejected with {model}, {failed} failed "
          f"-> {out_dir / 'skeptic.json'}")


def load_ai_outputs(settings: Settings) -> export.AIOutputs:
    """Whatever the AI steps have produced so far; missing steps give empty maps."""
    work = settings.work_dir
    index: dict = read_json(work / "extract_sample.json", {})
    cache = extract.load_cache(extraction_cache_path(settings))
    theme_map: dict = read_json(work / "themes.json", {})
    themed = {cid: _themes_for(entry) for cid, entry in theme_map.items()}
    return export.AIOutputs(
        themes={cid: found for cid, found in themed.items() if found is not None},
        briefs={cid: Brief.model_validate(b)
                for cid, b in read_json(work / "briefs.json", {}).items()},
        reviews={cid: SkepticReview.model_validate(r)
                 for cid, r in read_json(work / "skeptic.json", {}).items()},
        samples={cid: {x: cache[x] for x in ids if x in cache} for cid, ids in index.items()},
    )


def cmd_export(args: argparse.Namespace, settings: Settings) -> None:
    df = load_complaints(settings)
    marked = pd.read_parquet(require(settings.work_dir / "fingerprints.parquet", "templating"))
    analysis = load_emergence(settings, None)
    shares: dict = read_json(require(settings.work_dir / "templating.json", "templating"), {})
    ai = load_ai_outputs(settings)
    models = ModelIds(fast=settings.model_fast, writer=settings.model_writer,
                      reasoning=settings.model_reasoning)
    public = settings.public_dir
    export.copy_optional(settings.work_dir, public)
    files = export.build(df, marked, analysis, shares, ai, models,
                         export.available_optional(public))
    size = export.write(public, files)
    months = sum(name.startswith("radar_") for name in files)
    clusters = sum(name.startswith("cluster_") for name in files)
    print(f"export: {months} radar months, {clusters} cluster files, {len(ai.briefs)} with "
          f"briefs, {size / 1e6:.1f} MB -> {public}")
    if size > export.SIZE_LIMIT_BYTES:
        print(f"  warning: over the {export.SIZE_LIMIT_BYTES // 2**20} MB budget")


def cmd_backtest(args: argparse.Namespace, settings: Settings) -> None:
    if args.as_of and args.cluster:
        cases = [BacktestCase(name=args.cluster, public_date="", as_of=args.as_of,
                              cluster=args.cluster, source_url="")]
    else:
        cases = backtest.load_cases()
    if not cases:
        sys.exit(f"no cases: add some to {backtest.CASES_PATH} or pass --as-of and --cluster")
    df = load_complaints(settings)
    available = ingest.complete_months(df)
    late = [c for c in cases if c.as_of not in available]
    if late:
        sys.exit(f"as_of {', '.join(c.as_of for c in late)} is outside the loaded data "
                 f"({available[0]}..{available[-1]}). Run: python -m radar.cli ingest --exports all")
    cache_path = extraction_cache_path(settings)
    cache = extract.load_cache(cache_path)
    calls = sum(backtest.planned_calls(c, df, cache) for c in cases)
    print(f"backtest: {len(cases)} cases, about {calls} API calls")
    if args.dry_run or not confirm_spend(calls, args.yes):
        return
    out = settings.work_dir / "backtests.json"
    saved = {r.name: r for r in (BacktestsFile.model_validate_json(out.read_text()).results
                                  if out.exists() else [])}
    llm = make_llm()
    models = (settings.model_fast, settings.model_writer, settings.model_reasoning)

    def save_extractions(fresh: dict, model: str) -> None:
        extract.append_cache(cache_path, fresh, model)
        cache.update(fresh)

    for case in cases:
        try:
            result = backtest.run_case(case, df, llm, models, cache, save_extractions)
        except LLMError as exc:
            print(f"  {case.name}: {exc}")
            continue
        saved[case.name] = result
        out.write_text(BacktestsFile(results=list(saved.values())).model_dump_json(indent=1))
        print(f"  {case.name}: {result.outcome}")
    flagged = sum(r.flagged for r in saved.values())
    print(f"backtest: {flagged} of {len(saved)} cases flagged -> {out}")


def _stability_run(settings: Settings) -> StabilityResult | None:
    """Theme the best-sampled cluster twice. Two reasoning-model calls."""
    inputs = list(_cluster_inputs(settings, None, 25))
    if not inputs:
        return None
    cluster, items = max(inputs, key=lambda pair: len(pair[1]))
    llm, model = make_llm(), settings.model_reasoning
    runs = [themes.consolidate(llm, model, cluster, list(items.items())) for _ in range(2)]
    first, second = runs
    if first is None or second is None:
        return None
    return evaluate.stability(f"{cluster.product} / {cluster.issue}", model, first, second)


def cmd_evaluate(args: argparse.Namespace, settings: Settings) -> None:
    work = settings.work_dir
    out = work / "evaluation.json"
    previous = Evaluation.model_validate_json(out.read_text()) if out.exists() else None

    sheet = work / "review_sheet.csv"
    if not sheet.exists():
        rows = evaluate.review_rows(load_complaints(settings),
                                    extract.load_cache(extraction_cache_path(settings)))
        evaluate.write_sheet(sheet, rows)
        print(f"  wrote {len(rows)} rows to {sheet}; fill the rating column "
              f"({', '.join(evaluate.RATINGS)}) and rerun evaluate")
    score = evaluate.score_sheet(sheet)
    status = (
        f"not rated yet: fill the rating column in {sheet.relative_to(settings.data_dir.parent)}"
        if score.rated == 0 else f"{score.rated} of {score.total} rated"
    )

    reviews = [SkepticReview.model_validate(r) for r in read_json(work / "skeptic.json", {}).values()]
    stats = evaluate.skeptic_stats(reviews) if reviews else None

    stable = previous.stability if previous else None
    if args.stability and confirm_spend(2, args.yes):
        try:
            stable = _stability_run(settings) or stable
        except LLMError as exc:
            print(f"  stability: {exc}")

    result = Evaluation(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        extraction=score if score.rated else None,
        extraction_status=status,
        skeptic=stats,
        stability=stable,
    )
    out.write_text(result.model_dump_json(indent=1))
    accuracy = f"{score.accuracy:.0%} accurate" if score.accuracy is not None else "unrated"
    overlap = f"label overlap {stable.label_overlap:.2f}, pair agreement {stable.pair_agreement:.2f}" if stable else "no stability run (use --stability)"
    print(f"evaluate: extraction {accuracy} ({status}); "
          f"skeptic {stats.kept if stats else 0} kept / {stats.rejected if stats else 0} rejected; "
          f"{overlap} -> {out}")


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

    p = sub.add_parser("extract", help="AI extraction over sampled narratives")
    p.add_argument("--as-of", help="match the emergence run's --as-of")
    p.add_argument("--clusters", type=int, default=25)
    p.add_argument("--per-cluster", type=int, default=40)
    p.add_argument("--limit", type=int, help="make at most N API calls")
    p.add_argument("--batch", action="store_true", help="use the Message Batches API")
    p.add_argument("--dry-run", action="store_true", help="print the plan, make no calls")
    p.add_argument("--yes", action="store_true", help="skip the spend confirmation")
    p.set_defaults(func=cmd_extract)

    for name, func, help_text in [
        ("themes", cmd_themes, "AI consolidation of root causes into themes"),
        ("analyst", cmd_analyst, "analyst agent writes a brief per cluster"),
        ("skeptic", cmd_skeptic, "skeptic agent keeps or rejects each brief"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--as-of", help="match the emergence run's --as-of")
        p.add_argument("--clusters", type=int, default=25)
        p.add_argument("--force", action="store_true", help="redo clusters already done")
        p.set_defaults(func=func)

    p = sub.add_parser("backtest", help="replay the radar as of earlier months for each case")
    p.add_argument("--as-of", help="YYYY-MM for an ad hoc case (with --cluster)")
    p.add_argument("--cluster", help='"<product> / <issue>" for an ad hoc case')
    p.add_argument("--dry-run", action="store_true", help="print the plan, make no calls")
    p.add_argument("--yes", action="store_true", help="skip the spend confirmation")
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("evaluate", help="review sheet, skeptic stats, theme stability")
    p.add_argument("--stability", action="store_true", help="rerun themes twice on one cluster (2 calls)")
    p.add_argument("--yes", action="store_true", help="skip the spend confirmation")
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("export", help="write static JSON for the frontend to public_data/")
    p.set_defaults(func=cmd_export)

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args, get_settings())


if __name__ == "__main__":
    main()
