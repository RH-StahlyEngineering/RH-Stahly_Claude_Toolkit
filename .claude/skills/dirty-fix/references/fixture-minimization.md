# Fixture minimization

The fixture is the smallest **real** input that still exercises the phenomenon, plus the
context the logic needs around it, plus the tail cases production actually contains.

Getting this wrong is the classic spike failure: proved on 5k rows, the 40M rows had
three format variants the 5k didn't, back to the drawing board. Everything below exists
to make that outcome mechanical to avoid rather than a matter of foresight.

---

## Step 1 — Profile production BEFORE reducing

**Never open with "what should go in the fixture?"** The human will answer from memory,
and memory omits precisely the variant that later breaks everything.

Instead, characterize the full input. This is affordable because profiling is `O(scan)`
while the work is `O(algorithm)` — typically 10–1000× cheaper. If even a full scan is
too expensive, sample stratified and record the sampling method and its confidence.

Inventory, adapted to the input type:

| Dimension | Examples |
|---|---|
| Structural variants | format versions, schema drift, encodings, compression, dialects |
| Value ranges | min/max/percentiles per meaningful field |
| Categorical spread | distinct values, class balance, long-tail categories |
| Absence patterns | nulls, empties, missing optional blocks, sentinel values |
| Density / size | records per unit, points per m², file size distribution, row counts |
| Outliers | the 99.9th percentile specimen for each dimension that matters |
| Temporal | does any of the above drift across the time span |

Record it:

```
df.py profile <slug> --json <profile.json>
```

The profile is the source of truth for coverage. It ships in the bundle.

### When profiling is impossible

External APIs, live streams, or inputs whose characterization requires the very
processing being proven. Say so explicitly, proceed with a fixture, and record in
`coverage.md` that the confidence claim is reduced accordingly. Do not pretend a
profile exists.

---

## Step 2 — Choose the reduction strategy

Cropping is one strategy for one data shape. Pick by what the input actually is:

| Strategy | Fits | Watch for |
|---|---|---|
| Spatial crop + halo | point clouds, imagery, rasters, maps | edge effects at the crop margin |
| Record sample | tables, databases, event streams | broken join cardinality, lost referential integrity |
| Time slice | logs, telemetry, time series | seasonality, state accumulated before the window |
| Single instance + deps | one document from a corpus, one package from a monorepo, one tenant | dependencies that live outside the instance |
| Shortened run | long batch jobs | only valid if the logic is genuinely per-unit |
| Narrowed surface | APIs, routes, format variants | interactions between surfaces |

### The context halo

The question people skip, and skipping it produces a fixture that cannot reproduce the
behavior at all:

> **What does the logic look at beyond the target itself?**

A building classifier reading height-above-ground needs the surrounding ground. A join
needs both sides. An incident detector needs the quiet period before the spike. A parser
needs the header block. Cut the halo in deliberately and record its extent in
`fixture.lock`.

### Preserved properties

What must match production exactly for the proof to transfer? Density, resolution, CRS,
encoding, class balance, cardinality, ordering, precision.

**Measure these in the fixture and compare to the profile.** Do not assume the reduction
preserved them — a fixture that silently drifted in density will teach a lesson that does
not scale. Report both numbers.

---

## Step 3 — Select typical + tail

The instinct is to grab a clean, representative specimen. That instinct is the failure
mode. A pleasant fixture proves a pleasant subset.

Selection is deliberate:

- **one typical instance** — the modal case
- **the tail the profile surfaced** — the malformed record, the empty geometry, the
  mixed encoding, the tenant with 400× the volume, the file in the old format version

If a tail case cannot be included (too large, doesn't exist in accessible data), it goes
straight into absent coverage. That is the correct outcome — a named gap beats a silent
one.

**Never synthesize.** If production has no example of a case, the case is unproven. It
does not get invented, because invented data encodes the assumption you were trying to
test.

---

## Step 4 — Cut the holdout

A **second, different** slice: another region, another tenant, another week, another
source file.

Rules:

- It is **never examined during the loop.** Not once, not to "check if it's working."
- It is run **exactly once**, in Phase 4, before sealing.
- If it fails, the fixture was unrepresentative. Return to the loop, fix, then cut a
  **new** holdout — the old one is consumed.

This is train/test discipline. Iterating against the holdout is leakage and leaves it
with no evidentiary value whatsoever.

The holdout is the cheapest insurance in the design: it catches crashes, format
surprises, and silently-satisfied assumptions at dirty-session prices instead of after
an expensive build.

---

## Step 5 — Coverage diff

Mechanically diff the fixture against the profile. For every inventory entry:

| Verdict | Meaning |
|---|---|
| `covered` | present in the fixture in meaningful quantity |
| `underrepresented` | present but thin — proof is weak here |
| `absent` | not in the fixture at all |

Everything `underrepresented` or `absent` is auto-written into `coverage.md` and flows
into `acceptance.md` under **What this fixture cannot prove**. Nobody has to remember
it; the profile already saw it.

Show the human the absent list. They may say "I need that one" — then refine the
fixture. That decision is theirs and it is cheap to make here.

---

## Step 6 — Size to the budget

The fixture is correctly sized when **one full iteration fits in the budget** (default
90 seconds).

Over budget → **shrink the fixture.** Never optimize the dirty code to fit. Optimizing
the dirty code is how a proof-of-concept quietly becomes a project.

Under budget with room to spare → consider adding another tail case.

---

## The NOT-REDUCIBLE test

Some phenomena only exist at full scale or under real conditions. Fixture minimization
fails for them **by definition**, and a fixture that pretends otherwise is worse than
none — it manufactures confidence.

Exit `NOT_REDUCIBLE`, within ten minutes, if the behavior in question depends on:

- concurrency, races, lock contention, or ordering under load
- distributed coordination, partitions, or cross-node consistency
- memory or I/O pressure that only appears at volume
- emergent behavior across a full population that no subset exhibits
- real user or third-party behavior that cannot be captured

Report: what was attempted, why it does not reduce, and what proving it large would
actually require. That is a genuinely useful answer delivered for ten minutes of spend.

---

## Side effects are always stubbed

dirty-fix never sends the email, charges the card, writes to production, or mutates
shared state. The stub is part of the fixture contract, is recorded in `fixture.lock`,
and appears in **cannot prove** — because a stubbed boundary is an unproven boundary.

---

## What lands in `fixture.lock`

Enough for anyone to re-obtain or verify the fixture without this skill:

```json
{
  "source": "<absolute path or URI of production input>",
  "source_hash": "<hash or mtime+size if hashing is impractical>",
  "strategy": "spatial-crop | record-sample | time-slice | instance | shortened-run | narrowed-surface",
  "params": { "...": "strategy-specific, enough to reproduce the cut" },
  "halo": "what context was included beyond the target, and how much",
  "preserved": { "density": ["prod", "fixture"], "...": ["prod", "fixture"] },
  "tail_cases": ["which outliers were deliberately included"],
  "holdout": { "source": "...", "params": {}, "consumed": false },
  "stubs": ["which side effects were faked"]
}
```
