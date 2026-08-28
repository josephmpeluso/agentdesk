# AgentDesk

**A three-agent pipeline with enforcement that isn't a prompt.**

Research → draft → review, where the hard limits are checked in code, the QA
gate can't be talked past, and the retry budget runs out instead of lowering
the bar.

```bash
pip install anthropic jsonschema

python orchestrator/run.py --dry-run                          # releases
python orchestrator/run.py --dry-run --scenario generic_email # blocks, revises, releases
python orchestrator/run.py --dry-run --scenario thin_evidence # halts before drafting
python orchestrator/run.py --dry-run --scenario escalation    # exhausts retry budget, escalates
python evals/run_eval.py                                      # scores the gate
```

No API key needed for any of the above. Add one and `--company "Acme Corp"`
runs it live.

**To see real evidence instead of reading claims about it:** open
[`web/index.html`](web/index.html) — a static audit viewer over 13 real API
runs against Sonos, including the run this project is proudest of.

---

## The starting point

This began as a prompt worth taking seriously:

> spin up a 3 agent team. one to research, one to draft and one to review.
> Follow the hard limits for each agent […] Nothing reaches me below an 8.

Run it once, it's impressive. Run it four hundred times and the same three
things break:

**The limits are suggestions.** "120 words" yields 118, 131, 147. The model
estimates, and it estimates optimistically. Eval case b08 in this repo has a
model reporting 122 words while emitting 155.

**The reviewer is agreeable.** Ask a model to grade output from its own family,
in the same context, against a threshold you named — and the score converges
on the threshold. 8 stops being a measurement and becomes a target.

**The handoffs are prose.** The drafter receives the researcher's summary as
text and reads it however it likes. There's no mechanical way to ask "did the
drafter make this up," because there's nothing to compare against.

AgentDesk is what the prompt becomes once those three are treated as
engineering problems.

---

## The three agents

| Agent | Model | Tools | Can it edit? |
|---|---|---|---|
| **Researcher** | Haiku 4.5 | Web search — the only agent with any tool access at all | No — read-only, produces a `research_brief` |
| **Drafter** | Sonnet 5 | None. No search, no fetch. | Writes the `draft_package`, never touches the brief |
| **QA Reviewer** | Opus 5 | None. Different model family than the drafter. | Never — flags and scores only |

These are separate API calls to separate models with separate tool grants,
run by code that decides what each one is allowed to see and do — not three
turns of one conversation. The drafter cannot search because fabrication has
to be structurally impossible, not merely discouraged. The reviewer runs on a
different model family than the drafter because a model grading its own
family's output shares its family's blind spots.

---

## What actually changed

**Handoffs became typed contracts.** Three JSON schemas in `contracts/`. The
load-bearing one is `claim_refs` — the drafter must tag each factual sentence
`[c2]` and declare which claim ids it used. That turns "did the drafter
fabricate this?" from a judgment call into a set operation.

**Five gates, one of which is a model.**

| | Gate | Mechanism |
|---|---|---|
| 1 | prompt contract | `SKILL.md` per agent |
| 2 | schema validation | reject malformed, no retry |
| 2b | provenance | every claim carries a retrieved URL |
| 3 | deterministic | word count, banned phrases, claim-ref integrity |
| 4 | adversarial review | different model family, no tools, no editing |
| 5 | release decision | recomputed in code; the reviewer's `pass` is advisory |

Worth being precise about gate 5: even the check sitting right next to the
one model's own verdict is deterministic. `release_decision()` recomputes
pass/fail from the score and flags in code — the reviewer's own `pass` field
is read, logged, and then ignored if the arithmetic disagrees. A gate a model
can talk itself past isn't a gate.

**"Generic" became testable.** The original instruction — *flag anything
generic enough to send to any company* — is right and unenforceable as
written. The mechanization: replace every company-specific noun with
`[COMPANY]`/`[PRODUCT]` and read what's left. Still sendable → it was a
template. Collapses into nonsense → the specifics were load-bearing. The
reviewer emits the redacted text so a human can audit the audit in four
seconds.

