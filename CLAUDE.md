# AgentDesk — context for Claude Code

## What this is

A three-agent pipeline (research → draft → review) where the hard limits are
enforced in code rather than requested in prompts. It is a portfolio artifact
demonstrating multi-agent orchestration, so **the enforcement layer is the
product** — not the outreach emails it happens to produce.

Read `README.md` first, then `ARCHITECTURE.md`. Both explain the reasoning
behind decisions that look over-engineered until you know why.

## How to work in this repo

- **Explain before you change.** Say what you're about to do in plain terms and
  why, then do it.
- **Comment the reasoning, not the syntax.** `# retry budget stops at 2 because
  attempt 3 optimizes against the rubric` is useful. `# loop over items` is not.
- **Avoid unexplained magic.** If a change makes the system harder to describe
  in one sentence, it is probably the wrong change.
- **Say when something is a judgment call**, not a fact. Whoever reads this
  needs to know which parts they could defend differently.

## Invariants — do not "fix" these

Each of these looks like a bug and is a deliberate decision. Changing any of
them without being asked destroys the thing the repo demonstrates.

1. **Malformed agent output is rejected without retry** (`ContractError` in
   `run.py`). A model that can't produce the schema is a prompt bug. Retrying
   turns a loud, findable bug into a quiet, intermittent one.
2. **`MAX_REVISIONS = 2`.** Do not raise it. Attempt three onward optimizes
   against the rubric instead of toward a better email — Goodhart's law on
   schedule. Escalating to a human is the correct terminal state.
3. **`PASS_SCORE = 8` never moves.** If the release rate is bad, the fix is
   upstream. Raising or lowering the threshold treats the symptom.
4. **The QA reviewer runs on a different model family than the drafter.** A
   model grading its own family shares its blind spots. Do not "simplify" the
   config by unifying models.
5. **The reviewer never edits.** It flags and scores only. If the reviewer
   fixes the work, nobody reviewed the work.
6. **The banned-phrase list leaks, on purpose.** Eval case `b11` opens with
   "I hope you are having a great week," which is not on the list. Do not patch
   it by adding the phrase. It is documented in `ARCHITECTURE.md` as a known
   limitation because denylists only catch what you thought of, and the honest
   version of that finding is worth more than a passing test.
7. **`halted` is a success outcome.** A pipeline that always produces an email
   will invent facts about companies it couldn't research.
8. **`release_decision()` recomputes pass/fail in code.** The reviewer's own
   `pass` field is advisory. A gate a model can talk past is not a gate.

## Keep in sync

The deterministic checks exist in two places and must match:

- `orchestrator/run.py` → `deterministic_checks()`
- `orchestration/build_n8n_workflow.py` → the `JS_CHECKS` block

Change one, change the other, then regenerate the workflow. Same for the JSON
schemas in `contracts/` — both runtimes read them.

## Generated files — edit the generator, not the output

| Generated | Generator |
|---|---|
| `orchestration/agentdesk.n8n.json` | `orchestration/build_n8n_workflow.py` |
| `evals/golden_set.jsonl` | `evals/build_golden_set.py` |
| `orchestrator/fixtures/dry_run.json` | `orchestrator/fixtures/_build_fixtures.py` |

Each generator self-validates on run (word counts, graph reachability, dangling
edges). Hand-editing the output skips those checks.

## Commands

```bash
python orchestrator/run.py --dry-run                          # releases
python orchestrator/run.py --dry-run --scenario generic_email # blocks, revises, releases
python orchestrator/run.py --dry-run --scenario thin_evidence # halts
python evals/run_eval.py                                      # offline gate score
python evals/run_eval.py --live                               # adds real QA calls (costs money)
```

Windows: `.\setup.ps1` runs all of the above as a verification pass.

## Definition of done for any change

1. All four `--dry-run` scenarios still produce their expected outcome
2. `python evals/run_eval.py` still shows **0 false blocks**
3. Any new failure mode discovered gets added to `evals/build_golden_set.py`
   as its own mutation — the golden set grows and never shrinks
4. If a known limitation was resolved, remove it from `ARCHITECTURE.md`;
   if a new one was introduced, add it

## Current state

Working and verified: the CLI orchestrator, all four scenarios, the offline
eval (71% recall, 0% false blocks), the n8n workflow graph.

Not built: the live eval has never been run; the device-fleet-triage vertical
is specified in `verticals/` but not implemented; there is no suppression list,
no rate limiting, and no cost ceiling. Do not describe any of these as done.
