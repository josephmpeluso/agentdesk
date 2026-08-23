(function () {
  "use strict";

  var DATA = window.RUNS_DATA || { runs: [], models: {}, default_run_id: null };
  var RUNS = DATA.runs || [];
  var MODELS = DATA.models || {};

  var RESEARCHER_GATES = ["schema:research_brief", "evidence:sufficient", "provenance:all_claims_sourced"];

  var GATE_LABELS = {
    "schema:research_brief": "Schema — research brief",
    "evidence:sufficient": "Evidence sufficient",
    "provenance:all_claims_sourced": "Provenance — every claim sourced",
    "schema:draft_package": "Schema — draft package",
    "draftable": "Drafter agreed to draft",
    "deterministic": "Deterministic checks",
    "schema:qa_verdict": "Schema — QA verdict",
    "contract": "Contract — reply parsed",
  };

  function gateLabel(g) {
    if (GATE_LABELS[g.gate]) return GATE_LABELS[g.gate];
    if (g.gate.indexOf("release_gate") === 0) return "Release gate";
    return g.gate;
  }

  var STATE_META = {
    released: { pill: "pill-released", word: "RELEASED", narrative: "narrative-released",
      copy: "This draft cleared every gate — schema, provenance, deterministic checks, and the QA reviewer's score at or above threshold with no blocking flags. It reached a human inbox-ready state." },
    escalated: { pill: "pill-escalated", word: "ESCALATED", narrative: "narrative-escalated",
      copy: "The retry budget ran out with the QA reviewer still blocking the draft. Rather than lower the bar, the pipeline routed this to a human queue. That is the system working as designed, not a crash." },
    halted: { pill: "pill-halted", word: "HALTED", narrative: "narrative-halted",
      copy: "The researcher could not meet its evidence bar and stopped before anything was drafted. A pipeline that always produces an email is a pipeline that will invent facts about companies it couldn't research — halting here is the correct outcome." },
    rejected: { pill: "pill-rejected", word: "REJECTED", narrative: "narrative-rejected",
      copy: "An agent's reply did not conform to its contract — malformed structure, a field over its length limit, or an unparseable response. Per this system's design, malformed output is rejected outright and never retried: a model that can't produce the schema is a prompt bug, not a flake." },
  };

  function fmtTokens(n) {
    if (n == null) return "—";
    return n.toLocaleString("en-US");
  }

  function fmtDuration(s) {
    if (s == null) return "—";
    if (s < 60) return s.toFixed(1) + "s";
    var m = Math.floor(s / 60);
    var rem = Math.round(s % 60);
    return m + "m " + rem + "s";
  }

  function esc(str) {
    var d = document.createElement("div");
    d.textContent = str == null ? "" : String(str);
    return d.innerHTML;
  }

  /* ----------------------------------------------------------
     group a run's flat gate list into: researcher gates, then
     an ordered list of "attempts" (drafter+QA loop iterations).
     boundary = each "schema:draft_package" gate. anything after
     the last boundary — including a trailing contract failure —
     stays attached to that same attempt group. this only groups
     what the log unambiguously supports; it never infers an
     attempt number the log didn't actually mark.
     ---------------------------------------------------------- */
  function groupGates(gates) {
    gates = gates || [];
    var i = 0;
    var researcher = [];
    while (i < gates.length && RESEARCHER_GATES.indexOf(gates[i].gate) !== -1) {
      researcher.push(gates[i]);
      i++;
    }
    var attempts = [];
    var current = null;
    for (; i < gates.length; i++) {
      var g = gates[i];
      if (g.gate === "schema:draft_package" && current) {
        attempts.push(current);
        current = [g];
      } else {
        if (!current) current = [];
        current.push(g);
      }
    }
    if (current && current.length) attempts.push(current);
    return { researcher: researcher, attempts: attempts };
  }

  function stageReached(grouped, stage) {
    if (stage === "researcher") return grouped.researcher.length > 0;
    if (stage === "drafter") return grouped.attempts.length > 0;
    if (stage === "qa") return grouped.attempts.some(function (a) {
      return a.some(function (g) { return g.gate === "schema:qa_verdict"; });
    });
    return false;
  }

  /* ---------------------------------------------------------- */

  function renderRunList() {
    var wrap = document.getElementById("run-list-items");
    var count = document.getElementById("run-count");
    count.textContent = RUNS.length + " runs";
    wrap.innerHTML = "";
    RUNS.forEach(function (r) {
      var meta = STATE_META[r.outcome] || STATE_META.rejected;
      var btn = document.createElement("button");
      btn.className = "run-card";
      btn.type = "button";
      btn.dataset.runId = r.run_id;
      btn.style.setProperty("--state-color", "var(--" + r.outcome + ")");
      btn.innerHTML =
        '<div class="run-card-top">' +
          '<span class="run-card-id mono">' + esc(r.run_id) + "</span>" +
          '<span class="pill ' + meta.pill + '">' + meta.word + "</span>" +
        "</div>" +
        '<div class="run-card-company">' + esc(r.company) + "</div>" +
        '<div class="run-card-meta">' +
          "<span>" + r.attempts + " attempt" + (r.attempts === 1 ? "" : "s") + "</span>" +
          (r.score != null ? "<span>· score " + r.score + "</span>" : "") +
        "</div>";
      btn.addEventListener("click", function () { selectRun(r.run_id); });
      wrap.appendChild(btn);
    });
  }

  function renderModelKey() {
    var el = document.getElementById("model-key");
    var order = [["researcher", "Researcher"], ["drafter", "Drafter"], ["qa-reviewer", "QA Reviewer"]];
    el.innerHTML = order.map(function (pair) {
      return '<span class="m"><b>' + pair[1] + "</b> " + esc(MODELS[pair[0]] || "?") + "</span>";
    }).join("");
  }

  function gateChip(g) {
    var cls = g.passed ? "gate-pass" : "gate-fail";
    return '<span class="gate-chip kind-code ' + cls + '" title="' + esc(g.detail) + '">' +
      '<span class="shape"></span>' + esc(gateLabel(g)) + "</span>";
  }

  function renderPipeline(grouped, run) {
    var researcherOk = grouped.researcher.length && grouped.researcher.every(function (g) { return g.passed; });
    var drafterOk = grouped.attempts.length > 0;
    var qaOk = stageReached(grouped, "qa");

    var html = '<div class="pipeline">';

    html += '<div class="stage-card' + (stageReached(grouped, "researcher") ? "" : " not-reached") + '">' +
      '<div class="stage-name">1 · Researcher</div>' +
      '<div class="stage-model mono">' + esc(MODELS.researcher) + "</div></div>";

    html += '<div class="gate-connector">' + grouped.researcher.map(gateChip).join("") + "</div>";

    html += '<div class="stage-card' + (drafterOk ? "" : " not-reached") + '">' +
      '<div class="stage-name">2 · Drafter</div>' +
      '<div class="stage-model mono">' + esc(MODELS.drafter) + "</div></div>";

    var draftGates = [];
    grouped.attempts.forEach(function (a) { a.forEach(function (g) {
      if (g.gate === "schema:draft_package" || g.gate === "deterministic" || g.gate === "draftable") draftGates.push(g);
    }); });
    html += '<div class="gate-connector">' + draftGates.map(gateChip).join("") + "</div>";

    html += '<div class="stage-card' + (qaOk ? "" : " not-reached") + '" style="' +
      (qaOk ? "border-color:var(--accent-tint-border);background:var(--accent-tint);" : "") + '">' +
      '<div class="stage-name">3 · QA Reviewer</div>' +
      '<div class="stage-model mono">' + esc(MODELS["qa-reviewer"]) + "</div>" +
      (qaOk ? '<div class="src-badge" style="margin-top:6px;background:var(--accent);color:var(--accent-ink);">MODEL JUDGMENT</div>' : "") +
      "</div>";

    var qaGates = [];
    grouped.attempts.forEach(function (a) { a.forEach(function (g) {
      if (g.gate === "schema:qa_verdict" || g.gate.indexOf("release_gate") === 0 || g.gate === "contract") qaGates.push(g);
    }); });
    html += '<div class="gate-connector">' + qaGates.map(gateChip).join("") + "</div>";

    html += "</div>";
    return html;
  }

  function renderAttempts(grouped) {
    if (!grouped.attempts.length) return "";
    var html = '<div class="card"><h3>Attempt history</h3><div class="attempts">';
    grouped.attempts.forEach(function (a, idx) {
      html += '<div class="attempt"><div class="attempt-head">' +
        '<span class="attempt-num">' + (idx + 1) + "</span>" +
        "<span>Attempt " + (idx + 1) + "</span></div>";
      html += '<div class="attempt-gates">';
      a.forEach(function (g) {
        html += '<div class="attempt-gate-row" style="width:100%;">' +
          '<span class="gate-status-dot ' + (g.passed ? "pass" : "fail") + '"></span>' +
          '<span class="gate-name">' + esc(gateLabel(g)) + "</span>" +
          (g.detail ? '<span class="gate-detail">— ' + esc(g.detail) + "</span>" : "") +
          "</div>";
      });
      html += "</div></div>";
    });
    html += "</div></div>";
    return html;
  }

  function renderResearcherPanel(run) {
    var b = run.researcher;
    var html = '<div class="card"><div class="panel-head"><h3>Researcher</h3></div>';
    if (b) {
      if (b.what_they_sell) html += '<div class="finding-row"><b>Sells</b> [' + esc(b.what_they_sell.claim_id) + "] " + esc(b.what_they_sell.summary) + "</div>";
      if (b.recent_news) html += '<div class="finding-row"><b>News</b> [' + esc(b.recent_news.claim_id) + "] " + esc(b.recent_news.summary) + "</div>";
      if (b.marketing_task) {
        html += '<div class="finding-row"><b>Task</b> [' + esc(b.marketing_task.claim_id) + "] " + esc(b.marketing_task.description) + "</div>";
        if (b.marketing_task.rejected_reason) {
          html += '<div class="flagged-field"><div class="label">Why this run stopped here</div>' +
            '<div class="why">' + esc(b.marketing_task.rejected_reason) + "</div></div>";
        }
      }
      html += '<div style="margin-top:12px;">';
      (b.claims || []).forEach(function (c) {
        html += '<div class="claim"><div class="claim-top">' +
          '<span class="claim-id">[' + esc(c.claim_id) + "]</span>" +
          '<span class="claim-confidence">' + esc(c.confidence) + "</span></div>" +
          '<div class="claim-statement">' + esc(c.statement) + "</div>" +
          '<div class="claim-source">source: <a href="' + esc(c.source_url) + '" target="_blank" rel="noopener">' + esc(c.source_url) + "</a></div></div>";
      });
      html += "</div>";
    } else {
      html += notCapturedBlock(run, "researcher");
    }
    html += "</div>";
    return html;
  }

  function renderDraftPanel(run) {
    var html = '<div class="card"><div class="panel-head"><h3>Drafter</h3></div>';
    html += notCapturedBlock(run, "draft");
    html += "</div>";
    return html;
  }

  function renderQaPanel(run) {
    var html = '<div class="card"><div class="panel-head"><h3>QA Reviewer</h3></div>';
    html += notCapturedBlock(run, "verdict");
    html += "</div>";
    return html;
  }

  function notCapturedBlock(run, which) {
    // For draft/verdict, distinguish "stage never ran" (correct gate
    // behavior, not a gap) from "stage ran but wasn't logged" (a real
    // observability gap). researcher is always attempted, so it only
    // ever hits the second case.
    var grouped = groupGates(run.gates);
    var neverRan = false;
    if (which === "draft") neverRan = grouped.attempts.length === 0;
    if (which === "verdict") neverRan = !stageReached(grouped, "qa");

    if (neverRan) {
      var stageWord = which === "draft" ? "the drafter" : "the QA reviewer";
      return '<div class="panel-empty">Pipeline never reached ' + stageWord +
        " — an earlier gate correctly stopped it first. This isn't missing data; the stage didn't run.</div>";
    }

    var items = run.not_captured || [];
    var relevant = items.filter(function (t) {
      if (which === "researcher") return /researcher/i.test(t);
      if (which === "draft") return /draft/i.test(t);
      if (which === "verdict") return /qa|verdict|flag/i.test(t);
      return true;
    });
    if (!relevant.length) relevant = items;

    var html = '<div class="not-captured"><div class="nc-label">Not captured</div><ul>';
    relevant.forEach(function (t) { html += "<li>" + esc(t) + "</li>"; });
    html += "</ul>";
    if (run.not_captured_reason) html += '<div class="nc-reason">' + esc(run.not_captured_reason) + "</div>";
    html += "</div>";
    return html;
  }

  function renderDetail(run) {
    var meta = STATE_META[run.outcome] || STATE_META.rejected;
    var grouped = groupGates(run.gates);
    var el = document.getElementById("detail");

    var scorePct = run.score != null ? Math.max(0, Math.min(100, (run.score / 10) * 100)) : null;
    var scoreColor = run.score == null ? "var(--not-reached)" : (run.score >= 8 ? "var(--released)" : "var(--rejected)");

    var html = "";

    html += '<div class="card summary">' +
      '<div class="summary-outcome">' +
        '<span class="pill pill-lg ' + meta.pill + '">' + meta.word + "</span>" +
        '<span class="summary-company">' + esc(run.company) + "</span>" +
        '<span class="summary-runid mono">run ' + esc(run.run_id) + "</span>" +
      "</div>" +
      '<div class="summary-stats">' +
        (run.score != null ?
          '<div class="score-gauge"><span class="score-gauge-label">QA score / threshold 8</span>' +
            '<span class="score-gauge-value" style="color:' + scoreColor + '">' + run.score + " / 10</span>" +
            '<div class="score-track"><div class="score-fill" style="width:' + scorePct + '%;background:' + scoreColor + ';"></div>' +
            '<div class="score-threshold" style="left:80%;"></div></div></div>'
          : '<div class="score-gauge"><span class="score-gauge-label">QA score</span><span class="score-gauge-value" style="color:var(--not-reached)">not reached</span></div>') +
        '<div class="stat"><span class="stat-label">Attempts</span><span class="stat-value">' + run.attempts + "</span></div>" +
        '<div class="stat"><span class="stat-label">Tokens in / out</span><span class="stat-value">' + fmtTokens(run.tokens_in) + " / " + fmtTokens(run.tokens_out) + "</span></div>" +
        '<div class="stat"><span class="stat-label">Duration</span><span class="stat-value">' + fmtDuration(run.duration_s) + "</span></div>" +
      "</div></div>";

    html += '<div class="narrative ' + meta.narrative + '">' + esc(meta.copy) + "</div>";

    html += '<div class="card"><div class="panel-head"><h3>Pipeline</h3>' +
      '<div class="legend"><span class="legend-item"><span class="shape code"></span>deterministic (code)</span>' +
      '<span class="legend-item"><span class="shape model" style="background:var(--accent);"></span>model judgment</span></div></div>' +
      renderPipeline(grouped, run) + "</div>";

    html += renderAttempts(grouped);

    html += '<div class="panels">' + renderResearcherPanel(run) + renderDraftPanel(run) + renderQaPanel(run) + "</div>";

    el.innerHTML = html;
  }

  function selectRun(runId) {
    var run = RUNS.filter(function (r) { return r.run_id === runId; })[0];
    if (!run) return;
    document.querySelectorAll(".run-card").forEach(function (c) {
      c.setAttribute("aria-current", c.dataset.runId === runId ? "true" : "false");
    });
    renderDetail(run);
    if (history.replaceState) history.replaceState(null, "", "#" + runId);
  }

  function init() {
    renderModelKey();
    renderRunList();
    var initial = (location.hash || "").replace("#", "") || DATA.default_run_id || (RUNS[0] && RUNS[0].run_id);
    if (initial) selectRun(initial);
  }

  document.addEventListener("DOMContentLoaded", init);

  // supports manual hash edits and browser back/forward between runs
  window.addEventListener("hashchange", function () {
    var id = (location.hash || "").replace("#", "");
    if (id) selectRun(id);
  });
})();
