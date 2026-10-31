"""ClinicalTrials.gov (API v2): trials for every tracked row, plus change detection.

Each tracked row carries a registry query and, optionally, match rules applied to the
results, because the registry's own search is fuzzy (a sponsor search for "Precision
Neuroscience" returns "Perception Neuroscience"). Rows marked ``aging_indication`` also
have to name aging in the study's conditions, keywords or title. All of it is plain
pattern matching, so the same registry data always gives the same board (SPEC D2, D4).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from uplift import net

API = "https://clinicaltrials.gov/api/v2/studies"
PAGE_SIZE = 200
AGING_RE = re.compile(
    r"\b(aging|ageing|older adults?|elderly|frailty|senescen\w*|longevity|healthspan|"
    r"geroscience|age-related)\b",
    re.I,
)
ACTIVE = {
    "RECRUITING",
    "NOT_YET_RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "ENROLLING_BY_INVITATION",
}
STATUS_LABEL = {
    "RECRUITING": "recruiting",
    "NOT_YET_RECRUITING": "not yet recruiting",
    "ACTIVE_NOT_RECRUITING": "active, not recruiting",
    "ENROLLING_BY_INVITATION": "enrolling by invitation",
    "COMPLETED": "completed",
    "TERMINATED": "terminated",
    "WITHDRAWN": "withdrawn",
    "SUSPENDED": "suspended",
    "UNKNOWN": "status unknown",
}
PHASE_LABEL = {
    "EARLY_PHASE1": "Early 1",
    "PHASE1": "1",
    "PHASE2": "2",
    "PHASE3": "3",
    "PHASE4": "4",
    "NA": "n.a.",
}


def _query(row: dict) -> dict:
    params = {"pageSize": PAGE_SIZE, "format": "json"}
    for field, param in (
        ("query_spons", "query.spons"),
        ("query_term", "query.term"),
        ("query_intr", "query.intr"),
        ("query_cond", "query.cond"),
    ):
        if (row.get(field) or "").strip():
            params[param] = row[field].strip()
    # Design and size filters are applied server-side to keep the download small, and
    # again in matches() so the rule holds whatever the server returns.
    adv = []
    if needs_randomized(row):
        adv.append("AREA[DesignAllocation]RANDOMIZED")
    if min_enrollment(row):
        adv.append(f"AREA[EnrollmentCount]RANGE[{min_enrollment(row)},MAX]")
    if adv:
        params["filter.advanced"] = " AND ".join(adv)
    return params


def needs_aging(row: dict) -> bool:
    return row["qualifies"] == "aging_indication" or row.get("require_aging") == "yes"


def needs_randomized(row: dict) -> bool:
    return row.get("randomized_only") == "yes"


def min_enrollment(row: dict) -> int:
    return int(row.get("min_enrollment") or 0)


def _fetch_all(params: dict) -> list[dict]:
    studies, token = [], None
    while True:
        p = dict(params, **({"pageToken": token} if token else {}))
        body = net.get(API, params=p).json()
        studies.extend(body.get("studies", []))
        token = body.get("nextPageToken")
        if not token:
            return studies


def _date(struct: dict | None) -> tuple[str | None, str | None]:
    """Registry date -> (YYYY-MM[-DD], 'ACTUAL' | 'ESTIMATED')."""
    if not struct:
        return None, None
    return struct.get("date"), struct.get("type")


def flatten(study: dict) -> dict:
    """Keep the fields the page uses; everything else stays upstream."""
    p = study["protocolSection"]
    ident, status = p["identificationModule"], p["statusModule"]
    design = p.get("designModule", {})
    spons = p.get("sponsorCollaboratorsModule", {})
    arms = p.get("armsInterventionsModule", {})
    conds = p.get("conditionsModule", {})
    outcomes = p.get("outcomesModule", {})
    info = design.get("designInfo", {})
    primary_date, primary_type = _date(status.get("primaryCompletionDateStruct"))
    enrol = design.get("enrollmentInfo", {})
    prim = outcomes.get("primaryOutcomes") or []
    return {
        "nct": ident["nctId"],
        "title": ident.get("briefTitle", ""),
        "official_title": ident.get("officialTitle", ""),
        "status": status.get("overallStatus", "UNKNOWN"),
        "last_update": (status.get("lastUpdatePostDateStruct") or {}).get("date"),
        "start": (status.get("startDateStruct") or {}).get("date"),
        "primary_completion": primary_date,
        "primary_completion_type": primary_type,
        "phases": design.get("phases") or [],
        "study_type": design.get("studyType"),
        "allocation": info.get("allocation"),
        "masking": (info.get("maskingInfo") or {}).get("masking"),
        "enrollment": enrol.get("count"),
        "enrollment_type": enrol.get("type"),
        "lead_sponsor": (spons.get("leadSponsor") or {}).get("name", ""),
        "collaborators": [c.get("name", "") for c in spons.get("collaborators", [])],
        "interventions": [i.get("name", "") for i in arms.get("interventions", [])],
        "conditions": conds.get("conditions") or [],
        "keywords": conds.get("keywords") or [],
        "primary_outcome": (prim[0].get("measure") if prim else None),
        # For grading the planned analysis (uplift/grade.py).
        "primary_outcomes": [
            {
                "measure": o.get("measure", ""),
                "description": (o.get("description") or "")[:400],
                "timeFrame": o.get("timeFrame", ""),
            }
            for o in prim
        ],
        "first_submitted": status.get("studyFirstSubmitDate"),
        "has_sap": any(
            d.get("hasSap")
            for d in (
                study.get("documentSection", {})
                .get("largeDocumentModule", {})
                .get("largeDocs")
                or []
            )
        ),
        "has_protocol": any(
            d.get("hasProtocol")
            for d in (
                study.get("documentSection", {})
                .get("largeDocumentModule", {})
                .get("largeDocs")
                or []
            )
        ),
        "has_results": bool(study.get("hasResults")),
        "start_type": (status.get("startDateStruct") or {}).get("type"),
        "results_posted": (status.get("resultsFirstPostDateStruct") or {}).get("date"),
    }


def matches(row: dict, s: dict) -> bool:
    """Apply a tracked row's match rules to one flattened study."""
    if row.get("match_sponsor"):
        names = [s["lead_sponsor"], *s["collaborators"]]
        if not any(re.search(row["match_sponsor"], n, re.I) for n in names):
            return False
    if row.get("match_intervention"):
        if not any(
            re.search(row["match_intervention"], n, re.I) for n in s["interventions"]
        ):
            return False
    if needs_randomized(row) and s.get("allocation") != "RANDOMIZED":
        return False
    if min_enrollment(row) and (s.get("enrollment") or 0) < min_enrollment(row):
        return False
    if needs_aging(row):
        text = " ".join([s["title"], *s["conditions"], *s["keywords"]])
        if not AGING_RE.search(text):
            return False
    return True


