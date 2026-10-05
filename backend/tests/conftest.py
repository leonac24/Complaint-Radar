from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from radar import ingest
from tests import fixtures


@pytest.fixture(scope="session")
def fixture_zips(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    return fixtures.generate(tmp_path_factory.mktemp("raw"))


@pytest.fixture(scope="session")
def complaints(fixture_zips: list[Path]) -> pd.DataFrame:
    return ingest.load(fixture_zips)
