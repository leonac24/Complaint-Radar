"use client";

import { useEffect, useRef, useState } from "react";
import type { Loadable } from "@/lib/data";
import { capitalize, CHECK_LABEL, CHECK_ORDER, count, FAMILY_LABEL, liftReading, liftText, monthLong, percent } from "@/lib/format";
import type { ClusterDetail, LensCluster, MonthCount, RadarCluster, SkepticCheck } from "@/lib/types";
import { Sparkline } from "./Sparkline";
import { StateMap } from "./StateMap";
import styles from "./BriefPanel.module.css";

const REPLAY_MS = 700;

export interface Selection {
  id: string;
  /** This cluster in the month on screen; null when it is below the volume floor that month. */
  cluster: RadarCluster | null;
  rank: number;
  detail: Loadable<ClusterDetail>;
}

interface Props {
  month: string;
  analysisMonth: string;
  radarMonths: string[];
  clusterCount: number;
  briefCount: number;
  keptCount: number;
  selection: Selection | null;
  lens: { company: string; rows: LensCluster[]; loading: boolean; onClear: () => void } | null;
  /** Company names that have a precomputed lens. */
  lensable: Set<string>;
  reduced: boolean;
  onSelect: (id: string) => void;
  onLens: (company: string) => void;
  onPickMonth: (month: string) => void;
}

export function BriefPanel(props: Props) {
  const { selection, lens, briefCount, keptCount } = props;
  return (
    <aside aria-label="Brief" className={styles.panel}>
      {lens && <LensSection {...lens} onSelect={props.onSelect} />}
      {!selection && briefCount === 0 && (
        <section className={styles.intro}>
          <div className={styles.introTitle}>No briefs yet</div>
          <p className={styles.muted}>
            The analyst and skeptic steps haven&apos;t run, so the scope shows velocity and volume only.
            Severity, themes and verdicts appear once briefs exist.
          </p>
          <div>Run <code>make pipeline</code> to generate briefs.</div>
        </section>
      )}
      {!selection && !lens && briefCount > 0 && (
        <section className={styles.intro}>
          <div className={styles.introTitle}>Select a blip to read its brief</div>
          <p className={styles.muted}>
            {briefCount} clusters have briefs, written for {monthLong(props.analysisMonth)}. The skeptic
            kept {keptCount} and rejected {briefCount - keptCount}; rejected briefs stay on the scope as
            hollow outlines.
          </p>
        </section>
      )}
      {selection && <SelectedCluster key={selection.id} {...props} selection={selection} />}
    </aside>
  );
}

