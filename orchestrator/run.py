#!/usr/bin/env python3
"""
AgentDesk orchestrator.

Runs the researcher -> drafter -> qa-reviewer pipeline with the hard limits
enforced in code rather than trusted to the models.

The design claim this file exists to demonstrate: an agent team is only as
good as the layer that refuses its output. Five gates sit between a company
name and a human's inbox, and only one of them is a model.

    Gate 1  prompt        the SKILL.md contract given to each agent
    Gate 2  schema        JSON Schema validation, no retry on malformed
    Gate 3  deterministic word count, banned phrases, claim-ref coverage
    Gate 4  adversarial   the QA reviewer, on a different model
    Gate 5  budget        bounded retries, then escalate to a human queue

Usage:
    python run.py --company "Acme Robotics" --domain acme.com
    python run.py --dry-run                 # no API key needed, uses fixtures
    python run.py --dry-run --scenario generic_email
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from jsonio import extract_json, ParseFailure  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS = ROOT / "contracts"
SKILLS = ROOT / "skills"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Model tiering. Research is extraction-shaped and tolerates a cheaper model.
# Drafting and review are judgment-shaped. Review deliberately runs on a
# different model family than drafting: a model grading its own output shares
# its own blind spots, and correlated blind spots are how bad drafts pass.
MODELS = {
    "researcher": os.environ.get("AGENTDESK_RESEARCHER_MODEL", "claude-haiku-4-5-20251001"),
    "drafter": os.environ.get("AGENTDESK_DRAFTER_MODEL", "claude-sonnet-5"),
    "qa-reviewer": os.environ.get("AGENTDESK_QA_MODEL", "claude-opus-5"),
}

# Output budgets, per agent. Undersizing these is not a soft failure — the
# reply gets cut mid-JSON and surfaces as "Unterminated string", which looks
# like a model problem and is a budget problem. As of the Claude 5 family,
# extended thinking is on by default and its tokens are drawn from this same
# budget — a model can spend all 4000 tokens "thinking" and leave zero for
# the actual JSON, which is what happened to the drafter at 4000. qa-reviewer
# was raised to 8000 last session and held up against a synthetic test case,
# but a real verdict — with several flags and the full email reproduced in
# swap_test.redacted_body — ran the ceiling out again on a live run, so it's
# raised further here with more headroom. researcher raised to match: it
# hadn't hit this specific bug in the 18 live runs to date, but it runs on
# the same Claude 5 family and was carrying the exact vulnerable value (4000)
# this comment already describes failing at — Crux hit the identical bug in
# its own debater budgets independently, which is what prompted checking
# this one rather than waiting for a live run to prove it too.
MAX_TOKENS = {
    "researcher": 16000,
    "drafter": 16000,
    "qa-reviewer": 16000,
}

MAX_REVISIONS = 2          # after this many failed QA passes, escalate
PASS_SCORE = 8             # nothing below this reaches a human
WORD_TARGET = 120
WORD_TOLERANCE = 10

BANNED_PHRASES = [
    "i hope this email finds you well",
    "i hope you're doing well",
    "i hope this finds you well",
    "i came across your company",
    "i wanted to reach out",
    "in today's fast-paced",
    "game-changer",
    "game changer",
    "revolutionize",
    "leverage synergies",
    "circle back",
    "just following up",
    "i'll cut to the chase",
    "as you may know",
    "touch base",
    "at the end of the day",
]

CLAIM_REF_RE = re.compile(r"\[(c\d+)\]")


# --------------------------------------------------------------------------
# Run record
# --------------------------------------------------------------------------

@dataclass
class GateResult:
    gate: str
    passed: bool
    detail: str = ""


@dataclass
class RunRecord:
    run_id: str
    company: str
    started_at: float
    gates: list[GateResult] = field(default_factory=list)
    attempts: int = 0
    outcome: str = "incomplete"     # released | escalated | halted | rejected | interrupted
    score: int | None = None
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    # Full agent output, persisted to runs.jsonl for every terminal state —
    # this is what makes the log a self-contained audit record instead of a
    # gate-pass/fail summary. drafts/verdicts are lists, one entry per retry
    # attempt: an earlier version of this file kept only the *last* draft and
    # verdict, which silently discarded every earlier attempt's actual text
    # in memory, before a crash could even be the reason detail was lost.
    brief: dict | None = None
    drafts: list[dict] = field(default_factory=list)
    verdicts: list[dict] = field(default_factory=list)

    def gate(self, name: str, passed: bool, detail: str = "") -> bool:
        self.gates.append(GateResult(name, passed, detail))
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
        return passed

    def to_json(self) -> str:
        d = asdict(self)
        d["duration_s"] = round(time.time() - self.started_at, 2)
        return json.dumps(d)


# --------------------------------------------------------------------------
# Model transport
# --------------------------------------------------------------------------

def load_skill(name: str) -> str:
    """Read a SKILL.md and strip its YAML frontmatter for use as a system prompt."""
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text.strip()


SCHEMA_FILES = {
    "researcher": "research_brief.schema.json",
    "drafter": "draft_package.schema.json",
    "qa-reviewer": "qa_verdict.schema.json",
}


def call_agent(agent: str, user_content: str, record: RunRecord, attempt: int = 1) -> dict[str, Any]:
    """Single model call. Returns the parsed JSON artifact.

    Raises ContractError on unparseable output — deliberately not retried
    here, because malformed structure is a prompt bug, not a flake, and
    silently retrying it hides the bug.
    """
    try:
        import anthropic
    except ImportError:
        raise SystemExit("pip install anthropic  (or use --dry-run)")

    client = anthropic.Anthropic()

    # The SKILL.md only names the schema file by path — a model has no way to
    # read that file, so it guesses a shape. Embedding the literal schema is
    # what actually makes "conforming to research_brief.schema.json" true.
    schema_text = (CONTRACTS / SCHEMA_FILES[agent]).read_text(encoding="utf-8")
    system_prompt = (
        load_skill(agent)
        + "\n\n## Output schema — match this exactly (additionalProperties is false)\n\n"
        + f"```json\n{schema_text}\n```"
    )
    if agent == "researcher":
        system_prompt += (
            "\n\n## Search tool note\n\nCite sources only via `source_url`, a plain string "
            "starting with `http://` or `https://`. Every field in this brief is plain text — "
            "no markup, no tags, ever. Search results sometimes carry citation annotations "
            "like `<cite index=\"5-6,5-7\">...</cite>` — never copy those into any field, "
            "`source_url` or otherwise. Same for footnote brackets and markdown link syntax. "
            "Write plain prose. Before you emit a field, check it doesn't still have a tag "
            "fragment sitting in it from whatever you read.\n\n"
            "Every string field with a maxLength has a *word* ceiling stated in the skill "
            "above that leaves real margin under the character cap — use that word count, "
            "not the character count. Counting words is something you do reliably; counting "
            "characters in your own output is not, and a field that looks fine by eye can "
            "still be over the character cap. Stay under the word ceiling and the character "
            "cap takes care of itself. `marketing_task.description` (35 words, 400-char cap) "
            "is where this has actually gone wrong before — it's the field you're told to "
            "spend the most effort on, so it's the one that grows. One tight sentence naming "
            "the task and its evidence is enough; put elaboration in `why_ai_helps` (also "
            "35 words) instead of stuffing it all into `description`.\n\n"
            "`claim_id` must match `^c[0-9]+$` exactly: the letter c followed only by "
            "digits — c1, c2, c3, c11. Never c1b, c2a, c2-2, c2.1, or any other suffix.\n\n"
            "You will often have two or three claims that all support the same top-level "
            "finding (what_they_sell, recent_news, or marketing_task) — that's expected, "
            "since a finding is a synthesis and claims[] is the evidence under it. Do not "
            "invent a lettered variant to relate them. Just give each its own next plain "
            "integer id (c1, c2, c3, c4, c5...) in claims[], and set the finding's single "
            "`claim_id` field to whichever one claim best anchors that finding.\n\n"
            "`marketing_task.evidence_type` must be exactly one of: job_posting, "
            "content_cadence, product_surface, support_channel, public_statement, "
            "site_structure — no other string.\n\n"
            "`recent_news.published_date` and every `claims[].retrieved_at` must be "
            "YYYY-MM-DD, e.g. 2026-08-14."
        )

    kwargs: dict[str, Any] = dict(
        model=MODELS[agent],
        max_tokens=MAX_TOKENS[agent],
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    # Only the researcher gets a fetch tool. The drafter and qa-reviewer are
    # deliberately blind to the internet — that's what makes a fabricated
    # claim structurally visible instead of a matter of trust.
    if agent == "researcher":
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}]

    t0 = time.time()
    resp = client.messages.create(**kwargs)
    latency = int((time.time() - t0) * 1000)

    record.tokens_in += resp.usage.input_tokens
    record.tokens_out += resp.usage.output_tokens

    try:
        obj = extract_json(resp)
    except ParseFailure as e:
        raise ContractError(f"{agent}: {e.summary()}") from e

    obj.setdefault("run_meta", {})
    obj["run_meta"]["latency_ms"] = latency
    obj["run_meta"]["model"] = MODELS[agent]
    obj["run_meta"]["agent"] = agent
    obj["run_meta"]["attempt"] = attempt
    return obj


class ContractError(Exception):
    """Raised when an agent's output violates its contract."""


