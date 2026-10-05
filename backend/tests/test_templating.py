from __future__ import annotations

import pandas as pd

from radar import emergence, templating
from radar.taxonomy import cluster_id
from tests import fixtures


def test_fingerprint_ignores_redactions_case_and_punctuation() -> None:
    a = "On XX/XX/XXXX I noticed account XXXX. Please FIX it!"
    b = "on xx/xx/xx i noticed account xxxxxx please fix it"
    assert templating.fingerprint(a) == templating.fingerprint(b)
    assert templating.fingerprint("XXXX 123") is None


def test_fingerprint_uses_first_400_chars() -> None:
    head = "word " * 100
    assert templating.fingerprint(head + "alpha") == templating.fingerprint(head + "beta")


def test_mark_templated_threshold() -> None:
    df = pd.DataFrame({
        "complaint_id": [str(i) for i in range(9)],
        "product": ["p"] * 9,
        "issue": ["i"] * 9,
        "month": ["2026-01"] * 9,
        "narrative": ["same letter XXXX"] * 5 + ["one", "two", "three", ""],
    })
    marked = templating.mark_templated(df)
    assert len(marked) == 8
    assert marked["templated"].tolist() == [True] * 5 + [False] * 3


def test_templated_cluster_detected(complaints: pd.DataFrame) -> None:
    result = emergence.compute(complaints)
    shares = templating.templated_shares(templating.mark_templated(complaints), result)
    assert shares[cluster_id(*fixtures.TEMPLATED)] > 0.5
    assert shares[cluster_id(*fixtures.ACCELERATING)] < 0.05
