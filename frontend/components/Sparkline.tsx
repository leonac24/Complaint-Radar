"use client";

import { useState } from "react";
import { count, monthLong, monthShort } from "@/lib/format";
import type { MonthCount } from "@/lib/types";
import styles from "./Sparkline.module.css";

const W = 480;
const PAD = 12;
const TOP = 14;
const BOTTOM = 76;

interface Props {
  series: MonthCount[];
  /** The month the radar shows; the recent and baseline bands are drawn relative to it. */
  month: string;
  /** Months the slider can jump to. */
  pickable: Set<string>;
  onPick: (month: string) => void;
}

function trendNote(counts: number[]): string {
  const [a, b, c] = counts.slice(-3);
  if (a === undefined || b === undefined || c === undefined) return "";
  if (c < b && b < a) return "Fell the last two months";
  if (c > b && b > a) return "Rose the last two months";
  return "";
}

export function Sparkline({ series, month, pickable, onPick }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const counts = series.map((m) => m.count);
  const max = Math.max(1, ...counts);
  const step = (W - 2 * PAD) / Math.max(1, series.length - 1);
  const x = (i: number) => PAD + i * step;
  const y = (n: number) => BOTTOM - (n / max) * (BOTTOM - TOP);
  const peak = counts.indexOf(max);
  const at = Math.max(0, series.findIndex((m) => m.month === month));
  const recentStart = Math.max(0, at - 2);
  const baseStart = Math.max(0, at - 8);
  const shown = counts.slice(0, at + 1);
  const hovered = hover === null ? undefined : series[hover];
  const note = hovered
    ? `${monthLong(hovered.month)}: ${count(hovered.count)} claims${pickable.has(hovered.month) ? " · select to jump" : ""}`
    : trendNote(shown);

  return (
    <section className={styles.section}>
      <div className={styles.head}>
        <div className={styles.title}>Monthly trend</div>
        <div className={styles.note}>{note}</div>
      </div>
      <div className={styles.chart}>
        <svg viewBox={`0 0 ${W} 96`} className={styles.svg} role="img"
          aria-label={`Monthly complaints, ${series.map((m) => `${monthShort(m.month)} ${m.count}`).join(", ")}`}>
          {recentStart > baseStart && (
            <rect x={x(baseStart) - step / 2} y={4} width={step * (recentStart - baseStart)} height={72} className={styles.base} />
          )}
          <rect x={x(recentStart) - step / 2} y={4} width={step * (at - recentStart + 1)} height={72} className={styles.recent} />
          <line x1={x(at)} y1={0} x2={x(at)} y2={80} className={styles.marker} />
          <polyline points={counts.map((n, i) => `${x(i).toFixed(1)},${y(n).toFixed(1)}`).join(" ")} className={styles.line} />
          {counts.map((n, i) => (
            <circle key={i} cx={x(i)} cy={y(n)} r={i === peak ? 4.5 : 2.5} className={i === peak ? styles.peak : styles.dot} />
          ))}
          {series.map((m, i) => (
            <rect
              key={m.month}
              x={x(i) - step / 2}
              y={0}
              width={step}
              height={80}
              className={hover === i ? styles.hitOn : styles.hit}
              style={{ cursor: pickable.has(m.month) ? "pointer" : "default" }}
              onClick={() => pickable.has(m.month) && onPick(m.month)}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            />
          ))}
        </svg>
        <div className={styles.peakLabel} style={{ left: `${(x(peak) / W) * 100}%`, top: `${(Math.max(14, y(max) - 7) / 96) * 100}%` }}>
          Peak {count(max)} · {monthShort(series[peak]?.month ?? "")}
        </div>
        {recentStart > baseStart && (
          <div className={styles.band} style={{ left: `${(x((baseStart + recentStart - 1) / 2) / W) * 100}%` }}>
            baseline
          </div>
        )}
        <div className={styles.band} style={{ left: `${(x((recentStart + at) / 2) / W) * 100}%` }}>
          recent 3 mo
        </div>
      </div>
      <div className={styles.ends}>
        <span>{monthLong(series[0]?.month ?? "")}</span>
        <span>{monthLong(series[series.length - 1]?.month ?? "")}</span>
      </div>
    </section>
  );
}