CLAIM_ID_RE = re.compile(r"^c[0-9]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EVIDENCE_TYPES = {
    "job_posting", "content_cadence", "product_surface",
    "support_channel", "public_statement", "site_structure",
}

# Matches only the <cite ...> / </cite> tags the web_search tool sometimes
# leaves in its results, e.g. <cite index="5-6,5-7">...</cite>. Deliberately
# narrow: it strips this one known tag by name, not "anything in angle
# brackets" — a company name like "<Company>" or a real comparison operator
# in prose must survive untouched. The tagged text itself is never removed,
# only the wrapper.
CITATION_MARKUP_RE = re.compile(r"</?cite\b[^>]*>", re.IGNORECASE)


def sanitize_research_brief(brief: dict) -> tuple[dict, list[str]]:
    """Strips citation markup the search tool leaks into plain-text fields,
    before any length check or schema validation ever sees them.

    This is a distinct bug from the schema under-specification fixed
    earlier: that one was the model misjudging its own field length. This
    one is tool output contaminating model output — the underlying claim
    text is correct, only the <cite> wrapper around it is wrong. Rejecting
    a correct claim over stray tags would waste a whole research call on
    something a few characters of regex already fixes, so this sanitizes
    rather than rejects. Every field in the brief is in scope, not just the
    length-capped ones — a citation tag in claims[].statement is just as
    much tool contamination as one in marketing_task.description, even
    though that field has no cap to breach.

    Returns the sanitized brief (a new object; the input is never mutated)
    and the list of field paths where a strip actually fired, so the caller
    can log it — a silent strip is exactly the kind of thing this project's
    own invariants exist to prevent.
    """
    fired: list[str] = []

    def clean(obj, path):
        if isinstance(obj, dict):
            return {k: clean(v, f"{path}.{k}" if path else k) for k, v in obj.items()}
        if isinstance(obj, list):
            return [clean(v, f"{path}[{i}]") for i, v in enumerate(obj)]
        if isinstance(obj, str):
            stripped = CITATION_MARKUP_RE.sub("", obj)
            if stripped != obj:
                fired.append(path)
            return stripped
        return obj

    return clean(brief, ""), fired


