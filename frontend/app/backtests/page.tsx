"use client";

import { Header } from "@/components/Header";
import { MiniScope } from "@/components/MiniScope";
import { fetchBacktests, useLoad } from "@/lib/data";
import { monthLong } from "@/lib/format";
import type { BacktestResult } from "@/lib/types";
import styles from "../pages.module.css";

function Case({ result }: { result: BacktestResult }) {
  return (
    <article className={styles.case}>
      <MiniScope
        blips={result.scope}
        targetId={result.target_id}
        label={`Radar as of ${monthLong(result.as_of)} with the target cluster ${result.found ? "ringed" : "absent"}.`}
      />
      <div className={styles.muted}>As of {monthLong(result.as_of)}{result.public_date && ` · public ${result.public_date}`}</div>
      <div className={styles.caseName}>{result.name}</div>
      <div className={styles.muted}>{result.cluster}</div>
      <div className={result.flagged ? styles.hit : styles.miss}>{result.flagged ? "✓ Flagged" : "✕ Not flagged"}</div>
      <p className={styles.caseText}>{result.outcome}</p>
      {result.note && <p className={styles.muted}>Skeptic: {result.note}</p>}
      {result.source_url && <a href={result.source_url}>Public source</a>}
    </article>
  );
}

export default function Backtests() {
  const backtests = useLoad("backtests", fetchBacktests);
  const results = backtests.state === "ready" ? backtests.data.results : [];
  const flagged = results.filter((r) => r.flagged).length;
  return (
    <>
      <Header current="backtests" />
      <main className={styles.page}>
        <h1 className={styles.title}>Backtests</h1>
        <p className={styles.lede}>
          Each case replays the radar using only data up to an earlier month and asks whether the target
          cluster was already visible and kept by the skeptic. Misses are listed the same way as hits.
        </p>
        {backtests.state === "loading" && <p className={styles.muted}>Loading…</p>}
        {backtests.state === "missing" && (
          <div className={styles.empty}>
            Backtests haven&apos;t run yet. Add verified cases to <code>backend/radar/backtest_cases.yaml</code>,
            then run <code>python -m radar.cli backtest</code> and <code>make export</code>.
          </div>
        )}
        {backtests.state === "error" && <div className={styles.empty}>{backtests.message}</div>}
        {backtests.state === "ready" && (
          <>
            <p className={styles.summaryLine}>{flagged} of {results.length} cases flagged before they became public.</p>
            <div className={styles.cases}>
              {results.map((r) => <Case key={r.name} result={r} />)}
            </div>
          </>
        )}
      </main>
    </>
  );
}