**Halting became a success state.** If research is thin, the pipeline stops
and returns nothing. A pipeline that always produces an email is a pipeline
that will invent facts about companies it couldn't research.

**Low-confidence claims get deleted, not discouraged.** They're stripped from
the brief before the drafter sees it. The alternative is asking the drafter for
restraint. Deletion works every time; restraint works most of the time, and
"most of the time" isn't a property you can put in a runbook.

---

## Measured results

`python evals/run_eval.py` — 18 cases, each one named mutation of a single
known-good baseline, so every case isolates one failure mode.

```
recall             10/14   71%   (known-bad drafts blocked)
false block rate    0/4     0%   (known-good drafts blocked)
blocked by code    10
blocked by model    0
```

**Ten of fourteen bad drafts blocked before spending a single review call, at
zero false positives.** Review is the most expensive stage. On the 18-case
golden set, 10 cases never reach the reviewer at all — caught by code first.

The four escapes are the honest part:

- **b11** — a generic template opening "I hope you are having a great week,"
  which is not on the banned-phrase list. That's a finding, not a pass:
  denylists catch what you thought of. The tempting fix is to add the phrase.
  The real fix is admitting the mechanism doesn't generalize, which is why it
  sits in `ARCHITECTURE.md` under known limitations instead of getting patched.
- **b12** — correct word count, valid citation, no banned phrases, reads well,
  and swap the company name for any other and it still sends. Code cannot
  touch this one. It's the case the swap test exists for.
- **b13** — cites a real claim, then restates it as something the source never
  said. A fabrication wearing a valid citation.
- **b14** — an invented statistic attached to a real claim id.

`run_eval.py --live` would add real reviewer calls and measure whether the
model catches those four. **It has not been run** — the account that funded
this project's live testing ran out of credit first (see below). The number
stated above is the honest one: 10/14 by code, 0/4 false blocks, and four
cases that need a model call this project hasn't paid for yet.

---

## Reproducing the results

Everything below the first three lines needs no API key and no internet
access — you can confirm the offline numbers above in under two minutes.

```bash
pip install anthropic jsonschema                               # once

# --- zero cost, no API key ---
python orchestrator/run.py --dry-run                            # RELEASED
python orchestrator/run.py --dry-run --scenario generic_email   # RELEASED, after 1 revision
python orchestrator/run.py --dry-run --scenario thin_evidence   # HALTED
python orchestrator/run.py --dry-run --scenario wordcount_violation  # RELEASED, after 1 revision
python orchestrator/run.py --dry-run --scenario escalation      # ESCALATED, retry budget exhausted
python evals/run_eval.py                                        # 10/14 recall, 0/4 false blocks — reproduces "Measured results" above exactly
python orchestrator/test_jsonio.py                               # 6/6 — the JSON-extraction parser tests
```

Open `web/index.html` directly in a browser (double-click it — no server, no
build step) to see the audit trail behind the "13 real API runs" claims
throughout this document. On Windows, `.\setup.ps1` runs everything above as
one pass and tells you if anything's broken.

```bash
# --- needs ANTHROPIC_API_KEY, costs real money ---
python evals/run_eval.py --live                    # ~8 real QA-reviewer calls (Opus): the 4 good cases plus b11-b14, the ones code can't catch
python orchestrator/run.py --company "Some Company" --domain example.com   # one full live pipeline run
```

A self-audit against these files caught four numbers elsewhere in this
document and `ARCHITECTURE.md` that didn't hold up — one off-by-one word
count, two live-run counts overstated as exact when the gate log only ever
kept a floor, and one "~40% of review spend" figure with no computation
behind it anywhere in this repo. All four are corrected in place; the review
spend figure is replaced with the actual measured count it was standing in
for. A repo whose thesis is "unsupported claims get blocked" should show
that check on itself too.

`run_eval.py --live` is the only thing standing between "10/14, 0/4 false
blocks" and a real measurement of whether the QA reviewer catches the four
escapes. See "Measured results" above for why that number isn't in this
document yet.