def research_brief_precheck(brief: dict) -> tuple[bool, list[str]]:
    """Field-specific checks for research_brief, run before raw schema validation.

    Every constraint here must match contracts/research_brief.schema.json
    exactly (see CLAUDE.md -> "Keep in sync"). This exists because a raw
    jsonschema error names a field path but the message is often eaten by the
    (long) offending string itself — "first at marketing_task/description:
    'Sonos publishes extensive educational content...' is too long" doesn't
    tell you it's 437 characters against a 400 cap. This says that: which
    field, what the actual number was, and what the limit is. On a pass, raw
    schema validation still runs afterward as the comprehensive backstop for
    anything not covered here (missing required fields, wrong types,
    additionalProperties leaks).
    """
    problems: list[str] = []

    def check_len(label: str, value: Any, cap: int) -> None:
        if isinstance(value, str) and len(value) > cap:
            problems.append(f"{label}: {len(value)} characters, exceeds {cap}-char cap by {len(value) - cap}")

    def check_claim_id(label: str, value: Any) -> None:
        if isinstance(value, str) and not CLAIM_ID_RE.match(value):
            problems.append(
                f"{label}: '{value}' does not match ^c[0-9]+$ "
                "(letter c then digits only — no suffixes like c1b, c2a)"
            )

    def check_date(label: str, value: Any) -> None:
        if isinstance(value, str) and not DATE_RE.match(value):
            problems.append(f"{label}: '{value}' is not YYYY-MM-DD format")

    wts = brief.get("what_they_sell") or {}
    check_len("what_they_sell.summary", wts.get("summary"), 300)
    check_claim_id("what_they_sell.claim_id", wts.get("claim_id"))

    rn = brief.get("recent_news") or {}
    check_len("recent_news.summary", rn.get("summary"), 300)
    check_claim_id("recent_news.claim_id", rn.get("claim_id"))
    check_date("recent_news.published_date", rn.get("published_date"))

    mt = brief.get("marketing_task") or {}
    check_len("marketing_task.description", mt.get("description"), 400)
    check_len("marketing_task.why_ai_helps", mt.get("why_ai_helps"), 400)
    check_claim_id("marketing_task.claim_id", mt.get("claim_id"))
    evidence_type = mt.get("evidence_type")
    if evidence_type is not None and evidence_type not in EVIDENCE_TYPES:
        problems.append(
            f"marketing_task.evidence_type: '{evidence_type}' is not one of {sorted(EVIDENCE_TYPES)}"
        )

    for i, c in enumerate(brief.get("claims", []) or []):
        if not isinstance(c, dict):
            continue
        check_claim_id(f"claims[{i}].claim_id", c.get("claim_id"))
        check_date(f"claims[{i}].retrieved_at", c.get("retrieved_at"))
        url = c.get("source_url")
        if isinstance(url, str) and not url.startswith(("http://", "https://")):
            problems.append(f"claims[{i}].source_url: '{url[:60]}' does not start with http:// or https://")

    return len(problems) == 0, problems


