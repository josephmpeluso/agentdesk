# Evidence

`runs.sample.jsonl` in this directory is the raw, unedited gate log for the
**13 real live API runs** this project ran against Sonos on 2026-08-22. It is
a frozen historical snapshot, extracted once from the working `runs.jsonl`
and committed as-is — it is not regenerated and not meant to be re-run or
appended to.

Breakdown: 12 `rejected` (10 at the researcher's schema gate on first pass,
2 more the same way with fuller detail captured), 1 `escalated` (`785069cb`
— the retry budget ran out after two real `claim_drift` catches). Zero
`released`, zero `halted`, live. See `STATE.md` and `README.md` for what
that does and doesn't prove.

The curated, dashboard-facing version of this same evidence lives in
`web/data/runs.js` / `web/data/runs.json`, built from these entries by
`web/data/build_runs_json.py`.

## Why this file exists separately from `runs.jsonl`

The repo-root `runs.jsonl` is a **working log**, not evidence — every
`--dry-run` invocation appends fixture noise to it (44 fixture entries
accumulated there alongside the 13 real ones as of this writing). It is
gitignored and untracked on purpose: nothing about a local dry-run run
should be able to alter what the public repo claims happened. This file is
the part of that log worth keeping, lifted out once and frozen.
