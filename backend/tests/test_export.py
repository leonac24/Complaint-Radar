from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from radar import api, export, templating
from radar.schemas import (
    Brief,
    ClusterDetail,
    Extraction,
    Meta,
    ModelIds,
    RadarFile,
    SkepticReview,
    ThemeOut,
)
from tests.fakes import BRIEF, EXTRACTION, REVIEW

MODELS = ModelIds(fast="f", writer="w", reasoning="r")


@pytest.fixture(scope="module")
def marked(complaints: pd.DataFrame) -> pd.DataFrame:
    return templating.mark_templated(complaints)


@pytest.fixture(scope="module")
def ai(analysis) -> export.AIOutputs:
    top = analysis.clusters[0].id
    sample = {f"9{i:03d}": Extraction.model_validate({**EXTRACTION, "severity": 2 + i % 3})
              for i in range(6)}
    ids = list(sample)
    return export.AIOutputs(
        themes={top: [ThemeOut(label="a", description="d", complaint_ids=ids[:4]),
                      ThemeOut(label="b", description="d", complaint_ids=ids[4:])]},
        briefs={top: Brief.model_validate(BRIEF)},
        reviews={top: SkepticReview.model_validate(REVIEW)},
        samples={top: sample},
    )


@pytest.fixture(scope="module")
def files(complaints, marked, analysis, ai) -> dict:
    shares = templating.templated_shares(marked, analysis)
    return export.build(complaints, marked, analysis, shares, ai, MODELS, [])


def test_radar_months_skip_months_without_history(complaints: pd.DataFrame) -> None:
    months = export.radar_months(complaints)
    assert months[0] == "2025-12"  # Sep-Nov 2025 have no baseline before them
    assert months[-1] == "2026-07"  # August 2026 is partial in the fixtures


def test_every_radar_month_is_written(files: dict, complaints: pd.DataFrame) -> None:
    for month in export.radar_months(complaints):
        radar = files[f"radar_{month}.json"]
        assert isinstance(radar, RadarFile) and radar.month == month


def test_ai_fields_only_on_the_analysis_month(files: dict, analysis) -> None:
    top = analysis.clusters[0].id
    current = {c.id: c for c in files[f"radar_{analysis.month}.json"].clusters}[top]
    assert current.brief is not None and current.skeptic is not None
    assert current.severity == pytest.approx(sum(2 + i % 3 for i in range(6)) / 6, abs=0.01)
    assert [t.share for t in current.themes] == [pytest.approx(4 / 6, abs=0.001),
                                                 pytest.approx(2 / 6, abs=0.001)]
    earlier = {c.id: c for c in files["radar_2026-03.json"].clusters}
    assert all(c.brief is None and c.severity is None and not c.themes for c in earlier.values())


def test_cluster_detail_has_examples_with_complaint_ids(files: dict, analysis) -> None:
    top = analysis.clusters[0].id
    detail = files[f"cluster_{top}.json"]
    assert isinstance(detail, ClusterDetail)
    assert len(detail.examples) == export.CLUSTER_EXAMPLES
    assert detail.themes[0].examples[0].complaint_id == "9000"
    assert detail.skeptic is not None and len(detail.skeptic.checks) == 5
    no_ai = files[f"cluster_{analysis.clusters[1].id}.json"]
    assert no_ai.brief is None and no_ai.examples == []


def test_meta_describes_the_export(files: dict, analysis, complaints) -> None:
    meta = files["meta.json"]
    assert isinstance(meta, Meta)
    assert meta.analysis_month == analysis.month
    assert meta.clusters_with_briefs == 1
    assert meta.total_complaints == len(complaints)


def test_write_replaces_stale_files_and_keeps_later_steps(tmp_path: Path, files: dict) -> None:
    (tmp_path / "cluster_deadbeef00.json").write_text("{}")
    (tmp_path / "backtests.json").write_text("[]")
    size = export.write(tmp_path, files)
    assert not (tmp_path / "cluster_deadbeef00.json").exists()
    assert (tmp_path / "backtests.json").exists()
    assert export.available_optional(tmp_path) == ["backtests"]
    assert 0 < size < export.SIZE_LIMIT_BYTES


# ---------- API ----------


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory, files: dict) -> TestClient:
    directory = tmp_path_factory.mktemp("public")
    export.write(directory, files)
    api.app.dependency_overrides[api.public_dir] = lambda: directory
    return TestClient(api.app)


def test_api_serves_export_shapes(client: TestClient, analysis) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/meta").json()["analysis_month"] == analysis.month
    default = client.get("/api/radar").json()
    assert default["month"] == analysis.month
    assert client.get("/api/radar", params={"month": "2026-03"}).json()["month"] == "2026-03"
    top = analysis.clusters[0].id
    assert client.get(f"/api/clusters/{top}").json()["brief"]["headline"] == BRIEF["headline"]


def test_api_missing_step_names_the_command(client: TestClient) -> None:
    response = client.get("/api/backtests")
    assert response.status_code == 404
    assert "radar.cli backtest" in response.json()["detail"]


def test_api_rejects_unsafe_parameters(client: TestClient) -> None:
    assert client.get("/api/radar", params={"month": "../meta"}).status_code == 422
    assert client.get("/api/clusters/..%2Fmeta").status_code in {404, 422}
    assert client.get("/api/companies/Bad_Slug").status_code == 422
