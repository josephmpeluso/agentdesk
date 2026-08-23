#!/usr/bin/env python3
"""Generates agentdesk.n8n.json.

Written as a generator rather than hand-authored JSON because the Code nodes
contain real JavaScript, and JS embedded in hand-edited JSON is where
workflows go to die.

Design note: this uses plain HTTP Request nodes against the Anthropic API
rather than n8n's native AI Agent node. That is deliberate. The native node
manages its own loop and retry behavior, which is exactly the behavior this
system needs to own — the retry budget, the gate, and the escalation path are
the product. Wrapping them in something else's control flow gives that away.
"""
import json
from pathlib import Path

API = "https://api.anthropic.com/v1/messages"


def anthropic_node(name, model, system_ref, user_expr, x, y):
    """HTTP Request node hitting the Messages API."""
    body = (
        "={{ JSON.stringify({ model: '" + model + "', max_tokens: 4000, "
        "system: " + system_ref + ", messages: [{ role: 'user', content: " + user_expr + " }] }) }}"
    )
    return {
        "parameters": {
            "method": "POST",
            "url": API,
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "x-api-key", "value": "={{ $env.ANTHROPIC_API_KEY }}"},
                {"name": "anthropic-version", "value": "2023-06-01"},
                {"name": "content-type", "value": "application/json"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": body,
            "options": {"timeout": 120000, "response": {"response": {"neverError": False}}},
        },
        "id": name.lower().replace(" ", "-"),
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [x, y],
    }


def code_node(name, js, x, y):
    return {
        "parameters": {"jsCode": js},
        "id": name.lower().replace(" ", "-"),
        "name": name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [x, y],
    }


def if_node(name, left, x, y):
    return {
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                "conditions": [{
                    "id": name.lower().replace(" ", "-") + "-cond",
                    "leftValue": left,
                    "rightValue": "",
                    "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                }],
                "combinator": "and",
            },
            "options": {},
        },
        "id": name.lower().replace(" ", "-"),
        "name": name,
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [x, y],
    }


# ------------------------------------------------------------------ JS blocks

JS_PARSE_BRIEF = r"""
// Parse the researcher's reply, then run Gate 2 (structure) and the
// provenance check. Anything that fails here never reaches the drafter.
const raw = $input.first().json.content.map(b => b.text || '').join('').trim();
const cleaned = raw.replace(/^```(?:json)?/gm, '').replace(/```$/gm, '').trim();

let brief;
try {
  brief = JSON.parse(cleaned);
} catch (e) {
  return [{ json: { fatal: true, stage: 'researcher', reason: 'unparseable JSON: ' + e.message } }];
}

const required = ['company', 'insufficient_evidence', 'claims', 'gaps'];
const missing = required.filter(k => !(k in brief));
if (missing.length) {
  return [{ json: { fatal: true, stage: 'researcher', reason: 'missing keys: ' + missing.join(', ') } }];
}

// Provenance: every claim must carry a real retrieved URL.
const unsourced = (brief.claims || []).filter(c => !/^https?:\/\//.test(c.source_url || ''));
if (unsourced.length) {
  return [{ json: { fatal: true, stage: 'researcher',
    reason: 'unsourced claims: ' + unsourced.map(c => c.claim_id).join(', ') } }];
}

// Low-confidence claims are stripped here, not left to the drafter's restraint.
const drafterBrief = { ...brief, claims: (brief.claims || []).filter(c => c.confidence !== 'low') };

return [{ json: {
  fatal: false,
  sufficient: brief.insufficient_evidence !== true,
  brief,
  drafterBrief,
  attempt: 1,
  company: brief.company,
} }];
"""

