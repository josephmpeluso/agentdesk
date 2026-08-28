# Architecture

## The problem with three-agent prompts

The prompt this system started from is a good prompt:

> spin up a 3 agent team. one to research, one to draft and one to review.
> Follow the hard limits for each agent […] Nothing reaches me below an 8.

Run it once and you get something impressive. Run it four hundred times and
three things break, every time, in the same order:

1. **The limits are suggestions.** "120 words" produces 118, 131, 147. The
   model is not counting; it is estimating, and it estimates optimistically.
2. **The reviewer is agreeable.** Ask a model to grade work it just produced,
   in the same context window, and it grades generously. The score converges
   on 8 because 8 is what you asked for — the number becomes a target rather
   than a measurement.
3. **The handoffs are prose.** The drafter gets the researcher's summary as
   text and reads it however it likes. There is no mechanical way to ask "did
   the drafter make this up?" because there is nothing to compare against.

Everything below exists to fix one of those three.

---

## The five gates

Between a company name and a human's inbox there are five places output can
be refused. Only one of them is a model.

```
company name
     │
     ▼
┌──────────────┐
│  RESEARCHER  │  Gate 1  prompt contract (SKILL.md)
│  haiku       │          read-only, tools restricted at the harness
└──────┬───────┘
       │  research_brief
       ▼
   Gate 2  schema validation ──────── reject ──► no retry (structure bugs
       │                                          are prompt bugs)
   Gate 2b provenance ─────────────── reject ──► any claim without a
       │                                          retrieved URL
   [low-confidence claims stripped here]
       │
       ▼  insufficient_evidence? ──── halt ────► human queue, no draft
       │
┌──────┴───────┐
│   DRAFTER    │  Gate 1  prompt contract
│   sonnet     │          no search tools — fabrication becomes structural
└──────┬───────┘
       │  draft_package (+ claim_refs)
       ▼
   Gate 3  deterministic ──── fail ──► revise, QA never called
       │   word count · banned phrases · claim-ref integrity
       │   low-confidence leak · mandatory sections
       ▼
┌──────────────┐
│ QA REVIEWER  │  Gate 4  adversarial review
│ opus         │          different model family than the drafter
└──────┬───────┘
       │  qa_verdict
       ▼
   Gate 5  release decision ─── fail ──► revise (budget: 2)
       │   recomputed in code; reviewer's own `pass` is advisory
       │                            └──► budget spent ──► ESCALATE
       ▼
    RELEASED
```

## Why each gate exists

**Gate 1 — the prompt contract.** Each agent is a `SKILL.md`: frontmatter that
controls when it triggers, a body that states hard limits, method, and output
shape. This is the layer everyone builds. On its own it is worth roughly what
a code comment is worth: real, but not enforcement.

**Gate 2 — schema.** Every handoff is a JSON object with a published schema.
Malformed output is rejected *without a retry*, deliberately. A model that
can't produce the shape on the first try is telling you the prompt is wrong,
and retrying converts a loud, cheap, findable bug into a quiet, expensive,
intermittent one.

**Gate 2b — provenance.** Every claim carries a `source_url` that was actually
retrieved. A URL the model remembers is a fabrication with good manners. This
check is four lines of code and it removes an entire class of failure.

**Low-confidence stripping.** Claims marked `low` are deleted from the brief
before the drafter ever sees it. The alternative is instructing the drafter to
use restraint. Deletion works every time; restraint works most of the time,
and "most of the time" is not a property you can put in a runbook.

**Gate 3 — deterministic checks.** Word count, banned phrases, claim-reference
integrity, mandatory sections. All of it could be judged by a model. None of
it should be. This gate is free, instant, has no variance, and — the part that
matters operationally — it runs *before* the QA call, so a draft that violates
arithmetic never costs a review.

The mechanism that makes this possible is `claim_refs`. The drafter must tag
each factual sentence `[c2]` and declare the ids it used. That turns "did the
drafter make something up?" from a judgment call into a set operation.

**Gate 4 — adversarial review.** The QA reviewer runs on a different model
family than the drafter, with no search tools and no ability to edit. Three
constraints, three reasons:

- *Different family* — a model reviewing its own output shares its own blind
  spots. Correlated blind spots are how bad drafts pass review.
- *No search* — the reviewer must judge against the brief, not against its own
  knowledge. Its knowledge might be right, but it isn't reproducible and it
  isn't what the drafter had.
- *No editing* — if the reviewer fixes the work, nobody reviewed the work.

**Gate 5 — release decision.** The reviewer emits a `pass` field. The
orchestrator ignores it and recomputes: `score >= 8 AND no blocking flags AND
swap test failed`. A gate a model can talk its way past is not a gate.

Disagreement is logged rather than resolved. When the reviewer says fail and
the arithmetic says pass, the reviewer wins and the event is recorded — that
pattern usually means the rubric is missing a case.

---

## The swap test

The original prompt says: *flag anything generic enough to send to any
company.* That is the right instruction and it is unenforceable as written,
because "generic" is a vibe.

The mechanization: **replace every company-specific noun with `[COMPANY]` and
`[PRODUCT]`, then read what's left.** If it still reads as a sendable email,
the specifics were decoration and it is a template. If it collapses into
nonsense, the specifics were load-bearing.

The reviewer emits the redacted text in `swap_test.redacted_body`, so a human
can check the reviewer's work in about four seconds. That matters — this is
the check most likely to be disputed, so it is the one that shows its work.

---

## Contracts

