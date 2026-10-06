"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { fetchAllRadar, fetchCluster, fetchCompanies, fetchLens, fetchMeta, useLoad } from "@/lib/data";
import { monthLong, SEVERITY_COLORS } from "@/lib/format";
import { ALL_COMPANIES } from "@/lib/lens";
import { rankOf } from "@/lib/scope";
import type { Meta, RadarFile } from "@/lib/types";
import { BriefPanel } from "./BriefPanel";
import { ClusterTable } from "./ClusterTable";
import { Header } from "./Header";
import { MonthSlider } from "./MonthSlider";
import { Scope } from "./Scope";
import styles from "./RadarApp.module.css";

// The month the CFPB stopped publishing narratives. A fact about the source, not the data.
const PUBLICATION_ENDED = "2026-08";
const AUG_NOTE =
  "Public narrative publication ended in August 2026. Regulators still receive complaints; banks can run this radar on their own data.";
const PLAY_MS = 900;

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const update = () => setReduced(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return reduced;
}

export function RadarApp() {
  const meta = useLoad("meta", fetchMeta);
  const files = useLoad(meta.state === "ready" ? "files" : null, () =>
    meta.state === "ready" ? fetchAllRadar(meta.data) : Promise.reject(new Error("no meta")),
  );

  if (meta.state === "missing") {
    return (
      <Shell>
        <Empty title="No exported data yet">
          The radar reads the pipeline&apos;s exported files. Run <code>make pipeline</code>, or{" "}
          <code>make export</code> if the earlier steps have already run, then reload.
        </Empty>
      </Shell>
    );
  }
  if (meta.state === "error" || files.state === "error" || files.state === "missing") {
    const message = meta.state === "error" ? meta.message : files.state === "error" ? files.message : "A radar month file is missing.";
    return (
      <Shell>
        <Empty title="The data could not be loaded">
          {message} Run <code>make export</code> to rewrite it.
        </Empty>
      </Shell>
    );
  }
  if (meta.state !== "ready" || files.state !== "ready") {
    return (
      <Shell>
        <p className={styles.loading}>Loading the radar…</p>
      </Shell>
    );
  }
  return <Radar meta={meta.data} files={files.data} />;
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Header current="radar" />
      <main className={styles.shell}>{children}</main>
    </>
  );
}

function Empty({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className={styles.empty}>
      <h1 className={styles.emptyTitle}>{title}</h1>
      <p className={styles.emptyText}>{children}</p>
    </section>
  );
}