JS_CHECKS = r"""
// Gate 3. Deterministic checks, run before spending a QA call.
// Mirrors orchestrator/run.py:deterministic_checks — keep them in sync.
const state = $('Validate Brief').first().json;
const raw = $input.first().json.content.map(b => b.text || '').join('').trim();
const cleaned = raw.replace(/^```(?:json)?/gm, '').replace(/```$/gm, '').trim();

let draft;
try { draft = JSON.parse(cleaned); }
catch (e) { return [{ json: { ...state, fatal: true, stage: 'drafter', reason: 'unparseable JSON' } }]; }

if (draft.draftable === false) {
  return [{ json: { ...state, draft, halted: true, reason: draft.blocker || 'drafter declined' } }];
}

const BANNED = ["i hope this email finds you well","i hope you're doing well",
  "i hope this finds you well","i came across your company","i wanted to reach out",
  "in today's fast-paced","game-changer","game changer","revolutionize",
  "leverage synergies","circle back","just following up","i'll cut to the chase",
  "as you may know","touch base","at the end of the day"];

const body = (draft.email && draft.email.body) || '';
const refRe = /\[(c\d+)\]/g;
const words = body.replace(refRe, '').split(/\s+/).filter(Boolean).length;
const problems = [];

if (Math.abs(words - 120) > 10) problems.push(`word_count: ${words}, must be 120±10`);
const declaredWc = draft.email && draft.email.word_count;
if (declaredWc && Math.abs(declaredWc - words) > 3)
  problems.push(`word_count_selfreport: claimed ${declaredWc}, actual ${words}`);

const low = body.toLowerCase();
BANNED.forEach(p => { if (low.includes(p)) problems.push(`banned_phrase: '${p}'`); });

const subject = (draft.email && draft.email.subject) || '';
if (!subject) problems.push('subject: missing');
else if (subject.length > 60) problems.push(`subject: ${subject.length} chars, max 60`);

const validIds = new Set((state.brief.claims || []).map(c => c.claim_id));
const lowConf = new Set((state.brief.claims || []).filter(c => c.confidence === 'low').map(c => c.claim_id));
const declared = new Set((draft.claim_refs || []).map(r => r.claim_id));
const used = new Set([...body.matchAll(/\[(c\d+)\]/g)].map(m => m[1]));

const dangling = [...used].filter(id => !validIds.has(id));
if (dangling.length) problems.push(`dangling_claim_ref: ${dangling.join(', ')}`);
const undeclared = [...used].filter(id => !declared.has(id));
if (undeclared.length) problems.push(`undeclared_claim_ref: ${undeclared.join(', ')}`);
if (used.size === 0) problems.push('no_claim_refs: asserts facts with zero references');
const leaked = [...used].filter(id => lowConf.has(id));
if (leaked.length) problems.push(`low_confidence_leak: ${leaked.join(', ')}`);

const ab = draft.account_brief || {};
if (!ab.what_i_dont_know || ab.what_i_dont_know.length === 0)
  problems.push("account_brief: 'what_i_dont_know' is mandatory and empty");

return [{ json: { ...state, draft, deterministicPass: problems.length === 0, problems } }];
"""

JS_RELEASE = r"""
// Gates 4 and 5. The reviewer's own `pass` field is advisory; the decision is
// recomputed here. A gate a model can talk its way past is not a gate.
const state = $('Deterministic Checks').first().json;
const raw = $input.first().json.content.map(b => b.text || '').join('').trim();
const cleaned = raw.replace(/^```(?:json)?/gm, '').replace(/```$/gm, '').trim();

let verdict;
try { verdict = JSON.parse(cleaned); }
catch (e) { return [{ json: { ...state, fatal: true, stage: 'qa', reason: 'unparseable JSON' } }]; }

const score = verdict.score || 0;
const blocking = (verdict.flags || []).filter(f => f.severity === 'blocking');
const swapFailed = verdict.swap_test && verdict.swap_test.still_coherent === true;

let released = true;
let reason = `score ${score}, no blocking flags`;
if (swapFailed) { released = false; reason = 'swap test: email survives redaction, it is a template'; }
else if (blocking.length) { released = false; reason = `${blocking.length} blocking flag(s)`; }
else if (score < 8) { released = false; reason = `score ${score} below threshold 8`; }
else if (verdict.pass === false) { released = false; reason = 'reviewer overrode a passing score'; }

const attempt = state.attempt || 1;
const budgetLeft = attempt <= 2;

return [{ json: { ...state, verdict, score, released, reason, attempt,
  retry: !released && budgetLeft,
  escalate: !released && !budgetLeft } }];
"""