# --------------------------------------------------------------------------
# Gate 2 — schema validation
# --------------------------------------------------------------------------

def validate_schema(obj: dict, schema_name: str) -> tuple[bool, str]:
    schema = json.loads((CONTRACTS / schema_name).read_text(encoding="utf-8"))
    try:
        import jsonschema
    except ImportError:
        # Degraded mode: check required top-level keys only. Reported, not
        # silently tolerated — a gate you can't fully run is a known risk.
        missing = [k for k in schema.get("required", []) if k not in obj]
        if missing:
            return False, f"missing required keys {missing} (jsonschema not installed)"
        return True, "shallow check only — pip install jsonschema for full validation"

    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(obj), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        path = "/".join(str(p) for p in first.path) or "<root>"
        return False, f"{len(errors)} error(s); first at {path}: {first.message[:160]}"
    return True, f"conforms to {schema_name}"


# --------------------------------------------------------------------------
# Gate 3 — deterministic checks
# --------------------------------------------------------------------------

def deterministic_checks(brief: dict, draft: dict) -> tuple[bool, list[str]]:
    """Cheap, certain checks that run before spending a QA call.

    Everything here could in principle be judged by a model. None of it
    should be. Code is cheaper, faster, and does not have an opinion on
    Tuesdays.
    """
    problems: list[str] = []

    if not draft.get("draftable", False):
        return True, []  # a refusal to draft is valid; nothing to check

    email = draft.get("email", {})
    body = email.get("body", "")

    # -- word count, counted here rather than trusting the model's own count
    words = len(re.sub(CLAIM_REF_RE, "", body).split())
    if abs(words - WORD_TARGET) > WORD_TOLERANCE:
        problems.append(
            f"word_count: body is {words} words, must be {WORD_TARGET}±{WORD_TOLERANCE}"
        )
    if email.get("word_count") not in (None, words) and abs(email["word_count"] - words) > 3:
        problems.append(
            f"word_count_selfreport: model claimed {email['word_count']}, actual {words}"
        )

    # -- banned phrases
    low = body.lower()
    for phrase in BANNED_PHRASES:
        if phrase in low:
            problems.append(f"banned_phrase: '{phrase}'")

    # -- subject line
    subject = email.get("subject", "")
    if not subject:
        problems.append("subject: missing")
    elif len(subject) > 60:
        problems.append(f"subject: {len(subject)} chars, max 60")

    # -- claim reference integrity
    valid_ids = {c["claim_id"] for c in brief.get("claims", [])}
    used_ids = set(CLAIM_REF_RE.findall(body))
    declared = {r["claim_id"] for r in draft.get("claim_refs", [])}

    dangling = used_ids - valid_ids
    if dangling:
        problems.append(f"dangling_claim_ref: {sorted(dangling)} not in brief")

    undeclared = used_ids - declared
    if undeclared:
        problems.append(f"undeclared_claim_ref: {sorted(undeclared)} used but not in claim_refs")

    if not used_ids:
        problems.append("no_claim_refs: email asserts facts with zero source references")

    # -- low-confidence claims must never reach the drafter, so they must
    #    never appear in a draft either
    low_conf = {c["claim_id"] for c in brief.get("claims", []) if c.get("confidence") == "low"}
    leaked = used_ids & low_conf
    if leaked:
        problems.append(f"low_confidence_leak: {sorted(leaked)} should have been stripped upstream")

    # -- account brief
    ab = draft.get("account_brief", {})
    if ab and not ab.get("what_i_dont_know"):
        problems.append("account_brief: 'what_i_dont_know' is empty; it is mandatory")

    return len(problems) == 0, problems


