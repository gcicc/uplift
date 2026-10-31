"""UPLIFT entry point.

    python run.py             # refresh what has gone stale, then render
    python run.py --force     # refresh everything regardless of cache age
    python run.py --render    # render from cache only, no network at all

The curated tracked list is validated first, so a bad row fails before any network
call. Registry changes are found by comparing the previous snapshot with the new one and
appended to ``data/changes.json``, a ledger that only grows (SPEC D4).
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from uplift import cache, ctgov, curated
from uplift.render import render

ROOT = Path(__file__).resolve().parent
CHANGES = ROOT / "data" / "changes.json"
CHANGES_KEEP = 1000
UPCOMING_SHOWN = 8


def cached(name: str):
    env = cache.load(name)
    return env["data"] if env else None


def record_changes(old: dict | None, new: dict | None) -> list[dict]:
    """Append this run's registry changes to the ledger and return the ledger."""
    ledger = json.loads(CHANGES.read_text(encoding="utf-8")) if CHANGES.exists() else []
    if new and (not old or old.get("fetched_at") != new.get("fetched_at")):
        events = ctgov.diff(old, new, date.today().isoformat())
        if events:
            ledger = (events + ledger)[:CHANGES_KEEP]
            CHANGES.write_text(json.dumps(ledger, indent=1), encoding="utf-8")
            print(f"  [changes] {len(events)} recorded")
    return ledger


def upcoming(rows: list[dict], by_row: dict, today: str) -> list[dict]:
    """Active trials whose primary completion date is still ahead, soonest first.

    One entry per trial even if two tracked rows find it. A date given only to the month
    keeps month precision; the countdown never shows finer units than that.
    """
    names = {r["id"]: r for r in rows}
    out, seen = [], set()
    for row_id, studies in by_row.items():
        for s in studies:
            d = s.get("primary_completion")
            if s["status"] not in ctgov.ACTIVE or not d or s["nct"] in seen:
                continue
            precision = "day" if len(d) == 10 else "month"
            end = d if precision == "day" else d + "-28"
            if end < today:
                continue
            seen.add(s["nct"])
            out.append(
                {
                    "nct": s["nct"],
                    "title": s["title"],
                    "date": d,
                    "precision": precision,
                    "estimated": s.get("primary_completion_type") != "ACTUAL",
                    "row": names[row_id]["name"],
                    "lane": names[row_id]["lane"],
                    "sponsor": s["lead_sponsor"],
                }
            )
    # A month-only date sorts at month end: "2026-11" is not known to precede 2026-11-01.
    return sorted(
        out, key=lambda u: u["date"] if len(u["date"]) == 10 else u["date"] + "-31"
    )[:UPCOMING_SHOWN]


def build_board(rows: list[dict], by_row: dict, today: str) -> list[dict]:
    """Lanes -> tracked rows -> trials, active trials first, with design flags."""
    lanes = []
    for lane, label in curated.LANES.items():
        members = []
        for r in (x for x in rows if x["lane"] == lane):
            studies = by_row.get(r["id"], [])
            for s in studies:
                s["flags"] = ctgov.design_flags(s)
                s["phase"] = ctgov.phase_label(s["phases"])
                s["status_label"] = ctgov.STATUS_LABEL.get(
                    s["status"], s["status"].lower()
                )
                s["active"] = s["status"] in ctgov.ACTIVE
                # An active trial whose registered completion date has passed: the
                # registry estimate is stale, or the trial is running late.
                pc = s.get("primary_completion") or ""
                s["overdue"] = (
                    s["active"]
                    and bool(pc)
                    and (pc if len(pc) == 10 else pc + "-31") < today
                )
            studies = sorted(
                studies,
                key=lambda s: (not s["active"], s.get("primary_completion") or "9999"),
            )
            members.append(
                {
                    **r,
                    "qualifies_label": curated.QUALIFIES[r["qualifies"]],
                    "trials": studies,
                    "n_active": sum(s["active"] for s in studies),
                    "n_overdue": sum(s["overdue"] for s in studies),
                }
            )
        lanes.append({"id": lane, "label": label, "rows": members})
    return lanes


def build_payload(today: date) -> dict:
    rows = curated.load_tracked()
    ct = cached("ctgov") or {"by_row": {}, "raw_counts": {}}
    changes = (
        json.loads(CHANGES.read_text(encoding="utf-8")) if CHANGES.exists() else []
    )
    trials = {s["nct"] for v in ct["by_row"].values() for s in v}
    return {
        "meta": {"generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M")},
        "counts": {
            "tracked": len(rows),
            "trials": len(trials),
            "active": len(
                {
                    s["nct"]
                    for v in ct["by_row"].values()
                    for s in v
                    if s["status"] in ctgov.ACTIVE
                }
            ),
        },
        "upcoming": upcoming(rows, ct["by_row"], today.isoformat()),
        "board": build_board(rows, ct["by_row"], today.isoformat()),
        "raw_counts": ct.get("raw_counts", {}),
        "changes": changes[:40],
        "aging_terms": ctgov.AGING_RE.pattern,
        "status": cache.status_report(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the UPLIFT pages.")
    parser.add_argument("--force", action="store_true", help="refresh every source")
    parser.add_argument(
        "--render", action="store_true", help="render from cache; no network"
    )
    args = parser.parse_args()

    tracked = curated.load_tracked()

    if not args.render:
        old = cached("ctgov")
        cache.refresh("ctgov", lambda: ctgov.fetch_for(tracked), force=args.force)
        record_changes(old, cached("ctgov"))

    payload = build_payload(datetime.now(UTC).date())

    print("\n=== STATUS ===")
    for name, s in payload["status"].items():
        flag = "STALE" if s["stale"] else "ok   "
        err = f"  last error: {s['last_error']}" if s["last_error"] else ""
        print(f"  {flag} {name:10s} age={s['age']:>6}{err}")
    c = payload["counts"]
    print(f"  tracked={c['tracked']} trials={c['trials']} active={c['active']}")

    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(exist_ok=True)
    render(payload, out)
    print(f"\nWrote {out.stat().st_size:,} bytes to {out}")


if __name__ == "__main__":
    main()
