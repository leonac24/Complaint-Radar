"""FastAPI app serving the same JSON shapes as public_data/.

    uvicorn radar.api:app --port 8000

It reads the files `export` writes, so the API and the static demo cannot disagree.
A missing file returns 404 with the command that produces it.
"""

from __future__ import annotations

from pathlib import Path as FilePath
from typing import Annotated, TypeVar

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from radar.config import get_settings
from radar.schemas import (
    BacktestsFile,
    ClusterDetail,
    CompaniesFile,
    Evaluation,
    LensFile,
    Meta,
    RadarFile,
)

MONTH = r"^\d{4}-\d{2}$"
CLUSTER_ID = r"^[0-9a-f]{10}$"
SLUG = r"^[a-z0-9-]+$"

T = TypeVar("T", bound=BaseModel)

app = FastAPI(title="Complaint Radar", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def public_dir() -> FilePath:
    return get_settings().public_dir


PublicDir = Annotated[FilePath, Depends(public_dir)]


def serve(directory: FilePath, name: str, command: str, model: type[T]) -> T:
    """Load one exported file as its contract model; 404 names the command that writes it."""
    path = directory / name
    if not path.exists():
        raise HTTPException(404, f"{name} not found. Run: python -m radar.cli {command}")
    return model.model_validate_json(path.read_text())


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta")
def meta(directory: PublicDir) -> Meta:
    return serve(directory, "meta.json", "export", Meta)


@app.get("/api/radar")
def radar(directory: PublicDir,
          month: Annotated[str | None, Query(pattern=MONTH)] = None) -> RadarFile:
    chosen = month or meta(directory).analysis_month
    return serve(directory, f"radar_{chosen}.json", "export", RadarFile)


@app.get("/api/clusters/{cluster_id}")
def cluster(directory: PublicDir,
            cluster_id: Annotated[str, Path(pattern=CLUSTER_ID)]) -> ClusterDetail:
    return serve(directory, f"cluster_{cluster_id}.json", "export", ClusterDetail)


@app.get("/api/companies")
def companies(directory: PublicDir) -> CompaniesFile:
    return serve(directory, "companies.json", "export", CompaniesFile)


@app.get("/api/companies/{slug}")
def company(directory: PublicDir, slug: Annotated[str, Path(pattern=SLUG)]) -> LensFile:
    return serve(directory, f"lens_{slug}.json", "export", LensFile)


@app.get("/api/backtests")
def backtests(directory: PublicDir) -> BacktestsFile:
    return serve(directory, "backtests.json", "backtest", BacktestsFile)


@app.get("/api/evaluation")
def evaluation(directory: PublicDir) -> Evaluation:
    return serve(directory, "evaluation.json", "evaluate", Evaluation)
