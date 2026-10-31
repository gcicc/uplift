# UPLIFT — project rules

Large project. `SPEC.md` holds the goal, kickoff decisions (K1–K5) and done criteria (D1–D8).
ADRs are in `decisions/`; never edited, only superseded. Live at https://gcicc.github.io/uplift/.

## Architecture

`run.py` → `uplift/curated.py` (validates `data/curated/tracked.csv`) → `uplift/cache.py`
(per-source `max_age`) → `uplift/ctgov.py` (ClinicalTrials.gov v2: query, match rules,
snapshot diff) → `data/changes.json` (append-only change ledger) → `uplift/render.py` +
`templates/` → `docs/index.html` (evidence-gated: countdown, changes, pipeline) and
`docs/claims.html` (claims, speculative, follow-up links). One template, switched on `page`.

## Rules

- Main page = registered trials or published data only (K4). Everything else goes to claims.
- No me-too drugs (K1): a drug program qualifies only as first-in-class or aimed at aging.
- Programs are curated; trials are fetched. Never type a trial, NCT ID or date in by hand.
- Every tracked row and every claim needs a source URL; quotes confirmed in raw page text.
- No LLM calls in the pipeline. Selection, gating and status are deterministic.
- Dependencies are `requests` and `jinja2` only. Ask Greg before adding one.
- Run `python -m pytest -q` and `python -m ruff check uplift tests run.py` before
  committing. Open both pages in a browser (1280 and 390 px) before saying a change is done.
