# STATE

Internal. Written 2026-08-23. This is the **first commit** this repo will
ever have — there is no prior `git log` to cross-reference yet. Whoever
updates this file next should run `git log --oneline` first and check every
claim below still matches what's actually committed, not what this file says.

---

## Built and verified with real live API calls

- **The researcher can actually research.** It has a real `web_search` tool
  wired into `orchestrator/run.py` (it didn't, until this session — see
  "Fixed this session" below). Two live runs (`65de63f2`, `0f8a2da1`) show it
  producing real, dated, sourced claims — including a mix of strong sources
  (`newsroom.sonos.com`, `docs.sonos.com`) and weaker ones (third-party
  marketing-strategy blog sites), which is itself an honest data point about
  live research quality, not something to clean up before showing anyone.
- **A complete, real, three-agent run**, live, start to finish: researcher →
  drafter → QA reviewer → revise → QA reviewer again → escalate. Run
  `785069cb`. The QA reviewer (Opus) caught a real `claim_drift` — a citation
  quietly restated as something stronger than its source said — twice in a
  row, across two independent drafts. The retry budget (`MAX_REVISIONS=2`)
  ran out and the pipeline escalated to a human queue instead of lowering the
  threshold. This is the best evidence this project has, and it happened
  without anyone scripting the outcome.
- **Gate 2 (schema validation, no retry) held under real pressure.** Of the
  13 live runs, 12 were `REJECTED` overall; 9 of those were specifically
  `schema:research_brief` gate failures (the other 3 were `contract`-gate
  truncations at the drafter/QA stage — see below). A full per-run audit this
  session (not just the two most-visible shapes) found the 9 broke down as:
  4 field-length overruns (across `marketing_task.description`,
  `marketing_task.why_ai_helps`, and `what_they_sell.summary` — not only
  `description`), 3 malformed `claim_id`s, 1 citation-markup leak, and 1 run
  missing a required field outright. Every rejection was correct and none
  were retried, per the system's own invariant.
- **Gate 3 (deterministic checks) caught a real self-report mismatch twice**
  live — the drafter claimed a word count that didn't match the actual count
  (113 vs. 117 in one run, 124 vs. 129 in another) — and correctly skipped
  the QA call rather than paying for a judgment call on something arithmetic
  already caught.
- **Gate 5 (release decision, recomputed in code) never deferred to the
  reviewer's own `pass` field.** Not directly exercised as a disagreement in
  this session's runs, but `release_decision()` ran on every real QA verdict
  received and correctly blocked twice on `claim_drift`.
- **The offline deterministic eval** (`python evals/run_eval.py`) — needs no
  API key, ran clean: **15/19 recall, 0/9 false blocks.**
- **All five dry-run scenarios** (`--dry-run --scenario {happy_path,
  generic_email, thin_evidence, wordcount_violation, escalation}`) still pass
  their expected terminal state after every code change made this session and
  last. `escalation` is new this session — see below.

## Fixed this session and last (real bugs, not the eight protected invariants)

1. `run_meta.agent` / `run_meta.attempt` were required by all three JSON
   schemas but never populated by `call_agent()` — every live call, for every
   agent, was guaranteed to fail schema validation regardless of API key.
   Fixed.
2. The researcher had no web-search tool despite its `SKILL.md` requiring
   one. It was fabricating plausible source URLs. Fixed — this is also the
   headline "what live testing found" lesson: dry-run fixtures were 100%
   green through this entire bug's lifetime, because fixtures don't call
   tools.
3. Extended thinking (on by default, Claude 5 family) draws from the same
   `max_tokens` budget as visible output. Drafter and QA reviewer budgets
   were raised (4,000 → 16,000 for the drafter; 8,000 → 16,000 for the QA
   reviewer) after live calls proved the lower numbers insufficient.
4. `print_artifact()` was dead code — never called from `main()`. Even a
   fully `RELEASED` run would have printed nothing but a bare outcome line.
   Replaced with `print_audit()`, which shows full content for **any**
   terminal state, not just `released`.

## New this session: escalation fixture coverage

The original four dry-run scenarios never reached `ESCALATED`: `happy_path`
resolves in 1 attempt, `generic_email` and `wordcount_violation` resolve on
revision (2 attempts), and `thin_evidence` halts before drafting (0 attempts).
None exhausted the retry budget, so the terminal state this project's best
real run (`785069cb`) actually reached had zero dry-run coverage. Added a
fifth scenario, `escalation`, in `orchestrator/fixtures/_build_fixtures.py`:
three deterministically-clean drafts, each carrying the same `claim_drift`
QA flag reworded, mirroring `785069cb`'s real story. `MAX_REVISIONS=2` runs
out after `draft_package_r2`/`qa_verdict_r2`, and the run correctly lands on
`ESCALATED`. Verified: all five scenarios now produce their expected terminal
state (`RELEASED` ×3, `HALTED` ×1, `ESCALATED` ×1).

## New this session: fixed the researcher's schema under-specification

