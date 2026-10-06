"use client";

import { Header } from "@/components/Header";
import { fetchCluster, fetchEvaluation, fetchMeta, fetchRadar, useLoad } from "@/lib/data";
import { CHECK_LABEL, CHECK_ORDER, monthLong, percent } from "@/lib/format";
import type { ClusterDetail, Evaluation, Meta } from "@/lib/types";
import styles from "../pages.module.css";

// The default for RADAR_MODEL_REASONING in backend/radar/config.py.
const DEFAULT_REASONING_MODEL = "claude-opus-5-5";

interface SkepticTotals {
  kept: number;
  rejected: number;
  fails: Record<string, number>;
}

async function skepticTotals(meta: Meta): Promise<SkepticTotals> {
  const radar = await fetchRadar(meta.analysis_month);
  const ids = radar.clusters.filter((c) => c.skeptic).map((c) => c.id);
  const details: ClusterDetail[] = await Promise.all(ids.map(fetchCluster));
  const reviews = details.flatMap((d) => d.skeptic ?? []);
  const fails = Object.fromEntries(
    CHECK_ORDER.map((name) => [
      name,
      reviews.filter((r) => r.checks.some((c) => c.name === name && c.result === "fail")).length,
    ]),
  );
  return {
    kept: reviews.filter((r) => r.verdict === "kept").length,
    rejected: reviews.filter((r) => r.verdict === "rejected").length,
    fails,
  };
}

const LIMITATIONS: [string, string][] = [
  ["Unverified allegations.", "Complaints are consumers' claims. A rising cluster is a signal to investigate, not evidence that a company did anything wrong."],
  ["Size normalization.", "Lift compares a company with peers in the same product. It does not account for differences in customer mix."],
  ["Templating.", "Form letters and coordinated campaigns can inflate counts. They are detected and reported, not removed."],
  ["Sampling.", "The AI reads up to 40 narratives per cluster, not every complaint. Themes and briefs describe that sample."],
  ["Narrative lag.", "Fewer narratives are published for recent months, so the newest signals have the least text behind them."],
  ["One analysis month.", "The AI steps ran on the latest month only. Earlier months on the slider show statistics without briefs."],
];

