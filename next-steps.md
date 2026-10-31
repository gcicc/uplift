---
name: uplift
type: project
category: building
updated: 2026-10-31
url: https://gcicc.github.io/uplift/
note: third sister site to HANGAR and OVERHANG
---
# UPLIFT — next steps

## Where this stands

**2026-10-31 (later): K6 + K7.** Non-drug lane added (8 programs incl. Joe Dispenza's two
registered retreat studies, both single-group) and a "What to act on" summary at the top
(4 fixed rules). Board now 18 programs, 347 trials, 122 active; 34 active trials overdue.
Fixed: adding a program no longer logs its trials as "new" in the change ledger.
12 tests pass.

Slice 1 published 2026-10-31 at https://gcicc.github.io/uplift/ (repo `gcicc/uplift`, Pages
from `/docs` on `main`, branch build). Name UPLIFT confirmed by Greg. First scheduled-workflow
run verified green on manual dispatch.
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

1. Slice 2: gated news + follow-up links (ADR needed: how a story is matched to a tracked
   item), and the claims ledger.
2. Remaining lanes: Body, Gene editing, AI in medicine (curated rows, sourced).

## Blockers

None.

## What keeps this current

`.github/workflows/refresh.yml` (copied from OVERHANG), cron every 6 h, commits `docs/` and
`data/`. Live since 2026-10-31.
