"""Load and validate the hand-curated tracked list in ``data/curated/tracked.csv``.

Each row names one intervention or company and the registry query that finds its
trials. The row is the editorial decision (SPEC K1: first-in-class, aimed at aging, or a
device); the trials themselves are fetched, never typed in. An invalid row fails the
build rather than being skipped, because a dropped row is a decision nobody made.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

CURATED = Path(__file__).resolve().parent.parent / "data" / "curated"

LANES = {
    "longevity": "Longevity",
    "neural": "Neural",
    "body": "Body",
    "gene": "Gene editing",
    "ai": "AI in medicine",
}
# Why a row is allowed on the board (SPEC K1). Devices are not drugs, so the me-too
# test does not apply to them.
QUALIFIES = {
    "first_in_class": "first in class",
    "aging_indication": "aimed at aging",
    "device": "device",
}
QUERY_FIELDS = ("query_spons", "query_term", "query_intr", "query_cond")


class CuratedError(ValueError):
    """A curated row fails validation; the message names the file, row id and field."""


def _read(name: str) -> list[dict]:
    with (CURATED / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_tracked() -> list[dict]:
    rows = _read("tracked.csv")
    seen: set[str] = set()
    for r in rows:
        where = f"tracked.csv[{r.get('id')}]"
        for f in ("id", "lane", "name", "what", "qualifies", "source_url"):
            if not (r.get(f) or "").strip():
                raise CuratedError(f"{where}: missing {f}")
        if r["id"] in seen:
            raise CuratedError(f"{where}: duplicate id")
        seen.add(r["id"])
        if r["lane"] not in LANES:
            raise CuratedError(f"{where}: lane {r['lane']!r} not in {sorted(LANES)}")
        if r["qualifies"] not in QUALIFIES:
            raise CuratedError(
                f"{where}: qualifies {r['qualifies']!r} not in {sorted(QUALIFIES)}"
            )
        if not r["source_url"].startswith(("http://", "https://")):
            raise CuratedError(f"{where}: source_url is not a URL")
        if not any((r.get(f) or "").strip() for f in QUERY_FIELDS):
            raise CuratedError(f"{where}: no registry query field set")
        for f in ("match_sponsor", "match_intervention"):
            if r.get(f):
                try:
                    re.compile(r[f], re.I)
                except re.error as exc:
                    raise CuratedError(
                        f"{where}: {f} is not a valid pattern: {exc}"
                    ) from exc
    return rows
