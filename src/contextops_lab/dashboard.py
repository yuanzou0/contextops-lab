"""Self-contained analytics dashboard generation."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Iterable

from .analytics import SEGMENTERS, segment_events
from .failures import analyze_failures
from .metrics import summarize
from .models import RequestEvent


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _cost_improvement(baseline: float, compressed: float) -> float:
    return (baseline - compressed) / baseline if baseline and baseline != float("inf") else 0.0


def build_dashboard(
    events: Iterable[RequestEvent],
    policy: dict,
    *,
    evidence_label: str,
) -> str:
    rows = list(events)
    metrics = summarize(rows)
    baseline = metrics["baseline"]
    compressed = metrics["compressed"]
    segments = segment_events(rows, SEGMENTERS.keys())
    failures = analyze_failures(rows)
    paired_tasks = len({event.task_id for event in rows})
    cost_improvement = _cost_improvement(
        baseline["cost_per_successful_task"], compressed["cost_per_successful_task"]
    )
    success_delta = compressed["task_success_rate"] - baseline["task_success_rate"]
    rules = policy.get("rules", [])
    mode_counts = {mode: sum(rule["mode"] == mode for rule in rules) for mode in ("off", "conservative", "balanced")}
    payload = json.dumps(
        {
            "segments": [segment.to_dict() for segment in segments],
            "failures": [failure.to_dict() for failure in failures],
        },
        separators=(",", ":"),
    )
    evidence = html.escape(evidence_label)
    production_state = "Production rollout locked" if not policy.get("production_ready") else "Production rollout eligible"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ContextOps Lab Analytics</title>
<style>
:root {{ color-scheme: dark; --bg:#07111f; --panel:#0d1b2d; --line:#223653; --text:#eef5ff; --muted:#94a9c5; --blue:#55a7ff; --green:#48d597; --amber:#ffbf69; --red:#ff7185; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:linear-gradient(145deg,#06101d,#0a1730 65%,#101b35); color:var(--text); font:14px/1.45 Inter,ui-sans-serif,system-ui,sans-serif; }}
main {{ max-width:1180px; margin:auto; padding:32px 22px 48px; }}
header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:24px; }}
h1 {{ margin:0; font-size:28px; letter-spacing:-.03em; }}
.sub {{ color:var(--muted); margin-top:5px; }}
.evidence {{ border:1px solid var(--amber); color:var(--amber); padding:7px 10px; border-radius:8px; white-space:nowrap; }}
.grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
.panel,.kpi {{ background:rgba(13,27,45,.92); border:1px solid var(--line); border-radius:14px; }}
.kpi {{ padding:17px; }} .kpi span {{ color:var(--muted); display:block; font-size:12px; }} .kpi strong {{ display:block; font-size:24px; margin-top:6px; }}
.content {{ display:grid; grid-template-columns:2fr 1fr; gap:14px; margin-top:14px; }}
.panel {{ padding:18px; }} h2 {{ font-size:16px; margin:0 0 14px; }}
.toolbar {{ display:flex; justify-content:space-between; align-items:center; gap:12px; }}
select {{ background:#081526; border:1px solid var(--line); color:var(--text); padding:7px 9px; border-radius:8px; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ text-align:left; padding:10px 8px; border-bottom:1px solid var(--line); }} th {{ color:var(--muted); font-weight:500; font-size:12px; }}
.mode {{ font-weight:600; }} .mode.off {{ color:var(--red); }} .mode.conservative {{ color:var(--amber); }} .mode.balanced {{ color:var(--green); }}
.bar-row {{ margin:12px 0; }} .bar-label {{ display:flex; justify-content:space-between; color:var(--muted); font-size:12px; }} .bar {{ height:8px; background:#081526; border-radius:99px; overflow:hidden; margin-top:5px; }} .bar i {{ display:block; height:100%; background:var(--blue); }}
.decision {{ display:flex; justify-content:space-between; gap:12px; align-items:center; }}
.decision strong {{ color:var(--amber); }} .counts {{ display:flex; gap:12px; color:var(--muted); }}
footer {{ color:var(--muted); margin-top:16px; font-size:12px; }}
@media (max-width:800px) {{ .grid {{ grid-template-columns:repeat(2,1fr); }} .content {{ grid-template-columns:1fr; }} header {{ flex-direction:column; }} }}
@media (max-width:480px) {{ .grid {{ grid-template-columns:1fr; }} main {{ padding:22px 12px; }} .table-wrap {{ overflow-x:auto; }} }}
</style>
</head>
<body><main>
<header><div><h1>ContextOps Lab</h1><div class="sub">Agent reliability, economics, and rollout decisions · {paired_tasks} paired tasks</div></div><div class="evidence">Evidence: {evidence}</div></header>
<section class="grid">
<div class="kpi"><span>Compressed task-proxy success</span><strong>{_pct(compressed['task_success_rate'])}</strong></div>
<div class="kpi"><span>Task-proxy delta</span><strong>{_pct(success_delta)}</strong></div>
<div class="kpi"><span>Cost / success improvement</span><strong>{_pct(cost_improvement)}</strong></div>
<div class="kpi"><span>Fallback rate</span><strong>{_pct(compressed['fallback_rate'])}</strong></div>
</section>
<section class="content">
<div class="panel"><div class="toolbar"><h2>Workload segmentation</h2><label>Dimension <select id="dimension"></select></label></div><div class="table-wrap"><table><thead><tr><th>Segment</th><th>Pairs</th><th>Task-proxy Δ</th><th>Cost improvement</th><th>Fallback</th><th>Recommendation</th></tr></thead><tbody id="segments"></tbody></table></div></div>
<div class="panel"><h2>Failure reasons</h2><div id="failures"></div></div>
</section>
<section class="panel" style="margin-top:14px"><div class="decision"><div><h2 style="margin-bottom:4px">Rollout decision</h2><strong>{production_state}</strong></div><div class="counts"><span>off {mode_counts['off']}</span><span>conservative {mode_counts['conservative']}</span><span>balanced {mode_counts['balanced']}</span></div></div></section>
<footer>Task-proxy outcomes are not semantic equivalence · Failed tasks remain in cost denominators · Policy defaults to off when evidence is non-production.</footer>
</main>
<script>
const DATA={payload};
const RULES={json.dumps({rule['value']: rule['mode'] for rule in rules}, separators=(',', ':'))};
const dims=[...new Set(DATA.segments.map(x=>x.dimension))];
const select=document.getElementById('dimension');
dims.forEach(d=>{{const o=document.createElement('option');o.value=d;o.textContent=d.replaceAll('_',' ');select.appendChild(o);}});
function pct(x){{return (x*100).toFixed(1)+'%'}}
function renderSegments(){{const tbody=document.getElementById('segments');tbody.textContent='';DATA.segments.filter(x=>x.dimension===select.value).forEach(x=>{{const mode=x.dimension==='task_type'?(RULES[x.value]||'off'):'—';const cost=x.treatment_cost_per_success_defined?pct(x.cost_improvement_rate):'N/A';const tr=document.createElement('tr');tr.innerHTML=`<td>${{x.value}}</td><td>${{x.paired_tasks}}</td><td>${{pct(x.success_rate_delta)}}</td><td>${{cost}}</td><td>${{pct(x.fallback_rate)}}</td><td class="mode ${{mode}}">${{mode}}</td>`;tbody.appendChild(tr);}})}}
function renderFailures(){{const root=document.getElementById('failures');if(!DATA.failures.length){{root.textContent='No recorded failure events.';return}}const max=Math.max(...DATA.failures.map(x=>x.count));DATA.failures.forEach(x=>{{const row=document.createElement('div');row.className='bar-row';row.innerHTML=`<div class="bar-label"><span>${{x.reason}}</span><span>${{x.count}}</span></div><div class="bar"><i style="width:${{100*x.count/max}}%"></i></div>`;root.appendChild(row);}})}}
select.addEventListener('change',renderSegments);select.value='task_type';renderSegments();renderFailures();
</script></body></html>"""


def write_dashboard(content: str, path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