function Radar({ meta, files }: { meta: Meta; files: Record<string, RadarFile> }) {
  const months = meta.radar_months;
  const allFiles = useMemo(() => months.flatMap((m) => files[m] ?? []), [months, files]);
  const reduced = usePrefersReducedMotion();

  const [index, setIndex] = useState(Math.max(0, months.indexOf(meta.analysis_month)));
  const [augDismissed, setAugDismissed] = useState(true);
  const [view, setView] = useState<"radar" | "table">("radar");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [lensSlug, setLensSlug] = useState(ALL_COMPANIES);
  const [playing, setPlaying] = useState(false);
  const playTimer = useRef<number | undefined>(undefined);

  const month = months[index] ?? meta.analysis_month;
  const file = files[month] ?? { month, clusters: [] };

  const goTo = (next: number) => {
    setIndex(next);
    if (months[next] === PUBLICATION_ENDED) setAugDismissed(false);
  };

  const stopPlaying = () => {
    window.clearInterval(playTimer.current);
    setPlaying(false);
  };

  const togglePlay = () => {
    if (playing) {
      stopPlaying();
      return;
    }
    let at = index >= months.length - 1 ? 0 : index;
    goTo(at);
    setPlaying(true);
    playTimer.current = window.setInterval(() => {
      at += 1;
      goTo(Math.min(at, months.length - 1));
      if (at >= months.length - 1) stopPlaying();
    }, reduced ? PLAY_MS * 1.5 : PLAY_MS);
  };
  useEffect(() => () => window.clearInterval(playTimer.current), []);

  const detail = useLoad(selectedId ? `cluster:${selectedId}` : null, () => fetchCluster(selectedId ?? ""));

  const companiesFile = useLoad("companies", fetchCompanies);
  const companies = companiesFile.state === "ready" ? companiesFile.data.companies : [];
  const lensOn = lensSlug !== ALL_COMPANIES;
  const lensFile = useLoad(lensOn ? `lens:${lensSlug}` : null, () => fetchLens(lensSlug));
  const lensName = companies.find((c) => c.slug === lensSlug)?.name ?? lensSlug;
  const rows = useMemo(
    () => (lensOn && lensFile.state === "ready" ? lensFile.data.months[month] ?? [] : []),
    [lensOn, lensFile, month],
  );
  const lensMap = useMemo(() => (lensOn ? new Map(rows.map((r) => [r.id, r.lift])) : null), [rows, lensOn]);
  const slugByName = useMemo(() => new Map(companies.map((c) => [c.name, c.slug])), [companies]);
  const byVolume = companies.filter((c) => c.reason === "most complaints");
  const leaders = companies.filter((c) => c.reason !== "most complaints");

  const analysisFile = files[meta.analysis_month];
  const briefs = analysisFile?.clusters.filter((c) => c.skeptic) ?? [];
  const kept = briefs.filter((c) => c.skeptic?.verdict === "kept").length;

  const augShow = month === PUBLICATION_ENDED && !augDismissed && view === "radar";
  const selectedCluster = selectedId ? file.clusters.find((c) => c.id === selectedId) ?? null : null;

  return (
    <>
      <Header current="radar">
        <label className={styles.lensLabel}>
          Bank lens
          <select className={styles.select} value={lensSlug} disabled={companies.length === 0}
            title={companies.length === 0 ? "Run make export to build the lens" : undefined}
            onChange={(e) => setLensSlug(e.target.value)}>
            <option value={ALL_COMPANIES}>All companies</option>
            {byVolume.length > 0 && (
              <optgroup label="Most complaints">
                {byVolume.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
              </optgroup>
            )}
            {leaders.length > 0 && (
              <optgroup label="Leads a briefed cluster by lift">
                {leaders.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
              </optgroup>
            )}
          </select>
        </label>
      </Header>
      <main className={styles.main}>
        <div className={styles.left}>
          <div className={styles.toolbar}>
            <div className={styles.summary}>
              {monthLong(month)} · {file.clusters.length} clusters · {briefs.length} briefs
            </div>
            <div role="group" aria-label="View" className={styles.toggle}>
              <button type="button" aria-pressed={view === "radar"} className={view === "radar" ? styles.toggleOn : styles.toggleOff}
                onClick={() => setView("radar")}>Radar</button>
              <button type="button" aria-pressed={view === "table"} className={view === "table" ? styles.toggleOn : styles.toggleOff}
                onClick={() => setView("table")}>View as table</button>
            </div>
          </div>

          {view === "radar" ? (
            <Scope
              file={file}
              allFiles={allFiles}
              selectedId={selectedId}
              onSelect={setSelectedId}
              reduced={reduced}
              dimmed={augShow}
              lens={lensMap}
              overlay={augShow && (
                <div className={styles.augWrap}>
                  <div role="note" className={styles.augNote}>
                    <p className={styles.augText}>{AUG_NOTE}</p>
                    <button type="button" className={styles.augButton} onClick={() => setAugDismissed(true)}>
                      Continue to the radar
                    </button>
                  </div>
                </div>
              )}
            />
          ) : (
            <ClusterTable clusters={file.clusters} selectedId={selectedId} onSelect={setSelectedId} />
          )}

          {view === "radar" && !lensOn && (
            <div className={styles.legend}>
              <span>Distance from center: velocity, log scale</span>
              <span>Size: recent monthly volume (capped)</span>
              <span className={styles.key}>
                Severity 1
                {SEVERITY_COLORS.map((c) => <span key={c} className={styles.swatch} style={{ background: c }} />)}
                5
              </span>
              <span className={styles.key}><span className={styles.swatch} style={{ background: "#5E5870" }} />Kept</span>
              <span className={styles.key}><span className={styles.ring} />Rejected</span>
              <span className={styles.key}><span className={styles.dot} />No brief</span>
            </div>
          )}
          {view === "radar" && lensOn && (
            <div className={styles.legend}>
              <span>Lens color: {lensName}&apos;s lift in each cluster</span>
              {["under 1", "1–2", "2–5", "over 5"].map((label, i) => (
                <span key={label} className={styles.key}>
                  <span className={styles.swatch} style={{ background: SEVERITY_COLORS[i] }} />{label}
                </span>
              ))}
              <span>Faded: fewer than 10 of its complaints</span>
            </div>
          )}

          <MonthSlider
            months={months}
            index={index}
            onChange={(i) => {
              stopPlaying();
              goTo(i);
            }}
            playing={playing}
            onTogglePlay={togglePlay}
            caption={month === PUBLICATION_ENDED && !augShow ? AUG_NOTE : null}
          />
        </div>

        <BriefPanel
          month={month}
          analysisMonth={meta.analysis_month}
          radarMonths={months}
          clusterCount={file.clusters.length}
          briefCount={meta.clusters_with_briefs}
          keptCount={kept}
          selection={selectedId ? { id: selectedId, cluster: selectedCluster, rank: rankOf(file, selectedId), detail } : null}
          lens={lensOn ? {
            company: lensName,
            rows,
            loading: lensFile.state === "loading",
            onClear: () => setLensSlug(ALL_COMPANIES),
          } : null}
          lensable={new Set(slugByName.keys())}
          reduced={reduced}
          onSelect={setSelectedId}
          onLens={(name) => setLensSlug(slugByName.get(name) ?? ALL_COMPANIES)}
          onPickMonth={(m) => goTo(Math.max(0, months.indexOf(m)))}
        />
      </main>
    </>
  );
}
