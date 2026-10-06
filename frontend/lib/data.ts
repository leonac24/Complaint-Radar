// Reads the exported JSON. With NEXT_PUBLIC_API_URL set it calls the FastAPI app;
// otherwise it reads the static copy of public_data/ served at /data/.

import { useEffect, useState } from "react";
import type { BacktestsFile, ClusterDetail, CompaniesFile, Evaluation, LensFile, Meta, RadarFile } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

const paths = {
  meta: () => (API ? `${API}/api/meta` : "/data/meta.json"),
  radar: (month: string) => (API ? `${API}/api/radar?month=${month}` : `/data/radar_${month}.json`),
  cluster: (id: string) => (API ? `${API}/api/clusters/${id}` : `/data/cluster_${id}.json`),
  companies: () => (API ? `${API}/api/companies` : "/data/companies.json"),
  lens: (slug: string) => (API ? `${API}/api/companies/${slug}` : `/data/lens_${slug}.json`),
  backtests: () => (API ? `${API}/api/backtests` : "/data/backtests.json"),
  evaluation: () => (API ? `${API}/api/evaluation` : "/data/evaluation.json"),
};

export class MissingData extends Error {}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (response.status === 404) throw new MissingData(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return (await response.json()) as T;
}

export const fetchMeta = () => getJson<Meta>(paths.meta());
export const fetchRadar = (month: string) => getJson<RadarFile>(paths.radar(month));
export const fetchCluster = (id: string) => getJson<ClusterDetail>(paths.cluster(id));
export const fetchCompanies = () => getJson<CompaniesFile>(paths.companies());
export const fetchLens = (slug: string) => getJson<LensFile>(paths.lens(slug));
export const fetchBacktests = () => getJson<BacktestsFile>(paths.backtests());
export const fetchEvaluation = () => getJson<Evaluation>(paths.evaluation());

export type Loadable<T> =
  | { state: "loading" }
  | { state: "missing" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

/** Run an async loader when `key` changes. A null key means nothing to load yet. */
export function useLoad<T>(key: string | null, load: () => Promise<T>): Loadable<T> {
  const [value, setValue] = useState<Loadable<T>>({ state: "loading" });
  useEffect(() => {
    if (key === null) return undefined;
    let live = true;
    setValue({ state: "loading" });
    load().then(
      (data) => live && setValue({ state: "ready", data }),
      (error: unknown) =>
        live &&
        setValue(
          error instanceof MissingData
            ? { state: "missing" }
            : { state: "error", message: String(error) },
        ),
    );
    return () => {
      live = false;
    };
    // `load` is recreated each render; `key` identifies what it loads.
  }, [key]);
  return value;
}

/** Every radar month at once, so the slider and animations never wait on the network. */
export async function fetchAllRadar(meta: Meta): Promise<Record<string, RadarFile>> {
  const files = await Promise.all(meta.radar_months.map(fetchRadar));
  return Object.fromEntries(files.map((file) => [file.month, file]));
}