export default function Method() {
  const meta = useLoad("meta", fetchMeta);
  const totals = useLoad(meta.state === "ready" ? "totals" : null, () =>
    meta.state === "ready" ? skepticTotals(meta.data) : Promise.reject(new Error("no meta")),
  );
  const evaluation = useLoad("evaluation", fetchEvaluation);
  const models = meta.state === "ready" ? meta.data.models : null;

  const steps: { name: string; detail: string; ai: boolean }[] = [
    { name: "Ingest", detail: "normalize, dedupe", ai: false },
    { name: "Emergence", detail: "velocity, lift", ai: false },
    { name: "Templating", detail: "copy-paste detection", ai: false },
    { name: "Extract", detail: models?.fast ?? "fast model", ai: true },
    { name: "Themes", detail: models?.reasoning ?? "reasoning model", ai: true },
    { name: "Analyst", detail: models?.writer ?? "writer model", ai: true },
    { name: "Skeptic", detail: models?.reasoning ?? "reasoning model", ai: true },
    { name: "Export", detail: "static JSON", ai: false },
  ];
  const maxFail = totals.state === "ready" ? Math.max(1, ...Object.values(totals.data.fails)) : 1;

  return (
    <>
      <Header current="method" />
      <main className={styles.page}>
        <h1 className={styles.title}>Method</h1>
        {meta.state === "ready" && (
          <p className={styles.lede}>
            {meta.data.total_complaints.toLocaleString("en-US")} complaints from the{" "}
            <a href={meta.data.source_url}>{meta.data.source}</a>, {monthLong(meta.data.window_start)} to{" "}
            {monthLong(meta.data.window_end)}. AI steps ran on {monthLong(meta.data.analysis_month)}.
          </p>
        )}
        {meta.state === "missing" && (
          <div className={styles.empty}>No exported data yet. Run <code>make pipeline</code>.</div>
        )}

        {models && models.reasoning !== DEFAULT_REASONING_MODEL && (
          <p className={styles.muted}>
            Themes and the skeptic default to <code>{DEFAULT_REASONING_MODEL}</code>; this run used{" "}
            <code>{models.reasoning}</code> to stay within the project&apos;s budget.
          </p>
        )}

        <ol className={styles.pipeline} aria-label="Pipeline">
          {steps.map((s) => (
            <li key={s.name} className={s.ai ? styles.stepAi : styles.step}>
              <div className={styles.stepName}>{s.name}</div>
              <div className={s.ai ? styles.stepModel : styles.stepDetail}>{s.detail}</div>
            </li>
          ))}
        </ol>

        <div className={styles.grid}>
          <section className={styles.block}>
            <h2 className={styles.h2}>
              Skeptic results{totals.state === "ready" ? `, ${totals.data.kept + totals.data.rejected} briefs` : ""}
            </h2>
            {totals.state === "ready" ? (
              <>
                <div className={styles.bigNumbers}>
                  <div><div className={styles.big}>{totals.data.kept}</div><div className={styles.muted}>kept</div></div>
                  <div><div className={styles.big}>{totals.data.rejected}</div><div className={styles.muted}>rejected</div></div>
                </div>
                <div className={styles.muted}>Briefs failing each check (a brief can fail more than one)</div>
                <div className={styles.bars}>
                  {CHECK_ORDER.map((name) => {
                    const n = totals.data.fails[name] ?? 0;
                    return (
                      <div key={name} className={styles.barRow}>
                        <span>{CHECK_LABEL[name]}</span>
                        <span className={styles.barTrack}><span className={styles.barFill} style={{ width: `${(n / maxFail) * 100}%` }} /></span>
                        <span className={styles.barValue}>{n}</span>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : (
              <p className={styles.muted}>{totals.state === "loading" ? "Loading…" : "No skeptic results yet. Run make pipeline."}</p>
            )}
          </section>
          <section className={styles.block}>
            <h2 className={styles.h2}>Extraction accuracy and theme stability</h2>
            {evaluation.state === "ready" ? (
              <EvaluationResults evaluation={evaluation.data} />
            ) : (
              <div className={styles.empty}>
                Evaluation hasn&apos;t run yet. Run <code>python -m radar.cli evaluate</code>, then <code>make export</code>.
              </div>
            )}
          </section>
        </div>

        <section className={styles.block}>
          <h2 className={styles.h2}>Limitations</h2>
          <div className={styles.limits}>
            {LIMITATIONS.map(([lead, text]) => (
              <p key={lead} className={styles.limit}><b>{lead}</b> {text}</p>
            ))}
          </div>
        </section>
      </main>
    </>
  );
}

function EvaluationResults({ evaluation }: { evaluation: Evaluation }) {
  const { extraction, stability } = evaluation;
  return (
    <>
      <div className={styles.label}>
        Extraction accuracy (50 random extractions rated against their narratives
        {evaluation.extraction_reviewer ? ` by ${evaluation.extraction_reviewer}` : ""})
      </div>
      {extraction && extraction.accuracy !== null ? (
        <div className={styles.bigNumbers}>
          <div><div className={styles.big}>{percent(extraction.accuracy)}</div><div className={styles.muted}>accurate</div></div>
          <div>
            <div className={styles.big}>{percent(extraction.accurate_or_partial ?? 0)}</div>
            <div className={styles.muted}>accurate or partially</div>
          </div>
          <div><div className={styles.big}>{extraction.wrong}</div><div className={styles.muted}>wrong of {extraction.rated} rated</div></div>
        </div>
      ) : (
        <div className={styles.empty}>Not rated yet. Rate the review sheet and the result appears here.</div>
      )}
      <div className={styles.label}>Theme stability (themes run twice on one cluster)</div>
      {stability ? (
        <>
          <div className={styles.bigNumbers}>
            <div><div className={styles.big}>{percent(stability.pair_agreement)}</div><div className={styles.muted}>complaint pairs grouped the same way</div></div>
            <div><div className={styles.big}>{stability.label_overlap.toFixed(2)}</div><div className={styles.muted}>label word overlap</div></div>
          </div>
          <div className={styles.muted}>{stability.cluster}</div>
          <div className={styles.runs}>
            {[stability.first_labels, stability.second_labels].map((labels, i) => (
              <div key={i}>
                <div className={styles.label}>Run {i + 1}</div>
                <ul className={styles.runList}>{labels.map((l) => <li key={l}>{l}</li>)}</ul>
              </div>
            ))}
          </div>
        </>
      ) : (
        <div className={styles.empty}>Not run yet. Run <code>python -m radar.cli evaluate --stability</code>.</div>
      )}
    </>
  );
}
