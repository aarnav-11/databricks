"""Small self-contained browser UI for the supervisor POC."""


def render_ui() -> str:
    return r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Insurance Fraud Supervisor POC</title>
  <style>
    :root { color-scheme: light; --ink:#182230; --muted:#64748b; --line:#dbe3ec;
      --blue:#2457d6; --blue-soft:#eef3ff; --green:#087443; --green-soft:#e9f8f0;
      --paper:#ffffff; --bg:#f4f7fb; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.55 ui-sans-serif,
      system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
    .shell { max-width:1120px; margin:0 auto; padding:34px 22px 64px; }
    .top { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; margin-bottom:26px; }
    .eyebrow { color:var(--blue); font-size:12px; font-weight:750; letter-spacing:.12em; text-transform:uppercase; }
    h1 { font:650 clamp(28px,4vw,44px)/1.08 Georgia,serif; letter-spacing:-.02em; margin:8px 0 10px; }
    .lede { color:var(--muted); max-width:690px; margin:0; }
    .badge { background:var(--green-soft); border:1px solid #b9e8cc; border-radius:999px; color:var(--green);
      font-size:12px; font-weight:700; padding:7px 11px; white-space:nowrap; }
    .panel { background:var(--paper); border:1px solid var(--line); border-radius:16px; box-shadow:0 8px 30px rgba(31,51,79,.06); }
    .prompt { padding:20px; }
    label { display:block; font-weight:700; margin-bottom:8px; }
    textarea { border:1px solid #bac8d8; border-radius:10px; display:block; font:inherit; min-height:92px;
      padding:12px 13px; resize:vertical; width:100%; }
    textarea:focus { border-color:var(--blue); box-shadow:0 0 0 3px #dfe8ff; outline:0; }
    .actions { align-items:center; display:flex; flex-wrap:wrap; gap:12px; margin-top:14px; }
    button { background:var(--blue); border:0; border-radius:9px; color:#fff; cursor:pointer; font-weight:750;
      padding:10px 16px; }
    button:hover { background:#1c46b2; }
    button:disabled { cursor:wait; opacity:.65; }
    .example { background:transparent; border:1px solid var(--line); color:var(--muted); font-weight:600; }
    .status { color:var(--muted); min-height:24px; }
    .status.error { color:#b42318; }
    #result { display:none; margin-top:24px; }
    .doc-head { border-bottom:1px solid var(--line); padding:24px 26px 18px; }
    .doc-title { font:650 28px/1.2 Georgia,serif; margin:0 0 10px; }
    .meta { color:var(--muted); display:flex; flex-wrap:wrap; gap:8px; }
    .chip { background:var(--blue-soft); border-radius:999px; color:#23428f; font-size:12px; padding:4px 9px; }
    .answer { padding:24px 26px 28px; }
    .answer p { margin:0 0 14px; }
    .answer ul { margin:0 0 14px; padding-left:22px; }
    .answer code { background:#f0f3f7; border-radius:4px; padding:1px 4px; }
    .trace-wrap { border-top:1px solid var(--line); padding:0 26px 26px; }
    details > summary { color:#23428f; cursor:pointer; font-weight:750; padding:18px 0; }
    .trace-note { color:var(--muted); font-size:13px; margin:-6px 0 16px; }
    .trace-card { border:1px solid var(--line); border-left:4px solid var(--blue); border-radius:9px; margin:10px 0;
      padding:13px 15px; }
    .trace-card.query { border-left-color:#7a4ed1; }
    .trace-card.synthesis { border-left-color:var(--green); }
    .trace-card h3 { font-size:14px; margin:0 0 8px; }
    .trace-grid { display:grid; gap:6px 18px; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); }
    .trace-label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }
    .trace-value { font-weight:650; }
    .call { background:#f8fafc; border-radius:7px; margin-top:8px; padding:8px 10px; }
    .diagram { background:#f8fafc; border:1px solid var(--line); border-radius:10px; margin:0 0 18px; padding:14px; }
    .diagram-title { color:var(--muted); font-size:12px; font-weight:750; letter-spacing:.06em; margin-bottom:10px; text-transform:uppercase; }
    .diagram-step { display:grid; grid-template-columns:22px minmax(0,1fr); gap:10px; min-height:62px; }
    .diagram-rail { display:flex; justify-content:center; position:relative; }
    .diagram-rail::before { background:#cbd6e4; content:""; left:10px; position:absolute; top:14px; bottom:-14px; width:2px; }
    .diagram-step:last-child .diagram-rail::before { display:none; }
    .diagram-dot { background:var(--blue); border:3px solid #dfe8ff; border-radius:50%; height:14px; margin-top:5px; position:relative; width:14px; z-index:1; }
    .diagram-node { background:#fff; border:1px solid var(--line); border-left:3px solid #94a3b8; border-radius:8px; margin-bottom:10px; padding:9px 11px; }
    .diagram-node.decision { border-left-color:var(--blue); }
    .diagram-node.query { border-left-color:#7a4ed1; }
    .diagram-node.synthesis { border-left-color:var(--green); }
    .diagram-kicker { color:var(--muted); font-size:11px; letter-spacing:.05em; text-transform:uppercase; }
    .diagram-main { font-weight:750; margin-top:2px; }
    .diagram-detail { color:var(--muted); font-size:13px; margin-top:2px; overflow-wrap:anywhere; }
    .raw { background:#111827; border-radius:9px; color:#d9e4f2; font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
      max-height:360px; overflow:auto; padding:14px; white-space:pre-wrap; }
    @media (max-width:640px) { .top { display:block; } .badge { display:inline-block; margin-top:16px; } .answer,.doc-head,.trace-wrap { padding-left:18px; padding-right:18px; } }
  </style>
</head>
<body>
  <main class="shell">
    <header class="top">
      <div>
        <div class="eyebrow">Databricks · development POC</div>
        <h1>Insurance fraud supervisor</h1>
        <p class="lede">Ask about a synthetic claim and receive a document-style triage memo with the governed planes and tool activity used to assemble it.</p>
      </div>
      <div class="badge">RUNNING · read-only triage</div>
    </header>

    <section class="panel prompt">
      <form id="query-form">
        <label for="question">Investigation request</label>
        <textarea id="question" required>For CLM-1001, give me a concise triage summary.</textarea>
        <div class="actions">
          <button id="submit" type="submit">Generate memo</button>
          <button class="example" type="button" data-question="For CLM-1001, explain the strongest risk signals and the next human-review step.">Use evidence example</button>
          <span class="status" id="status">Trace view is enabled for this POC.</span>
        </div>
      </form>
    </section>

    <section class="panel" id="result" aria-live="polite">
      <div class="doc-head">
        <div class="eyebrow">Supervisor memo</div>
        <h2 class="doc-title" id="doc-title">Investigation result</h2>
        <div class="meta" id="meta"></div>
      </div>
      <article class="answer" id="answer"></article>
      <div class="trace-wrap">
        <details open>
          <summary>Supervisor orchestration trace</summary>
          <p class="trace-note">This is a safe execution trace: routing decisions, planes, functions, statuses, row counts, and stop reasons. It does not expose private model chain-of-thought or hidden prompts.</p>
          <div class="diagram" id="trace-diagram" role="list" aria-label="Supervisor trace path"></div>
          <div id="timeline"></div>
          <details>
            <summary>Raw trace JSON</summary>
            <pre class="raw" id="raw-trace"></pre>
          </details>
        </details>
      </div>
    </section>
  </main>
  <script>
    const form = document.getElementById("query-form");
    const question = document.getElementById("question");
    const submit = document.getElementById("submit");
    const status = document.getElementById("status");
    const result = document.getElementById("result");
    const answer = document.getElementById("answer");
    const meta = document.getElementById("meta");
    const diagram = document.getElementById("trace-diagram");
    const timeline = document.getElementById("timeline");
    const rawTrace = document.getElementById("raw-trace");

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch]));
    }
    function inline(value) {
      return escapeHtml(value).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
    }
    function formatAnswer(text) {
      const blocks = escapeHtml(text).split(/\n{2,}/);
      return blocks.map(block => {
        const lines = block.split("\n");
        if (lines.length && lines.every(line => line.trim().startsWith("- "))) {
          return "<ul>" + lines.map(line => "<li>" + inline(line.trim().slice(2)) + "</li>").join("") + "</ul>";
        }
        return "<p>" + block.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\n/g, "<br>") + "</p>";
      }).join("");
    }
    function value(label, text) {
      return `<div><div class="trace-label">${escapeHtml(label)}</div><div class="trace-value">${escapeHtml(text)}</div></div>`;
    }
    function list(valueToShow) {
      return Array.isArray(valueToShow) && valueToShow.length ? valueToShow.join(", ") : "none";
    }
    function renderQueryResults(results) {
      return (results || []).map(item => {
        const calls = (item.calls || []).map(call => `<div class="call"><strong>${escapeHtml(call.function || item.tool || "tool")}</strong> · ${escapeHtml(call.status || "unknown")} · ${escapeHtml(call.row_count ?? "n/a")} rows</div>`).join("");
        return `<div class="call"><strong>${escapeHtml(item.plane || "plane")}</strong> · ${escapeHtml(item.status || "unknown")}${calls}</div>`;
      }).join("");
    }
    function renderDiagram(trace) {
      const steps = [{kind:"request", label:"Request", main:trace.claim_id ? `Claim ${trace.claim_id}` : "Claim clarification", detail:"User question enters the supervisor"}];
      (trace.events || []).forEach(event => {
        const type = event.event || "event";
        if (type === "decision") {
          const planes = list(event.accepted_planes || event.requested_planes);
          steps.push({kind:"decision", label:`Decision · iteration ${event.iteration}`, main:event.enough_information ? "Enough information" : "Needs more evidence", detail:planes === "none" ? "No new planes selected" : `Accepted planes: ${planes}`});
        } else if (type === "query") {
          const planes = list(event.planes);
          const calls = (event.results || []).reduce((total, item) => total + (item.calls || []).length, 0);
          steps.push({kind:"query", label:`Query · iteration ${event.iteration}`, main:planes === "none" ? "No planes queried" : planes, detail:calls ? `${calls} governed function/tool call${calls === 1 ? "" : "s"}` : "No calls recorded"});
        } else if (type === "synthesis") {
          steps.push({kind:"synthesis", label:"Synthesis", main:"Memo generated", detail:event.stop_reason || "Supervisor completed"});
        }
      });
      return `<div class="diagram-title">Trace path</div>` + steps.map(step => `<div class="diagram-step" role="listitem"><div class="diagram-rail"><div class="diagram-dot"></div></div><div class="diagram-node ${escapeHtml(step.kind)}"><div class="diagram-kicker">${escapeHtml(step.label)}</div><div class="diagram-main">${escapeHtml(step.main)}</div><div class="diagram-detail">${escapeHtml(step.detail)}</div></div></div>`).join("");
    }
    function renderTrace(trace) {
      const events = trace.events || [];
      return events.map(event => {
        const type = event.event || "event";
        if (type === "decision") {
          return `<article class="trace-card"><h3>Decision · iteration ${escapeHtml(event.iteration)}</h3><div class="trace-grid">${value("Enough information", event.enough_information)}${value("Requested planes", list(event.requested_planes))}${value("Accepted planes", list(event.accepted_planes))}${value("Rejected planes", list(event.rejected_planes))}${value("Stop reason", event.stop_reason || "continue")}</div></article>`;
        }
        if (type === "query") {
          return `<article class="trace-card query"><h3>Query · iteration ${escapeHtml(event.iteration)}</h3><div class="trace-grid">${value("Planes", list(event.planes))}</div>${renderQueryResults(event.results)}</article>`;
        }
        return `<article class="trace-card synthesis"><h3>Synthesis</h3><div class="trace-grid">${value("Status", event.status)}${value("Answer source", event.answer_source || "n/a")}${value("Evidence planes", list(event.evidence_planes))}${value("Stop reason", event.stop_reason || "n/a")}</div></article>`;
      }).join("") || "<p class=\"trace-note\">No trace events were returned.</p>";
    }
    function showResponse(body) {
      const trace = body.custom_outputs && body.custom_outputs.supervisor_trace;
      const text = (body.output || []).flatMap(item => item.content || []).map(item => item.text || "").join("\n").trim();
      const claim = trace && trace.claim_id ? trace.claim_id : "No claim ID";
      document.getElementById("doc-title").textContent = trace && trace.claim_id ? `Triage memo · ${trace.claim_id}` : "Clarification required";
      meta.innerHTML = "";
      if (trace) {
        [value("Claim", claim), value("Iterations", trace.iterations), value("Stop reason", trace.stop_reason || "completed"), value("Planes queried", list(trace.queried_planes))].forEach(item => { meta.insertAdjacentHTML("beforeend", item); });
        diagram.innerHTML = renderDiagram(trace);
        timeline.innerHTML = renderTrace(trace);
        rawTrace.textContent = JSON.stringify(trace, null, 2);
      } else {
        diagram.innerHTML = "";
        timeline.innerHTML = "<p class=\"trace-note\">No trace returned.</p>";
        rawTrace.textContent = "";
      }
      answer.innerHTML = formatAnswer(text || "No answer was returned.");
      result.style.display = "block";
      result.scrollIntoView({behavior:"smooth", block:"start"});
    }
    form.addEventListener("submit", async event => {
      event.preventDefault();
      submit.disabled = true;
      status.className = "status";
      status.textContent = "Running the bounded supervisor loop…";
      try {
        const response = await fetch("/responses", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({input:[{role:"user", content:question.value}], custom_inputs:{debug_trace:true}})});
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || body.message || `HTTP ${response.status}`);
        showResponse(body);
        status.textContent = "Memo generated with trace.";
      } catch (error) {
        status.className = "status error";
        status.textContent = `Request failed: ${error.message}`;
      } finally { submit.disabled = false; }
    });
    document.querySelector(".example").addEventListener("click", event => { question.value = event.currentTarget.dataset.question; question.focus(); });
  </script>
</body>
</html>"""