---

## What live testing found

Dry-run fixtures got every gate to green before a single dollar was spent.
Then this ran against a real company (Sonos) with a real API key, and the
gap between "the code path works" and "the system works" showed up
immediately.

**The researcher had no web-search tool wired in.** Its `SKILL.md` says,
explicitly, "Requires a web search / fetch tool." The orchestrator never
passed one. Every dry-run scenario was green throughout, because fixtures
don't call a tool — they're pre-written JSON. The first live run exposed it
instantly: the researcher fabricated plausible company facts and source URLs
it had never fetched, for a company (Sonos) the underlying model has
training-data knowledge of. **This is the eval-design lesson worth keeping:**
a fixture-based test suite can be 100% green while the one thing the agent's
own contract requires — a live tool call — silently never happens. Green
dry-runs prove the gate logic works. They prove nothing about whether the
agent can do the thing its `SKILL.md` says it must.

**Two more infra bugs surfaced the same way** — invisible to fixtures,
immediate on a live call: `run_meta.agent`/`run_meta.attempt` were required by
every contract schema but never populated by the harness, so the first real
schema validation on *any* agent would have failed regardless of tool access;
and the Claude 5 family's extended thinking draws from the same `max_tokens`
budget as the visible reply, so a model could spend an entire 4,000-token
budget "thinking" and return zero output tokens — surfacing as a truncation
error that reads like a model problem and is actually a budget problem, the
same class of bug the researcher's own `SKILL.md` names.

**What live behavior showed, once the infra was fixed, matched this
project's own thesis about the drafter — but for the researcher too.** Across
13 live runs, the researcher repeatedly overran its own declared field-length
limits (`marketing_task.description`, capped at 400 characters, ran over by
several dozen on at least 2 separate live runs) and invented non-conforming
claim IDs on at least 3 separate live runs. Both counts are floors, not exact
totals: the schema gate records only the *first* validation error per run
(see "Known limitations" in `ARCHITECTURE.md`), so a second violation hiding
behind an earlier one in the same run was never persisted anywhere and can't
be recovered now. Every instance actually caught was rejected without retry,
per this system's core invariant: malformed output is a prompt bug, not a
flake, and silently retrying it hides the bug.

**One run is worth reading in full.** A live run against Sonos went researcher
→ drafter → QA cleanly, and the QA reviewer (Opus) caught a real `claim_drift`
— a citation that had been quietly restated as something stronger than the
source said. The pipeline revised. The reviewer caught the same drift again.
The retry budget (2 revisions) ran out, and the run escalated to a human queue
rather than lowering the threshold. Nobody scripted that outcome — it's what
the gate did under real pressure. See it in [`web/index.html`](web/index.html).

**That run's own claim text, draft body, and QA flag detail are gone.** The
code that printed and persisted full pipeline detail (`print_audit()`, plus
the `runs.jsonl` fields it now writes) was added *after* this run executed —
it existed only in memory, and the process exited before anything captured
it. Only the gate sequence survived. The lesson: detailed logging has to
exist before the run you'll want it for, not after. You don't get to choose
in advance which run turns out to be the one worth showing.

**Then the account ran out of credit**, mid-way through what would have been
the furthest-reaching live run yet. Two planned phases — running all four
scenarios live, and measuring the QA reviewer against the four eval cases
only a model can catch — are unmeasured as a result, not because they were
skipped by choice.

---

## Repo

```
skills/            three SKILL.md agents — the contract each one operates under
contracts/         JSON schemas for every handoff
orchestrator/      run.py — gates, retry budget, run logging, dry-run fixtures
orchestration/     importable n8n workflow (16 nodes, generated + graph-checked)
evals/             mutation-based golden set, scorer, and results
web/               static audit viewer over the 13 live runs — open index.html
verticals/         device fleet triage — the same architecture, specced not built
ops/               runbook: metrics, cost model, failure playbooks
ARCHITECTURE.md    why each gate exists, and what this system can't do
STATE.md           what's built, what's verified live, what's unproven — as of today
DEMO.md            a plain-language script for walking someone through this
```

