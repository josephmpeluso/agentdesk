# Runbook

The thing that separates a working demo from a system someone else can
operate: what you do at 2am when it misbehaves, and what you watch so you find
out before the customer does.

## Metrics

Every run appends one JSON line to `runs.jsonl`. Five numbers matter.

| Metric | Definition | Healthy | What a move means |
|---|---|---|---|
| **release rate** | released ÷ total | 55–75% | above 80% suggests the reviewer went agreeable; below 40% suggests the drafter's instructions broke |
| **first-pass rate** | released on attempt 1 ÷ released | 60%+ | falling means the drafter and reviewer disagree about the bar — a rubric problem, not a draft problem |
| **halt rate** | halted ÷ total | 10–20% | this is *good* when it fires correctly; near 0% means the researcher is inventing rather than admitting gaps |
| **escalation rate** | escalated ÷ total | under 15% | rising means retries aren't converging; read the flags before touching the budget |
| **cost per released asset** | total spend ÷ released | see below | the only cost number that means anything |

**Cost per released asset is the headline.** Cost per API call is vanity.
A cheaper model that fails QA twice as often costs more per usable email, and
the only way to see that is to divide by what actually shipped.

## Cost model

Per attempt, order of magnitude:

| Stage | Model | ~tokens (in/out) | ~cost |
|---|---|---|---|
| researcher | Haiku | 8k / 1.5k | $0.01–0.02 |
| drafter | Sonnet | 3k / 1.5k | $0.03–0.04 |
| qa-reviewer | Opus | 5k / 1.5k | $0.10–0.15 |

Rough per-outcome:

- released first pass — **~$0.17**
- released after one revision — **~$0.32**
- escalated (3 attempts) — **~$0.60**, and no usable output
- halted at research — **~$0.02**, and no usable output

At a 65% release rate with 60% first-pass, cost per released asset lands
around **$0.35**. Confirm against your own `runs.jsonl` rather than trusting
that number; token counts move with company complexity.

Two things that move it most:

1. **Deterministic gate hit rate.** Every draft caught by Gate 3 skips a
   reviewer call — the most expensive stage. On the 18-case golden set, 10
   cases never reach QA at all — caught by code first.
2. **Reviewer model choice.** Opus is 3–5× Sonnet here. Whether it earns that
   is an empirical question with an answer: run `evals/run_eval.py --live` on
   both and compare recall on cases b11–b14. Don't argue about it.

## Failure playbooks

### Release rate above 85%
Almost always reviewer drift toward agreeableness, not a sudden improvement in
drafting.

1. Pull 10 released runs from `runs.jsonl` and read the emails yourself.
2. Run `evals/run_eval.py --live`. If recall on b11–b14 dropped, it's the
   reviewer.
3. Check the reviewer is still on a different model family than the drafter.
   A config change that quietly aligned them is the most common root cause.
4. Do **not** raise the threshold above 8. That treats the symptom and hides
   the drift.

### Escalation rate above 25%
Retries are not converging.

1. Read `flags[]` across escalated runs. Same flag type repeating means the
   drafter's SKILL.md is missing an instruction the reviewer expects.
2. If flags are scattered and contradictory, the reviewer is inconsistent —
   check the rubric for cases that overlap.
3. Resist raising `MAX_REVISIONS`. Attempt three onward optimizes against the
   rubric rather than toward a better email. More attempts buy worse output
   that scores higher.

### Halt rate near zero
The researcher has stopped admitting gaps.

1. Sample 10 briefs. Are `gaps[]` arrays getting shorter?
2. Check `confidence` distribution. If nearly everything is `high`, the
   calibration instruction has stopped landing.
3. This is the most dangerous failure in the system and the least visible,
   because it produces *more* output, not less. Everything downstream inherits
   a fabricated premise and every gate below passes it, because every gate
   below trusts the brief.

### Schema rejection spike
Gate 2 firing repeatedly means a prompt or model change altered output shape.

1. Check whether a model version rolled.
2. Re-read the SKILL.md output section — did an edit introduce ambiguity about
   fences or preamble?
3. Do not add a repair step that coerces malformed output into shape. That
   converts a loud bug into a silent one.

## Deployment checklist

- [ ] `ANTHROPIC_API_KEY` set (env var, not committed — the n8n workflow reads
      `$env.ANTHROPIC_API_KEY`)
- [ ] `pip install anthropic jsonschema`
- [ ] `python evals/run_eval.py` passes with 0 false blocks
- [ ] `python orchestrator/run.py --dry-run` releases; `--scenario thin_evidence` halts;
      `--scenario escalation` exhausts the retry budget and escalates
- [ ] Reviewer model confirmed different family from drafter
- [ ] `runs.jsonl` writing to durable storage, not a container filesystem
- [ ] Escalation queue has a human attached to it and that human knows it
- [ ] Suppression list in place before any live send — this repo has none

## What is not in here

Named honestly, because a runbook that implies completeness is worse than a
short one.

- **No suppression or dedup.** Run the same company twice, send twice. Build
  this before any live sending.
- **No rate limiting or backoff.** A burst will hit API limits and the
  workflow has no retry-with-jitter.
- **No PII handling policy.** Research pulls public web content; nothing
  classifies or redacts what comes back.
- **No cost ceiling.** Nothing stops a runaway batch. A per-batch spend cap is
  the first thing to add.
- **No human review sampling.** Escalations reach a human; releases do not.
  A 5% random audit of *released* assets is how you catch reviewer drift
  before the metrics do.
