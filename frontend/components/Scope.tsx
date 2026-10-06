"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { count, FAMILY_LABEL, liftColor, liftText, severityColor } from "@/lib/format";
import {
  blipRadius,
  blipState,
  CENTER,
  clusterAngles,
  familyLabelAngles,
  polar,
  RADIUS,
  RING_VELOCITIES,
  SIZE,
  spokeAngles,
  velocityRadius,
  type BlipState,
} from "@/lib/scope";
import type { RadarCluster, RadarFile } from "@/lib/types";
import styles from "./Scope.module.css";

const SWEEP_MS = 6000;
const GLOW_DEG = 55;

interface Props {
  file: RadarFile;
  allFiles: RadarFile[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  reduced: boolean;
  dimmed: boolean;
  /** cluster id -> the lens company's lift there; null when no lens is active. */
  lens: Map<string, number> | null;
  overlay?: ReactNode;
}

interface Blip {
  cluster: RadarCluster;
  state: BlipState;
  angle: number;
  x: number;
  y: number;
  r: number;
  capped: boolean;
  fill: string;
  stroke: string;
  strokeWidth: number;
  opacity: number;
  title: string;
  meta: string;
}

const pct = (v: number) => `${(v / SIZE) * 100}%`;

function verdictText(state: BlipState): string {
  if (state === "kept") return "Kept by skeptic";
  if (state === "rejected") return "Rejected by skeptic";
  return "No brief";
}

function buildBlip(c: RadarCluster, angle: number, lens: Map<string, number> | null): Blip {
  const state = blipState(c);
  const { x, y } = polar(angle, velocityRadius(c.velocity));
  const size = blipRadius(c.recent_monthly_avg);
  const base = { cluster: c, state, angle, x, y, r: size.r, capped: size.capped, stroke: "none", strokeWidth: 0, opacity: 1 };
  const title = c.brief?.headline ?? `${c.product}: ${c.issue}`;
  const meta = `${c.velocity.toFixed(2)}× · ${count(c.recent_monthly_avg)}/mo · ${verdictText(state)}`;
  if (lens) {
    const lift = lens.get(c.id);
    return lift === undefined
      ? { ...base, r: 3, capped: false, fill: "var(--blip-faded)", opacity: 0.35, title, meta }
      : { ...base, r: Math.max(size.r, 7), capped: false, fill: liftColor(lift), title, meta: `${meta} · lift ${liftText(lift)}` };
  }
  if (state === "kept") return { ...base, fill: severityColor(c.severity) ?? "var(--scope-ink-2)", title, meta };
  if (state === "rejected") {
    // Hollow, as the spec asks: outline only. The hit circle keeps it easy to click.
    return { ...base, fill: "transparent", stroke: "var(--rejected)", strokeWidth: 2.5, title, meta };
  }
  return { ...base, fill: "var(--blip-none)", title, meta };
}

export function Scope({ file, allFiles, selectedId, onSelect, reduced, dimmed, lens, overlay }: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const sweepRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);

  const angles = useMemo(() => clusterAngles(allFiles.map((f) => f.clusters)), [allFiles]);
  // DOM order is velocity order, so Tab walks from the fastest cluster down.
  const blips = useMemo(
    () =>
      [...file.clusters]
        .sort((a, b) => b.velocity - a.velocity)
        .map((c) => buildBlip(c, angles[c.id] ?? 0, lens)),
    [file, angles, lens],
  );

