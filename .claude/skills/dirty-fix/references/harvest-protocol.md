# Harvest protocol

Converting a human's visual judgment into arithmetic a future implementation must satisfy.

This is the phase that makes the whole skill worth building, and it is the phase most
likely to be skipped — because it lands exactly when the human is satisfied and wants to
stop. The protocol exists to make sure it never lands there.

---

## The rule: harvest continuously, never at the end

**When a rejection gets fixed, that is the moment its check gets written.**

Not at the end. At the end, three things are true and all of them are bad:

- the counterexample has been overwritten by later iterations
- the human is happy and wants to stop
- the reasoning behind the rejection has faded into "it looked wrong"

At the moment of the fix, all three are inverted. The failing output is on disk. The
human is engaged. The reason is fresh.

---

## The loop, per fix

Iteration N-1 produced output the human rejected. Iteration N fixed it. Now:

### 1. Write the check

Translate the observation into an assertion.

| Observation | Check |
|---|---|
| "eaves are getting clipped" | `eave_points_classified_building / eave_points_total >= 0.95` |
| "it's dropping the last row" | `len(output) == len(input)` |
| "dates come out as strings sometimes" | every `date` field parses as ISO-8601 |
| "it misses the second invoice on multi-invoice PDFs" | all 4 known multi-invoice documents yield ≥2 records |
| "totals don't add up" | `sum(line_items) == header_total` within 0.01 |
| "it 500s on empty payloads" | empty payload returns 4xx, never 5xx |

Pick the comparator mode:

| Mode | Use for |
|---|---|
| `exact` | parsers, formatters, migrations — byte or value equality |
| `tolerance` | numeric or geometric output with acceptable drift |
| `invariant` | structural truths: counts reconcile, no nulls in X, 1:1 mapping |
| `set` | membership: these must be tagged X, these must not |
| `behavioral` | these inputs produce these status codes / outcomes |
| `statistical` | non-deterministic work: asserted over N runs, or seeded |

### 2. Validate it against the real failure

**Run the new check against iteration N-1's output. It must fail.**

This is mutation testing, and it costs nothing because the mutant is a real failure the
human actually observed rather than a synthetic corruption.

A check that passes on the output that provoked it is decoration. Rewrite it or delete
it. Never keep it — a decorative check in a gate is worse than a missing one, because it
launders false confidence through an expensive build.

### 3. Record it

```
df.py check-add <slug> \
  --id eaves_classified \
  --mode tolerance \
  --desc "eave points classified as building" \
  --assert "eave_points_building / eave_points_total >= 0.95" \
  --from-rejection 4 \
  --validated-against work/iter-04-output.las
```

`--from-rejection` and `--validated-against` are what let `seal` verify the gate is real.
Sealing refuses without them.

---

## Negative checks

Positive checks alone pass an implementation that labels everything as the target class,
returns 200 for every request, or emits every record.

Before sealing, at least one check must assert what must **not** appear:

- these ground points must NOT be classified building
- no record may appear twice
- malformed input must NOT produce a success status
- no output field may be silently defaulted

Derive them from the profile's tail cases and from anything the human said "no, not
that" about.

---

## Gated vs. declared-subjective

Some criteria genuinely cannot be asserted. Taste, legibility, "does this look right."

Do not force them into `check.py`. The moment taste leaks into the comparator, the gate
stops meaning anything and exit 0 becomes an opinion.

Instead:

- **gated** criteria live in `metrics.json` and are enforced by `check.py`
- **declared-subjective** criteria are named in `acceptance.md` as requiring human
  sign-off, and become an explicit review task downstream

To make that review cheap, `check.py` emits **review artifacts** — renders, crops,
excerpts, or summaries at exactly the loci the human cared about during the loop. The
person signing off later looks at the same views, in seconds.

`check.py` exit 0 remains mandatory regardless. A subjective criterion is *additional*,
never a substitute.

---

## What `check.py` claims

It never reports "correct." It reports:

> matches approved reference within tolerance

Naming it accurately is a real mitigation. A human-approved wrong output frozen into a
spec is the residual risk of this entire approach, and calling the result "correct"
compounds it by inviting the misread.

---

## The closing question

Before sealing, ask it verbatim:

> Here are the N checks. If a future implementation passes all of them and you never see
> its output, is that acceptable?

A "no" means the metrics are incomplete — keep eliciting until the answer is yes or the
remainder is explicitly moved to declared-subjective.

This is the acceptance gate on the acceptance gate, and it is the difference between a
benchmark and a checklist that merely feels thorough.

---

## Constraint vs. solution

Every fix teaches something. Sort what it taught before it leaves the session.

| Goes in `acceptance.md` (constraint) | Goes in `appendix-hacks.md` (solution) |
|---|---|
| "raw Z fails on slopes over 15%" | "used a HAG filter with k=8" |
| "returns are unordered per pulse" | "sorted in memory — won't fit at full scale" |
| "the v2 format omits the header block" | "sniffed the first 512 bytes to branch" |
| "totals reconcile only after tax rounding" | "rounded half-up at the line level" |
| what must be true | how it was made true |

The test: would this still be true for a completely different implementation? If yes it
is a constraint and belongs in the spec. If it names a technique, it is a solution and
belongs in the appendix.

The appendix lives outside the repo, so a later brainstorm cannot reach it by accident —
only by deliberately asking, after a design already exists.
