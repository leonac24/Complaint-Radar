// Bank lens built from each cluster's top companies in the month's radar file.
// A company only appears in clusters where it is among the top 10 by complaint count.

import type { RadarFile } from "./types";

export const ALL_COMPANIES = "All companies";
const LENS_COMPANIES = 15;

export interface LensRow {
  clusterId: string;
  product: string;
  issue: string;
  count: number;
  lift: number;
}

/** The companies with the most complaints across the month's clusters. */
export function lensCompanies(file: RadarFile): string[] {
  const totals = new Map<string, number>();
  file.clusters.forEach((c) =>
    c.top_companies.forEach((t) => totals.set(t.name, (totals.get(t.name) ?? 0) + t.count)),
  );
  return [...totals.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, LENS_COMPANIES)
    .map(([name]) => name);
}

/** Clusters where the company is among the top companies, highest lift first. */
export function lensRows(file: RadarFile, company: string): LensRow[] {
  return file.clusters
    .flatMap((c) =>
      c.top_companies
        .filter((t) => t.name === company)
        .map((t) => ({ clusterId: c.id, product: c.product, issue: c.issue, count: t.count, lift: t.lift })),
    )
    .sort((a, b) => b.lift - a.lift);
}
