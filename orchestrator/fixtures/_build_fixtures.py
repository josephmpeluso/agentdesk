#!/usr/bin/env python3
"""Builds dry_run.json and asserts every fixture matches its declared word count.

Kept in the repo because a fixture that silently drifts out of spec turns a
green test suite into a lie.
"""
import json
import re
from pathlib import Path

REF = re.compile(r"\[c\d+\]")


def wc(body: str) -> int:
    return len(REF.sub("", body).split())


def claim(cid, statement, url, conf="high", date="2026-08-14", title=""):
    return {
        "claim_id": cid, "statement": statement, "source_url": url,
        "source_title": title, "confidence": conf, "retrieved_at": date,
    }


META = {"agent": None, "model": "fixture", "attempt": 1}


def meta(agent, attempt=1):
    return {"agent": agent, "model": "fixture", "attempt": attempt}


# ---------------------------------------------------------------- base brief
BASE_BRIEF = {
    "company": "Harborview Instruments",
    "resolved_domain": "harborviewinstruments.com",
    "insufficient_evidence": False,
    "what_they_sell": {
        "summary": "Benchtop clinical chemistry analyzers sold to mid-size hospital and reference labs, plus consumable reagent cartridges on subscription.",
        "claim_id": "c1",
    },
    "recent_news": {
        "summary": "Received FDA 510(k) clearance for the HV-220 analyzer, their first platform cleared for pediatric sample volumes.",
        "published_date": "2026-07-22",
        "claim_id": "c2",
    },
    "marketing_task": {
        "description": "Writing application notes: technical PDFs showing the analyzer running a specific assay. Their library lists 47, each authored by an application scientist.",
        "why_ai_helps": "First-draft generation from raw run data and protocol templates, leaving the scientist to verify rather than compose. They have two open application scientist reqs, so the work is currently under-staffed.",
        "evidence_type": "content_cadence",
        "claim_id": "c3",
    },
    "claims": [
        claim("c1", "Sells benchtop clinical chemistry analyzers and subscription reagent cartridges to hospital and reference labs.",
              "https://harborviewinstruments.com/products", title="Products — Harborview Instruments"),
        claim("c2", "FDA 510(k) clearance announced 22 July 2026 for the HV-220, cleared for pediatric sample volumes.",
              "https://harborviewinstruments.com/news/hv-220-510k", title="HV-220 receives 510(k) clearance"),
        claim("c3", "Application notes library contains 47 titles; two open application scientist positions listed.",
              "https://harborviewinstruments.com/resources/application-notes", title="Application Notes Library"),
        claim("c4", "Possibly expanding into veterinary diagnostics based on a conference abstract listing.",
              "https://example-conference.org/abstracts/2026", conf="low", title="Conference abstract index"),
    ],
    "gaps": [
        "No public pricing; unknown whether reagent subscription is per-instrument or per-site.",
        "Could not identify who owns marketing content — no CMO or content lead listed.",
        "Unknown how long an application note currently takes end to end.",
    ],
    "run_meta": meta("researcher"),
}

# ------------------------------------------------------------- happy path
GOOD_BODY = (
    "Congratulations on the HV-220 clearance [c2] — pediatric sample volumes are a "
    "genuinely hard validation problem and most benchtop platforms never bother.\n\n"
    "Your application notes library is at 47 titles [c3], and you have two application "
    "scientist seats open. Which means the people who write those notes are the same "
    "people you are short of.\n\n"
    "The part that compresses well is the first draft: pulling run data and protocol "
    "structure into a complete note your scientist edits instead of composes. Method "
    "sections, table formatting, the boilerplate around the actual result. The "
    "verification stays human, because it has to. The blank page does not.\n\n"
    "Worth fifteen minutes to show you what that looks like running on one of the notes "
    "you have already published?"
)

GOOD_DRAFT = {
    "draftable": True,
    "email": {
        "subject": "HV-220 clearance + your application note backlog",
        "body": GOOD_BODY,
        "word_count": wc(GOOD_BODY),
    },
    "account_brief": {
        "who_they_are": "Harborview builds benchtop clinical chemistry analyzers for mid-size hospital and reference labs, monetized through subscription reagent cartridges rather than instrument margin.",
        "why_now": "The HV-220 510(k) clearance in July opened pediatric volumes to them, which is a new segment and a new set of labs to educate. New segment means new application notes, and their note pipeline is already the constraint.",
        "the_wedge": "The application notes library — 47 titles, each written by an application scientist, with two of those seats currently unfilled. The bottleneck is authoring capacity, not subject-matter knowledge, which is exactly the shape of problem that first-draft generation fits. Nobody is asking the model to be right about chemistry; they are asking it to produce a structured draft a scientist can correct in twenty minutes instead of write in two days.",
        "what_i_dont_know": [
            "Who owns marketing content. No CMO or content lead is listed publicly, so the buyer is unidentified.",
            "How long an application note currently takes end to end. The whole pitch rests on that number and I do not have it.",
            "Whether notes are a marketing artifact or a regulatory one. If regulatory review gates them, the bottleneck is not authoring and the pitch is wrong.",
            "Reagent subscription structure, which determines whether new segments are expensive or cheap for them to enter.",
        ],
        "opening_question": "When a new assay ships, who actually writes the application note, and what does that person's queue look like right now?",
        "word_count": 262,
    },
    "claim_refs": [
        {"claim_id": "c2", "used_in": "both"},
        {"claim_id": "c3", "used_in": "both"},
        {"claim_id": "c1", "used_in": "account_brief"},
    ],
    "run_meta": meta("drafter"),
}

