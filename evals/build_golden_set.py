#!/usr/bin/env python3
"""Generates the golden eval set.

Each case is a named mutation applied to one known-good baseline draft, so
every case isolates exactly one failure mode. Hand-writing 14 bad emails
produces 14 subtly different emails and no clean attribution when the gate
misses one.

Each case declares `caught_by`:
  code   — a deterministic check should catch it, no model call needed
  model  — only the QA reviewer can catch it (judgment required)
  none   — intentionally clean; blocking it is a false positive

That split is the interesting number. A gate that only catches what code can
catch is a linter. A gate that needs a model for everything is expensive and
flaky. The mix is the design.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "orchestrator"))

FIX = json.loads((ROOT / "orchestrator" / "fixtures" / "dry_run.json").read_text())
BRIEF = FIX["happy_path"]["research_brief"]
BASE = FIX["happy_path"]["draft_package"]
REF = re.compile(r"\[c\d+\]")


def clone(d):
    return json.loads(json.dumps(d))


def wc(body):
    return len(REF.sub("", body).split())


CASES = []


def case(cid, label, failure_mode, caught_by, mutate=None, note=""):
    d = clone(BASE)
    if mutate:
        mutate(d)
    CASES.append({
        "id": cid,
        "label": label,                 # "good" or "bad"
        "failure_mode": failure_mode,
        "caught_by": caught_by,
        "note": note,
        "brief": BRIEF,
        "draft": d,
    })


def research_case(cid, label, failure_mode, caught_by, mutate, note=""):
    """A researcher-stage case: mutates a clone of the brief itself, not the
    draft. Tests research_brief_precheck (Gate 2's field-level precheck),
    not deterministic_checks. See evals/run_eval.py's stage branch."""
    b = clone(BRIEF)
    mutate(b)
    CASES.append({
        "id": cid,
        "label": label,
        "failure_mode": failure_mode,
        "caught_by": caught_by,
        "note": note,
        "stage": "researcher",
        "brief": b,
        "draft": clone(BASE),           # unused at this stage; kept for shape
    })


# ---------------------------------------------------------------- clean cases
case("g01", "good", None, "none", None,
     "Baseline. Must pass every gate. Blocking it is a false positive.")


def _reword(d):
    b = d["email"]["body"]
    b = b.replace("Congratulations on", "Nice work on")
    b = b.replace("Worth fifteen minutes", "Worth fifteen minutes of your time")
    d["email"]["body"] = b
    d["email"]["word_count"] = wc(b)


case("g02", "good", None, "none", _reword,
     "Baseline reworded. Guards against the gate keying on exact strings.")


def _minor_tone(d):
    b = d["email"]["body"].replace("The blank page does not.", "The blank page, less so.")
    d["email"]["body"] = b
    d["email"]["word_count"] = wc(b)


case("g03", "good", None, "none", _minor_tone,
     "Stylistic wobble only. Should score 8-9, not be blocked.")


# ------------------------------------------------- code-catchable failures
def _strip_refs(d):
    d["email"]["body"] = REF.sub("", d["email"]["body"])
    d["claim_refs"] = []


case("b01", "bad", "no_claim_refs", "code", _strip_refs,
     "Asserts facts about the company with zero source references.")


def _dangling(d):
    d["email"]["body"] = d["email"]["body"].replace("[c2]", "[c9]")
    d["claim_refs"].append({"claim_id": "c9", "used_in": "email"})


case("b02", "bad", "dangling_claim_ref", "code", _dangling,
     "Cites a claim id that does not exist in the brief. Fabricated citation.")


def _undeclared(d):
    d["claim_refs"] = [r for r in d["claim_refs"] if r["claim_id"] != "c3"]


case("b03", "bad", "undeclared_claim_ref", "code", _undeclared,
     "Uses [c3] inline but omits it from claim_refs. Breaks the audit trail.")


def _low_conf_leak(d):
    b = d["email"]["body"].replace(
        "pediatric sample volumes are a",
        "your move into veterinary diagnostics [c4] suggests pediatric volumes are a")
    d["email"]["body"] = b
    d["email"]["word_count"] = wc(b)
    d["claim_refs"].append({"claim_id": "c4", "used_in": "email"})


case("b04", "bad", "low_confidence_leak", "code", _low_conf_leak,
     "Leans on a low-confidence claim that should have been stripped upstream.")


def _banned(d):
    b = "I hope this email finds you well.\n\n" + d["email"]["body"]
    # trim to stay near target so word count is not the thing that fires
    b = b.replace("Method sections, table formatting, the boilerplate around the actual result. ", "")
    d["email"]["body"] = b
    d["email"]["word_count"] = wc(b)


case("b05", "bad", "banned_phrase", "code", _banned,
     "Banned opener. Word count kept in range so the phrase check is what fires.")


def _overlong(d):
    b = d["email"]["body"] + (
        "\n\nI also noticed your reagent subscription program has been expanding, which "
        "points to a broader shift in how the business thinks about recurring revenue "
        "across the installed base of instruments currently deployed in the field.")
    d["email"]["body"] = b
    d["email"]["word_count"] = wc(b)


case("b06", "bad", "word_count_over", "code", _overlong, "158 words against a 130 ceiling.")


def _underlong(d):
    b = ("Congratulations on the HV-220 clearance [c2]. Your application notes library is "
         "at 47 titles [c3]. Worth fifteen minutes?")
    d["email"]["body"] = b
    d["email"]["word_count"] = wc(b)


case("b07", "bad", "word_count_under", "code", _underlong, "21 words against a 110 floor.")


def _lie(d):
    d["email"]["word_count"] = 120  # actual is 122 — within tolerance, must NOT fire


case("g04", "good", None, "none", _lie,
     "Self-reported count off by 2. Inside tolerance. Must not block.")


def _big_lie(d):
    b = d["email"]["body"] + (
        "\n\nSeparately, I wanted to flag that we have worked with several other "
        "diagnostics manufacturers on exactly this problem and the pattern holds "
        "across all of them without exception in our experience so far.")
    d["email"]["body"] = b
    d["email"]["word_count"] = 122  # unchanged — the model lied about its own output


case("b08", "bad", "word_count_selfreport", "code", _big_lie,
     "Model reports 122 while emitting 156. Tests that we count, not trust.")


def _long_subject(d):
    d["email"]["subject"] = (
        "Congratulations on your recent HV-220 FDA clearance and a thought about your "
        "application notes")


case("b09", "bad", "subject_too_long", "code", _long_subject, "78 chars against a 60 ceiling.")


def _no_gaps(d):
    d["account_brief"]["what_i_dont_know"] = []


case("b10", "bad", "missing_gaps_section", "code", _no_gaps,
     "Account brief drops the mandatory 'what I don't know' section.")


# ------------------------------------------------- model-only failures
def _generic(d):
    b = ("I hope you are having a great week. I have been following Harborview [c1] and "
         "I am genuinely impressed by what your team has been building over the past "
         "couple of years.\n\n"
         "Companies like yours are increasingly turning to AI to accelerate content "
         "operations. We help organizations unlock efficiency and drive meaningful "
         "outcomes across their entire go-to-market motion. Many of our clients have "
         "seen dramatic improvements in both speed and quality after adopting our "
         "approach to this problem.\n\n"
         "I would love to share how this could apply to your specific situation and "
         "explore whether there might be a fit between our teams. Do you have time for "
         "a brief introductory call sometime in the next couple of weeks to discuss "
         "further?")
    d["email"]["body"] = b
    d["email"]["word_count"] = wc(b)
    d["claim_refs"] = [{"claim_id": "c1", "used_in": "email"}]


case("b11", "bad", "generic_template", "model", _generic,
     "Survives the swap test. Contains a banned phrase too, so code catches it "
     "for the wrong reason — the swap test is what should fire.")


def _clean_generic(d):
    b = ("Harborview builds benchtop analyzers for hospital labs [c1], and teams in that "
         "position tend to share a common constraint around technical content.\n\n"
         "Producing documentation at the pace the product ships is hard when the people "
         "who understand the science are the same people who have to write it up. That "
         "tension shows up at nearly every instrument company we talk to, and it gets "
         "worse as the catalog grows.\n\n"
         "We have built a way to compress the first draft of that work without touching "
         "the parts that need real expertise and judgment from the people on your team "
         "who actually own the result.\n\n"
         "Would fifteen minutes next week be useful to walk through what that looks "
         "like?")
    d["email"]["body"] = b
    d["email"]["word_count"] = wc(b)
    d["claim_refs"] = [{"claim_id": "c1", "used_in": "email"}]


case("b12", "bad", "generic_no_tells", "model", _clean_generic,
     "The hard one. Correct word count, valid ref, no banned phrases, reads well. "
     "But swap Harborview for any instrument company and it still sends. "
     "Code cannot catch this. If the model misses it, it ships.")


def _drift(d):
    b = d["email"]["body"].replace(
        "Your application notes library is at 47 titles [c3]",
        "Your team ships roughly twenty application notes a quarter [c3]")
    d["email"]["body"] = b
    d["email"]["word_count"] = wc(b)


case("b13", "bad", "claim_drift", "model", _drift,
     "Cites a real claim but restates it as something the source never said. "
     "A fabrication wearing a valid citation. Structurally invisible to code.")


def _unsupported(d):
    b = d["email"]["body"].replace(
        "The verification stays human, because it has to.",
        "Teams doing this cut authoring time by 60% [c3].")
    d["email"]["body"] = b
    d["email"]["word_count"] = wc(b)


case("b14", "bad", "unsupported_metric", "model", _unsupported,
     "Invented statistic attached to a real claim id. The number is not in c3.")


# ------------------------------------------- researcher-stage failures
# The gate worked; the researcher's own output didn't respect its schema.
# 12 of 13 live runs were rejected here for exactly these two shapes — added
# after fixing skills/researcher/SKILL.md and the precheck, so a regression
# can't reintroduce either without the eval catching it.

def _over_length_description(b):
    b["marketing_task"]["description"] = (
        "Sonos publishes extensive educational content: setup guides, product "
        "documentation, quick-start materials, and dealer training content across "
        "multiple channels. Maintains dedicated trainer network and online learning "
        "portal for installer partners. Creates automated educational journeys for "
        "new customers, showcasing system expansion benefits. This content production "
        "requires continuous updates, testing, and multi-format adaptation."
    )  # 434 chars, over the 400-char schema cap — the real 65de63f2 shape


research_case("rb01", "bad", "description_over_400_chars", "code", _over_length_description,
              "marketing_task.description exceeds the 400-char cap. The real live shape "
              "that rejected 65de63f2 and 0f8a2da1.")


def _malformed_claim_id(b):
    b["claims"][0]["claim_id"] = "c1b"


research_case("rb02", "bad", "malformed_claim_id", "code", _malformed_claim_id,
              "A lettered-variant claim_id (c1b) instead of a plain next integer. The "
              "real live shape that rejected 06e8aa4d and 68ec5335.")


def _invalid_evidence_type(b):
    b["marketing_task"]["evidence_type"] = "job posting"  # space, not the enum's underscore


research_case("rb03", "bad", "invalid_evidence_type", "code", _invalid_evidence_type,
              "evidence_type must be one of six exact enum strings. A near-miss like "
              "'job posting' (space instead of underscore) is still invalid.")


def _malformed_date(b):
    b["recent_news"]["published_date"] = "June 23, 2026"


research_case("rb04", "bad", "malformed_date", "code", _malformed_date,
              "published_date must be YYYY-MM-DD. Prose dates fail schema's format:date.")


research_case("rg01", "good", None, "none", lambda b: None,
              "Unmutated brief. Must pass the precheck cleanly — guards against the "
              "precheck itself being too strict.")


# ------------------------------------------- citation-markup sanitization
# Distinct bug from rb01-rb04 above: that was the model misjudging its own
# field length. This is search-tool output (citation markup) contaminating
# model output — found live in 2 of 5 fresh Sonos/Notion/Figma/Linear/Basecamp
# runs (Figma, Linear). sanitize_research_brief() strips it before any check
# runs; these cases prove the strip actually fires and that a brief which
# only *looks* bad because of markup is not wrongly rejected once it does.

_MARKUP_CLEAN_DESC = (
    "Ridgeline publishes technical release notes for every product update, pairs each "
    "one with a short video walkthrough, and maintains a public changelog that "
    "engineering references before each sprint planning session and before each "
    "customer webinar, though the writing itself is handled entirely by two rotating "
    "on-call engineers each release cycle without a dedicated technical writer."
)


def _markup_over_cap(b):
    part1, part2 = _MARKUP_CLEAN_DESC.split(", though the writing")
    part1 += ","
    part2 = "though the writing" + part2
    b["marketing_task"]["description"] = (
        '<cite index="5-6,5-7,5-8,5-9,5-10">' + part1 + "</cite> "
        '<cite index="3-1,6-1,9-2,9-3,9-4">' + part2 + "</cite>"
    )


research_case("rs01", "good", None, "none", _markup_over_cap,
              "Citation markup pushes marketing_task.description to 467 chars — over the "
              "400-char cap — but the clean text underneath is 384 chars, comfortably "
              "under. Must be stripped and pass, not rejected. Real shape: this is what "
              "the Figma and Linear live rejections looked like.")


def _markup_in_claim_statement(b):
    b["claims"][0]["statement"] = '<cite index="1-1">' + b["claims"][0]["statement"] + "</cite>"


research_case("rs02", "good", None, "none", _markup_in_claim_statement,
              "Citation markup in claims[0].statement, a field with no length cap — "
              "would never be rejected either way, but must still be stripped. Proves "
              "sanitization covers every string field, not just the capped ones.")


def _markup_under_cap(b):
    clean = ("Ridgeline announced a new distribution partnership covering the western "
             "region in July 2026, expanding retail availability for its flagship "
             "product line.")
    b["recent_news"]["summary"] = '<cite index="2-1,2-2">' + clean + "</cite>"


research_case("rs03", "good", None, "none", _markup_under_cap,
              "Citation markup present (182 chars) but recent_news.summary stays well "
              "under its 300-char cap even without stripping. Must still be stripped — "
              "the point isn't that this one would have failed, it's that sanitization "
              "isn't conditional on whether the field happens to be near its limit.")


# ------------------------------------------- word-budget/char-cap consistency
# Measured 2026-09-01 against the 7 real research_brief summaries this
# project has: what_they_sell.summary's old 40-word budget produces 300+
# characters at even the *mean* observed density (7.78 chars/word) — no
# markup involved, just realistic technical prose. Budget tightened to 27
# words (recent_news.summary to 33, same margin standard, though its old
# budget wasn't independently broken). rb05 proves the old budget was really
# broken; rg02 proves the new one has real room even close to its own limit.

def _dense_prose_over_cap(b):
    b["what_they_sell"]["summary"] = (
        "Harborview Instruments designs, manufactures, and services benchtop clinical "
        "chemistry analyzers for mid-size hospital laboratories and independent reference "
        "labs, monetizing primarily through recurring consumable reagent cartridge "
        "subscriptions rather than one-time instrument hardware margin, with service "
        "contracts sold separately to institutional buyers."
    )  # 40 words (the old budget) at realistic density -> 358 chars, over the 300 cap


research_case("rb05", "bad", "summary_word_budget_inconsistent_with_cap", "code",
              _dense_prose_over_cap,
              "No markup involved — real technical prose at the old 40-word budget, "
              "measured density. 358 characters against a 300-char cap. Proves the old "
              "word budget was mathematically inconsistent with the schema cap, "
              "independent of the citation-markup issue.")


def _tightened_budgets_still_fit(b):
    b["what_they_sell"]["summary"] = (
        "Harborview Instruments designs and manufactures benchtop clinical chemistry "
        "analyzers for mid-size hospital labs and reference labs, monetized through "
        "recurring reagent cartridge subscriptions rather than instrument margin."
    )  # 26 words, close to the new 27-word budget -> 223 chars
    b["recent_news"]["summary"] = (
        "Harborview received FDA 510(k) clearance in July 2026 for the HV-220 analyzer, "
        "its first platform cleared for pediatric sample volumes across the full assay "
        "menu, expanding its addressable base of hospital labs."
    )  # 32 words, close to the new 33-word budget -> 211 chars


research_case("rg02", "good", None, "none", _tightened_budgets_still_fit,
              "Both summaries written close to their new, tighter word budgets (26/27 "
              "and 32/33 words) at realistic density. Must pass with real margin, not "
              "just barely — guards against the tightened budget being too tight to "
              "actually use.")


if __name__ == "__main__":
    # Self-check the three sanitization cases directly against the real
    # function, not just via the eval harness — concrete proof the strip
    # actually fires, independent of whether the precheck would have caught
    # the unstripped version anyway.
    from run import sanitize_research_brief, research_brief_precheck  # noqa: E402

    rs01 = next(c for c in CASES if c["id"] == "rs01")["brief"]
    marked_desc = rs01["marketing_task"]["description"]
    assert len(marked_desc) > 400, f"rs01 marked description is only {len(marked_desc)} chars, needs to exceed 400"
    clean01, hits01 = sanitize_research_brief(rs01)
    assert "marketing_task.description" in hits01, "rs01: sanitize didn't fire on marketing_task.description"
    assert "<cite" not in clean01["marketing_task"]["description"] and "cite index" not in clean01["marketing_task"]["description"], \
        "rs01: markup survived sanitization"
    assert len(clean01["marketing_task"]["description"]) <= 400, \
        f"rs01: still over cap after stripping ({len(clean01['marketing_task']['description'])} chars) — case doesn't prove what it claims"
    ok01, problems01 = research_brief_precheck(clean01)
    assert ok01, f"rs01: precheck still fails after sanitize: {problems01}"

    rs02 = next(c for c in CASES if c["id"] == "rs02")["brief"]
    clean02, hits02 = sanitize_research_brief(rs02)
    assert "claims[0].statement" in hits02, "rs02: sanitize didn't fire on claims[0].statement"
    assert "cite index" not in clean02["claims"][0]["statement"], "rs02: markup survived sanitization"

    rs03 = next(c for c in CASES if c["id"] == "rs03")["brief"]
    marked_news = rs03["recent_news"]["summary"]
    assert len(marked_news) <= 300, f"rs03 is supposed to stay under cap even with markup, but it's {len(marked_news)} chars"
    clean03, hits03 = sanitize_research_brief(rs03)
    assert "recent_news.summary" in hits03, "rs03: sanitize didn't fire even though markup is present"
    assert "cite index" not in clean03["recent_news"]["summary"], "rs03: markup survived sanitization"

    # Word-budget/char-cap consistency cases: verify the numbers, not just
    # the pass/fail outcome — a case that "happens" to pass or fail proves
    # nothing about *why*.
    rb05 = next(c for c in CASES if c["id"] == "rb05")["brief"]
    rb05_summary = rb05["what_they_sell"]["summary"]
    rb05_words = len(rb05_summary.split())
    assert rb05_words <= 41, f"rb05 is supposed to represent the old ~40-word budget, but it's {rb05_words} words"
    assert len(rb05_summary) > 300, f"rb05 is supposed to breach the 300-char cap on realistic prose alone, but it's only {len(rb05_summary)} chars"
    ok_rb05, problems_rb05 = research_brief_precheck(rb05)
    assert not ok_rb05, "rb05: precheck should reject this (over cap on realistic prose, no markup)"

    rg02 = next(c for c in CASES if c["id"] == "rg02")["brief"]
    wts_words = len(rg02["what_they_sell"]["summary"].split())
    news_words = len(rg02["recent_news"]["summary"].split())
    assert wts_words <= 27, f"rg02 what_they_sell.summary is supposed to fit the new 27-word budget, but it's {wts_words} words"
    assert news_words <= 33, f"rg02 recent_news.summary is supposed to fit the new 33-word budget, but it's {news_words} words"
    ok_rg02, problems_rg02 = research_brief_precheck(rg02)
    assert ok_rg02, f"rg02: precheck should pass at the new budgets, but got: {problems_rg02}"

    out = Path(__file__).parent / "golden_set.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for c in CASES:
            fh.write(json.dumps(c) + "\n")

    good = sum(1 for c in CASES if c["label"] == "good")
    by_code = sum(1 for c in CASES if c["caught_by"] == "code")
    by_model = sum(1 for c in CASES if c["caught_by"] == "model")
    print(f"wrote {out}")
    print(f"  {len(CASES)} cases: {good} clean, {by_code} code-catchable, {by_model} model-only")
    print("  sanitization self-checks passed: rs01 (over-cap-via-markup), "
          "rs02 (claim statement), rs03 (under-cap-with-markup)")
