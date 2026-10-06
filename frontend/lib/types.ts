// Mirrors the frontend contract in backend/radar/schemas.py. Keep the two in sync.
// Fields that depend on an AI step are null until that step has run.

export type ProductFamily =
  | "banking"
  | "cards"
  | "credit_reporting"
  | "debt_collection"
  | "lending"
  | "payments"
  | "other";

export type Verdict = "kept" | "rejected";

export type CheckName = "size" | "templating" | "concentration" | "thin_evidence" | "seasonality";

export interface MonthCount {
  month: string;
  count: number;
}

export interface TopCompany {
  name: string;
  count: number;
  lift: number;
}

export interface ThemeShare {
  label: string;
  description: string;
  share: number;
}

export interface BriefSummary {
  headline: string;
  confidence: number;
}

export interface SkepticSummary {
  verdict: Verdict;
  note: string;
}

export interface RadarCluster {
  id: string;
  product: string;
  issue: string;
  product_family: ProductFamily;
  velocity: number;
  recent_monthly_avg: number;
  baseline_monthly_avg: number;
  severity: number | null;
  templated_share: number | null;
  vulnerable_share: number | null;
  narrative_count: number;
  themes: ThemeShare[];
  top_companies: TopCompany[];
  states: Record<string, number>;
  months: MonthCount[];
  brief: BriefSummary | null;
  skeptic: SkepticSummary | null;
}

export interface RadarFile {
  month: string;
  clusters: RadarCluster[];
}

export interface ExampleSummary {
  complaint_id: string;
  summary: string;
}

export interface ThemeDetail {
  label: string;
  description: string;
  share: number;
  complaint_ids: string[];
  examples: ExampleSummary[];
}

export interface Brief {
  headline: string;
  what_is_happening: string;
  who_is_affected: string;
  likely_root_cause: string;
  process_or_control_to_check: string;
  regulatory_area: string;
  evidence: string[];
  confidence: number;
}

export interface SkepticCheck {
  name: CheckName;
  reason: string;
  result: "pass" | "fail";
}

export interface SkepticReview {
  checks: SkepticCheck[];
  verdict: Verdict;
  note: string;
}

export interface ClusterDetail {
  id: string;
  month: string;
  product: string;
  issue: string;
  product_family: ProductFamily;
  velocity: number;
  recent_monthly_avg: number;
  baseline_monthly_avg: number;
  severity: number | null;
  templated_share: number | null;
  vulnerable_share: number | null;
  narrative_count: number;
  top_companies: TopCompany[];
  states: Record<string, number>;
  months: MonthCount[];
  themes: ThemeDetail[];
  brief: Brief | null;
  skeptic: SkepticReview | null;
  examples: ExampleSummary[];
}

export interface ModelIds {
  fast: string;
  writer: string;
  reasoning: string;
}

export interface Meta {
  source: string;
  source_url: string;
  window_start: string;
  window_end: string;
  radar_months: string[];
  analysis_month: string;
  total_complaints: number;
  clusters_with_briefs: number;
  generated_at: string;
  models: ModelIds;
  available: string[];
}

export interface CompanyListItem {
  name: string;
  slug: string;
  complaints: number;
  reason: string;
}

export interface CompaniesFile {
  month: string;
  companies: CompanyListItem[];
}

export interface LensCluster {
  id: string;
  product: string;
  issue: string;
  product_family: ProductFamily;
  complaints: number;
  lift: number;
  company_velocity: number;
  peer_velocity: number;
}

export interface LensFile {
  company: string;
  slug: string;
  months: Record<string, LensCluster[]>;
}

export interface MiniBlip {
  id: string;
  product_family: ProductFamily;
  velocity: number;
  recent_monthly_avg: number;
}

export interface BacktestResult {
  name: string;
  public_date: string;
  as_of: string;
  cluster: string;
  source_url: string;
  found: boolean;
  rank: number | null;
  clusters_ranked: number;
  velocity: number | null;
  target_id: string | null;
  headline: string | null;
  verdict: Verdict | null;
  note: string | null;
  flagged: boolean;
  outcome: string;
  scope: MiniBlip[];
}

export interface BacktestsFile {
  results: BacktestResult[];
}

export interface ExtractionScore {
  total: number;
  rated: number;
  accurate: number;
  partially: number;
  wrong: number;
  accuracy: number | null;
  accurate_or_partial: number | null;
}

export interface StabilityResult {
  cluster: string;
  model: string;
  first_labels: string[];
  second_labels: string[];
  label_overlap: number;
  pair_agreement: number;
}

export interface Evaluation {
  generated_at: string;
  extraction: ExtractionScore | null;
  extraction_status: string;
  extraction_reviewer: string | null;
  skeptic: { kept: number; rejected: number; failed_checks: Record<string, number> } | null;
  stability: StabilityResult | null;
}