GOOD_VERDICT = {
    "score": 9,
    "pass": True,
    "flags": [
        {
            "type": "tone", "severity": "minor",
            "location": "The blank page does not.",
            "remediation": "Slightly writerly for a cold email. Acceptable — it lands and it is short.",
        }
    ],
    "swap_test": {
        "redacted_body": (
            "Congratulations on the [PRODUCT] clearance — [SEGMENT] are a genuinely hard "
            "validation problem. Your [CONTENT] library is at [N] titles and you have two "
            "[ROLE] seats open... "
        ),
        "still_coherent": False,
    },
    "notes": "Every assertion traces cleanly. Swap test collapses — the specifics are load-bearing, which is the point. The 'what I don't know' section correctly flags that the regulatory-vs-marketing question could invalidate the whole wedge.",
    "run_meta": meta("qa-reviewer"),
}

# ------------------------------------------------------------ generic email
GENERIC_BODY = (
    "I hope you are having a great week. I have been following Harborview Instruments [c1] "
    "and I am impressed by what your team is building in the diagnostics space.\n\n"
    "Companies like yours are increasingly turning to AI to accelerate their content "
    "operations and marketing workflows. We help organizations unlock efficiency and "
    "drive meaningful outcomes across their go-to-market motion.\n\n"
    "Many of our clients have seen dramatic improvements in speed and quality after "
    "adopting our approach. I would love to share how this could apply to your "
    "situation and explore whether there is a fit here.\n\n"
    "Do you have time for a brief call sometime in the next couple of weeks to discuss?"
)

GENERIC_DRAFT = {
    "draftable": True,
    "email": {
        "subject": "Quick idea for Harborview Instruments",
        "body": GENERIC_BODY,
        "word_count": wc(GENERIC_BODY),
    },
    "account_brief": {
        "who_they_are": "A diagnostics company in the medical device space.",
        "why_now": "They are growing and investing in their product line.",
        "the_wedge": "Content and marketing operations could be more efficient with AI assistance. Most companies in this space have the same challenge and there is a clear opportunity to add value through automation of routine marketing tasks and content production workflows.",
        "what_i_dont_know": ["Their budget."],
        "opening_question": "What are your biggest marketing challenges right now?",
        "word_count": 201,
    },
    "claim_refs": [{"claim_id": "c1", "used_in": "email"}],
    "run_meta": meta("drafter"),
}

GENERIC_VERDICT = {
    "score": 3,
    "pass": False,
    "flags": [
        {
            "type": "generic", "severity": "blocking",
            "location": "Companies like yours are increasingly turning to AI to accelerate their content operations",
            "remediation": "Replace with the specific observed task: the 47-title application notes library [c3] and the two unfilled application scientist reqs. Name the work, not the category.",
        },
        {
            "type": "unsupported_claim", "severity": "blocking",
            "location": "Many of our clients have seen dramatic improvements in speed and quality",
            "remediation": "No claim in the brief supports this. Remove it. Do not substitute a different unsourced proof point.",
        },
        {
            "type": "constraint", "severity": "major",
            "location": "I hope you are having a great week.",
            "remediation": "Banned opener. The first sentence must carry information.",
        },
        {
            "type": "tone", "severity": "major",
            "location": "explore whether there is a fit here",
            "remediation": "Vague ask. Replace with one specific, low-commitment request.",
        },
    ],
    "swap_test": {
        "redacted_body": (
            "I hope you are having a great week. I have been following [COMPANY] and I am "
            "impressed by what your team is building in the [INDUSTRY] space. Companies like "
            "yours are increasingly turning to AI to accelerate their content operations..."
        ),
        "still_coherent": True,
    },
    "notes": "This is a template with one proper noun dropped in. The swap test is fully intact — nothing in this email required knowing anything about Harborview. Blocking regardless of score.",
    "run_meta": meta("qa-reviewer"),
}

