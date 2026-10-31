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
    "NA": "device / n.a.",
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
    return params


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
        "has_results": bool(study.get("hasResults")),
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
    if row["qualifies"] == "aging_indication":
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
    to compare against: the first run would otherwise report every trial as new.
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
                events.append({**base, "kind": "new", "detail": "newly tracked trial"})
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