def fetch_for(tracked: list[dict]) -> dict:
    """{row_id: [study, ...]} for every tracked row, newest registry update first."""
    by_row: dict[str, list[dict]] = {}
    raw_counts: dict[str, int] = {}
    for row in tracked:
        studies = [flatten(s) for s in _fetch_all(_query(row))]
        raw_counts[row["id"]] = len(studies)
        kept = [s for s in studies if matches(row, s)]
        by_row[row["id"]] = sorted(
            kept, key=lambda s: s.get("last_update") or "", reverse=True
        )
        print(f"  [ctgov] {row['id']}: {len(studies)} returned, {len(kept)} kept")
    return {
        "by_row": by_row,
        "raw_counts": raw_counts,
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def diff(old: dict | None, new: dict, today: str) -> list[dict]:
    """Status changes between two registry snapshots (SPEC D4).

    A trial seen for the first time is ``new`` only when there was an earlier snapshot
    and its program was already in it: otherwise the first run, or adding a program to
    the tracked list, would report every trial as new.
    """
    if not old:
        return []
    before = {s["nct"]: s for rows in old.get("by_row", {}).values() for s in rows}
    events, seen = [], set()
    for row_id, studies in new["by_row"].items():
        for s in studies:
            if s["nct"] in seen:
                continue
            seen.add(s["nct"])
            b = before.get(s["nct"])
            base = {"date": today, "nct": s["nct"], "row": row_id, "title": s["title"]}
            if b is None:
                # Only a program that was already tracked can have a "new" trial; a
                # program just added to tracked.csv is a curation change, not news.
                if row_id in old.get("by_row", {}):
                    events.append(
                        {**base, "kind": "new", "detail": "new trial registered"}
                    )
                continue
            if b["status"] != s["status"]:
                events.append(
                    {
                        **base,
                        "kind": "status",
                        "detail": f"{STATUS_LABEL.get(b['status'], b['status'])} → "
                        f"{STATUS_LABEL.get(s['status'], s['status'])}",
                    }
                )
            if b["phases"] != s["phases"]:
                events.append(
                    {
                        **base,
                        "kind": "phase",
                        "detail": f"phase {phase_label(b['phases'])} → {phase_label(s['phases'])}",
                    }
                )
            if s["has_results"] and not b["has_results"]:
                events.append({**base, "kind": "results", "detail": "results posted"})
            if b.get("primary_completion") != s.get("primary_completion") and b.get(
                "primary_completion"
            ):
                events.append(
                    {
                        **base,
                        "kind": "date",
                        "detail": f"primary completion {b['primary_completion']} → "
                        f"{s['primary_completion']}",
                    }
                )
    return events


# FDA's device pathway runs early feasibility -> (traditional) feasibility -> pivotal.
# Read from the registry titles; a title that names no stage says so rather than guess.
DEVICE_STAGES = (
    ("pivotal", re.compile(r"(?<![a-z])pivotal(?![a-z])", re.I)),
    ("early feasibility", re.compile(r"early feasibility|first[- ]in[- ]human", re.I)),
    ("feasibility", re.compile(r"(?<![a-z])feasibility(?![a-z])", re.I)),
)


def device_stage(s: dict) -> str | None:
    text = f"{s.get('title', '')} {s.get('official_title', '')}"
    for label, rx in DEVICE_STAGES:
        if rx.search(text):
            return label
    return None


def phase_label(phases: list[str]) -> str:
    if not phases:
        return "n.a."
    return "/".join(PHASE_LABEL.get(p, p) for p in phases)


def design_flags(s: dict) -> dict:
    """Registry design fields as plain flags. Nothing here is inferred."""
    return {
        "randomized": s.get("allocation") == "RANDOMIZED",
        "single_arm": s.get("allocation") in (None, "NA")
        and s.get("study_type") == "INTERVENTIONAL",
        "blinded": s.get("masking") not in (None, "NONE"),
        "masking": (s.get("masking") or "none").lower(),
        "n": s.get("enrollment"),
        "n_type": (s.get("enrollment_type") or "").lower(),
    }