Both runtimes read the same `contracts/`. Change a schema and the CLI and the
n8n workflow both have to change — an interface nobody can quietly ignore.

The n8n workflow deliberately uses plain HTTP Request nodes rather than the
native AI Agent node. The native node manages its own loop and retry behavior,
and that behavior is the product. Wrapping it in someone else's control flow
gives away the part worth owning.

---

## Grounding

**AI Fluency: Framework & Foundations.** The 4D framework maps onto the
architecture directly, which is the argument for building it this way rather
than as one long prompt:

| Competency | Where it lives |
|---|---|
| **Delegation** | Which stage gets which model, and which decisions never get delegated — the `clinical_impact` hard ceiling in the triage vertical routes to a human at any score |
| **Description** | The `SKILL.md` contracts, and `claim_refs` as the mechanism that makes a description checkable rather than merely clear |
| **Discernment** | Gates 3–5 and the eval harness. Discernment applied once is a code review; automated and measured, it's a gate |
| **Diligence** | Provenance on every claim, `runs.jsonl` audit trail, escalation to a named human, and a known-limitations section that names what this doesn't catch |

The course also names three modes of AI interaction — automation, augmentation,
agency. This system is deliberately all three at once, and the boundaries are
the design: research is **automation** (bounded, read-only), drafting is
**agency** (the model produces work product independently), and the escalation
path is **augmentation** — when the gate refuses three times, a human writes it
with the flags in hand.

**Introduction to agent skills.** Each agent is a real `SKILL.md`: frontmatter
that governs triggering, a body under the progressive-disclosure limit, hard
limits stated as contract rather than preference, and an explicit output
schema. The `compatibility` field carries the tool restrictions — the drafter
runs with search disabled, which is what makes fabrication structurally visible
instead of a matter of trust.

---

## What this doesn't do

- **No suppression or dedup.** Run the same company twice, send twice. Build
  this before any live sending.
- **The banned-phrase list is a denylist and it leaks.** Proven by b11, in this
  repo, on purpose.
- **`confidence` is self-reported.** The researcher grades its own certainty
  and nothing validates it. A miscalibrated researcher poisons every stage
  downstream and the pipeline can't notice.
- **The eval set is synthetic.** It measures whether gates fire on known
  failure shapes. It does not measure reply rate, and nothing here does.
- **The triage vertical is specified, not shipped.** Contract mapping and gate
  modifications are documented in `verticals/`. Claiming it as built would be
  the exact kind of unsupported claim this system exists to block.
- **No cost ceiling.** Nothing stops a runaway batch — and the four live
  scenarios and four live eval cases below are unmeasured because a batch
  without one ran the account dry.
- **The four live-scenario runs and four QA-judgment eval cases are
  unmeasured.** See "What live testing found" above.
- **No live run has ever reached `RELEASED` or `HALTED`.** Of the 13 real API
  calls against Sonos, 12 were rejected at the researcher's schema gate and 1
  escalated after two revisions — that's the full outcome distribution. Those
  two terminal states are demonstrated only by the `happy_path`/`generic_email`/
  `wordcount_violation` and `thin_evidence` dry-run fixtures, which are real
  code paths but not live evidence that a real model, live, produces them.

---

## The argument

Anyone can write a three-agent prompt. The prompt at the top of this file is a
good one and it took about ninety seconds.

The part that takes judgment is deciding where a model is allowed to be wrong,
what happens when it is, and how you'd know. That's five gates, four terminal
states, a retry budget that expires, an eval set that reports its own escapes,
and a limitations list that names the mechanism most likely to fail.

The system is small. The claim is narrow. Both are checkable in about ten
minutes, which is the point — run `--dry-run --scenario generic_email` and
watch it block, revise, and release. Then open `web/index.html` and watch the
same gates hold up against a real model, under real pressure, for real money.
