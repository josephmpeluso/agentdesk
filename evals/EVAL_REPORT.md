# Gate evaluation

## What is being measured

Two numbers, which pull against each other:

- **Recall** — of known-bad drafts, what fraction did the gate block?
- **False block rate** — of known-good drafts, what fraction did it block anyway?

Reporting recall alone is how a gate with a 40% false block rate ships. Nobody
keeps that gate switched on for a week, and then the system has no gate at all.

## The golden set

18 cases: 4 clean, 14 bad. Every case is one named mutation applied to a single
known-good baseline, so each isolates exactly one failure mode. Hand-writing
14 bad emails produces 14 subtly different emails and no clean attribution
when one gets through.

Each case declares who *should* catch it:

- `code` — a deterministic check, no model call needed
- `model` — only the QA reviewer can catch it
- `none` — intentionally clean; blocking it is a false positive

Regenerate with `python build_golden_set.py`.

## Results — deterministic layer only

`python run_eval.py` · runs in under a second · no API key

```
recall             10/14   71%   (known-bad drafts blocked)
false block rate    0/4     0%   (known-good drafts blocked)
blocked by code    10
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

Ten of fourteen bad drafts blocked before spending a single review call, at
zero false positives. That is the case for the deterministic layer: the
cheapest gate catches most of the volume.

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

`python run_eval.py --live` adds real QA reviewer calls for every case that
clears the deterministic gate. Costs roughly 4 calls (only the escapees reach
the reviewer) at approximately $0.02–0.04 each.

The number to watch is recall on b11–b14. If the reviewer catches all four,
combined recall is 100% at 0% false blocks. If it catches two, the honest
report is 86%, and the gap is where the next iteration goes.

Run it before quoting a combined number. An unrun eval is a hypothesis.

## Regression discipline

The offline eval belongs in CI. It runs in under a second, needs no API key,
and fails the build on any false block. Every production escape gets added as
a new case with its own mutation function — the golden set should grow
monotonically and never shrink.

The live eval is a release gate, not a CI gate: it costs money and has
variance. Run it when a prompt changes, a model version changes, or the
tiering changes.