function LensSection({ company, rows, loading, onClear, onSelect }: NonNullable<Props["lens"]> & { onSelect: (id: string) => void }) {
  return (
    <section className={styles.stack}>
      <div className={styles.label}>Bank lens</div>
      <div className={styles.lensHead}>
        <div className={styles.lensName}>{company}</div>
        <button type="button" className={styles.textButton} onClick={onClear}>Clear lens</button>
      </div>
      <p className={styles.muted}>
        Lift is the company&apos;s share of a cluster divided by its share of that product. Above 1 means
        it is overrepresented among peers, not just large. Velocity compares the company&apos;s own
        recent complaints with its baseline, next to everyone else in the cluster. Clusters where it
        has at least 10 complaints in the recent three months.
      </p>
      <div>
        {loading && <p className={styles.muted}>Loading…</p>}
        {!loading && rows.length === 0 && <p className={styles.muted}>No cluster this month has 10 or more of its complaints.</p>}
        {rows.map((row) => (
          <button key={row.id} type="button" className={styles.lensRow} onClick={() => onSelect(row.id)}>
            <span className={styles.strong}>{row.issue}</span>
            <span className={styles.liftValue}>lift {liftText(row.lift)}</span>
            <span className={styles.small}>
              {row.product} · {count(row.complaints)} complaints · velocity {row.company_velocity.toFixed(2)}×
              vs. peers {row.peer_velocity.toFixed(2)}×
            </span>
            <span className={styles.tag}>{liftReading(row.lift)}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function verdictChip(detail: ClusterDetail | null, reviewing: boolean) {
  if (reviewing) return <span className={styles.chipReviewing}>Replaying skeptic…</span>;
  if (detail?.skeptic?.verdict === "kept") {
    return <span className={styles.chipKept}><span className={styles.chipDot} />Kept by skeptic</span>;
  }
  if (detail?.skeptic?.verdict === "rejected") {
    return <span className={styles.chipRejected}><span className={styles.chipRing} />Rejected by skeptic</span>;
  }
  return <span className={styles.chipNone}>No brief</span>;
}

function SelectedCluster(props: Props & { selection: Selection }) {
  const { selection, month, analysisMonth, reduced } = props;
  const detail = selection.detail.state === "ready" ? selection.detail.data : null;
  const stats = selection.cluster ?? detail;
  const hasBrief = Boolean(detail?.brief && detail.skeptic);
  const [step, setStep] = useState<number | null>(null);
  const [theme, setTheme] = useState<number | null>(null);

  const timer = useRef<number | undefined>(undefined);

  const replay = () => {
    window.clearInterval(timer.current);
    if (reduced || !hasBrief) return;
    let n = 0;
    setStep(0);
    timer.current = window.setInterval(() => {
      n += 1;
      const done = n > CHECK_ORDER.length;
      setStep(done ? null : n);
      if (done) window.clearInterval(timer.current);
    }, REPLAY_MS);
  };

  // Replay the skeptic once when a cluster with a brief opens; stop on close.
  useEffect(() => {
    replay();
    return () => window.clearInterval(timer.current);
  }, [hasBrief]);

  if (!stats) {
    return (
      <section className={styles.stack}>
        <p className={styles.muted}>{selection.detail.state === "loading" ? "Loading…" : "No data for this cluster."}</p>
      </section>
    );
  }

  const reviewing = step !== null;
  const title = detail?.brief?.headline ?? stats.issue;
  const otherMonth = month !== analysisMonth;
  const series: MonthCount[] = detail?.months ?? selection.cluster?.months ?? [];
  const companies = [...(selection.cluster?.top_companies ?? detail?.top_companies ?? [])]
    .sort((a, b) => b.lift - a.lift)
    .slice(0, 5);
  const chosenTheme = theme === null ? undefined : detail?.themes[theme];
  const examples = chosenTheme ? chosenTheme.examples : detail?.examples ?? [];

  const statItems = [
    { label: "Velocity", value: `${stats.velocity.toFixed(2)}×` },
    { label: "Recent vs. baseline", value: `${count(stats.recent_monthly_avg)} vs. ${count(stats.baseline_monthly_avg)}` },
    { label: "Narratives", value: count(stats.narrative_count) },
    ...(stats.templated_share === null ? [] : [{ label: "Templated", value: percent(stats.templated_share) }]),
    ...(stats.vulnerable_share === null ? [] : [{ label: "Vulnerable", value: percent(stats.vulnerable_share) }]),
  ];

  return (
    <>
      <section className={styles.stack}>
        <div className={styles.chips}>
          {verdictChip(detail, reviewing)}
          {detail?.brief && <span className={styles.muted}>Confidence {percent(detail.brief.confidence)}</span>}
          <span className={styles.rank}>
            {selection.cluster ? `Rank ${selection.rank} of ${props.clusterCount}` : `Below the volume floor in ${monthLong(month)}`}
          </span>
        </div>
        <h2 className={styles.headline}>{title}</h2>
        <div className={styles.muted}>
          {capitalize(FAMILY_LABEL[stats.product_family])} · {stats.product} / {stats.issue}
        </div>
        {otherMonth && hasBrief && (
          <p className={styles.notice}>
            Statistics are for {monthLong(month)}. The brief, themes and skeptic checks were written for{" "}
            {monthLong(analysisMonth)} data.
          </p>
        )}
        <div className={styles.stats}>
          {statItems.map((s) => (
            <div key={s.label} className={styles.stat}>
              <div className={styles.statLabel}>{s.label}</div>
              <div className={styles.statValue}>{s.value}</div>
            </div>
          ))}
        </div>
      </section>

      {detail && hasBrief && detail.brief && detail.skeptic && (
        <>
          {detail.themes.length > 0 && (
            <section className={styles.themes}>
              <div>
                <div className={styles.themesTitle}>Themes</div>
                <div className={styles.themesSub}>What the AI sees beyond the form category, by share of the AI sample</div>
              </div>
              {detail.themes.map((t, i) => {
                const top = Math.max(...detail.themes.map((x) => x.share));
                const on = theme === i;
                return (
                  <button key={t.label} type="button" aria-pressed={on} title={t.description}
                    className={on ? styles.themeOn : styles.theme}
                    style={{ opacity: theme === null || on ? 1 : 0.55 }}
                    onClick={() => setTheme(on ? null : i)}>
                    <span className={styles.themeRow}>
                      <span className={styles.themeLabel}>{t.label}</span>
                      <span className={styles.themePct}>{percent(t.share)}</span>
                    </span>
                    <span className={styles.bar}><span className={styles.barFill} style={{ width: `${(t.share / top) * 100}%` }} /></span>
                  </button>
                );
              })}
              <div className={styles.themesHint}>Select a theme to filter the example claims.</div>
            </section>
          )}

          <section className={styles.sections}>
            {[
              ["What is happening", detail.brief.what_is_happening],
              ["Who is affected", detail.brief.who_is_affected],
              ["Likely root cause (hypothesis)", detail.brief.likely_root_cause],
              ["Process or control to check", detail.brief.process_or_control_to_check],
              ["Regulatory area", detail.brief.regulatory_area],
            ].map(([label, text]) => (
              <div key={label}>
                <div className={styles.label}>{label}</div>
                <p className={styles.prose}>{text}</p>
              </div>
            ))}
          </section>

          <section className={styles.stack}>
            <div className={styles.sectionTitle}>Evidence</div>
            <ul className={styles.evidence}>
              {detail.brief.evidence.map((e) => <li key={e}>{e}</li>)}
            </ul>
          </section>

          <SkepticSection checks={detail.skeptic.checks} note={detail.skeptic.note} step={step}
            onReplay={replay} canReplay={!reduced} />

          <StateMap states={detail.states} />
        </>
      )}

      {series.length > 0 && (
        <Sparkline series={series} month={month} pickable={new Set(props.radarMonths)} onPick={props.onPickMonth} />
      )}

      {companies.length > 0 && (
        <section className={styles.stack}>
          <div className={styles.sectionTitle}>Top companies by lift</div>
          <div className={styles.small}>
            Lift = share of this cluster ÷ share of the product. Raw counts shown for context only. Companies
            with a bank lens open it when selected.
          </div>
          {companies.map((c) => {
            const inner = (
              <>
                <span className={styles.strong}>
                  {c.name}
                  <span className={styles.companyCount}>{count(c.count)} complaints</span>
                </span>
                <span className={styles.liftBig}>{liftText(c.lift)}×</span>
                <span className={styles.tag}>{liftReading(c.lift)}</span>
              </>
            );
            return props.lensable.has(c.name) ? (
              <button key={c.name} type="button" className={styles.company} onClick={() => props.onLens(c.name)}
                title="Open in bank lens">{inner}</button>
            ) : (
              <div key={c.name} className={styles.company} style={{ cursor: "default" }}>{inner}</div>
            );
          })}
        </section>
      )}

      {examples.length > 0 && (
        <section className={styles.stack}>
          <div className={styles.sectionTitle}>Example claims</div>
          <div className={styles.small}>AI-written one-sentence summaries. Unverified allegations.</div>
          {chosenTheme && (
            <div className={styles.filter}>
              <span className={styles.filterChip}>{chosenTheme.label}</span>
              <button type="button" className={styles.textButton} onClick={() => setTheme(null)}>Show all</button>
            </div>
          )}
          {examples.map((e) => (
            <div key={e.complaint_id} className={styles.example}>
              <p className={styles.exampleText}>{e.summary}</p>
              <div className={styles.complaintId}>CFPB complaint {e.complaint_id}</div>
            </div>
          ))}
        </section>
      )}

      {!hasBrief && selection.detail.state !== "loading" && (
        <p className={styles.muted}>
          Briefs are written for the 25 fastest-accelerating clusters in {monthLong(analysisMonth)}. This one is
          outside that cut, so it shows velocity and volume only.
        </p>
      )}
    </>
  );
}

function SkepticSection({ checks, note, step, onReplay, canReplay }: {
  checks: SkepticCheck[];
  note: string;
  step: number | null;
  onReplay: () => void;
  canReplay: boolean;
}) {
  const byName = new Map(checks.map((c) => [c.name, c]));
  const ordered = CHECK_ORDER.flatMap((name) => byName.get(name) ?? []);
  const passed = ordered.filter((c) => c.result === "pass").length;
  const reviewing = step !== null;
  return (
    <section className={styles.stack}>
      <div className={styles.skepticHead}>
        <div className={styles.sectionTitle}>Skeptic checks</div>
        <div className={styles.skepticMeta}>
          <span className={styles.muted}>
            {reviewing ? `Check ${Math.min(step + 1, ordered.length)} of ${ordered.length}` : `${passed} of ${ordered.length} passed`}
          </span>
          {canReplay && (
            <button type="button" className={styles.smallButton} onClick={onReplay}>Replay skeptic</button>
          )}
        </div>
      </div>
      <div className={styles.checks} aria-live="polite">
        {ordered.map((c, i) => {
          const pending = reviewing && i >= step;
          const failed = c.result === "fail";
          const rowClass = pending ? styles.check : failed ? styles.checkFail : styles.check;
          return (
            <div key={c.name} className={rowClass}>
              <span className={pending ? styles.resultPending : failed ? styles.resultFail : styles.resultPass}>
                {pending ? (i === step ? "◌ Checking" : "· Queued") : failed ? "✕ Fail" : "✓ Pass"}
              </span>
              <span className={pending ? styles.checkNamePending : failed ? styles.checkNameFail : styles.checkName}>
                {CHECK_LABEL[c.name]}
              </span>
              <span />
              <span className={pending ? styles.reasonPending : failed ? styles.reasonFail : styles.reason}>
                {pending ? (i === step ? "Showing the saved result…" : "") : c.reason}
              </span>
            </div>
          );
        })}
      </div>
      {!reviewing && (
        <div className={styles.note}>
          <div className={styles.label}>Skeptic&apos;s note</div>
          <p className={styles.prose}>{note}</p>
        </div>
      )}
    </section>
  );
}
