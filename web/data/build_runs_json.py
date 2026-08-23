"""
Builds web/data/runs.json from runs.jsonl (the authoritative gate/outcome log)
plus two researcher payloads hand-recovered from saved terminal transcripts.

Why this exists as a script and not a hand-edited JSON file: runs.jsonl is the
source of truth for gates/scores/tokens/outcome. Transcribing it by hand risks
a typo that makes the dashboard say something the log doesn't. Run this, don't
edit web/data/runs.json directly.

What's NOT here, and why: draft text and QA flag detail were never printed to
any surviving log for ANY live run — the audit-detail printer (print_audit in
orchestrator/run.py) was added mid-session, after most live runs had already
happened. Two runs (65de63f2, 0f8a2da1) got researcher-panel detail because
they ran after that printer existed but were rejected before reaching the
drafter. The escalated run (785069cb) — the best run this system ever
produced — ran before the printer existed, so only its gate sequence survives.
That gap is real. The dashboard shows it as "not captured," not as empty.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RUNS_JSONL = ROOT / "runs.jsonl"
OUT_JSON = Path(__file__).resolve().parent / "runs.json"
# index.html loads this one, via <script src>, not fetch() — fetch() of a
# local file is blocked by CORS in Chrome/Edge under file://, which would
# break "open by double-clicking index.html." A script tag isn't subject to
# that restriction, so the data ships as a JS literal instead of raw JSON.
OUT_JS = Path(__file__).resolve().parent / "runs.js"

MODELS = {
    "researcher": "claude-haiku-4-5-20251001",
    "drafter": "claude-sonnet-5",
    "qa-reviewer": "claude-opus-5",
}

# Hand-recovered verbatim from C:\Users\josep\AppData\Local\Temp\sonos_final.log
# and sonos_final2.log — the two live runs whose researcher stage was captured
# by the audit-detail printer before the pipeline was rejected at the schema
# gate (the marketing_task.description field ran over its 400-char limit in
# both cases — that's *why* each run stopped here, not a coincidence).
RESEARCHER_65DE63F2 = {
    "company": "Sonos",
    "resolved_domain": "sonos.com",
    "what_they_sell": {
        "claim_id": "c1",
        "summary": "Sonos designs and manufactures wireless audio systems including speakers, soundbars, subwoofers, headphones, and amplifiers. Products sold direct-to-consumer and through retail partners. Targets both home listeners and professional installers seeking premium, connected audio for multi-room listening.",
    },
    "recent_news": {
        "claim_id": "c2",
        "summary": "Announced partnership with Škoda as exclusive audio partner for the Škoda Peaq flagship electric vehicle, architecting the in-cabin listening experience from the ground up.",
    },
    "marketing_task": {
        "claim_id": "c3",
        "description": "Sonos publishes extensive educational content: setup guides, product documentation, quick-start materials, and dealer training content across multiple channels. Maintains dedicated trainer network and online learning portal for installer partners. Creates automated educational journeys for new customers, showcasing system expansion benefits. This content production requires continuous updates, testing, and multi-format adaptation.",
        "rejected_reason": "This field is 437 characters; the schema caps it at 400. This is the exact violation that rejected the run at the schema gate.",
    },
    "claims": [
        {"claim_id": "c1", "confidence": "high", "statement": "Sonos manufactures wireless speakers, soundbars, subwoofers, headphones, and amplifiers for home and professional audio applications.", "source_url": "https://www.bloomberg.com/profile/company/SONO:US"},
        {"claim_id": "c2", "confidence": "high", "statement": "On June 23, 2026, Sonos announced partnership with Škoda to architect in-cabin listening experience for Škoda Peaq electric vehicle.", "source_url": "https://newsroom.sonos.com/267365-sonos-partners-with-skoda-to-bring-premium-sound-to-the-all-new-peaq/"},
        {"claim_id": "c3", "confidence": "high", "statement": "Sonos provides setup guides, product documentation, quick-start materials, and maintains dedicated trainer network with online learning portal for dealer partners.", "source_url": "https://www.sonos.com/en-us/guides/setup"},
        {"claim_id": "c4", "confidence": "medium", "statement": "Sonos implements automated educational journeys for new customers showing benefits of expanding speakers and subwoofers to support average ~3.0 speakers per household.", "source_url": "https://businessmodelcanvastemplate.com/blogs/marketing-strategy/sonos-marketing-strategy"},
        {"claim_id": "c5", "confidence": "medium", "statement": "Sonos maintains network of certified installers with dedicated trainers across regions and online learning portal providing continuous product and integration training.", "source_url": "https://www.residentialsystems.com/features/going-forward/the-sonos-solution"},
        {"claim_id": "c6", "confidence": "medium", "statement": "Sonos offers content marketing including website articles, guides, and playlists highlighting ecosystem benefits and music service integration.", "source_url": "https://swottemplate.com/blogs/marketing-strategy/sonos-marketing-strategy"},
    ],
}

RESEARCHER_0F8A2DA1 = {
    "company": "Sonos",
    "resolved_domain": "sonos.com",
    "what_they_sell": {
        "claim_id": "c1",
        "summary": "Sonos designs, develops, and sells wireless audio systems for consumers and professionals, including connected speakers, soundbars, headphones, and portable speakers sold via retail, e-commerce, and direct channels in 60+ countries.",
    },
    "recent_news": {
        "claim_id": "c2",
        "summary": "Sonos announced partnership with Škoda on June 23, 2026, as audio partner for flagship Peaq electric vehicle, architecting in-cabin sound system from ground up. This marks second factory-fitted automotive audio deal.",
    },
    "marketing_task": {
        "claim_id": "c5",
        "description": "Sonos pursues targeted influencer marketing and brand partnerships requiring extensive content coordination across campaigns. Sonos hosts luxury brand experiences (e.g., 2026 Dolomites trip with influencers) and manages multiple content franchises across social platforms, requiring centralized asset management, campaign briefs, and media coordination spanning lifestyle, travel, and music verticals.",
        "rejected_reason": "This field runs past the schema's 400-character cap on marketing_task.description — the same failure mode as run 65de63f2, on a completely different angle into the same company. Two independent live runs, same specific field, same specific limit.",
    },
    "claims": [
        {"claim_id": "c1", "confidence": "high", "statement": "Sonos designs, develops, manufactures and sells audio products and services including wireless speakers, portable speakers, home theater systems, headphones sold through third-party retailers, e-commerce, custom installers, and sonos.com.", "source_url": "https://www.globaldata.com/company-profile/sonos-inc/"},
        {"claim_id": "c2", "confidence": "high", "statement": "On June 23, 2026, Sonos announced partnership with Škoda as audio partner for flagship Peaq electric vehicle, with Sonos architecting in-cabin listening experience from ground up.", "source_url": "https://newsroom.sonos.com/267365-sonos-partners-with-skoda-to-bring-premium-sound-to-the-all-new-peaq/"},
        {"claim_id": "c3", "confidence": "medium", "statement": "Sonos pursues data-driven marketing with targeted messaging and achieved 20% increase in marketing channel ROI through better targeting.", "source_url": "https://matrixbcg.com/blogs/marketing-strategy/sonos"},
        {"claim_id": "c4", "confidence": "high", "statement": "Sonos curated luxury influencer marketing events including 2026 Dolomites brand trip with content creators, earning 53.7M impressions across platforms.", "source_url": "https://www.praytellagency.com/case-studies/sonos"},
        {"claim_id": "c5", "confidence": "high", "statement": "Sonos manages multiple social content franchises like 'Sonos in the House,' 'Where does Move take you,' and 'Home Life Still Life' series developed over multi-year periods with creative professionals and artists.", "source_url": "https://imprintprojects.com/case-studies/social-strategy-and-content/"},
        {"claim_id": "c6", "confidence": "high", "statement": "Sonos maintains comprehensive technical documentation platforms for developers including Sonos Music API (SMAPI) and support guides, suggesting ongoing content production and documentation maintenance.", "source_url": "https://docs.sonos.com/docs/how-sonos-works"},
    ],
}

RESEARCHER_BY_RUN_ID = {
    "65de63f2": RESEARCHER_65DE63F2,
    "0f8a2da1": RESEARCHER_0F8A2DA1,
}

# Every non-gate field the dashboard would want but that no surviving log
# actually contains, per run. Nothing here is inferred or reconstructed.
NOT_CAPTURED_BY_RUN_ID = {
    "785069cb": [
        "Researcher's individual claims and source URLs — the gates confirm 6 sourced claims existed and passed provenance, but the claim text and URLs were never printed to any surviving log.",
        "Full draft email text and [cN] claim references for all 3 attempts — the gates confirm each attempt's schema/deterministic outcome, but the actual email bodies were never printed.",
        "QA flag location/remediation detail for both QA calls — the gates confirm the flag type (claim_drift) and blocking severity, but the specific sentence flagged and the reviewer's suggested fix were never printed.",
    ],
}
NOT_CAPTURED_REASON_785069CB = (
    "This run happened before print_audit() existed in orchestrator/run.py — it was added "
    "later the same session specifically because this run's rich detail was missing. Only "
    "print_artifact() existed at the time, and it only fired for outcome == 'released', so a "
    "run that escalated printed nothing beyond the terse pass/fail gate lines below. That's a "
    "real observability gap in how this run was captured, not a gap in what the pipeline did."
)

REJECTED_AT_RESEARCHER_NOTE = (
    "This run was rejected at the researcher's schema gate before print_audit() existed (or, "
    "for a schema failure, before the brief could be validated at all). The model's full reply "
    "was never printed — only the schema validator's truncated error detail survived, which is "
    "what's shown here."
)


def main() -> None:
    rows = [json.loads(l) for l in RUNS_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    live_rows = [r for r in rows if r.get("tokens_in") or r.get("tokens_out")]

    runs = []
    for r in live_rows:
        run_id = r["run_id"]
        researcher = RESEARCHER_BY_RUN_ID.get(run_id)

        if run_id in NOT_CAPTURED_BY_RUN_ID:
            not_captured = NOT_CAPTURED_BY_RUN_ID[run_id]
            not_captured_reason = NOT_CAPTURED_REASON_785069CB
        elif researcher is not None:
            not_captured = ["Draft and QA verdict — the pipeline never reached those stages; the schema gate stopped it at the researcher, correctly."]
            not_captured_reason = None
        else:
            not_captured = ["Full researcher output — only the schema validator's error detail survived."]
            not_captured_reason = REJECTED_AT_RESEARCHER_NOTE

        runs.append({
            "run_id": run_id,
            "company": r["company"],
            "outcome": r["outcome"],
            "score": r.get("score"),
            "attempts": r.get("attempts", 0),
            "tokens_in": r.get("tokens_in", 0),
            "tokens_out": r.get("tokens_out", 0),
            "duration_s": r.get("duration_s"),
            "started_at": r.get("started_at"),
            "gates": r.get("gates", []),
            "researcher": researcher,
            "draft": None,
            "verdict": None,
            "not_captured": not_captured,
            "not_captured_reason": not_captured_reason,
        })

    out = {
        "source": "13 live API runs against Sonos, from orchestrator/run.py, logged to runs.jsonl. "
                   "No fixture/dry-run data is included in this file.",
        "models": MODELS,
        "default_run_id": "785069cb",
        "runs": runs,
    }
    payload = json.dumps(out, indent=2, ensure_ascii=False)
    OUT_JSON.write_text(payload, encoding="utf-8")
    OUT_JS.write_text("window.RUNS_DATA = " + payload + ";\n", encoding="utf-8")
    print(f"wrote {OUT_JSON} and {OUT_JS} — {len(runs)} live runs")
    for r in runs:
        print(f"  {r['run_id']}  {r['outcome']:10s}  researcher={'yes' if r['researcher'] else 'no'}")


if __name__ == "__main__":
    main()
