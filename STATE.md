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
- **Gate 2 (schema validation, no retry) held under real pressure.** 10 of 13
  live runs were rejected at this gate, for genuinely different reasons each
  time (wrong field names, a citation-markup leak from the search tool, a
  `maxLength` overrun, a malformed `claim_id`). Every rejection was correct
  and none were retried, per the system's own invariant.
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
  API key, ran clean: **10/14 recall, 0/4 false blocks.**
- **All four dry-run scenarios** (`--dry-run --scenario {happy_path,
  generic_email, thin_evidence, wordcount_violation}`) still pass their
  expected terminal state after every code change made this session and last.

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

- **`RELEASED` has never happened on a live run.** Of 13 live runs: 10
  rejected at the researcher's schema gate, 2 more rejected the same way
  with fuller detail captured, 1 escalated. Zero released. The `RELEASED`
  terminal state is only demonstrated via the `happy_path`, `generic_email`,
  and `wordcount_violation` dry-run fixtures — real code paths, but not live
  evidence.
- **`HALTED` has never happened on a live run either.** Only the
  `thin_evidence` fixture demonstrates it. No live research call ever
  produced `insufficient_evidence: true` for Sonos.
- **The live QA-judgment eval (`run_eval.py --live`, cases b11–b14) has never
  been run.** The offline number (10/14, 0/4 false blocks) is the only
  honest figure available. A single ad-hoc test call against case b12 during
  debugging (not a full eval run) did get correctly blocked by Opus (score
  2, blocking `generic` flag) — suggestive, not a measurement, and not
  reported as one anywhere else in this repo.
- **The four dry-run scenarios have never been run live** (only against
  fixtures). This was planned, then explicitly **cancelled** this session —
  see below.
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
**10/14 recall, 0/4 false blocks, by deterministic code alone.** If someone
picks this project back up with API credit, those two things are exactly
where to resume.

## What's still broken or unverified, listed plainly

- No live `RELEASED` or `HALTED` run exists.
- The live QA-judgment number is permanently a hypothesis until someone runs
  it with credit.
- `785069cb`'s underlying content (claims, draft text, flag detail) is gone —
  not hidden, gone. It cannot be recovered without re-running the pipeline.
- The researcher still intermittently overruns its own field-length limits
  live, even after prompt hardening (see `ARCHITECTURE.md` → Known
  limitations). This is caught correctly by Gate 2 every time, but it is not
  *fixed* — it's a live, recorded, real unreliability, same category as the
  drafter's word-count problem this whole project exists to catch.
- This repo was not a git repository until this session. `git init` and the
  first commit both happen today.
