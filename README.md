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
[`web/index.html`](web/index.html) locally, or visit
[agentdesk-4f6.pages.dev](https://agentdesk-4f6.pages.dev) — a static audit
viewer over 18 real API runs across 5 companies (Sonos, Notion, Figma,
Linear, Basecamp), including the first live `RELEASED` this project ever
produced. (Moving to `agentdesk.joeypeluso.com`; see `DEPLOY.md`.)

---

## Sibling project: Crux

AgentDesk is one half of a pair. Its sibling is
**[Crux](https://github.com/josephmpeluso/crux)** — a parallel debate that
ends by naming the one fact that would settle a disagreement, instead of
averaging two arguments into "it depends."

They solve opposite problems and share one spine:

- **Reach for AgentDesk when the task has a ground truth.** Every claim in
  the output traces to a source URL, so the job is to *gate* — check the
  trace mechanically, block whatever fails, retry twice, escalate to a human
  when the budget runs out.
- **Reach for Crux when the task is a judgment call with no ground truth.**
  Build vs. buy, take the offer vs. walk. There's nothing to verify — two
  honest arguments and, usually, one fact underneath both of them nobody has
  looked up yet. Crux's job is to *find that fact*, not to gate anything —
  its mediator names the crux and often withholds a verdict entirely, rather
  than average two positions into something true and useless.

Same spine either way: typed JSON contracts, schema validation, deterministic
checks that run before any model call, and a known-limitations section that
says plainly what each system can't catch. The contrast is the point — the
same engineering discipline produces a linear gated pipeline when there's a
right answer to check against, and a parallel decision aid that admits when
there isn't.

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

`python evals/run_eval.py` — 23 cases, each one named mutation of a single
known-good baseline, so every case isolates one failure mode.

```
recall             14/18   78%   (known-bad drafts blocked)
false block rate    0/5     0%   (known-good drafts blocked)
blocked by code    14
blocked by model    0
```

**Fourteen of eighteen bad drafts and briefs blocked before spending a single
model call, at zero false positives.** Review is the most expensive stage. On
the 23-case golden set, 14 cases never reach a model at all — caught by code
first.

Five of those 23 cases (`rb01`–`rb04`, `rg01`) are new: they test the
*researcher's* own output against `research_brief_precheck()`, not the
drafter. They exist because 12 of the 13 live runs against Sonos were
rejected at the researcher's schema gate — the gate worked, but the
researcher's `SKILL.md` was under-specified relative to its own schema. See
"What live testing found" below for the real story and the fix; `rb01`/`rb02`
are the regression guard for the two defects that caused most of it.

The four remaining escapes are the honest part:

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
stated above is the honest one: 14/18 by code, 0/5 false blocks, and four
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
python evals/run_eval.py                                        # 14/18 recall, 0/5 false blocks — reproduces "Measured results" above exactly
python orchestrator/test_jsonio.py                               # 6/6 — the JSON-extraction parser tests
```

Open `web/index.html` directly in a browser (double-click it — no server, no
build step) to see the audit trail behind the "18 real API runs" claims
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

`run_eval.py --live` is the only thing standing between "14/18, 0/5 false
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
project's own thesis about the drafter — but for the researcher too, and
worse than a couple of stray runs.** Of the 13 live runs, 12 were `REJECTED`
at the researcher's own schema gate. A full audit of every gate detail — not
just the first two shapes noticed at the time — found 7 of those 12 were
exactly two defects: a field over its character cap (4 runs, across
`marketing_task.description`, `marketing_task.why_ai_helps`, and
`what_they_sell.summary`) and a non-conforming `claim_id` like `c1b` instead
of a plain integer (3 runs). The other 5 were unrelated: 3 output-budget
truncations at the drafter/QA stage (already fixed in an earlier pass), a
citation-markup leak, and one run missing a required field outright. The gate
worked correctly every time — this was the researcher's own `SKILL.md` under-
specifying two of its own schema's constraints, not a gate failure.

**That's fixed in the source, and now proven live — partially.** The prompt
told the model to count *characters* before emitting a field, which a model
does unreliably; it now gives an explicit word budget with real margin
instead, plus explicit `claim_id` examples and two more gaps the same audit
surfaced (`evidence_type`'s enum and the required date format were never
stated at all). A new `research_brief_precheck()` also catches all of these
before raw schema validation runs, with a message that names the field and
the actual number instead of a jsonschema dump truncated mid-string.
Golden-set cases `rb01`–`rb04` guard against a regression.

Five fresh live runs, against five different companies (Sonos, Notion,
Figma, Linear, Basecamp), confirm the fix for the two defects it targeted:
**zero** field-length or `claim_id`-format violations across any of them.
But live testing found something the fixture-only fix couldn't: **the
citation-markup leak was not actually fixed by reinforcement alone, and it
recurred in 2 of the 5 fresh runs** (Figma, Linear) — `<cite
index="...">...</cite>` tags copied straight out of the search tool's
results into `what_they_sell` and `recent_news`, inflating those fields
past their 300-character cap as a direct side effect. The gate caught both
correctly and rejected without retry, exactly as designed.

**That's fixed now too (2026-08-30), verified on fixtures, not yet
confirmed live.** Belt-and-braces, because reinforcement alone had already
proven insufficient: `sanitize_research_brief()` strips citation markup
from every string field in the brief — before any length check or schema
validation runs, content preserved, only the tag removed, every strip
logged — and `SKILL.md` was strengthened to state plainly that every field
is plain text, no markup of any kind. Golden-set cases `rs01`-`rs03` cover
it. Re-running the sanitizer against the actual Figma and Linear brief data
confirmed the markup is now fully removed from both — but also found the
underlying clean prose in both was still over its cap even without the
markup (Figma 311/300, Linear 354/300). The leak was a real contributing
cause, not the sole one, for those two specific rejections; the 40-word
budgets for `what_they_sell.summary`/`recent_news.summary` evidently don't
have as much margin as judged when only `marketing_task` was tightened.
Not fixed here — see `ARCHITECTURE.md` → Known limitations.

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
only a model can catch — were unmeasured as a result, not because they were
skipped by choice.

**Credit came back, and so did live testing — this time against five
different companies, not just Sonos.** The point wasn't just to prove the
researcher fix; it was to see what a healthier pipeline actually produces,
instead of a stage-one failure loop. It produced a real mix:

| Company | Outcome | Attempts | Score | What happened |
|---|---|---|---|---|
| Sonos | `ESCALATED` | 3 | 6/10 | Researcher clean. QA blocked on `unsupported_claim`, then `claim_drift`, then `unsupported_claim` again. Retry budget spent, correctly escalated. |
| **Notion** | **`RELEASED`** | 3 | 8/10 | Researcher clean. Two revisions to clear `claim_drift` and generic-language flags, then cleared the bar. **The first live `RELEASED` this project has ever produced.** |
| Figma | `REJECTED` | 0 | — | Citation-markup leak (see above) inflated two fields past their character cap. Correctly rejected before drafting. |
| Linear | `REJECTED` | 0 | — | Same defect, same shape, different company — confirms it's a pattern, not a fluke. |
| Basecamp | `ESCALATED` | 3 | 4/10 | Researcher clean. The *drafter's* self-reported word count was wrong twice (a pre-existing, documented behavior — see "The limits are suggestions" above), plus one `claim_drift` QA block. Retry budget spent. |

No `HALTED` in this batch — every company researched had enough public
surface to clear the evidence bar. That's not a claim that halting doesn't
work; the `thin_evidence` dry-run fixture still demonstrates it, and it just
didn't come up against five real, well-documented companies.

---

## Repo

```
skills/            three SKILL.md agents — the contract each one operates under
contracts/         JSON schemas for every handoff
orchestrator/      run.py — gates, retry budget, run logging, dry-run fixtures
orchestration/     importable n8n workflow (16 nodes, generated + graph-checked)
evals/             mutation-based golden set, scorer, and results
web/               static audit viewer over 18 live runs across 5 companies — open index.html
verticals/         device fleet triage — the same architecture, specced not built
ops/               runbook: metrics, cost model, failure playbooks
ARCHITECTURE.md    why each gate exists, and what this system can't do
STATE.md           what's built, what's verified live, what's unproven — as of today
DEMO.md            a plain-language script for walking someone through this
DEPLOY.md          how web/ actually gets deployed (Cloudflare Pages), and the redeploy command
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
- **No live run has ever reached `HALTED`.** Of 18 real API runs, none have
  triggered `insufficient_evidence` — every company researched (Sonos, Notion,
  Figma, Linear, Basecamp) had enough public surface to clear the evidence
  bar. `HALTED` is demonstrated only by the `thin_evidence` dry-run fixture —
  a real code path, but not live evidence that a real model, live, produces
  it. `RELEASED` **has** now happened live: Notion, 3 attempts, score 8/10.

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
