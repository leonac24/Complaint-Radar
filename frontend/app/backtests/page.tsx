"use client";

import { Header } from "@/components/Header";
import { fetchBacktests, useLoad } from "@/lib/data";
import styles from "../pages.module.css";

export default function Backtests() {
  const backtests = useLoad("backtests", fetchBacktests);
  return (
    <>
      <Header current="backtests" />
      <main className={styles.page}>
        <h1 className={styles.title}>Backtests</h1>
        <p className={styles.lede}>
          Each case replays the radar as of an earlier month and asks whether the target cluster was already
          visible. Misses are listed the same way as hits.
        </p>
        {backtests.state === "loading" && <p className={styles.muted}>Loading…</p>}
        {backtests.state === "missing" && (
          <div className={styles.empty}>
            Backtests haven&apos;t run yet. Add cases to <code>backend/radar/backtest_cases.yaml</code>, then run{" "}
            <code>python -m radar.cli backtest</code> and <code>make export</code>.
          </div>
        )}
        {backtests.state === "error" && <div className={styles.empty}>{backtests.message}</div>}
        {backtests.state === "ready" && (
          <div className={styles.empty}>
            Backtest results exist, but this page does not display them yet (milestone 6).
          </div>
        )}
      </main>
    </>
  );
}