def strip_low_confidence(brief: dict) -> dict:
    """Low-confidence claims are removed before the drafter sees the brief.

    Cheaper than asking the drafter to exercise restraint, and unlike
    restraint it works every time.
    """
    out = json.loads(json.dumps(brief))
    out["claims"] = [c for c in out.get("claims", []) if c.get("confidence") != "low"]
    return out


# --------------------------------------------------------------------------
# Gate 4/5 — QA verdict and release decision
# --------------------------------------------------------------------------

def release_decision(verdict: dict) -> tuple[bool, str]:
    """The orchestrator recomputes pass/fail. The reviewer's own `pass` field
    is advisory. A gate a model can talk its way past is not a gate."""
    score = verdict.get("score", 0)
    blocking = [f for f in verdict.get("flags", []) if f.get("severity") == "blocking"]
    swap_failed = verdict.get("swap_test", {}).get("still_coherent", False)

    if swap_failed:
        return False, "swap test: email survives redaction, so it is a template"
    if blocking:
        types = sorted({f["type"] for f in blocking})
        return False, f"{len(blocking)} blocking flag(s): {', '.join(types)}"
    if score < PASS_SCORE:
        return False, f"score {score} below threshold {PASS_SCORE}"

    if verdict.get("pass") is False:
        # Reviewer said fail, arithmetic says pass. Trust the reviewer and log
        # the disagreement — it usually means the rubric is missing a case.
        return False, "reviewer overrode a passing score; check rubric coverage"

    return True, f"score {score}, no blocking flags"


def build_revision_prompt(brief: dict, draft: dict, verdict: dict) -> str:
    fixes = "\n".join(
        f"- [{f['severity']}] {f['type']} — {f['location'][:120]}\n  FIX: {f['remediation']}"
        for f in verdict.get("flags", [])
    )
    return (
        "Your previous draft was rejected by QA. Revise it.\n\n"
        f"RESEARCH BRIEF:\n{json.dumps(brief, indent=2)}\n\n"
        f"YOUR PREVIOUS DRAFT:\n{json.dumps(draft, indent=2)}\n\n"
        f"QA SCORE: {verdict.get('score')} (need {PASS_SCORE})\n"
        f"REQUIRED FIXES:\n{fixes}\n\n"
        "Address every fix. Do not re-litigate the flags. Do not add facts "
        "absent from the brief. Emit a complete draft_package object."
    )


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------

