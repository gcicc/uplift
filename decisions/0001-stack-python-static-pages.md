# 0001 — Python pipeline rendering static pages (inherited from OVERHANG)

Date: 2026-10-31 · Status: accepted (SPEC constraints, approved by Greg 2026-10-31)

**Decision.** Same stack as OVERHANG ADR 0001: a Python pipeline (`requests` + `jinja2`)
renders self-contained static HTML, committed to `/docs` and served by GitHub Pages; a
scheduled GitHub Actions workflow refreshes it.

**Context.** Third sister site to HANGAR and OVERHANG. Free public data (ClinicalTrials.gov),
no server, no database, refresh every 6 hours is ample for a registry that updates daily.

**Consequences.** Registry change history lives in a committed JSON ledger
(`data/changes.json`), which grows; revisit storage at the growth checkpoint (SPEC ADR list).
