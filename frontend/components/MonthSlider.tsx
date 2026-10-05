"use client";

import { monthLong, monthShort } from "@/lib/format";
import styles from "./MonthSlider.module.css";

interface Props {
  months: string[];
  index: number;
  onChange: (index: number) => void;
  playing: boolean;
  onTogglePlay: () => void;
  caption: string | null;
}

export function MonthSlider({ months, index, onChange, playing, onTogglePlay, caption }: Props) {
  const current = months[index] ?? "";
  const years = [...new Set(months.map((m) => m.slice(0, 4)))];
  return (
    <div className={styles.panel}>
      <div className={styles.top}>
        <button
          type="button"
          className={styles.play}
          onClick={onTogglePlay}
          aria-label={playing ? "Pause month playback" : `Play months from ${monthLong(months[0] ?? "")}`}
        >
          {playing ? "Pause" : "▶ Play"}
        </button>
        <span>Month</span>
        <span className={styles.current}>{monthLong(current)}</span>
      </div>
      <input
        type="range"
        className={styles.range}
        min={0}
        max={Math.max(0, months.length - 1)}
        step={1}
        value={index}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-label="Month"
        aria-valuetext={monthLong(current)}
      />
      <div className={styles.ticks} aria-hidden="true">
        {months.map((m, i) => (
          <span key={m} className={i === index ? styles.tickOn : styles.tick}>
            {monthShort(m)}
          </span>
        ))}
      </div>
      <div className={styles.years} aria-hidden="true">
        {years.map((y) => (
          <span key={y}>{y}</span>
        ))}
      </div>
      {caption && <p className={styles.caption}>{caption}</p>}
    </div>
  );
}