def run_pipeline(company: str, domain: str | None, fixtures: dict | None, record: RunRecord) -> RunRecord:
    dry = fixtures is not None

    def agent(name: str, prompt: str, step: str, attempt: int = 1) -> dict:
        if dry:
            return json.loads(json.dumps(fixtures[step]))
        return call_agent(name, prompt, record, attempt)

    # ---- Stage 1: research -------------------------------------------------
    print(f"\n[1/3] researcher  ({MODELS['researcher'] if not dry else 'fixture'})")
    brief = agent(
        "researcher",
        f"Company: {company}\nKnown domain: {domain or 'unknown'}\n\n"
        "Produce the research_brief.",
        "research_brief",
    )

    # Sanitize before anything else touches the brief — a length check or
    # schema validation run on unsanitized text would reject correct content
    # over the search tool's own markup, not the researcher's own mistake.
    brief, sanitize_hits = sanitize_research_brief(brief)
    if sanitize_hits:
        print(f"  [INFO] stripped citation markup from {len(sanitize_hits)} field(s): {', '.join(sanitize_hits)}")

    record.brief = brief

    # Precheck first: same gate ("schema:research_brief"), a clearer message
    # when it fires. Only fall through to raw jsonschema validation if the
    # precheck passes — it's the comprehensive backstop for anything the
    # precheck doesn't cover (missing fields, wrong types, stray properties).
    ok, problems = research_brief_precheck(brief)
    if not ok:
        record.gate("schema:research_brief", False, "; ".join(problems))
        record.outcome = "rejected"
        return record

    ok, detail = validate_schema(brief, "research_brief.schema.json")
    if not record.gate("schema:research_brief", ok, detail):
        record.outcome = "rejected"
        return record

    if brief.get("insufficient_evidence"):
        record.gate("evidence:sufficient", False, f"gaps: {'; '.join(brief.get('gaps', []))}")
        record.outcome = "halted"
        print("\n  Halted before drafting. This is a success, not a failure —")
        print("  the pipeline declined to build outreach on thin evidence.")
        return record
    record.gate("evidence:sufficient", True, f"{len(brief.get('claims', []))} sourced claims")

    unsourced = [c["claim_id"] for c in brief.get("claims", []) if not c.get("source_url", "").startswith("http")]
    if not record.gate("provenance:all_claims_sourced", not unsourced,
                       f"unsourced: {unsourced}" if unsourced else "every claim carries a retrieved URL"):
        record.outcome = "rejected"
        return record

    drafter_brief = strip_low_confidence(brief)
    stripped = len(brief.get("claims", [])) - len(drafter_brief["claims"])
    if stripped:
        print(f"  [INFO] stripped {stripped} low-confidence claim(s) before drafting")

    # ---- Stage 2 + 3: draft / review loop ---------------------------------
    draft = None
    verdict = None

    for attempt in range(1, MAX_REVISIONS + 2):
        record.attempts = attempt
        print(f"\n[2/3] drafter     attempt {attempt}/{MAX_REVISIONS + 1}")

        prompt = (
            build_revision_prompt(drafter_brief, draft, verdict)
            if draft and verdict
            else f"RESEARCH BRIEF:\n{json.dumps(drafter_brief, indent=2)}\n\nProduce the draft_package."
        )
        step = "draft_package" if attempt == 1 else f"draft_package_r{attempt - 1}"
        draft = agent("drafter", prompt, step if not dry or step in fixtures else "draft_package", attempt)
        record.drafts.append(draft)

        ok, detail = validate_schema(draft, "draft_package.schema.json")
        if not record.gate("schema:draft_package", ok, detail):
            record.outcome = "rejected"
            return record

        if not draft.get("draftable", True):
            record.gate("draftable", False, draft.get("blocker", "drafter declined"))
            record.outcome = "halted"
            return record

        ok, problems = deterministic_checks(brief, draft)
        record.gate("deterministic", ok, "; ".join(problems) if problems else "word count, phrases, claim refs clean")
        if not ok:
            # Deterministic failures skip QA entirely. No reason to pay for a
            # judgment call on something arithmetic already rejected.
            verdict = {
                "score": 4,
                "flags": [
                    {"type": "constraint", "severity": "blocking", "location": p, "remediation": f"Fix: {p}"}
                    for p in problems
                ],
                "swap_test": {"redacted_body": "", "still_coherent": False},
            }
            record.verdicts.append(verdict)
            print("  [INFO] skipping QA call — deterministic gate already rejected")
            if attempt <= MAX_REVISIONS:
                continue
            record.outcome = "escalated"
            record.score = 4
            return record

        print(f"\n[3/3] qa-reviewer ({MODELS['qa-reviewer'] if not dry else 'fixture'})")
        vstep = "qa_verdict" if attempt == 1 else f"qa_verdict_r{attempt - 1}"
        verdict = agent(
            "qa-reviewer",
            f"RESEARCH BRIEF:\n{json.dumps(drafter_brief, indent=2)}\n\n"
            f"DRAFT PACKAGE:\n{json.dumps(draft, indent=2)}\n\nProduce the qa_verdict.",
            vstep if not dry or vstep in fixtures else "qa_verdict",
            attempt,
        )
        record.verdicts.append(verdict)

        ok, detail = validate_schema(verdict, "qa_verdict.schema.json")
        if not record.gate("schema:qa_verdict", ok, detail):
            record.outcome = "rejected"
            return record

        record.score = verdict.get("score")
        released, reason = release_decision(verdict)
        record.gate(f"release_gate (>= {PASS_SCORE})", released, reason)

        if released:
            record.outcome = "released"
            return record

        if attempt <= MAX_REVISIONS:
            print(f"  [INFO] bouncing back to drafter with {len(verdict.get('flags', []))} flag(s)")

    record.outcome = "escalated"
    print(f"\n  Retry budget exhausted after {MAX_REVISIONS + 1} attempts.")
    print("  Routed to the human queue rather than lowering the bar. This is")
    print("  the intended behavior: the gate does not negotiate with itself.")
    return record


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def print_audit(record: RunRecord) -> None:
    """Show what the agents actually produced, regardless of terminal state.

    A REJECTED, ESCALATED, or INTERRUPTED run is still a real result with
    real content behind it — the researcher's sourced claims, every draft
    that was tried, every verdict the reviewer gave. Hiding that behind a
    bare gate name is how a status file starts drifting from what actually
    happened. This prints every attempt, not just the last one that survived
    in memory.
    """
    brief = record.brief
    if not any([brief, record.drafts, record.verdicts]):
        return

    print("\n" + "=" * 68)
    print(f"AUDIT — {record.outcome.upper()}")
    print("=" * 68)

    if brief:
        print(f"\nRESEARCHER — {brief.get('company', '?')} ({brief.get('resolved_domain', '?')})")
        # These fields are only meaningful once evidence is sufficient — the
        # schema doesn't require them at all when insufficient_evidence is
        # true, and a fixture or a model may leave stale content in them.
        if not brief.get("insufficient_evidence"):
            for key, label in (("what_they_sell", "sells"), ("recent_news", "news"), ("marketing_task", "task")):
                f = brief.get(key)
                if f:
                    print(f"  [{f.get('claim_id', '?')}] {label}: {f.get('summary') or f.get('description', '')}")
        print(f"  claims ({len(brief.get('claims', []))} sourced):")
        for c in brief.get("claims", []):
            print(f"    [{c['claim_id']}] ({c['confidence']}) {c['statement']}")
            print(f"           source: {c['source_url']}")
        if brief.get("gaps"):
            print(f"  gaps: {'; '.join(brief['gaps'])}")

    # drafts and verdicts are parallel lists in the common case (each
    # attempt produces a draft, and either a real or synthetic verdict), but
    # a run can die mid-attempt — a drafter call that crashed produces a
    # draft with no matching verdict. Walk by index rather than zip so a
    # missing verdict prints as missing instead of misaligning with the next
    # attempt's draft.
    n = max(len(record.drafts), len(record.verdicts))
    for i in range(n):
        draft = record.drafts[i] if i < len(record.drafts) else None
        verdict = record.verdicts[i] if i < len(record.verdicts) else None

        if draft and draft.get("draftable", True) and draft.get("email"):
            e = draft["email"]
            print(f"\nDRAFTER — attempt {i + 1}")
            print(f"  Subject: {e.get('subject')}")
            print("  " + e.get("body", "").replace("\n", "\n  "))
            ab = draft.get("account_brief", {})
            if ab.get("what_i_dont_know"):
                print("  What I don't know:")
                for gap in ab["what_i_dont_know"]:
                    print(f"    · {gap}")
        elif draft and not draft.get("draftable", True):
            print(f"\nDRAFTER — attempt {i + 1} — declined: {draft.get('blocker', '(no reason given)')}")
        elif verdict is not None:
            print(f"\nDRAFTER — attempt {i + 1} — no draft on record")

        if verdict:
            print(f"QA-REVIEWER — attempt {i + 1} — score {verdict.get('score')} (threshold {PASS_SCORE})")
            for f in verdict.get("flags", []):
                print(f"  [{f.get('severity')}] {f.get('type')}: {str(f.get('location', ''))[:100]}")
                if f.get("remediation"):
                    print(f"      fix: {f['remediation'][:100]}")
            st = verdict.get("swap_test", {})
            if st:
                print(f"  swap test — still coherent after redaction: {st.get('still_coherent')}")
            if verdict.get("notes"):
                print(f"  notes: {verdict['notes']}")
        elif draft:
            print(f"QA-REVIEWER — attempt {i + 1} — not reached")

    print("\n" + "=" * 68)
    print(f"TERMINAL STATE: {record.outcome.upper()}")
    print("=" * 68)


