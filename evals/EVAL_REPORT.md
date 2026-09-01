# Gate evaluation

## What is being measured

Two numbers, which pull against each other:

- **Recall** — of known-bad drafts, what fraction did the gate block?
- **False block rate** — of known-good drafts, what fraction did it block anyway?

Reporting recall alone is how a gate with a 40% false block rate ships. Nobody
keeps that gate switched on for a week, and then the system has no gate at all.

## The golden set

28 cases: 9 clean, 19 bad. Every case is one named mutation applied to a
single known-good baseline, so each isolates exactly one failure mode.
Hand-writing 19 bad emails produces 19 subtly different emails and no clean
attribution when one gets through.

Each case declares who *should* catch it:

- `code` — a deterministic check, no model call needed
- `model` — only the QA reviewer can catch it
- `none` — intentionally clean; blocking it is a false positive

Ten cases (`rb01`–`rb05`, `rg01`–`rg02`, `rs01`–`rs03`) carry
`"stage": "researcher"` and test `research_brief_precheck()` and
`sanitize_research_brief()` against a mutated *brief*, not a mutated draft —
see "Researcher-stage cases" below. Everything else tests the drafter/QA
path via `deterministic_checks()`, unchanged.

Regenerate with `python build_golden_set.py`.

## Results — deterministic layer only

`python run_eval.py` · runs in under a second · no API key

```
recall             15/19   79%   (known-bad drafts blocked)
false block rate    0/9     0%   (known-good drafts blocked)
blocked by code    15
blocked by model    0
```

| id | failure mode | should be caught by | result |
|---|---|---|---|
| g01 | baseline | — | passed |
| g02 | baseline, reworded | — | passed |
| g03 | stylistic wobble | — | passed |
| g04 | self-reported count off by 2 (in tolerance) | — | passed |
| b01 | no claim refs | code | **caught** |
| b02 | dangling claim ref | code | **caught** |
| b03 | undeclared claim ref | code | **caught** |
| b04 | low-confidence leak | code | **caught** |
| b05 | banned phrase | code | **caught** |
| b06 | 157 words | code | **caught** |
| b07 | 18 words | code | **caught** |
| b08 | model misreports its own word count | code | **caught** |
| b09 | 94-char subject | code | **caught** |
| b10 | missing "what I don't know" | code | **caught** |
| b11 | generic template | model | escaped |
| b12 | generic, no tells | model | escaped |
| b13 | claim drift | model | escaped |
| b14 | invented metric on a real claim id | model | escaped |
| rb01 | marketing_task.description over 400 chars | code | **caught** |
| rb02 | malformed claim_id (`c1b`) | code | **caught** |
| rb03 | evidence_type not in the enum | code | **caught** |
| rb04 | published_date not YYYY-MM-DD | code | **caught** |
| rg01 | unmutated brief (guards the precheck against false positives) | — | passed |
| rs01 | citation markup pushes description over its cap | code | **caught\*** |
| rs02 | citation markup in an uncapped claim statement | — | passed\* |
| rs03 | citation markup present, never threatens the cap | — | passed\* |
| rb05 | what_they_sell.summary over cap on realistic prose, no markup | code | **caught** |
| rg02 | both summaries at their new, tighter word budgets | — | passed |

\* `rs01`–`rs03` are "good" cases (label `good`, `caught_by: none`) — the
markup is stripped by `sanitize_research_brief()` before the precheck ever
runs, so the *correct* result is a pass. `rs01`'s pass is the interesting
one: without sanitizing first, that brief would fail the length check.

Fifteen of nineteen bad drafts and briefs blocked before spending a single
model call, at zero false positives. That is the case for the deterministic
layer: the cheapest gate catches most of the volume.

## Researcher-stage cases

`rb01`–`rb04` exist because the offline number above used to hide a real
production defect: 12 of 13 live runs against Sonos were `REJECTED` at the
researcher's own schema gate, and 7 of those 12 were exactly the two shapes
`rb01` and `rb02` test — a field over its length cap, and a claim id like
`c1b` instead of a plain integer. The gate was working. The researcher's
`SKILL.md` was under-specified relative to the schema it was supposed to
produce: it told the model to count *characters*, which a model can't do
reliably, instead of giving it a word budget with real margin, and it never
stated the `claim_id` pattern with valid/invalid examples at all. Both are
fixed in `skills/researcher/SKILL.md` and reinforced in `run.py`'s injected
prompt; `rb01`/`rb02` are the regression guard so it can't quietly come back.
`rb03` and `rb04` close two more gaps the same audit found: `evidence_type`'s
six-value enum and the `YYYY-MM-DD` date format were never stated in the
prompt at all, even though the schema requires both.

