#!/usr/bin/env python3
"""One QA call, fully instrumented. Costs about three cents.

Use this before spending credit on a full eval run. It answers the questions
a batch failure can't: did the reply get truncated, did the model wrap the
JSON in prose, or is something else going on entirely.

    python evals/debug_qa.py
    python evals/debug_qa.py --case b12
    python evals/debug_qa.py --raw        # dump the entire reply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "orchestrator"))

from run import MODELS, MAX_TOKENS, load_skill, release_decision  # noqa: E402
from jsonio import extract_json, response_text, ParseFailure      # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="b12", help="golden set case id")
    ap.add_argument("--raw", action="store_true", help="print the full reply")
    args = ap.parse_args()

    cases = {json.loads(l)["id"]: json.loads(l)
             for l in (Path(__file__).parent / "golden_set.jsonl").read_text().splitlines() if l.strip()}
    if args.case not in cases:
        print(f"Unknown case '{args.case}'. Available: {', '.join(cases)}")
        return 2
    case = cases[args.case]

    print("=" * 74)
    print(f"QA diagnostic — case {case['id']} ({case['failure_mode'] or 'clean'})")
    print(f"expected: {'BLOCK' if case['label'] == 'bad' else 'PASS'}")
    print(f"model:    {MODELS['qa-reviewer']}")
    print(f"budget:   {MAX_TOKENS['qa-reviewer']} output tokens")
    print("=" * 74)

    try:
        import anthropic
    except ImportError:
        print("\npip install anthropic")
        return 1

    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=MODELS["qa-reviewer"],
            max_tokens=MAX_TOKENS["qa-reviewer"],
            system=load_skill("qa-reviewer"),
            messages=[{"role": "user", "content":
                       f"RESEARCH BRIEF:\n{json.dumps(case['brief'], indent=2)}\n\n"
                       f"DRAFT PACKAGE:\n{json.dumps(case['draft'], indent=2)}\n\n"
                       "Produce the qa_verdict."}],
        )
    except Exception as e:                                  # noqa: BLE001
        print(f"\nAPI CALL FAILED: {type(e).__name__}: {e}")
        print("\nUsual causes: ANTHROPIC_API_KEY unset in this window, no credit,")
        print("or a model name that no longer exists.")
        return 1

    print(f"\nstop_reason:   {resp.stop_reason}")
    print(f"input tokens:  {resp.usage.input_tokens}")
    print(f"output tokens: {resp.usage.output_tokens}")

    if resp.stop_reason == "max_tokens":
        print("\n>>> TRUNCATED. The reply hit the ceiling mid-JSON.")
        print(f">>> Raise MAX_TOKENS['qa-reviewer'] in orchestrator/run.py above "
              f"{MAX_TOKENS['qa-reviewer']}.")

    raw = response_text(resp)
    if args.raw:
        print("\n" + "-" * 74 + "\nFULL REPLY\n" + "-" * 74)
        print(raw)
    else:
        print("\n--- first 300 chars ---")
        print(raw[:300])

    if raw and not raw.lstrip().startswith("{"):
        print("\n>>> Reply does not start with '{'. The model added a preamble.")
        print(">>> extract_json handles this, but it wastes tokens — worth")
        print(">>> tightening the output section of skills/qa-reviewer/SKILL.md.")

    print("\n" + "-" * 74)
    try:
        verdict = extract_json(resp)
    except ParseFailure as e:
        print("PARSE FAILED\n")
        print(e.detail())
        return 1

    print("PARSE OK\n")
    print(f"  score:        {verdict.get('score')}")
    print(f"  model's pass: {verdict.get('pass')}")
    print(f"  swap test coherent: {verdict.get('swap_test', {}).get('still_coherent')}"
          "   (True means it read as a template)")
    for f in verdict.get("flags", []):
        print(f"    [{f.get('severity')}] {f.get('type')}: {str(f.get('location'))[:60]}")

    released, reason = release_decision(verdict)
    print(f"\n  gate decision: {'RELEASE' if released else 'BLOCK'} — {reason}")

    correct = (not released) if case["label"] == "bad" else released
    print(f"  {'CORRECT' if correct else 'WRONG'} for this case")
    print("-" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