# revision that fixes it
FIXED_BODY = GOOD_BODY
FIXED_DRAFT = json.loads(json.dumps(GOOD_DRAFT))
FIXED_DRAFT["run_meta"] = meta("drafter", 2)
FIXED_DRAFT["run_meta"]["revision_of"] = "attempt-1"
FIXED_VERDICT = json.loads(json.dumps(GOOD_VERDICT))
FIXED_VERDICT["score"] = 8
FIXED_VERDICT["run_meta"] = meta("qa-reviewer", 2)
FIXED_VERDICT["notes"] = "Revision resolved both blocking flags. Score 8 — clears the bar, does not clear it comfortably. Released."

# ------------------------------------------------------------ thin evidence
THIN_BRIEF = json.loads(json.dumps(BASE_BRIEF))
THIN_BRIEF["company"] = "Ridgeline Components"
THIN_BRIEF["resolved_domain"] = "unresolved"
THIN_BRIEF["insufficient_evidence"] = True
THIN_BRIEF.pop("recent_news")
THIN_BRIEF.pop("marketing_task")
THIN_BRIEF["claims"] = [
    claim("c1", "Company website is a single page with a contact form; no product detail published.",
          "https://ridgelinecomponents.example/", conf="medium", title="Ridgeline Components")
]
THIN_BRIEF["gaps"] = [
    "Two distinct entities share this name — a Colorado machine shop and an Ontario electronics distributor. Could not determine which is intended.",
    "No news in the last 180 days from either entity.",
    "No observable marketing surface: no blog, no resources section, no open roles.",
]

# ------------------------------------------------------- wordcount violation
LONG_BODY = GOOD_BODY + (
    "\n\nI also noticed you have been expanding your reagent subscription program, which "
    "suggests a broader shift in how you think about recurring revenue and customer "
    "retention across the installed base of instruments in the field today."
)
LONG_DRAFT = json.loads(json.dumps(GOOD_DRAFT))
LONG_DRAFT["email"]["body"] = LONG_BODY
LONG_DRAFT["email"]["word_count"] = 121  # model under-reports; code catches both problems

# --------------------------------------------------------------- escalation
# Mirrors the real live run (785069cb, see STATE.md): every draft is
# deterministically clean (schema, word count, phrases, claim refs all pass),
# so QA is called every time — and every time, QA catches the same claim_drift
# (c2's clearance quietly restated as broader than the source says). The
# drafter never fixes the underlying drift across two revisions, the retry
# budget (MAX_REVISIONS=2) runs out, and the pipeline escalates. This is the
# only fixture that exercises draft_package_r2 / qa_verdict_r2 — every other
# scenario resolves (or halts, or rejects) before the budget is exhausted, so
# until this one, ESCALATED had zero test coverage.

ESC_BODY_1 = GOOD_BODY.replace(
    "pediatric sample volumes are a genuinely hard validation problem and most "
    "benchtop platforms never bother.",
    "that clearance makes them the only benchtop platform on the market cleared "
    "for pediatric use — most competitors never attempt it.",
)
ESC_DRAFT_1 = json.loads(json.dumps(GOOD_DRAFT))
ESC_DRAFT_1["email"]["body"] = ESC_BODY_1
ESC_DRAFT_1["run_meta"] = meta("drafter", 1)

ESC_VERDICT_1 = {
    "score": 5,
    "pass": False,
    "flags": [
        {
            "type": "claim_drift", "severity": "blocking",
            "location": "the only benchtop platform on the market cleared for pediatric use",
            "remediation": "c2 says the HV-220 was cleared for pediatric sample volumes. It does not say Harborview is the only company with pediatric clearance — that's a stronger, unsourced claim. Restate to what the source actually says.",
        }
    ],
    "swap_test": {"redacted_body": "", "still_coherent": False},
    "notes": "Everything else traces cleanly. One claim was quietly upgraded from 'cleared for' to 'the only one cleared for,' which the source does not support.",
    "run_meta": meta("qa-reviewer", 1),
}

# revision 1 — drafter softens the wording but the drift survives in a new form
ESC_BODY_2 = GOOD_BODY.replace(
    "pediatric sample volumes are a genuinely hard validation problem and most "
    "benchtop platforms never bother.",
    "that clearance makes them the first to market with pediatric clearance in "
    "this category.",
)
ESC_DRAFT_2 = json.loads(json.dumps(GOOD_DRAFT))
ESC_DRAFT_2["email"]["body"] = ESC_BODY_2
ESC_DRAFT_2["run_meta"] = meta("drafter", 2)
ESC_DRAFT_2["run_meta"]["revision_of"] = "attempt-1"

