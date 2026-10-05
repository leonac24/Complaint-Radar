"use client";

import { useState } from "react";
import { count, FAMILY_LABEL, severityColor } from "@/lib/format";
import type { RadarCluster } from "@/lib/types";
import styles from "./ClusterTable.module.css";

type Key = "name" | "velocity" | "volume" | "severity" | "verdict";

const COLUMNS: { key: Key; label: string; numeric: boolean }[] = [
  { key: "name", label: "Cluster", numeric: false },
  { key: "velocity", label: "Velocity", numeric: true },
  { key: "volume", label: "Recent/mo", numeric: true },
  { key: "severity", label: "Severity", numeric: true },
  { key: "verdict", label: "Skeptic", numeric: false },
];

const VERDICT_ORDER = { kept: 2, rejected: 1 } as const;

function sortValue(c: RadarCluster, key: Key): string | number {
  const values: Record<Key, () => string | number> = {
    name: () => c.issue,
    velocity: () => c.velocity,
    volume: () => c.recent_monthly_avg,
    severity: () => c.severity ?? -1,
    verdict: () => (c.skeptic ? VERDICT_ORDER[c.skeptic.verdict] : 0),
  };
  return values[key]();
}

interface Props {
  clusters: RadarCluster[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export function ClusterTable({ clusters, selectedId, onSelect }: Props) {
  const [sort, setSort] = useState<{ key: Key; dir: 1 | -1 }>({ key: "velocity", dir: -1 });
  const rows = [...clusters].sort((a, b) => {
    const x = sortValue(a, sort.key);
    const y = sortValue(b, sort.key);
    return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
  });
  const toggle = (key: Key) =>
    setSort((s) => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : key === "name" ? 1 : -1 }));

  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <caption className="visually-hidden">
          Clusters for the selected month. Select a column heading to sort; select a row to open its brief.
        </caption>
        <thead>
          <tr>
            {COLUMNS.map((col) => {
              const active = sort.key === col.key;
              return (
                <th key={col.key} scope="col" aria-sort={active ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
                  className={col.numeric ? styles.num : undefined}>
                  <button type="button" className={active ? styles.sortOn : styles.sort} onClick={() => toggle(col.key)}>
                    {col.label} <span className={styles.dir}>{active ? (sort.dir === 1 ? "↑" : "↓") : ""}</span>
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => {
            const color = severityColor(c.severity);
            return (
              <tr key={c.id} className={c.id === selectedId ? styles.selected : undefined}>
                <td>
                  <button type="button" className={styles.rowButton} onClick={() => onSelect(c.id)}>
                    <span className={styles.issue}>{c.issue}</span>
                    <span className={styles.product}>{c.product} · {FAMILY_LABEL[c.product_family]}</span>
                  </button>
                </td>
                <td className={styles.num}>{c.velocity.toFixed(2)}×</td>
                <td className={styles.num}>{count(c.recent_monthly_avg)}</td>
                <td className={styles.num}>
                  <span className={styles.sev}>
                    <span className={styles.dot} style={{ background: color ?? "transparent" }} />
                    {c.severity === null ? "—" : c.severity.toFixed(1)}
                  </span>
                </td>
                <td className={styles.verdict}>{c.skeptic ? (c.skeptic.verdict === "kept" ? "● Kept" : "○ Rejected") : "No brief"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className={styles.foot}>
        {clusters.length} clusters. Lift is shown per company in the brief, never as a raw-count ranking.
      </div>
    </div>
  );
}
