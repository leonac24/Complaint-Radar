"""Synthetic CFPB-format export zips with planted patterns.

    python -m tests.fixtures <out_dir>

Planted patterns (everything else is stable background):
- ACCELERATING: a payments fraud cluster that ramps from ~35/mo to ~220/mo from
  March 2026, dominated by ACCEL_COMPANY, a small company overall.
- TEMPLATED: a credit reporting cluster where most narratives are copies of a few
  form letters that differ only in redacted dates.

Two zips use different header styles (CSV-style vs API-style) and share some
complaint IDs, so normalization and dedupe are exercised. Data runs from
2025-09-01 to 2026-08-14, so August 2026 is a partial month like the real archive.
"""

from __future__ import annotations

import random
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ACCELERATING = ("Money transfer, virtual currency, or money service", "Fraud or scam")
TEMPLATED = (
    "Credit reporting or other personal consumer reports",
    "Incorrect information on your report",
)
ACCEL_COMPANY = "Acme Pay Inc."

START = date(2025, 9, 1)
END = date(2026, 8, 14)

COMPANIES: dict[str, float] = {
    "Big National Bank": 0.40,
    "Coastal Credit Union": 0.15,
    "Summit Card Services": 0.15,
    "Ledger Credit Bureau": 0.15,
    "Harbor Collections LLC": 0.10,
    ACCEL_COMPANY: 0.05,
}

# (product, issue) -> complaints per month for background clusters.
BACKGROUND: dict[tuple[str, str], int] = {
    ("Checking or savings account", "Managing an account"): 120,
    ("Credit card", "Fees or interest"): 90,
    # Same product as ACCELERATING, so ACCEL_COMPANY has peers to be measured against.
    ("Money transfer, virtual currency, or money service", "Other transaction problem"): 300,
    ("Debt collection", "Attempts to collect debt not owed"): 70,
    ("Mortgage", "Trouble during payment process"): 60,
    ("Credit reporting or other personal consumer reports", "Improper use of your report"): 100,
    ("Vehicle loan or lease", "Struggling to pay your loan"): 8,  # below the volume floor
}

ACCEL_MONTHLY: dict[str, int] = {
    "2026-03": 60, "2026-04": 90, "2026-05": 140, "2026-06": 180, "2026-07": 220, "2026-08": 110,
}
ACCEL_BASE = 35
TEMPLATED_MONTHLY = 80

FORM_LETTERS = [
    "I am writing to dispute the following information in my file. The items listed below "
    "are inaccurate and incomplete. Account XXXX opened XX/XX/XXXX is not mine. Under federal "
    "law you must investigate and remove these items within 30 days.",
    "This letter is a formal request to correct inaccurate information on my consumer report. "
    "On XX/XX/XXXX I noticed an account I do not recognize. I demand that this unverified "
    "account be deleted from my report immediately.",
    "I have been a victim of identity theft and the following accounts were not opened by me. "
    "Please block account XXXX reported on XX/XX/XXXX from my file as required.",
]

WORDS = (
    "account balance transfer charged refund branch phone agent called waited weeks letter "
    "statement payment deposit missing hold closed fee dispute card app login error told "
    "manager email online overdraft limit interest late reported credit score lender bank "
    "transaction unauthorized recipient scam sent money platform support reversed denied"
).split()

STATES = ["CA", "TX", "FL", "NY", "PA", "IL", "OH", "GA", "NC", "MI", "NJ", "VA", "WA", "AZ"]

CSV_HEADERS = {
    "date_received": "Date received",
    "product": "Product",
    "sub_product": "Sub-product",
    "issue": "Issue",
    "sub_issue": "Sub-issue",
    "narrative": "Consumer complaint narrative",
    "company": "Company",
    "state": "State",
    "zip_code": "ZIP code",
    "tags": "Tags",
    "submitted_via": "Submitted via",
    "company_response": "Company response to consumer",
    "timely": "Timely response?",
    "complaint_id": "Complaint ID",
}
API_HEADERS = {**{k: k for k in CSV_HEADERS}, "narrative": "complaint_what_happened"}


def months() -> list[tuple[str, date, date]]:
    """(YYYY-MM, first day, last day within START..END) for each month."""
    out = []
    first = START
    while first <= END:
        nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append((first.strftime("%Y-%m"), first, min(nxt - timedelta(days=1), END)))
        first = nxt
    return out


def _narrative(rng: random.Random) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(rng.randint(25, 60))).capitalize() + "."


def _letter(rng: random.Random) -> str:
    # Redacted spans vary in length; the fingerprint must still match.
    return rng.choice(FORM_LETTERS).replace("XXXX", "X" * rng.randint(2, 6))


def _company(rng: random.Random) -> str:
    return rng.choices(list(COMPANIES), weights=list(COMPANIES.values()))[0]


def _row(rng: random.Random, cid: int, day: date, product: str, issue: str, company: str,
         narrative: str) -> dict[str, str]:
    return {
        "date_received": day.isoformat(),
        "product": product,
        "sub_product": "",
        "issue": issue,
        "sub_issue": "",
        "narrative": narrative,
        "company": company,
        "state": rng.choice(STATES),
        "zip_code": f"{rng.randint(10000, 99999)}",
        "tags": "",
        "submitted_via": "Web",
        "company_response": "Closed with explanation",
        "timely": "Yes",
        "complaint_id": str(cid),
    }


def generate_rows(seed: int = 7) -> list[dict[str, str]]:
    rng = random.Random(seed)
    rows: list[dict[str, str]] = []

    def add(n: int, first: date, last: date, product: str, issue: str, pick_company, text) -> None:
        span = (last - first).days
        rows.extend(
            _row(rng, 1_000_000 + len(rows), first + timedelta(days=rng.randint(0, span)),
                 product, issue, pick_company(), text() if rng.random() < 0.6 else "")
            for _ in range(n)
        )

    for label, first, last in months():
        scale = (last.day - first.day + 1) / 30  # partial month gets fewer rows
        for (product, issue), per_month in BACKGROUND.items():
            add(round(per_month * scale), first, last, product, issue,
                lambda: _company(rng), lambda: _narrative(rng))
        accel = ACCEL_MONTHLY.get(label, ACCEL_BASE)
        accel_share = 0.75 if label in ACCEL_MONTHLY else 0.1
        add(accel, first, last, *ACCELERATING,
            lambda: ACCEL_COMPANY if rng.random() < accel_share else _company(rng),
            lambda: _narrative(rng))
        add(round(TEMPLATED_MONTHLY * scale), first, last, *TEMPLATED,
            lambda: "Ledger Credit Bureau",
            lambda: _letter(rng) if rng.random() < 0.7 else _narrative(rng))
    return rows


def write_zip(rows: list[dict[str, str]], path: Path, headers: dict[str, str]) -> Path:
    df = pd.DataFrame(rows).rename(columns=headers)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(path.stem + ".csv", df.to_csv(index=False))
    return path


def generate(out_dir: Path, seed: int = 7) -> list[Path]:
    """Write two overlapping export zips; return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = sorted(generate_rows(seed), key=lambda r: r["date_received"])
    cut = len(rows) // 2
    overlap = 200
    return [
        write_zip(rows[: cut + overlap], out_dir / "fixture_export_a.zip", CSV_HEADERS),
        write_zip(rows[cut:], out_dir / "fixture_export_b.zip", API_HEADERS),
    ]


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw/fixtures")
    written = generate(target)
    print(f"fixtures: wrote {len(written)} zips to {target}")
