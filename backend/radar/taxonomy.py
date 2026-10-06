"""Cluster ids and the mapping from CFPB products to radar sectors."""

from __future__ import annotations

import hashlib
import re
from typing import Literal, get_args

ProductFamily = Literal[
    "banking", "cards", "credit_reporting", "debt_collection", "lending", "payments", "other"
]
PRODUCT_FAMILIES: list[ProductFamily] = list(get_args(ProductFamily))

# Checked in order; the first keyword found in the lowercased product wins.
# "credit card or prepaid card" is a legacy product and lands in cards.
_FAMILY_KEYWORDS: list[tuple[str, ProductFamily]] = [
    ("credit report", "credit_reporting"),
    ("debt collection", "debt_collection"),
    ("credit card", "cards"),
    ("prepaid", "payments"),
    ("money transfer", "payments"),
    ("virtual currency", "payments"),
    ("money service", "payments"),
    ("checking", "banking"),
    ("savings", "banking"),
    ("bank account", "banking"),
    ("mortgage", "lending"),
    ("vehicle loan", "lending"),
    ("student loan", "lending"),
    ("payday", "lending"),
    ("personal loan", "lending"),
    ("consumer loan", "lending"),
]


def product_family(product: str) -> ProductFamily:
    lowered = product.lower()
    return next((fam for kw, fam in _FAMILY_KEYWORDS if kw in lowered), "other")


def cluster_label(product: str, issue: str) -> str:
    return f"{product} / {issue}"


def cluster_id(product: str, issue: str) -> str:
    return hashlib.sha1(cluster_label(product, issue).encode("utf-8")).hexdigest()[:10]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
