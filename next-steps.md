---
name: uplift
type: project
category: building
updated: 2026-10-31
note: working name; third sister site to HANGAR and OVERHANG
---
# UPLIFT — next steps

## Where this stands

Slice 1 built and verified locally 2026-10-31 (SPEC approved same day, "hit it").
`python run.py` reads ClinicalTrials.gov for 10 curated programs and renders two pages.
9 tests pass, ruff clean, both pages checked in a browser at 1280 and 390 px.

| Panel | State |
|---|---|
| Tracked programs | 10: Neural 6 (Neuralink, Synchron, Paradromics, Blackrock, BrainGate, ONWARD), Longevity 4 (mTOR inhibitors, metformin, dasatinib + quercetin, fisetin) |
| Trials | 79 registered, 45 active, after match rules |
| Countdown | Next registered primary completion; day or month precision only, "registered estimate" labelled |
| Design flags | Randomized / blinded / single-arm / n from registry fields; "overdue" when active past its completion date |
| Registry changes | Snapshot diff into `data/changes.json`; baseline taken 2026-10-31, events from the next refresh |
| Claims page | Shell only: ledger, speculative, follow-up links are slice 2 |

Known: the aging rule is literal. NCT03861767 (a surgical prehabilitation trial) passes
because the registry lists its condition as "Aging". An `exclude_nct` column with a
printed reason would handle such cases; an editorial call for Greg.

Precision Neuroscience is excluded because it has no registered trial (K4 working as intended).

## Next task

1. Greg picks the name (SPEC open question 1). Then `gh repo create`, push, enable Pages
   from `/docs`, run the workflow once by hand.
2. Slice 2: gated news + follow-up links (ADR needed: how a story is matched to a tracked
   item), and the claims ledger.
3. Remaining lanes: Body, Gene editing, AI in medicine (curated rows, sourced).

## Blockers

- Name (blocks publishing only; building continues).

## What keeps this current

`.github/workflows/refresh.yml` (copied from OVERHANG), cron every 6 h, commits `docs/` and
`data/`. Not live until the repo exists.