| Artifact | Producer | Key field | What it enables |
|---|---|---|---|
| `research_brief` | researcher | `claims[].source_url` | provenance checking |
| | | `claims[].confidence` | routing, not decoration — `low` gets stripped |
| | | `insufficient_evidence` | halting is a first-class outcome |
| | | `gaps[]` | feeds the brief's "what I don't know" |
| `draft_package` | drafter | `claim_refs[]` | makes QA a set operation |
| | | `draftable: false` | declining to draft is a valid output |
| `qa_verdict` | qa-reviewer | `flags[].remediation` | retry prompts are built from these |
| | | `swap_test` | shows its work on the contested check |

Schemas live in `contracts/`. They are the interface. Change a schema and both
the CLI orchestrator and the n8n workflow have to change with it, which is the
point — an interface nobody can quietly ignore.

---

## Terminal states

Four, and three of them are not "released":

| Outcome | Meaning | Right response |
|---|---|---|
| `released` | cleared all five gates | send it |
| `halted` | research too thin, or drafter declined | nothing — the system worked |
| `escalated` | retry budget spent, still below 8 | human writes it, and the flags say why |
| `rejected` | contract violation | fix the prompt, not the data |

`halted` deserves emphasis. A pipeline that always produces an email is a
pipeline that will invent facts about companies it couldn't research. The
ability to return nothing is a feature, and the rate at which it fires is a
health metric, not a defect count.

---

## Retry budget

Two revisions, then escalate. Not five, not "until it passes."

Each revision costs a drafter call plus a reviewer call. More importantly,
each revision is fed the previous draft plus the flags — so by attempt three
the model is optimizing against the rubric rather than writing a better email.
That is Goodhart's law arriving on schedule, and the fix is to stop before it
does rather than to add a rule against it.

The failure mode this prevents is the one that matters: a loop that eventually
finds a phrasing the reviewer accepts, producing a technically-passing email
nobody would send.

---

## Model tiering

| Agent | Model | Why |
|---|---|---|
| researcher | Haiku | extraction-shaped; tool loops dominate latency, not reasoning |
| drafter | Sonnet | judgment and voice; the expensive part is worth paying for |
| qa-reviewer | Opus | adversarial reading, and a different family than the drafter |

Set via `AGENTDESK_*_MODEL` environment variables. The tiering is a hypothesis
worth testing per deployment, not a law — the eval harness is how you test it.
Swap the researcher to Sonnet, re-run `evals/run_eval.py --live`, and see
whether recall moves enough to justify the bill.

---

## Known limitations

Listing these because a system diagram without them is marketing.

- **The banned-phrase list is a denylist, and denylists leak.** Eval case b11
  proves it: "I hope you are having a great week" is not on the list and
  sails through the deterministic gate. Every new bad opener is a patch after
  the fact. A learned classifier would generalize; it would also need training
  data this system doesn't have yet. This isn't unique to this repo:
  [Crux](https://github.com/josephmpeluso/crux)'s phantom-opponent check is
  the same mechanism — a phrase denylist over a different failure shape — and
  it was independently measured leaking the same way, on a paraphrase the
  list didn't anticipate (`m01` in Crux's own eval set). Two independent
  systems, same failure mode. Worth reading as a property of denylists in
  general, not a bug in either one.
- **The swap test is the only defense against a well-written template**, and
  it runs on a model. Eval case b12 is correctly worded, correctly sourced,
  correctly counted, and completely generic. Code cannot touch it. If the
  reviewer has an off day, b12 ships.
- **Claim drift is hard.** A citation pointing at a real claim that has been
  quietly distorted (case b13) is structurally identical to a good citation.
  Detection depends entirely on the reviewer reading carefully.
- **`confidence` is self-reported.** The researcher grades its own certainty.
  Nothing validates it. A miscalibrated researcher poisons everything
  downstream and the pipeline has no way to notice.
- **No cross-run memory.** Contacting the same company twice produces two
  unrelated emails. Deduplication and suppression lists are the obvious next
  build and are not here.
- **The eval set is synthetic.** Fourteen mutations of one baseline. It
  measures whether gates fire on known failure shapes. It does not measure
  reply rate, and nothing in this repo does.
- **The researcher overruns its own declared field-length limits, live.**
  Across 13 live runs against Sonos, `marketing_task.description` (capped at
  400 characters) ran over the limit on at least 2 separate runs, and the
  model invented non-conforming `claim_id`s (`c1b`, `c2b`) on at least 3
  separate runs rather than assigning a plain next integer. Both counts are
  floors: `validate_schema()` records only the *first* jsonschema error per
  run, so a second violation of the same run's brief could be hiding behind
  an earlier one and was never persisted anywhere — see the logging-gap bullet
  below. Prompt clarifications reduced but did not eliminate the underlying
  problem — schema gate 2 catches every instance and rejects without retry,
  which is the correct behavior, but the underlying unreliability is the same
  "limits are suggestions" problem this project documents for the drafter,
  just not yet fixed for the researcher.
- **The gate log records only the first schema-validation error per run, not
  every error.** A deliberate, correct choice for the pipeline itself — one
  loud, findable failure beats a wall of secondary errors nobody reads before
  fixing the first one. The cost: the historical record in `runs.jsonl` can't
  answer "how many times did failure mode X actually happen," only "how many
  runs had X as their first-reported problem." The two floors above (2 and 3
  runs) are a direct consequence — the true counts could be higher and there
  is no way to recover them without re-running the pipeline.
- **The live eval is unmeasured.** `run_eval.py --live` and all four
  scenarios' live runs are unrun — not skipped by choice, but because the
  Anthropic account funding this project's live testing ran out of credit.
  See `README.md` → "What live testing found" and `STATE.md`.
- **No live run has ever produced `RELEASED` or `HALTED`.** Of 13 real API
  calls against Sonos, 12 were rejected at the researcher's schema gate and 1
  escalated. `RELEASED` and `HALTED` are demonstrated only via dry-run
  fixtures — real code paths, not live evidence.
