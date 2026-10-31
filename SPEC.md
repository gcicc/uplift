# SPEC — UPLIFT

Status: **approved by Greg 2026-10-31 ("hit it")** · assumptions A1–A4 accepted as written · written 2026-10-31 · kickoff decisions recorded below

## Goal

A self-refreshing public website that tracks **frontier human enhancement**: living longer and
doing more. The site follows research, clinical trials and regulatory decisions across longevity,
neural and bodily augmentation, in-body gene editing and AI in medicine. Its organising rule is
**evidence-gated**: the main page shows only work with a registered trial or published data, and
everything further out is held to account as a dated claim on a second page. Third in the family
with HANGAR (SpaceX & Tesla) and OVERHANG (AI), built the same way.

## Kickoff decisions (Greg, 2026-10-31)

| # | Decision | Greg's words / answer |
|---|---|---|
| K1 | No me-too drugs. Inclusion: first-in-class (new mechanism or target), **or** aimed at aging itself even if the mechanism is known | "I don't care about me-too drugs"; chose (b) |
| K2 | Brain-computer interfaces are in: Neuralink and its competitors | "add in neurulink and competitors" |
| K3 | Scope is frontier enhancement, not longevity alone | "longevity, augmentation, etc. futuristic stuff" |
| K4 | Speculative topics with no trial or data (cryonics, mind uploading, "live to 150") appear only as claims on the claims page. The main page requires a registered trial or published data | "claims page only, trials required for the main page" |
| K5 | News on the main page is gated the same way. Stories that do not qualify are kept as follow-up links, not discarded | "gated news - with links that I can follow-up on if I'm interested" |
| K6 | Non-drug interventions are a lane, all of them (exercise, fasting, mind-body, breathwork, heat/cold, sleep), not only mind-body. Named programs (e.g. Joe Dispenza's retreat studies) tracked by sponsor; broad categories must name aging and count randomized trials only, exercise also n ≥ 300 | "include studies along lines of joe dispenza ... non-pharmalogical"; "Every non-drug intervention" (2026-10-31) |
| K7 | The main page opens with an actionable summary, even when the action is "keep your eye on this". Built from fixed, printed rules; a reading list, not medical advice | "this page needs an 'actionable summary' at the top" (2026-10-31) |
| K8 | Devices are not held to randomization: a sham-controlled brain implant is not a realistic design. They are exempt from "no randomized trial yet" and shown by device stage (early feasibility, feasibility, pivotal), read from registry titles. Basis: FDA RISE workshop 2026-09-29 (Session 1 nonrandomized designs; Session 4 BCI pivotal studies in ALS) | "wash this against FDA guidance ... RISE FDA workshop"; "you cant do rct with brain implat!" (2026-10-31) |

## Pages

**Main page (`index.html`): evidence only.**
0. **What to act on** (K7): read now (results posted ≤ 90 days), readout soon (randomized,
   primary completion ≤ 120 days), keep your eye on this (registry changes ≤ 30 days,
   randomized trials started ≤ 120 days), no randomized trial yet (per program).
1. **Countdown** to the next dated readout or regulatory decision (trial primary completion date,
   FDA action date, scheduled data presentation). Never shows finer units than the date is known to.
   A trial's registered completion date is labelled "registered estimate", since they slip.
2. **Recent news by lane**, gated: a story qualifies only if it names something tracked (a
   registered trial, a tracked sponsor, or an FDA action).
3. **Pipeline board**: every tracked intervention by lane and phase, with status changes flagged
   (new trial, phase advance, completion, termination, results posted).
4. **Design-quality flags** per trial, read from registry fields: randomised or not, blinded or
   not, enrolment, primary endpoint hard or surrogate.

**Claims page (`claims.html`): what has been said.**
1. **Claims ledger**: dated promises (founders, companies, researchers, podcasters) with a
   verbatim quote, source and horizon; status computed, never written by hand (OVERHANG rules).
2. **Speculative topics** (K4): cryonics, mind uploading, radical life extension and the like,
   as claims only.
3. **Follow-up links** (K5): news stories that did not pass the main-page gate, newest first,
   each a plain link with outlet and date.

## Lanes

| Lane | Covers |
|---|---|
| Longevity | Interventions aimed at aging itself (K1): senolytics, rapalogs, partial reprogramming, aging-targeted gene therapies, first-in-class drugs with an aging indication |
| Neural | Brain-computer interfaces (K2), vision restoration, neuroprosthetics |
| Body | Bionic limbs, exoskeletons, xenotransplantation, bioengineered organs |
| Gene editing | One-time in-body edits (base, prime, CRISPR) that are first-in-class |
| AI in medicine | AI-discovered molecules by phase; FDA's list of AI-enabled devices |
| Non-drug (K6) | Exercise, fasting and caloric restriction, meditation and mindfulness, tai chi/yoga/qigong, breathwork, heat and cold, sleep; named programs such as Joe Dispenza's retreat studies |

## Done criteria (testable)

- [ ] D1. `python run.py` builds `docs/index.html` and `docs/claims.html` with no network
      (`--render`) from cached data, and refreshes stale sources otherwise.
- [ ] D2. Every main-page item links to a registered trial (NCT or equivalent ID), a published
      paper, or an FDA document. A test fails the build on any main-page item without one.
- [ ] D3. The K1 rule is applied from a curated, sourced list of tracked interventions, each with
      its lane, mechanism and the reason it qualifies (first-in-class or aging indication). The
      build fails on a row without a source.
- [ ] D4. Pipeline status changes are detected by comparing registry snapshots, not by hand.
- [ ] D5. Every claim's quote is confirmed verbatim in the raw source page before it shows.
      Status is computed; a passed deadline reads "outcome unverified" without evidence.
- [ ] D6. News gating is deterministic and its rule is printed on the page. A rejected story
      appears in the follow-up list, never silently dropped.
- [ ] D7. A failed source keeps its last good copy and is flagged stale.
- [ ] D8. Tests pass, ruff is clean, both pages are checked in a browser at desktop and phone
      width before any "done" claim. Published on GitHub Pages with a scheduled refresh.

## Out of scope (v1)

- Greg's own health data, appraisals and `register.csv` (public site; see A1).
- Me-too drugs (K1). Supplements without a registered trial.
- Any LLM in the pipeline: selection, gating and status are deterministic.
- Paid data sources.

## Constraints

- Free sources only, rate limits respected. Candidates: ClinicalTrials.gov API v2, openFDA,
  FDA's AI-enabled device list, PubMed E-utilities, bioRxiv/medRxiv API, RSS.
- Same stack as OVERHANG (ADR 0001 there): Python, `requests` + `jinja2`, server-rendered static
  pages, GitHub Pages from `/docs`. Ask before any other dependency.
- Never add a tracked intervention or claim from memory: every row needs a source.

## Assumptions (labelled — not confirmed by Greg)

- A1. A public observatory like HANGAR and OVERHANG, not a personal decision tool. Inferred from
  "futuristic stuff".
- A2. The follow-up links (K5) live on the claims page rather than a third page.
- A3. Starts in `01-Active-Projects/uplift`, moving to `02-Maintain` once it is self-running.
  (OVERHANG started directly in 02-Maintain by Greg's call; say so if you want the same here.)
- A4. HANGAR keeps its light Neuralink coverage as the Musk-companies view.

## Open questions (one at a time, during the build)

1. ~~Name~~ — resolved 2026-10-31: UPLIFT (Greg).
2. Does "Body" include cosmetic or performance enhancement (e.g., gene doping) or medical only?
3. Should ClinTrialist link here, or this site link to it? They overlap on pharma news.

## ADR-level decisions (to be briefed in 4 lines each when reached)

- How a story is matched to a tracked item for the news gate (sponsor names, NCT IDs, drug
  names), since that rule decides what is on the main page.
- Snapshot storage for registry change detection (size grows with every refresh).