ESC_VERDICT_2 = {
    "score": 5,
    "pass": False,
    "flags": [
        {
            "type": "claim_drift", "severity": "blocking",
            "location": "the first to market with pediatric clearance",
            "remediation": "Same drift, reworded. c2 supports 'cleared for pediatric sample volumes,' not a first-to-market claim. Nothing in the brief establishes market ordering.",
        }
    ],
    "swap_test": {"redacted_body": "", "still_coherent": False},
    "notes": "Second consecutive attempt, second instance of the same drift under new phrasing. The revision changed the sentence, not the problem.",
    "run_meta": meta("qa-reviewer", 2),
}

# revision 2 — budget's last attempt; drift persists a third time
ESC_BODY_3 = GOOD_BODY.replace(
    "pediatric sample volumes are a genuinely hard validation problem and most "
    "benchtop platforms never bother.",
    "that clearance makes them the clear pediatric-clearance leader in the "
    "category.",
)
ESC_DRAFT_3 = json.loads(json.dumps(GOOD_DRAFT))
ESC_DRAFT_3["email"]["body"] = ESC_BODY_3
ESC_DRAFT_3["run_meta"] = meta("drafter", 3)
ESC_DRAFT_3["run_meta"]["revision_of"] = "attempt-2"

ESC_VERDICT_3 = {
    "score": 4,
    "pass": False,
    "flags": [
        {
            "type": "claim_drift", "severity": "blocking",
            "location": "the clear pediatric-clearance leader in the category",
            "remediation": "Third instance of the same unsupported superlative. c2 is a single clearance announcement, not a category-leadership claim. Retry budget is spent; this should escalate rather than attempt a fourth rewrite.",
        }
    ],
    "swap_test": {"redacted_body": "", "still_coherent": False},
    "notes": "Retry budget exhausted with the same drift in a third form. Escalating to a human is correct here — a fourth revision would optimize the wording against this reviewer rather than fix the claim.",
    "run_meta": meta("qa-reviewer", 3),
}

# ---------------------------------------------------------------- assemble
FIXTURES = {
    "happy_path": {
        "research_brief": BASE_BRIEF,
        "draft_package": GOOD_DRAFT,
        "qa_verdict": GOOD_VERDICT,
    },
    "generic_email": {
        "research_brief": BASE_BRIEF,
        "draft_package": GENERIC_DRAFT,
        "qa_verdict": GENERIC_VERDICT,
        "draft_package_r1": FIXED_DRAFT,
        "qa_verdict_r1": FIXED_VERDICT,
    },
    "thin_evidence": {
        "research_brief": THIN_BRIEF,
    },
    "wordcount_violation": {
        "research_brief": BASE_BRIEF,
        "draft_package": LONG_DRAFT,
        "qa_verdict": GOOD_VERDICT,
        "draft_package_r1": GOOD_DRAFT,
        "qa_verdict_r1": FIXED_VERDICT,
    },
    "escalation": {
        "research_brief": BASE_BRIEF,
        "draft_package": ESC_DRAFT_1,
        "qa_verdict": ESC_VERDICT_1,
        "draft_package_r1": ESC_DRAFT_2,
        "qa_verdict_r1": ESC_VERDICT_2,
        "draft_package_r2": ESC_DRAFT_3,
        "qa_verdict_r2": ESC_VERDICT_3,
    },
}

if __name__ == "__main__":
    # Self-check: declared word counts must match reality where they should.
    assert 110 <= wc(GOOD_BODY) <= 130, f"good body is {wc(GOOD_BODY)} words"
    assert 110 <= wc(GENERIC_BODY) <= 130, f"generic body is {wc(GENERIC_BODY)} words"
    assert wc(LONG_BODY) > 130, f"long body is only {wc(LONG_BODY)} words"
    GOOD_DRAFT["email"]["word_count"] = wc(GOOD_BODY)
    GENERIC_DRAFT["email"]["word_count"] = wc(GENERIC_BODY)
    FIXED_DRAFT["email"]["word_count"] = wc(GOOD_BODY)

    for name, body, draft in (
        ("escalation attempt 1", ESC_BODY_1, ESC_DRAFT_1),
        ("escalation attempt 2", ESC_BODY_2, ESC_DRAFT_2),
        ("escalation attempt 3", ESC_BODY_3, ESC_DRAFT_3),
    ):
        assert 110 <= wc(body) <= 130, f"{name} body is {wc(body)} words"
        draft["email"]["word_count"] = wc(body)

    out = Path(__file__).parent / "dry_run.json"
    out.write_text(json.dumps(FIXTURES, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(f"  happy_path body:    {wc(GOOD_BODY)} words")
    print(f"  generic_email body: {wc(GENERIC_BODY)} words")
    print(f"  long body:          {wc(LONG_BODY)} words (should exceed 130)")