Root-caused the 12/13 live rejection rate instead of treating it as noise.
Read `skills/researcher/SKILL.md` against `contracts/research_brief.schema.json`
field by field. Found: the prompt told the model to count *characters*
before emitting a length-capped field — unreliable, since a model doesn't
see individual characters the way it sees words — instead of a word budget
with real margin under the cap; `claim_id`'s `^c[0-9]+$` pattern was never
stated with valid/invalid examples; `evidence_type`'s six-value enum was
never named in the prompt at all; neither was the required `YYYY-MM-DD` date
format. Fixed all four in `SKILL.md` and in `call_agent()`'s injected
researcher-specific reinforcement. Added `research_brief_precheck()` in
`orchestrator/run.py` — runs before raw `validate_schema()`, same gate name
(`schema:research_brief`), checks the same constraints the schema does, but
names the field and the actual number instead of a jsonschema message
truncated mid-string by the offending value itself. Golden-set cases
`rb01`–`rb04` (plus `rg01`, a clean-brief guard against the precheck itself
being too strict) cover the fix; `evals/run_eval.py` now branches on a
`"stage"` field per case so researcher-stage cases test
`research_brief_precheck()` directly instead of the drafter's
`deterministic_checks()`. All five dry-run scenarios and the offline eval
still pass (now 15/19 recall, 0/9 false blocks — was 10/14, 0/4).

## New this session: 5 fresh live runs, first live RELEASED

Budget approved up to $4; used on 5 live runs against 5 real companies
(Sonos, Notion, Figma, Linear, Basecamp) — the point being not just to
prove the researcher fix, but to see the pipeline produce something other
than a stage-one failure loop. Outcome mix: `ESCALATED` (Sonos, 3 attempts,
score 6), **`RELEASED`** (Notion, 3 attempts, score 8 — the first live
`RELEASED` this project has ever produced), `REJECTED` (Figma), `REJECTED`
(Linear), `ESCALATED` (Basecamp, 3 attempts, score 4). No `HALTED` — every
company had enough public surface to clear the evidence bar.

The fix from above is confirmed for what it targeted: zero field-length or
`claim_id`-format violations across any of the 5 runs. It also surfaced
something the fix didn't touch: **the citation-markup leak recurred in 2 of
5 runs** (Figma, Linear) — `<cite index=...>` tags copied straight into
`what_they_sell`/`recent_news`, which is what actually blew the character
cap in both cases. The existing guidance (in `call_agent()`, reinforced
further this session) evidently isn't sufficient; a real fix would strip
known citation-markup patterns from search results before they reach the
model, not just ask it not to copy them. Not done yet — new known
limitation, documented in `ARCHITECTURE.md`.

Dashboard (`web/data/build_runs_json.py`, `web/app.js`) updated to use these
5 runs' real `brief`/`drafts`/`verdicts` fields directly — no hand-recovery
needed, unlike the original 13. This also meant building actual draft/QA
verdict rendering in `app.js` for the first time; previously `renderDraftPanel`
and `renderQaPanel` unconditionally showed "not captured" because no run's
data ever supported anything else. 18 total runs now on the dashboard.
README/ARCHITECTURE updated with the real outcome mix and the corrected
RELEASED/HALTED claims.

## New this session: sanitized citation markup instead of rejecting it

