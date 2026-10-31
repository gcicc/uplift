"""Grade each trial's planned analysis from registry fields (SPEC K9).

Design is not graded: a brain implant or a retreat cannot be randomized, and a
within-subject before/after comparison is a legitimate plan for a single-group study.
What is graded is whether the analysis was fixed in advance and can be checked:

1. Registered prospectively (outcomes declared before data existed).
2. A focused primary endpoint (multiplicity is a plan, or a problem).
3. A statistical analysis plan (or at least a protocol) posted with the results
   (scored only once results are posted).
4. A stated comparison: randomized, or a within-subject change from baseline
   (not scored when every primary endpoint is safety or feasibility).
5. Results reported on time (only where FDAAA requires them, once due).

A criterion that does not apply is left out, not scored zero; the grade is the share
of available points.

Every criterion is plain field logic. No criterion reads the result of the trial.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

# FDAAA allows registration up to 21 days after the first participant is enrolled.
REGISTRATION_GRACE_DAYS = 21
# FDAAA requires results within one year of primary completion (applicable trials).
RESULTS_DUE_DAYS = 365
WITHIN_SUBJECT_RE = re.compile(
    r"baseline|before and after|pre[- ]?(?:and|/|to)[- ]?post|pre[- ]?post|change from|"
    r"changes? (?:in|between)|prior to and (?:after|following)",
    re.I,
)
SAFETY_RE = re.compile(
    r"adverse|safety|serious|tolerab|toxicit|feasib|complication|device[- ]related",
    re.I,
)
RESULTS_PHASES = {"PHASE2", "PHASE3", "PHASE4"}
GRADES = ((0.85, "A"), (0.65, "B"), (0.45, "C"), (0.0, "D"))


def _day(d: str | None, end: bool = False) -> date | None:
    if not d:
        return None
    if len(d) == 7:
        d = d + ("-28" if end else "-01")
    try:
        return date.fromisoformat(d[:10])
    except ValueError:
        return None


def criteria(s: dict, today: date) -> list[dict]:
    """[{key, label, points, of, why}] for one flattened study."""
    out = []

    # 1. Prospective registration
    sub, start = _day(s.get("first_submitted")), _day(s.get("start"))
    done = _day(s.get("primary_completion"))
    if sub and start:
        lag = (sub - start).days
        if lag <= REGISTRATION_GRACE_DAYS:
            pts, why = 2, "registered before or within 21 days of start"
        elif done and s.get("primary_completion_type") == "ACTUAL" and sub > done:
            pts, why = 0, f"registered {sub} — after primary completion ({done})"
        else:
            pts, why = 0, f"registered {lag} days after start"
        out.append(
            {
                "key": "prospective",
                "label": "Prospective registration",
                "points": pts,
                "of": 2,
                "why": why,
            }
        )

    # 2. Primary endpoint focus
    k = len(s.get("primary_outcomes") or [])
    if k:
        pts = 2 if k == 1 else 1 if k <= 3 else 0
        why = (
            "1 primary endpoint"
            if k == 1
            else f"{k} primary endpoints"
            + (
                "; no multiplicity plan visible"
                if k > 1 and not s.get("has_sap")
                else ""
            )
        )
        out.append(
            {
                "key": "focus",
                "label": "Focused primary endpoint",
                "points": pts,
                "of": 2,
                "why": why,
            }
        )

    # 3. Analysis plan on file. The registry expects the protocol and SAP to be uploaded
    # with results, so the criterion is scored only once results are posted; before
    # then, an absent SAP is normal and says nothing.
    if s.get("has_results"):
        if s.get("has_sap"):
            pts, why = 2, "statistical analysis plan posted with results"
        elif s.get("has_protocol"):
            pts, why = 1, "protocol posted with results, no separate analysis plan"
        else:
            pts, why = 0, "results posted without a protocol or analysis plan"
        out.append(
            {
                "key": "sap",
                "label": "Analysis plan posted",
                "points": pts,
                "of": 2,
                "why": why,
            }
        )

    # 4. Stated comparison. A safety- or feasibility-only primary endpoint needs no
    # comparator (early device studies are built this way), so it is not scored.
    prim = s.get("primary_outcomes") or []
    text = " ".join(
        f"{o.get('measure', '')} {o.get('description', '')} {o.get('timeFrame', '')}"
        for o in prim
    )
    safety_only = bool(prim) and all(
        SAFETY_RE.search(f"{o.get('measure', '')} {o.get('description', '')}")
        for o in prim
    )
    if not safety_only:
        if s.get("allocation") == "RANDOMIZED":
            pts, why = 2, "randomized comparison"
        elif WITHIN_SUBJECT_RE.search(text):
            pts, why = 2, "within-subject change from baseline"
        else:
            pts, why = 0, "no comparison stated in the primary endpoint"
        out.append(
            {
                "key": "comparison",
                "label": "Stated comparison",
                "points": pts,
                "of": 2,
                "why": why,
            }
        )

    # 5. Results on time: scored only where FDAAA requires results (phase 2+ drug or
    # biologic trials, pivotal device trials), once a year has passed since actual
    # primary completion. Feasibility, phase 1 and behavioral studies are not docked.
    required = bool(set(s.get("phases") or []) & RESULTS_PHASES) or (
        s.get("device_stage") == "pivotal"
    )
    if required and done and s.get("primary_completion_type") == "ACTUAL":
        due = done + timedelta(days=RESULTS_DUE_DAYS)
        if today >= due:
            if s.get("has_results"):
                pts, why = 2, "results posted"
            else:
                pts, why = 0, f"no results posted; due {due}"
            out.append(
                {
                    "key": "results",
                    "label": "Results reported",
                    "points": pts,
                    "of": 2,
                    "why": why,
                }
            )
    return out


def grade(s: dict, today: date) -> dict:
    cs = criteria(s, today)
    got, avail = sum(c["points"] for c in cs), sum(c["of"] for c in cs)
    frac = got / avail if avail else 0.0
    letter = next(g for cut, g in GRADES if frac >= cut)
    return {"letter": letter, "points": got, "of": avail, "criteria": cs}