`rs01`–`rs03` exist because that fix's own reinforcement wasn't enough: the
search tool's citation markup (`<cite index="...">...</cite>`) leaked into
brief fields in 2 of 5 fresh live runs, inflating them past their caps as a
side effect. `sanitize_research_brief()` strips it — content preserved, tag
removed, every strip logged — before any length check or schema validation
runs. `rs01` proves a brief that would fail the length check unsanitized
correctly passes once sanitized; `rs02`/`rs03` prove the strip fires on
fields that were never going to be rejected either way, because it isn't
conditional on need.

`rb05`/`rg02` exist because sanitizing the real Figma/Linear briefs revealed
a second, independent problem: even with markup removed, `what_they_sell
.summary`'s clean text was *still* over its 300-char cap. Measured the
actual characters-per-word ratio across the 7 real briefs this project has
data for: 40 words at the mean observed density (7.78 c/w) is already 311
characters. Budget tightened to 27 words (`recent_news.summary` to 33, same
margin standard, though it wasn't independently broken). `rb05` proves the
old budget was mathematically inconsistent with the cap on realistic prose
alone; `rg02` proves the new budgets hold real margin even written close to
their own limit. See `ARCHITECTURE.md` → Known limitations for the full
measured table.

## What escaped, and why it matters

The four escapes are the interesting part, because they are the four that
need a model — and one of them shouldn't.

**b11 (generic template) is a finding, not a pass.** It opens with "I hope you
are having a great week," which is not on the banned list. The list has "I
hope this email finds you well" and "I hope you're doing well." A denylist
catches what you thought of.

The tempting fix is to add the phrase. That is a patch, and the next variant
escapes too. The honest version stays in `ARCHITECTURE.md` under known
limitations: **denylists leak, and this one leaks by design until it is
replaced with something that generalizes.**

**b12 (generic, no tells) is the case the whole system is built around.**
Correct word count. Valid, non-dangling claim reference. No banned phrases.
Reads well. And swap "Harborview" for any other instrument company and it
still sends. No amount of code catches this. It is entirely down to the QA
reviewer running the swap test honestly, which is why the reviewer emits
`swap_test.redacted_body` — so a human can audit the audit in four seconds.

**b13 (claim drift)** cites `[c3]` — a real claim — and then restates it as
something the source never said. "47 titles in the library" becomes "roughly
twenty a quarter." Structurally identical to a good citation. This is the
failure mode I would worry about most in production, because it looks correct
at every level a script can inspect.

**b14 (invented metric)** attaches "cut authoring time by 60%" to a real claim
id. Same shape as b13 with a number, which makes it worse: numbers read as
evidence.

## Live mode

`python run_eval.py --live` adds real QA reviewer calls for every *drafter*-stage
case that clears the deterministic gate — that's 8 calls, not 4: the 4 clean
baselines (`g01`–`g04`) plus the 4 escapes (`b11`–`b14`), all of which pass
`deterministic_checks()` and so all reach the reviewer. The 10 researcher-stage
cases never call the model at all — `research_brief_precheck()` and
`sanitize_research_brief()` are pure code, by design, since these are
schema/format defects, not judgment calls.

The number to watch is recall on b11–b14. If the reviewer catches all four,
combined recall is 100% at 0% false blocks. If it catches two, the honest
report is 17/19 — 89% — and the gap is where the next iteration goes.

Run it before quoting a combined number. An unrun eval is a hypothesis.

## Regression discipline

The offline eval belongs in CI. It runs in under a second, needs no API key,
and fails the build on any false block. Every production escape gets added as
a new case with its own mutation function — the golden set should grow
monotonically and never shrink.

The live eval is a release gate, not a CI gate: it costs money and has
variance. Run it when a prompt changes, a model version changes, or the
tiering changes.