JS_REVISION = r"""
// Builds the revision prompt from QA flags (or from deterministic problems,
// when the draft never reached QA) and increments the attempt counter.
const s = $input.first().json;
const flags = (s.verdict && s.verdict.flags) || [];

const fixes = flags.length
  ? flags.map(f => `- [${f.severity}] ${f.type} — ${String(f.location).slice(0,120)}\n  FIX: ${f.remediation}`).join('\n')
  : (s.problems || []).map(p => `- [blocking] constraint — ${p}\n  FIX: correct it`).join('\n');

const prompt = [
  'Your previous draft was rejected. Revise it.',
  '',
  'RESEARCH BRIEF:', JSON.stringify(s.drafterBrief, null, 2),
  '',
  'YOUR PREVIOUS DRAFT:', JSON.stringify(s.draft, null, 2),
  '',
  `QA SCORE: ${s.score === undefined ? 'n/a (rejected before QA)' : s.score} (need 8)`,
  'REQUIRED FIXES:', fixes,
  '',
  'Address every fix. Do not re-litigate the flags. Do not add facts absent',
  'from the brief. Emit a complete draft_package object.',
].join('\n');

return [{ json: { ...s, attempt: (s.attempt || 1) + 1, drafterPrompt: prompt } }];
"""

JS_ESCALATE = r"""
// Terminal state. The bar does not move to accommodate the retry budget.
const s = $input.first().json;
return [{ json: {
  outcome: 'escalated',
  company: s.company,
  attempts: s.attempt,
  final_score: s.score,
  reason: s.reason,
  flags: (s.verdict && s.verdict.flags) || s.problems,
  draft: s.draft,
  brief: s.brief,
  message: 'Retry budget exhausted. Routed to the human queue rather than lowering the threshold.',
} }];
"""

JS_RELEASE_OUT = r"""
// Strip the [cN] references for the sendable copy, but keep the annotated
// version and the full audit chain attached to the record.
const s = $input.first().json;
const body = s.draft.email.body.replace(/\s*\[c\d+\]/g, '');
return [{ json: {
  outcome: 'released',
  company: s.company,
  attempts: s.attempt,
  score: s.score,
  subject: s.draft.email.subject,
  body,
  annotated_body: s.draft.email.body,
  account_brief: s.draft.account_brief,
  audit: { brief: s.brief, verdict: s.verdict },
} }];
"""

JS_HALT = r"""
const s = $input.first().json;
return [{ json: {
  outcome: s.fatal ? 'rejected' : 'halted',
  company: s.company || (s.brief && s.brief.company),
  reason: s.reason || 'insufficient evidence to draft from',
  gaps: (s.brief && s.brief.gaps) || [],
  message: 'Stopped before drafting. Declining to build outreach on thin evidence is the intended behavior.',
} }];
"""

# --------------------------------------------------------------------- nodes

SYS_R = "$('Load Skills').first().json.researcher"
SYS_D = "$('Load Skills').first().json.drafter"
SYS_Q = "$('Load Skills').first().json.qa"

JS_LOAD = r"""
// System prompts live here so the workflow is self-contained on import.
// In production these are read from the skills/ directory at deploy time so
// the n8n copy and the CLI copy cannot drift apart.
return [{ json: {
  researcher: 'PASTE skills/researcher/SKILL.md BODY HERE',
  drafter:    'PASTE skills/drafter/SKILL.md BODY HERE',
  qa:         'PASTE skills/qa-reviewer/SKILL.md BODY HERE',
  company: $('Intake').first().json.body.company,
  domain:  $('Intake').first().json.body.domain || 'unknown',
} }];
"""

nodes = [
    {
        "parameters": {"httpMethod": "POST", "path": "agentdesk", "responseMode": "lastNode", "options": {}},
        "id": "intake", "name": "Intake", "type": "n8n-nodes-base.webhook",
        "typeVersion": 2, "position": [-460, 300], "webhookId": "agentdesk-intake",
    },
    code_node("Load Skills", JS_LOAD, -260, 300),
    anthropic_node("Researcher", "claude-haiku-4-5-20251001", SYS_R,
                   "'Company: ' + $('Load Skills').first().json.company + "
                   "'\\nKnown domain: ' + $('Load Skills').first().json.domain + "
                   "'\\n\\nProduce the research_brief.'", -60, 300),
    code_node("Validate Brief", JS_PARSE_BRIEF, 140, 300),
    if_node("Evidence Sufficient?", "={{ $json.sufficient && !$json.fatal }}", 340, 300),
    anthropic_node("Drafter", "claude-sonnet-4-6", SYS_D,
                   "$json.drafterPrompt || ('RESEARCH BRIEF:\\n' + "
                   "JSON.stringify($json.drafterBrief) + '\\n\\nProduce the draft_package.')",
                   560, 200),
    code_node("Deterministic Checks", JS_CHECKS, 760, 200),
    if_node("Deterministic Pass?", "={{ $json.deterministicPass && !$json.halted }}", 960, 200),
    anthropic_node("QA Reviewer", "claude-opus-4-5", SYS_Q,
                   "'RESEARCH BRIEF:\\n' + JSON.stringify($json.drafterBrief) + "
                   "'\\n\\nDRAFT PACKAGE:\\n' + JSON.stringify($json.draft) + "
                   "'\\n\\nProduce the qa_verdict.'", 1160, 120),
    code_node("Release Decision", JS_RELEASE, 1360, 120),
    if_node("Released?", "={{ $json.released }}", 1560, 120),
    code_node("Deliver", JS_RELEASE_OUT, 1780, 40),
    if_node("Retry Budget Left?", "={{ $json.retry }}", 1780, 240),
    code_node("Build Revision", JS_REVISION, 1560, 380),
    code_node("Escalate to Human", JS_ESCALATE, 1980, 340),
    code_node("Halt", JS_HALT, 560, 460),
]

