// Tile-grid choropleth of US states. No external tiles or map data.

import styles from "./StateMap.module.css";

const TILES: Record<string, [row: number, col: number]> = {
  AK: [0, 0], ME: [0, 11], WI: [1, 6], VT: [1, 10], NH: [1, 11], WA: [2, 1], ID: [2, 2],
  MT: [2, 3], ND: [2, 4], MN: [2, 5], IL: [2, 6], MI: [2, 7], NY: [2, 9], MA: [2, 10],
  OR: [3, 1], NV: [3, 2], WY: [3, 3], SD: [3, 4], IA: [3, 5], IN: [3, 6], OH: [3, 7],
  PA: [3, 8], NJ: [3, 9], CT: [3, 10], RI: [3, 11], CA: [4, 1], UT: [4, 2], CO: [4, 3],
  NE: [4, 4], MO: [4, 5], KY: [4, 6], WV: [4, 7], VA: [4, 8], MD: [4, 9], DE: [4, 10],
  AZ: [5, 2], NM: [5, 3], KS: [5, 4], AR: [5, 5], TN: [5, 6], NC: [5, 7], SC: [5, 8],
  DC: [5, 9], OK: [6, 4], LA: [6, 5], MS: [6, 6], AL: [6, 7], GA: [6, 8], HI: [7, 0],
  TX: [7, 4], FL: [7, 9],
};

const BUCKETS = [
  { max: 2, fill: "#E2DEEA", ink: "#1E1B2E", label: "under 2%" },
  { max: 5, fill: "#B7AECF", ink: "#1E1B2E", label: "2–5%" },
  { max: 10, fill: "#7C6FA8", ink: "#F5F3F8", label: "5–10%" },
  { max: Infinity, fill: "#3A2E66", ink: "#F5F3F8", label: "over 10%" },
] as const;

const bucket = (pct: number) => BUCKETS.find((b) => pct < b.max) ?? BUCKETS[3];

const CELL = 24;

export function StateMap({ states }: { states: Record<string, number> }) {
  const total = Object.values(states).reduce((sum, n) => sum + n, 0);
  const share = (s: string) => (total ? ((states[s] ?? 0) / total) * 100 : 0);
  const top = Object.keys(states)
    .filter((s) => s in TILES)
    .sort((a, b) => share(b) - share(a))
    .slice(0, 3)
    .map((s) => `${s} ${share(s).toFixed(1)}%`)
    .join(" · ");

  return (
    <section className={styles.section}>
      <div className={styles.head}>
        <div className={styles.title}>Where claims come from</div>
        <div className={styles.top}>{top}</div>
      </div>
      <svg viewBox={`0 0 ${12 * CELL} ${8 * CELL}`} className={styles.map} role="img"
        aria-label={`Share of claims by state. Highest: ${top}.`}>
        {Object.entries(TILES).map(([s, [row, col]]) => {
          const pct = share(s);
          const b = bucket(pct);
          return (
            <g key={s} transform={`translate(${col * CELL} ${row * CELL})`}>
              <title>{`${s}: ${pct < 0.1 ? "under 0.1" : pct.toFixed(1)}%`}</title>
              <rect width={CELL - 2} height={CELL - 2} rx={4} fill={b.fill} />
              <text x={(CELL - 2) / 2} y={(CELL - 2) / 2} fill={b.ink} className={styles.code}>{s}</text>
            </g>
          );
        })}
      </svg>
      <div className={styles.legend}>
        Share of claims
        {BUCKETS.map((b) => (
          <span key={b.label} className={styles.key}>
            <span className={styles.swatch} style={{ background: b.fill }} />
            {b.label}
          </span>
        ))}
      </div>
    </section>
  );
}