Fixed the citation-markup leak found above. Distinct bug from the schema
under-specification: that was the model misjudging its own length; this is
tool output (the search tool's citation annotations) contaminating model
output. Added `sanitize_research_brief()` in `orchestrator/run.py` — strips
`<cite>`/`</cite>` tags from every string field in the brief, content
preserved, before any length check or schema validation runs, every strip
logged by field path. Sanitize rather than reject: the underlying claim is
correct, only the wrapper is wrong. `SKILL.md` and the injected prompt
reinforcement also state plainly that every field is plain text. Golden-set
cases `rs01`–`rs03` cover it: over-cap-via-markup, markup-in-uncapped-field,
markup-that-never-threatened-the-cap. 26 cases, 14/18 recall, 0/8 false
blocks at that point.

Re-running the sanitizer against the actual Figma/Linear brief data
confirmed the markup is now fully stripped from both — but also found the
underlying clean prose in both was *still* over its cap (Figma 311/300,
Linear 354/300). The leak was a real contributing cause, not the sole one.
Also checked AgentDesk's own `MAX_TOKENS` against Crux's (which Crux had
just raised to 16000 after hitting the identical extended-thinking-eats-
the-budget bug AgentDesk's drafter/QA already had): `researcher` was still
at the original vulnerable value, 4000 — raised to 16000 to match, before
it failed live rather than after. Fix verified on fixtures only; not yet
proven live.

## New this session: word budgets fixed with measurement, not guesswork

Closed the loop on what the citation-markup fix surfaced: `what_they_sell
.summary`/`recent_news.summary`'s 40-word budgets weren't consistent with
their 300-char cap. Computed the actual characters-per-word ratio across
the 7 real `research_brief` summaries this project has (5 from the
2026-08-30 live batch, 2 hand-recovered — the other 11 of 18 live runs
never persisted a brief). `what_they_sell.summary`: mean 7.78 c/w, max 8.60
— 40 words at the *mean* ratio alone is 311 characters, already over the
300 cap. `recent_news.summary`: mean 6.73, max 7.17 — not independently
broken (40 words at worst observed ratio still fit, with thin 4.4% margin)
but tightened anyway. `marketing_task.description`/`why_ai_helps` (already
tightened to 35 words two sessions ago) checked against the same
measurement and confirmed fine — ~21–23% margin at worst observed density,
which turned out to be the number both newly-tightened fields were matched
to, not an arbitrary round figure.

New budgets: `what_they_sell.summary` 40 → 27 words, `recent_news.summary`
40 → 33 words. Documented directly in `orchestrator/run.py` as a comment
block with the measured table, not just in `SKILL.md` prose. The actual
enforcement mechanism (`research_brief_precheck()`'s `check_len()`) already
existed and needed no new code — this fix is entirely about making the
*prompt's* word budget numerically honest about what it produces. Golden-set
cases `rb05` (old budget genuinely breaches the cap on realistic prose,
no markup) and `rg02` (new budgets hold real margin even written close to
their own limit). 28 cases, 15/19 recall, 0/9 false blocks. Verified on
fixtures only; the next live batch is what actually tests whether 27/33
words changes what the model writes, not just what fits if it complies.

## A real observability gap, stated plainly

The best run this project produced — `785069cb`, the escalation — happened
**before** `print_audit()` existed. Its gate sequence is fully preserved in
`runs.jsonl` (13 gate checkpoints, all real), but the underlying content —
the researcher's actual claims and URLs, the drafter's actual email text
across all three attempts, the QA reviewer's actual flag locations and
remediation text — was never printed anywhere and cannot be recovered. The
dashboard (`web/index.html`) shows this run's content panels as "not
captured," with the reason stated, rather than reconstructing what that
content probably looked like. Two other live runs (`65de63f2`, `0f8a2da1`)
happened after the fix and do have full researcher-panel detail — they're
rejections, not the escalation, but they're real and complete as far as they
went.

## Not verified live — proven only via dry-run fixtures, or not proven at all

- **`RELEASED` has now happened on a live run** — Notion, 3 attempts, score
  8/10, part of the 5-run batch documented above. Historically, of the
  original 13 runs against Sonos: 9 rejected at the researcher's schema
  gate (2 with fuller detail captured), 3 rejected at a drafter/QA
  truncation, 1 escalated, zero released. Combined with the 5 new runs: 18
  total, 1 released.
- **`HALTED` has still never happened on a live run.** Only the
  `thin_evidence` fixture demonstrates it. No live research call, across 18
  real runs and 5 companies, ever produced `insufficient_evidence: true`.
- **The live QA-judgment eval (`run_eval.py --live`, cases b11–b14) has never
  been run.** The offline number (15/19, 0/9 false blocks) is the only
  honest figure available. A single ad-hoc test call against case b12 during
  debugging (not a full eval run) did get correctly blocked by Opus (score
  2, blocking `generic` flag) — suggestive, not a measurement, and not
  reported as one anywhere else in this repo.
- **None of the dry-run scenarios have ever been run live** (only against
  fixtures) — four at the time this was planned and cancelled, a fifth
  (`escalation`) added later purely as a fixture, so the live-run count below
  is unaffected. Running scenarios live was planned, then explicitly
  **cancelled** this session — see below.
- **Cost/ops figures in `ops/RUNBOOK.md`** are estimates, not validated
  against real spend beyond this project's own live testing (~$3–5 across 13
  runs, computed from `runs.jsonl` token counts at 2026-08 pricing).
- **The device-fleet-triage vertical** (`verticals/`) is specified, not
  built. Unchanged from before this session.
- **No suppression list, no rate limiting, no cost ceiling.** Unchanged from
  before this session — and the reason the API credit ran out mid-project is
  a direct, concrete illustration of why a cost ceiling matters.

## Explicitly cancelled, not deferred

Per this session's brief: running all four scenarios live, and running the
four live QA-judgment eval cases, are **cancelled** — not "next up," not
"blocked pending credit." The account that would fund them ran empty. The
honest, final number for this project's quality gate is the offline one:
**15/19 recall, 0/9 false blocks, by deterministic code alone.** If someone
picks this project back up with API credit, those two things are exactly
where to resume.

## What's still broken or unverified, listed plainly

- No live `HALTED` run exists. `RELEASED` now does (Notion, this session).
- The citation-markup leak recurred live (2 of 5 fresh runs) despite
  existing reinforcement. Not actually fixed — see the new known-limitation
  bullet in `ARCHITECTURE.md`.
- The live QA-judgment number is permanently a hypothesis until someone runs
  it with credit.
- `785069cb`'s underlying content (claims, draft text, flag detail) is gone —
  not hidden, gone. It cannot be recovered without re-running the pipeline.
- The researcher's field-length and `claim_id`-format under-specification is
  fixed in `SKILL.md` and `research_brief_precheck()` this session (see
  above), but **unverified live** — no run has happened against the fix yet.
  Caught correctly by Gate 2 every time it occurred, which is the right
  behavior regardless, but "caught correctly" and "fixed" are different
  claims and only the first one has live evidence behind it so far.
- This repo was not a git repository until this session. `git init` and the
  first commit both happen today.
