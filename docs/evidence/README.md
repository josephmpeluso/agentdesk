# Evidence

`runs.sample.jsonl` in this directory is the raw, unedited gate log for
**18 real live API runs** this project has run: 13 against Sonos on
2026-08-22, plus 5 more against Sonos, Notion, Figma, Linear, and Basecamp
on 2026-08-30. It's a deliberate, manual snapshot — extracted from the
working `runs.jsonl` and committed as-is — not an automatic mirror. It gets
updated when there's genuinely new real evidence worth adding, not on every
local run.

Breakdown: 14 `rejected`, 3 `escalated`, 1 `released`. The single `released`
run (Notion, 2026-08-30) is the first live `RELEASED` this project has ever
produced. See `STATE.md` and `README.md` for the full story, including which
defects the 2026-08-30 batch confirmed fixed and which one it found still
broken (a citation-markup leak, recurring in 2 of the 5 fresh runs).

The curated, dashboard-facing version of this same evidence lives in
`web/data/runs.js` / `web/data/runs.json`, built from these entries by
`web/data/build_runs_json.py`.

## Why this file exists separately from `runs.jsonl`

The repo-root `runs.jsonl` is a **working log**, not evidence — every
`--dry-run` invocation appends fixture noise to it. It is gitignored and
untracked on purpose: nothing about a local dry-run run should be able to
alter what the public repo claims happened. This file is the part of that
log worth keeping, lifted out deliberately and frozen until the next real
batch of live evidence is worth adding.
