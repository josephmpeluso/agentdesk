#!/usr/bin/env python3
"""Scores the gate against the golden set.

Two numbers matter and they pull against each other:

  recall      of the known-bad drafts, what fraction did the gate block?
  false block of the known-good drafts, what fraction did the gate block anyway?

A gate with 100% recall and a 40% false block rate is a gate nobody will keep
switched on. Reporting only recall is how that ships.

Offline mode (default) exercises the deterministic layer alone — no API key,
runs in under a second, and is the right thing to put in CI. It reports the
model-only cases as ESCAPED, because from code's point of view they did.

    python run_eval.py                 # deterministic layer only
    python run_eval.py --live          # adds real QA reviewer calls
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "orchestrator"))

from run import (  # noqa: E402
    deterministic_checks, release_decision, research_brief_precheck,
    sanitize_research_brief, MODELS, load_skill, MAX_TOKENS,
)
from jsonio import extract_json  # noqa: E402


def load_cases(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def qa_live(brief: dict, draft: dict) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODELS["qa-reviewer"],
        max_tokens=MAX_TOKENS["qa-reviewer"],
        system=load_skill("qa-reviewer"),
        messages=[{"role": "user", "content":
                   f"RESEARCH BRIEF:\n{json.dumps(brief, indent=2)}\n\n"
                   f"DRAFT PACKAGE:\n{json.dumps(draft, indent=2)}\n\nProduce the qa_verdict."}],
    )
    return extract_json(resp)


def evaluate(cases: list[dict], live: bool) -> dict:
    rows = []
    failures: list[tuple[str, str]] = []
    for c in cases:
        stage = c.get("stage", "drafter")
        if stage == "researcher":
            # A researcher-stage case tests the same path run_pipeline()
            # actually runs: sanitize first (strips tool-leaked citation
            # markup), then research_brief_precheck (Gate 2's field-level
            # precheck) on the sanitized result — there's no draft to speak
            # of at this stage, and no QA-reviewer path either: these are
            # pure schema/format defects, not judgment calls.
            sanitized, _ = sanitize_research_brief(c["brief"])
            code_ok, problems = research_brief_precheck(sanitized)
        else:
            code_ok, problems = deterministic_checks(c["brief"], c["draft"])
        blocked_by = None
        if not code_ok:
            blocked_by = "code"

        if live and code_ok and stage == "drafter":
            try:
                verdict = qa_live(c["brief"], c["draft"])
                released, reason = release_decision(verdict)
                if not released:
                    blocked_by = "model"
                    problems = [reason]
            except Exception as e:                      # noqa: BLE001
                detail = e.detail() if hasattr(e, "detail") else str(e)
                failures.append((c["id"], detail))
                problems = [f"qa call failed: {e}"]

        blocked = blocked_by is not None
        should_block = c["label"] == "bad"

        if should_block and blocked:
            outcome = "CAUGHT"
        elif should_block and not blocked:
            outcome = "ESCAPED"
        elif not should_block and blocked:
            outcome = "FALSE BLOCK"
        else:
            outcome = "PASSED"

        rows.append({**c, "blocked_by": blocked_by, "outcome": outcome,
                     "detail": "; ".join(problems)[:150]})

    if failures:
        print("\n" + "!" * 78)
        print("QA CALLS FAILED — these are infrastructure errors, not gate results.")
        print("The recall number below is meaningless until these are fixed.")
        print("!" * 78)
        for cid, detail in failures[:3]:
            print(f"\n[{cid}]\n{detail}")
        if len(failures) > 3:
            print(f"\n...and {len(failures) - 3} more with the same shape.")
        print("!" * 78)

    return rows


def report(rows: list[dict], live: bool) -> int:
    mode = "LIVE (deterministic + QA model)" if live else "OFFLINE (deterministic layer only)"
    print("=" * 78)
    print(f"AgentDesk gate evaluation — {mode}")
    print("=" * 78)
    print(f"{'id':<5}{'expected':<10}{'caught_by':<11}{'result':<13}detail")
    print("-" * 78)
    for r in rows:
        exp = "block" if r["label"] == "bad" else "pass"
        print(f"{r['id']:<5}{exp:<10}{r['caught_by'] or '-':<11}{r['outcome']:<13}{r['detail'][:38]}")

    bad = [r for r in rows if r["label"] == "bad"]
    good = [r for r in rows if r["label"] == "good"]
    caught = [r for r in bad if r["outcome"] == "CAUGHT"]
    escaped = [r for r in bad if r["outcome"] == "ESCAPED"]
    false_blocks = [r for r in good if r["outcome"] == "FALSE BLOCK"]

    recall = len(caught) / len(bad) if bad else 0
    fbr = len(false_blocks) / len(good) if good else 0

    print("-" * 78)
    print(f"recall             {len(caught)}/{len(bad)}   {recall:.0%}   (known-bad drafts blocked)")
    print(f"false block rate   {len(false_blocks)}/{len(good)}   {fbr:.0%}   (known-good drafts blocked)")

    by = Counter(r["blocked_by"] for r in caught)
    print(f"blocked by code    {by.get('code', 0)}")
    print(f"blocked by model   {by.get('model', 0)}")

    if escaped:
        print("\nESCAPED:")
        for r in escaped:
            print(f"  {r['id']}  {r['failure_mode']:<24} (needs: {r['caught_by']})")
        if not live:
            print("\n  Expected offline. These require judgment, not arithmetic.")
            print("  Re-run with --live to measure whether the QA model catches them.")

    print("=" * 78)
    return 1 if false_blocks else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="also call the QA reviewer model")
    ap.add_argument("--set", default=str(Path(__file__).parent / "golden_set.jsonl"))
    args = ap.parse_args()

    cases = load_cases(Path(args.set))
    rows = evaluate(cases, args.live)
    return report(rows, args.live)


if __name__ == "__main__":
    sys.exit(main())
