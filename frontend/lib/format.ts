import type { CheckName, ProductFamily } from "./types";

export const FAMILIES: ProductFamily[] = [
  "banking",
  "cards",
  "credit_reporting",
  "debt_collection",
  "lending",
  "payments",
  "other",
];

export const FAMILY_LABEL: Record<ProductFamily, string> = {
  banking: "banking",
  cards: "cards",
  credit_reporting: "credit reporting",
  debt_collection: "debt collection",
  lending: "lending",
  payments: "payments",
  other: "other",
};

export const CHECK_LABEL: Record<CheckName, string> = {
  size: "Size",
  templating: "Templating",
  concentration: "Concentration",
  thin_evidence: "Thin evidence",
  seasonality: "Seasonality",
};

export const CHECK_ORDER: CheckName[] = [
  "size",
  "templating",
  "concentration",
  "thin_evidence",
  "seasonality",
];

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-08" -> "Aug 2026" */
export function monthLong(month: string): string {
  const [year, m] = month.split("-");
  return `${MONTHS[Number(m) - 1] ?? m} ${year}`;
}

/** "2026-08" -> "Aug" */
export function monthShort(month: string): string {
  return MONTHS[Number(month.split("-")[1]) - 1] ?? month;
}

/** Compact counts: 43, 1.6k, 123k. */
export function count(n: number): string {
  if (n >= 10000) return `${Math.round(n / 1000)}k`;
  if (n >= 1000) return `${(n / 1000).toFixed(1).replace(".0", "")}k`;
  return String(Math.round(n));
}

export const percent = (share: number, digits = 0) => `${(share * 100).toFixed(digits)}%`;

export const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

// CSS variables from app/globals.css; use them through `style`, not SVG presentation attributes.
export const SEVERITY_COLORS = ["var(--sev-1)", "var(--sev-2)", "var(--sev-3)", "var(--sev-4)"] as const;

/** Mean severity 1-5 -> one of four colors, low to high. */
export function severityColor(severity: number | null): string | null {
  if (severity === null) return null;
  const index = severity < 2 ? 0 : severity < 3 ? 1 : severity < 4 ? 2 : 3;
  return SEVERITY_COLORS[index];
}

export function liftColor(lift: number): string {
  const index = lift < 1 ? 0 : lift < 2 ? 1 : lift < 5 ? 2 : 3;
  return SEVERITY_COLORS[index];
}

/** Lift with two decimals below 10 (1.04, 9.50) and one above (26.1). */
export const liftText = (lift: number) => lift.toFixed(lift < 10 ? 2 : 1);

/** Plain-language reading of lift; within 20% of 1 counts as in line with peers. */
export function liftReading(lift: number): string {
  if (lift >= 1.2) return "▲ above peers";
  if (lift <= 0.8) return "▼ below peers";
  return "in line with peers";
}