def main() -> int:
    ap = argparse.ArgumentParser(description="AgentDesk outreach pipeline")
    ap.add_argument("--company")
    ap.add_argument("--domain")
    ap.add_argument("--dry-run", action="store_true", help="run on fixtures, no API key needed")
    ap.add_argument("--scenario", default="happy_path", help="fixture scenario for --dry-run")
    ap.add_argument("--log", default="runs.jsonl")
    args = ap.parse_args()

    fixtures = None
    if args.dry_run:
        all_fixtures = json.loads((FIXTURES / "dry_run.json").read_text(encoding="utf-8"))
        if args.scenario not in all_fixtures:
            print(f"Unknown scenario '{args.scenario}'. Available: {', '.join(all_fixtures)}")
            return 2
        fixtures = all_fixtures[args.scenario]
        company = fixtures["research_brief"]["company"]
    elif args.company:
        company = args.company
    else:
        ap.error("--company is required unless --dry-run is set")

    record = RunRecord(run_id=uuid.uuid4().hex[:8], company=company, started_at=time.time())

    print("=" * 68)
    print(f"AgentDesk run {record.run_id} — {company}")
    if args.dry_run:
        print(f"DRY RUN — scenario: {args.scenario}")
    print("=" * 68)

    # run_pipeline mutates `record` in place, so everything it completed
    # before any exception — the brief, every draft and verdict tried so
    # far — is already sitting on this object regardless of how the call
    # below ends. The `finally` block is what turns that into a guarantee:
    # it runs on a clean return, on a ContractError, and on anything else
    # (a network failure, a rate limit, the credit-exhaustion error that
    # lost this project's best run last session, Ctrl+C) — nothing is held
    # in memory until a normal exit that might never come.
    try:
        try:
            record = run_pipeline(company, args.domain, fixtures, record)
        except ContractError as e:
            record.gate("contract", False, str(e))
            record.outcome = "rejected"
        except BaseException as e:
            # Not a gate decision — the process itself failed to complete.
            # Tag what happened, keep the outcome distinct from the four
            # gate-driven terminal states, then re-raise so the failure is
            # still visible on the terminal and the exit code stays honest.
            record.gate("infrastructure", False, f"{type(e).__name__}: {e}")
            record.outcome = "interrupted"
            raise
    finally:
        print_audit(record)

        print("\n" + "-" * 68)
        print(f"OUTCOME: {record.outcome.upper()}   attempts: {record.attempts}   score: {record.score}")
        if record.tokens_in or record.tokens_out:
            print(f"tokens: {record.tokens_in} in / {record.tokens_out} out")
        print("-" * 68)

        with open(args.log, "a", encoding="utf-8") as fh:
            fh.write(record.to_json() + "\n")
        print(f"logged to {args.log}")

    return 0 if record.outcome in ("released", "halted") else 1


if __name__ == "__main__":
    sys.exit(main())
