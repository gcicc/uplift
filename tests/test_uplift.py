"""Tests for the curated list, registry matching, change detection and the countdown."""

import pytest

import run
from uplift import ctgov, curated, render


def study(**kw):
    base = {
        "nct": "NCT00000001",
        "title": "A trial",
        "status": "RECRUITING",
        "phases": ["PHASE2"],
        "lead_sponsor": "Acme",
        "collaborators": [],
        "interventions": ["Drug X"],
        "conditions": [],
        "keywords": [],
        "has_results": False,
        "primary_completion": "2027-06-30",
        "primary_completion_type": "ESTIMATED",
        "allocation": "RANDOMIZED",
        "masking": "DOUBLE",
        "enrollment": 120,
        "enrollment_type": "ESTIMATED",
        "study_type": "INTERVENTIONAL",
    }
    base.update(kw)
    return base


def test_tracked_list_is_valid():
    rows = curated.load_tracked()
    assert {r["lane"] for r in rows} <= set(curated.LANES)
    assert all(r["source_url"].startswith("https://") for r in rows)


def test_tracked_row_without_query_fails(monkeypatch):
    row = {
        "id": "x",
        "lane": "neural",
        "name": "X",
        "what": "w",
        "qualifies": "device",
        "source_url": "https://example.com",
    }
    monkeypatch.setattr(curated, "_read", lambda name: [row])
    with pytest.raises(curated.CuratedError, match="no registry query"):
        curated.load_tracked()


def test_sponsor_rule_rejects_fuzzy_registry_match():
    row = {"qualifies": "device", "match_sponsor": "Precision Neuroscience"}
    assert not ctgov.matches(row, study(lead_sponsor="Perception Neuroscience"))
    assert ctgov.matches(row, study(collaborators=["Precision Neuroscience Corp"]))


def test_aging_rule_needs_aging_in_title_conditions_or_keywords():
    row = {"qualifies": "aging_indication", "match_intervention": "metformin"}
    assert not ctgov.matches(
        row, study(interventions=["Metformin"], conditions=["Diabetes"])
    )
    assert ctgov.matches(
        row, study(interventions=["Metformin"], conditions=["Frailty"])
    )
    assert not ctgov.matches(
        row, study(interventions=["Placebo"], conditions=["Aging"])
    )


def test_diff_reports_changes_but_not_on_first_snapshot():
    new = {
        "by_row": {
            "a": [study(status="COMPLETED", phases=["PHASE3"], has_results=True)]
        }
    }
    assert ctgov.diff(None, new, "2026-11-01") == []
    old = {"by_row": {"a": [study()]}}
    kinds = {e["kind"] for e in ctgov.diff(old, new, "2026-11-01")}
    assert kinds == {"status", "phase", "results"}
    added = {"by_row": {"a": [study(), study(nct="NCT00000002")]}}
    assert [e["kind"] for e in ctgov.diff(old, added, "2026-11-01")] == ["new"]


def test_upcoming_keeps_precision_and_skips_inactive_and_past():
    rows = [{"id": "a", "name": "A", "lane": "neural"}]
    by_row = {
        "a": [
            study(nct="N1", primary_completion="2027-03"),
            study(nct="N2", primary_completion="2026-12-15"),
            study(nct="N3", primary_completion="2026-01-01"),
            study(nct="N4", status="COMPLETED", primary_completion="2026-11-20"),
        ]
    }
    got = run.upcoming(rows, by_row, "2026-10-31")
    assert [(u["nct"], u["precision"]) for u in got] == [("N2", "day"), ("N1", "month")]


def test_design_flags_come_from_registry_fields():
    f = ctgov.design_flags(study(allocation="NA", masking="NONE"))
    assert (f["randomized"], f["blinded"], f["single_arm"]) == (False, False, True)


def test_cross_links():
    html = '<section id="board"></section><a href="#board">b</a><a href="#ledger">l</a>'
    out = render._cross_links(html, "main")
    assert 'href="#board"' in out and 'href="claims.html#ledger"' in out


def test_month_precision_sorts_after_days_in_that_month():
    rows = [{"id": "a", "name": "A", "lane": "neural"}]
    by_row = {
        "a": [
            study(nct="M", primary_completion="2026-11"),
            study(nct="D", primary_completion="2026-11-02"),
        ]
    }
    assert [u["nct"] for u in run.upcoming(rows, by_row, "2026-10-31")] == ["D", "M"]


def test_adding_a_program_is_not_reported_as_new_trials():
    old = {"by_row": {"a": [study()]}}
    new = {"by_row": {"a": [study()], "b": [study(nct="NCT00000009")]}}
    assert ctgov.diff(old, new, "2026-11-01") == []


def test_randomized_and_size_filters():
    row = {"qualifies": "non_drug", "randomized_only": "yes", "min_enrollment": "300"}
    assert ctgov.matches(row, study(enrollment=500))
    assert not ctgov.matches(row, study(enrollment=120))
    assert not ctgov.matches(row, study(allocation="NA", enrollment=500))


def test_summary_rules():
    from datetime import date

    today = date(2026, 10, 31)
    trials = [
        study(nct="R", results_posted="2026-10-01", has_results=True),
        study(nct="S", primary_completion="2026-12"),
        study(nct="T", start="2026-09-15", start_type="ACTUAL"),
        study(
            nct="L",
            primary_completion="2027-06-30",
            start="2020-01",
            start_type="ACTUAL",
        ),
    ]
    for s in trials:
        s["flags"] = ctgov.design_flags(s)
        s["active"] = True
    single = study(nct="U", allocation="NA")
    single["flags"] = ctgov.design_flags(single)
    single["active"] = True
    board = [
        {
            "label": "L",
            "rows": [
                {"id": "a", "name": "A", "qualifies": "non_drug", "trials": trials},
                {"id": "b", "name": "B", "qualifies": "non_drug", "trials": [single]},
            ],
        }
    ]
    sm = run.build_summary(board, [], today)
    assert [i["nct"] for i in sm["read_now"]] == ["R"]
    assert "S" in [i["nct"] for i in sm["soon"]] and "L" not in [
        i["nct"] for i in sm["soon"]
    ]
    assert [i["nct"] for i in sm["watch"]] == ["T"]
    assert [r["id"] for r in sm["no_rct"]] == ["b"]


def test_device_stage_from_titles():
    assert (
        ctgov.device_stage({"title": "X", "official_title": "A Pivotal Study of Y"})
        == "pivotal"
    )
    assert (
        ctgov.device_stage({"title": "VOICE: An Early Feasibility Study"})
        == "early feasibility"
    )
    assert (
        ctgov.device_stage({"title": "Feasibility of the BrainGate2 System"})
        == "feasibility"
    )
    assert ctgov.device_stage({"title": "Control of Assistive Devices"}) is None


def test_devices_exempt_from_no_rct():
    from datetime import date

    s = study(nct="D", allocation="NA")
    s["flags"] = ctgov.design_flags(s)
    s["active"] = True
    s["device_stage"] = "early feasibility"
    board = [
        {
            "label": "N",
            "rows": [
                {"id": "dev", "name": "Dev", "qualifies": "device", "trials": [s]},
                {
                    "id": "med",
                    "name": "Med",
                    "qualifies": "non_drug",
                    "trials": [dict(s, nct="M")],
                },
            ],
        }
    ]
    sm = run.build_summary(board, [], date(2026, 10, 31))
    assert [r["id"] for r in sm["no_rct"]] == ["med"]
    assert sm["devices"][0]["stages"]["early feasibility"] == 1
