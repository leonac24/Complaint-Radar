// Geometry of the radar scope, in a 640 x 640 SVG coordinate space.

import { FAMILIES } from "./format";
import type { ProductFamily, RadarCluster, RadarFile } from "./types";

interface Placed {
  id: string;
  product_family: ProductFamily;
}

export const SIZE = 640;
export const CENTER = SIZE / 2;
export const RADIUS = 248;

// Velocity sits on a log scale: MIN_V at the center, MAX_V at the rim.
const MIN_V = 0.8;
const MAX_V = 2;
export const RING_VELOCITIES = [1, 1.25, 1.5, 2];
const WEDGE = 360 / FAMILIES.length;

export function velocityRadius(velocity: number): number {
  const t = Math.log(velocity / MIN_V) / Math.log(MAX_V / MIN_V);
  return RADIUS * Math.min(1, Math.max(0.03, t));
}

export const MAX_BLIP = 16;

/** Blip radius from recent monthly volume (sqrt scale), and whether it hit the cap. */
export function blipRadius(volume: number): { r: number; capped: boolean } {
  const raw = 4 + Math.sqrt(volume / 40);
  return { r: Math.min(MAX_BLIP, raw), capped: raw > MAX_BLIP };
}

/**
 * A fixed angle per cluster, stable across months so blips move only outward or
 * inward as the month changes. Clusters share their family's wedge evenly, using
 * every cluster that appears in any month.
 */
export function clusterAngles(groups: Placed[][]): Record<string, number> {
  const byFamily = new Map<ProductFamily, Set<string>>();
  groups.forEach((group) =>
    group.forEach((c) => {
      const ids = byFamily.get(c.product_family) ?? new Set<string>();
      ids.add(c.id);
      byFamily.set(c.product_family, ids);
    }),
  );
  const angles: Record<string, number> = {};
  FAMILIES.forEach((family, f) => {
    const ids = [...(byFamily.get(family) ?? [])].sort();
    ids.forEach((id, k) => {
      angles[id] = f * WEDGE + (WEDGE * (k + 0.5)) / ids.length;
    });
  });
  return angles;
}

export function polar(angleDeg: number, r: number): { x: number; y: number } {
  const a = (angleDeg * Math.PI) / 180;
  return { x: CENTER + r * Math.sin(a), y: CENTER - r * Math.cos(a) };
}

export const spokeAngles = FAMILIES.map((_, i) => i * WEDGE);
export const familyLabelAngles = FAMILIES.map((family, i) => ({ family, angle: (i + 0.5) * WEDGE }));

/** Rank by velocity within the month's file (the export writes clusters in rank order). */
export function rankOf(file: RadarFile, id: string): number {
  return file.clusters.findIndex((c) => c.id === id) + 1;
}

export type BlipState = "kept" | "rejected" | "none";

export function blipState(cluster: RadarCluster): BlipState {
  return cluster.skeptic?.verdict ?? "none";
}
