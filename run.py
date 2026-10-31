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
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from uplift import cache, ctgov, curated
from uplift.render import render

ROOT = Path(__file__).resolve().parent
CHANGES = ROOT / "data" / "changes.json"
CHANGES_KEEP = 1000
UPCOMING_SHOWN = 8

# Actionable summary (SPEC K7). Fixed windows, printed on the page; no ranking model.
READ_WINDOW_DAYS = 90  # results first posted within this many days
SOON_WINDOW_DAYS = (
    120  # randomized trial reaching primary completion within this many days
)
STARTED_WINDOW_DAYS = (
    120  # randomized trial that actually started within this many days
)
CHANGE_WINDOW_DAYS = 30  # registry events within this many days
SUMMARY_ITEMS = 6


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
                s["device_stage"] = (
                    ctgov.device_stage(s) if r["qualifies"] == "device" else None
                )
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


def _end(d: str) -> str:
    """Latest day a registry date can mean: a month-only date means up to month end."""
    return d if len(d) == 10 else d + "-31"


def _start(d: str) -> str:
    return d if len(d) == 10 else d + "-01"


def build_summary(board: list[dict], changes: list[dict], today: date) -> dict:
    """What deserves attention now, from fixed rules over registry fields.

    Each item carries the rule that put it there. This is a reading list, not medical
    advice: "read now" means results exist to be read, not that anything works.
    """
    t = today.isoformat()
    read_after = (today - timedelta(days=READ_WINDOW_DAYS)).isoformat()
    soon_by = (today + timedelta(days=SOON_WINDOW_DAYS)).isoformat()
    started_after = (today - timedelta(days=STARTED_WINDOW_DAYS)).isoformat()
    change_after = (today - timedelta(days=CHANGE_WINDOW_DAYS)).isoformat()

    trials, programs = {}, {}
    for lane in board:
        for r in lane["rows"]:
            programs[r["id"]] = r
            for s in r["trials"]:
                trials.setdefault(
                    s["nct"], {**s, "program": r["name"], "lane": lane["label"]}
                )
    every = list(trials.values())

    def item(s: dict, why: str) -> dict:
        return {
            "nct": s["nct"],
            "title": s["title"],
            "program": s["program"],
            "why": why,
        }

    read_now = sorted(
        (
            s
            for s in every
            if s.get("results_posted") and s["results_posted"] >= read_after
        ),
        key=lambda s: s["results_posted"],
        reverse=True,
    )
    soon = sorted(
        (
            s
            for s in every
            if s["active"]
            and s["flags"]["randomized"]
            and s.get("primary_completion")
            and t <= _end(s["primary_completion"])
            and _start(s["primary_completion"]) <= soon_by
        ),
        key=lambda s: _end(s["primary_completion"]),
    )
    started = sorted(
        (
            s
            for s in every
            if s["flags"]["randomized"]
            and s.get("start_type") == "ACTUAL"
            and s.get("start")
            and _start(s["start"]) >= started_after
        ),
        key=lambda s: s["start"],
        reverse=True,
    )
    events = [c for c in changes if c["date"] >= change_after and c["kind"] != "date"]
    no_rct = [
        r
        for r in programs.values()
        # Devices are exempt: a sham-controlled implant is not a realistic design. FDA's
        # RISE workshop (2026-09-29) covered nonrandomized designs (Session 1) and pivotal
        # studies of BCI devices in small populations (Session 4). Shown by stage instead.
        if r["qualifies"] != "device"
        and r["trials"]
        and not any(s["flags"]["randomized"] for s in r["trials"])
    ]
    devices = [
        {
            "id": r["id"],
            "name": r["name"],
            "stages": {
                st: sum(
                    1
                    for s in r["trials"]
                    if s["active"] and s.get("device_stage") == st
                )
                for st in ("pivotal", "feasibility", "early feasibility")
            },
            "unstated": sum(
                1 for s in r["trials"] if s["active"] and not s.get("device_stage")
            ),
        }
        for r in programs.values()
        if r["qualifies"] == "device" and any(s["active"] for s in r["trials"])
    ]
    overdue = [s for s in every if s.get("overdue")]

    def fmt_n(s):
        return f"n={s['flags']['n']}" if s["flags"]["n"] else "n not given"

    return {
        "read_now": [
            item(s, f"results posted {s['results_posted']}") for s in read_now
        ][:SUMMARY_ITEMS],
        "soon": [
            item(
                s,
                f"randomized, {fmt_n(s)}; primary completion {s['primary_completion']}"
                + (
                    " (estimate)"
                    if s.get("primary_completion_type") != "ACTUAL"
                    else ""
                ),
            )
            for s in soon
        ][:SUMMARY_ITEMS],
        "watch": (
            [
                {
                    "nct": c["nct"],
                    "title": c["title"],
                    "program": programs.get(c["row"], {}).get("name", ""),
                    "why": f"{c['detail']} ({c['date']})",
                }
                for c in events
            ]
            + [
                item(s, f"randomized, {fmt_n(s)}; started {s['start']}")
                for s in started
            ]
        )[:SUMMARY_ITEMS],
        "no_rct": [
            {"id": r["id"], "name": r["name"], "n": len(r["trials"])} for r in no_rct
        ],
        "devices": devices,
        "overdue": len(overdue),
        "windows": {
            "read": READ_WINDOW_DAYS,
            "soon": SOON_WINDOW_DAYS,
            "started": STARTED_WINDOW_DAYS,
            "change": CHANGE_WINDOW_DAYS,
        },
    }


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
        "board": (board := build_board(rows, ct["by_row"], today.isoformat())),
        "summary": build_summary(board, changes, today),
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