connections = {
    "Intake": {"main": [[{"node": "Load Skills", "type": "main", "index": 0}]]},
    "Load Skills": {"main": [[{"node": "Researcher", "type": "main", "index": 0}]]},
    "Researcher": {"main": [[{"node": "Validate Brief", "type": "main", "index": 0}]]},
    "Validate Brief": {"main": [[{"node": "Evidence Sufficient?", "type": "main", "index": 0}]]},
    "Evidence Sufficient?": {"main": [
        [{"node": "Drafter", "type": "main", "index": 0}],
        [{"node": "Halt", "type": "main", "index": 0}],
    ]},
    "Drafter": {"main": [[{"node": "Deterministic Checks", "type": "main", "index": 0}]]},
    "Deterministic Checks": {"main": [[{"node": "Deterministic Pass?", "type": "main", "index": 0}]]},
    "Deterministic Pass?": {"main": [
        [{"node": "QA Reviewer", "type": "main", "index": 0}],
        [{"node": "Retry Budget Left?", "type": "main", "index": 0}],
    ]},
    "QA Reviewer": {"main": [[{"node": "Release Decision", "type": "main", "index": 0}]]},
    "Release Decision": {"main": [[{"node": "Released?", "type": "main", "index": 0}]]},
    "Released?": {"main": [
        [{"node": "Deliver", "type": "main", "index": 0}],
        [{"node": "Retry Budget Left?", "type": "main", "index": 0}],
    ]},
    "Retry Budget Left?": {"main": [
        [{"node": "Build Revision", "type": "main", "index": 0}],
        [{"node": "Escalate to Human", "type": "main", "index": 0}],
    ]},
    # The loop: revision feeds back into the drafter. Bounded by attempt count,
    # which is checked before this edge is ever taken.
    "Build Revision": {"main": [[{"node": "Drafter", "type": "main", "index": 0}]]},
}

workflow = {
    "name": "AgentDesk — Outreach Pipeline",
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1", "saveManualExecutions": True, "callerPolicy": "workflowsFromSameOwner"},
    "pinData": {},
    "meta": {"instanceId": "agentdesk"},
    "tags": [{"name": "agentdesk"}],
}

if __name__ == "__main__":
    out = Path(__file__).parent / "agentdesk.n8n.json"
    out.write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")

    names = {n["name"] for n in nodes}
    dangling = []
    for src, spec in connections.items():
        if src not in names:
            dangling.append(f"source '{src}' is not a node")
        for branch in spec["main"]:
            for edge in branch:
                if edge["node"] not in names:
                    dangling.append(f"'{src}' -> '{edge['node']}' (target missing)")
    if dangling:
        raise SystemExit("broken connections:\n  " + "\n  ".join(dangling))

    reachable = {"Intake"}
    changed = True
    while changed:
        changed = False
        for src, spec in connections.items():
            if src in reachable:
                for branch in spec["main"]:
                    for edge in branch:
                        if edge["node"] not in reachable:
                            reachable.add(edge["node"])
                            changed = True
    orphans = names - reachable
    if orphans:
        raise SystemExit(f"unreachable nodes: {sorted(orphans)}")

    print(f"wrote {out}")
    print(f"  {len(nodes)} nodes, all reachable from Intake, no dangling edges")