  useEffect(() => {
    if (reduced) return undefined;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const theta = (((now - start) / SWEEP_MS) * 360) % 360;
      if (sweepRef.current) sweepRef.current.style.transform = `rotate(${theta}deg)`;
      rootRef.current?.querySelectorAll<SVGCircleElement>("[data-angle]").forEach((halo) => {
        const behind = (theta - Number(halo.dataset.angle) + 360) % 360;
        halo.style.opacity = behind < GLOW_DEG ? String((1 - behind / GLOW_DEG) * 0.55) : "0";
      });
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [reduced]);

  const moveFocus = (from: Element, step: number) => {
    const all = [...(rootRef.current?.querySelectorAll<SVGGElement>("[data-blip]") ?? [])];
    const next = all[(all.indexOf(from as SVGGElement) + step + all.length) % all.length];
    next?.focus();
  };

  const onKey = (event: KeyboardEvent<SVGGElement>, id: string) => {
    const keys: Record<string, () => void> = {
      Enter: () => onSelect(id),
      " ": () => onSelect(id),
      ArrowRight: () => moveFocus(event.currentTarget, 1),
      ArrowDown: () => moveFocus(event.currentTarget, 1),
      ArrowLeft: () => moveFocus(event.currentTarget, -1),
      ArrowUp: () => moveFocus(event.currentTarget, -1),
      Escape: () => onSelect(null),
    };
    const action = keys[event.key];
    if (action) {
      event.preventDefault();
      action();
    }
  };

  const tipBlip = blips.find((b) => b.cluster.id === (hover ?? focus));
  const transition = reduced ? undefined : "transform 700ms cubic-bezier(.3,.7,.3,1)";

  return (
    <div className={styles.scope} ref={rootRef}>
      <div className={styles.layer} style={{ opacity: dimmed ? 0.32 : 1 }}>
        {!reduced && (
          <div
            ref={sweepRef}
            aria-hidden="true"
            className={styles.sweep}
            style={{ left: pct(CENTER - RADIUS), top: pct(CENTER - RADIUS), width: pct(2 * RADIUS), height: pct(2 * RADIUS) }}
          >
            <div className={styles.arm} />
          </div>
        )}
        <svg
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className={styles.svg}
          role="group"
          aria-label="Radar scope. Distance from center is velocity, blip size is monthly volume, color is mean severity."
        >
          <circle cx={CENTER} cy={CENTER} r={velocityRadius(1)} className={styles.core} />
          {RING_VELOCITIES.map((v) => (
            <circle key={v} cx={CENTER} cy={CENTER} r={velocityRadius(v)} className={styles.ring} />
          ))}
          {spokeAngles.map((angle) => {
            const end = polar(angle, RADIUS);
            return <line key={angle} x1={CENTER} y1={CENTER} x2={end.x} y2={end.y} className={styles.ring} />;
          })}
          {blips.map((b) => {
            const id = b.cluster.id;
            return (
              <g
                key={id}
                data-blip=""
                tabIndex={0}
                role="button"
                aria-pressed={selectedId === id}
                aria-label={`${b.title}. ${b.meta}.`}
                className={styles.blip}
                style={{ transform: `translate(${b.x}px, ${b.y}px)`, transition, opacity: b.opacity }}
                onClick={() => onSelect(id)}
                onKeyDown={(event) => onKey(event, id)}
                onMouseEnter={() => setHover(id)}
                onMouseLeave={() => setHover(null)}
                onFocus={(event) => event.currentTarget.matches(":focus-visible") && setFocus(id)}
                onBlur={() => setFocus(null)}
              >
                <circle data-angle={b.angle} r={b.r + 7} opacity={0}
                  style={{ fill: b.state === "rejected" ? "var(--scope-ink-2)" : b.fill }} />
                <circle r={Math.max(b.r + 4, 12)} fill="transparent" />
                <circle r={b.r} style={{ fill: b.fill, stroke: b.stroke, strokeWidth: b.strokeWidth }} />
                {b.capped && <circle r={b.r + 3.5} className={styles.cap} />}
                {selectedId === id && <circle r={b.r + 6} className={styles.selected} />}
                {focus === id && <circle r={b.r + 10} className={styles.focus} />}
              </g>
            );
          })}
        </svg>
        {RING_VELOCITIES.map((v) => (
          <div
            key={v}
            className={styles.ringLabel}
            style={{ left: pct(CENTER + 5), top: pct(CENTER - velocityRadius(v) - 3) }}
          >
            {v}×
          </div>
        ))}
        {familyLabelAngles.map(({ family, angle }) => {
          const at = polar(angle, RADIUS + 22);
          return (
            <div key={family} className={styles.familyLabel} style={{ left: pct(at.x), top: pct(at.y) }}>
              {FAMILY_LABEL[family]}
            </div>
          );
        })}
      </div>
      {tipBlip && (
        <div className={styles.tip} style={{ left: pct(tipBlip.x), top: pct(tipBlip.y) }} role="presentation">
          <div className={styles.tipTitle}>{tipBlip.title}</div>
          <div className={styles.tipMeta}>{tipBlip.meta}</div>
        </div>
      )}
      {overlay}
    </div>
  );
}
