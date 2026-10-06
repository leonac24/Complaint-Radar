// A still, small radar for one backtest: the scope as of a past month, target ringed.

import { blipRadius, CENTER, clusterAngles, polar, RADIUS, RING_VELOCITIES, SIZE, velocityRadius } from "@/lib/scope";
import type { MiniBlip } from "@/lib/types";
import styles from "./MiniScope.module.css";

export function MiniScope({ blips, targetId, label }: { blips: MiniBlip[]; targetId: string | null; label: string }) {
  const angles = clusterAngles([blips]);
  const target = blips.find((b) => b.id === targetId);
  const place = (b: MiniBlip) => polar(angles[b.id] ?? 0, velocityRadius(b.velocity));
  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className={styles.scope} role="img" aria-label={label}>
      <rect width={SIZE} height={SIZE} rx={24} className={styles.bg} />
      {RING_VELOCITIES.map((v) => (
        <circle key={v} cx={CENTER} cy={CENTER} r={velocityRadius(v)} className={styles.ring} />
      ))}
      {blips.filter((b) => b.id !== targetId).map((b) => {
        const { x, y } = place(b);
        return <circle key={b.id} cx={x} cy={y} r={blipRadius(b.recent_monthly_avg).r * 0.8} className={styles.blip} />;
      })}
      {target && (() => {
        const { x, y } = place(target);
        const r = blipRadius(target.recent_monthly_avg).r;
        return (
          <g>
            <circle cx={x} cy={y} r={r} className={styles.target} />
            <circle cx={x} cy={y} r={r + 12} className={styles.targetRing} />
          </g>
        );
      })()}
      <circle cx={CENTER} cy={CENTER} r={RADIUS} className={styles.ring} />
    </svg>
  );
}
