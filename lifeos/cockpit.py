"""Braille × LifeOS · cockpit: unified visual command centre across Personal, Education (IU & German), Lab, and Work Prompt Lab.

Supports both static single-file HTML export (`lifeos cockpit --export FILE`) and a live localhost web server
(`lifeos cockpit --serve [--port 8765]`) backed by store_lock and the privacy guard.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .guard import private_patterns, scan_text
from .kaizen import system_health
from .log import log_health, log_hours, log_ledger, log_proof
from .runs import summarize_runs
from .store import atomic_write_bytes
from .tasks import list_tasks, new_task
from .week import week_numbers


def _classify_lane(task_id, goal):
    combined = f"{task_id} {goal}".lower()
    if any(k in combined for k in ("prompt", "lab", "card", "console")):
        return "work"
    if any(k in combined for k in ("study", "exam", "german", "iu", "course", "math", "stats", "python")):
        return "study"
    if any(k in combined for k in ("engine", "kernel", "ask", "mcp", "iwa", "github", "plugin")):
        return "lab"
    return "personal"


def _parse_task_detail(path):
    raw = path.read_text(encoding="utf-8")
    meta = {}
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = parts[2]
        else:
            body = raw
    else:
        body = raw

    main_body, *results = re.split(r"^## Result.*$", body, flags=re.M)
    checklist = []
    for line in main_body.splitlines():
        m = re.match(r"^\s*-\s*\[(x| )\]\s*(.+)$", line, flags=re.I)
        if m:
            checklist.append({"done": m.group(1).lower() == "x", "text": m.group(2).strip()})

    tid = meta.get("id") or path.stem
    goal = meta.get("goal") or path.stem
    return {
        "id": tid,
        "goal": goal,
        "done_when": meta.get("done_when", ""),
        "route": meta.get("route", "Claude Code -> Codex review"),
        "level": meta.get("level", "L2"),
        "status": meta.get("status", "inbox"),
        "due": meta.get("due", ""),
        "lane": _classify_lane(tid, goal),
        "checklist": checklist,
        "results_count": len(results),
        "latest_result": results[-1].strip()[:600] if results else "",
    }


def _parse_now_sections(home):
    now_path = Path(home) / "now.md"
    if not now_path.exists():
        return {"bets": [], "top3": [], "deadlines": []}
    text = now_path.read_text(encoding="utf-8")

    def grab_list(header):
        m = re.search(rf"^{re.escape(header)}.*?\n(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
        if not m:
            return []
        items = []
        for line in m.group(1).splitlines():
            cleaned = re.sub(r"^\s*(?:\d+\.|-)\s*", "", line).strip()
            if cleaned:
                items.append(cleaned)
        return items

    return {
        "bets": grab_list("## Bets"),
        "top3": grab_list("## Top 3"),
        "deadlines": grab_list("## Deadlines"),
    }


def _list_study_packs(home):
    learning = Path(home) / "learning"
    if not learning.is_dir():
        return []
    packs = []
    for p in sorted(learning.rglob("*.md")):
        rel = p.relative_to(home).as_posix()
        first_line = (p.read_text(encoding="utf-8").splitlines() or [rel])[0].lstrip("# ").strip()
        packs.append({"path": rel, "title": first_line[:90]})
    return packs


def _list_prompt_cards(home):
    cards_dir = Path(home) / "prompts" / "cards" / "final"
    if not cards_dir.is_dir():
        return []
    out = []
    for p in sorted(cards_dir.glob("*.md")):
        if p.name.lower() == "readme.md":
            continue
        txt = p.read_text(encoding="utf-8")
        name_m = re.search(r"^name:\s*(.+)$", txt, re.M)
        ver_m = re.search(r"^version:\s*(.+)$", txt, re.M)
        goal_m = re.search(r"^goal:\s*(.+)$", txt, re.M)
        out.append({
            "file": p.relative_to(home).as_posix(),
            "name": name_m.group(1).strip() if name_m else p.stem,
            "version": ver_m.group(1).strip() if ver_m else "1",
            "goal": goal_m.group(1).strip() if goal_m else "",
        })
    return out


def build_cockpit_data(home, week=None, month=None):
    """Collect structured, privacy-guarded data for the LifeOS Cockpit from the data repository."""
    home = Path(home)
    tasks_dir = home / "tasks"
    detailed_tasks = []
    if tasks_dir.is_dir():
        for p in sorted(tasks_dir.glob("T-*.md")):
            detailed_tasks.append(_parse_task_detail(p))
    else:
        for t in list_tasks(home):
            detailed_tasks.append({
                **t, "done_when": "", "route": "", "level": "L2",
                "lane": _classify_lane(t["id"], t["goal"]), "checklist": [],
                "results_count": 0, "latest_result": "",
            })

    return {
        "now": _parse_now_sections(home),
        "week": week_numbers(home, week=week),
        "kaizen": system_health(home, month=month),
        "runs": summarize_runs(home, limit=15),
        "tasks": detailed_tasks,
        "study_packs": _list_study_packs(home),
        "prompt_cards": _list_prompt_cards(home),
    }


COCKPIT_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0A0A0A">
<meta name="color-scheme" content="dark">
<title>Braille × LifeOS · cockpit</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500&family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;1,6..72,400&family=Inter:wght@400;500;600&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
:root{
  --ink:#0A0A0A;--surface:#111;--surface-2:#161513;--surface-3:#1D1B18;
  --line:rgba(255,255,255,.18);--line-strong:rgba(255,255,255,.30);--hair:rgba(255,255,255,.10);
  --text:rgba(255,255,255,.96);--mute:rgba(255,255,255,.70);--dim:rgba(255,255,255,.55);
  --copper:#D39A5E;--copper-ink:#7A4A1E;--mint:#7FB8A8;--steel:#8B9EB8;--clay:#B0746A;
  --paper:#EDEAE4;--on-paper:#1A1815;--on-paper-dim:#67604D;
  --font-display:'Fraunces',Georgia,serif;--font-serif:'Newsreader',Georgia,serif;
  --font-sans:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --font-mono:'Space Mono',ui-monospace,Consolas,monospace;
  --r:14px;--r-s:8px;--gutter:clamp(16px,4vw,36px);
}
*,*::before,*::after{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--text);font-family:var(--font-sans);line-height:1.55;min-height:100dvh}
h1,h2,h3{margin:0;font-weight:400;line-height:1.15}
h1{font-family:var(--font-display);font-size:clamp(1.85rem,4vw,2.75rem);font-weight:300}
h2{font-family:var(--font-display);font-size:clamp(1.3rem,2.3vw,1.75rem);font-weight:300}
h3{font-size:1.05rem;font-weight:600}
.eyebrow{font-family:var(--font-mono);font-size:.73rem;letter-spacing:.14em;text-transform:uppercase;color:var(--copper)}
.mono{font-family:var(--font-mono);font-size:.75rem;color:var(--mute)}
.shell{display:grid;min-height:100dvh}
@media (min-width:900px){.shell{grid-template-columns:240px minmax(0,1fr)}}
.rail{border-right:1px solid var(--hair);padding:20px 14px;background:var(--ink);position:sticky;top:0;height:100dvh;overflow:auto}
.brand{padding:6px 10px 18px;border-bottom:1px solid var(--hair);margin-bottom:12px}
.brand b{font-family:var(--font-display);font-size:1.25rem;font-weight:400;display:block}
.grp{padding:14px 10px 6px;font-family:var(--font-mono);font-size:.68rem;letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
.nav{display:flex;align-items:center;justify-content:space-between;padding:9px 12px;border-radius:10px;text-decoration:none;color:var(--mute);font-size:.88rem;cursor:pointer;border:0;background:transparent;width:100%;text-align:left}
.nav:hover{background:var(--surface);color:var(--text)}
.nav.on{background:var(--surface-2);color:var(--text);border-left:2px solid var(--copper)}
.main{padding:var(--gutter);max-width:1220px;width:100%}
.hero{padding:10px 0 24px;border-bottom:1px solid var(--hair);margin-bottom:22px}
.hero h1{margin:8px 0 10px}
.grid{display:grid;gap:14px}
@media (min-width:680px){.grid.c2{grid-template-columns:1fr 1fr}.grid.c3{grid-template-columns:repeat(3,1fr)}.grid.c4{grid-template-columns:repeat(4,1fr)}}
.card{background:var(--surface);border:1px solid var(--hair);border-radius:var(--r);padding:18px;display:grid;gap:10px;align-content:start}
.stat .n{font-family:var(--font-display);font-size:2.1rem;font-weight:300;line-height:1}
.stat .l{color:var(--mute);font-size:.86rem}
.pill{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-family:var(--font-mono);font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;border:1px solid var(--line);color:var(--mute)}
.pill.copper{color:var(--copper);border-color:rgba(211,154,94,.45)}
.pill.mint{color:var(--mint);border-color:rgba(127,184,168,.45)}
.pill.steel{color:var(--steel);border-color:rgba(139,158,184,.45)}
.pill.clay{color:var(--clay);border-color:rgba(176,116,106,.45)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.chip{padding:7px 13px;border:1px solid var(--line);border-radius:999px;font-size:.82rem;cursor:pointer;background:transparent;color:var(--mute)}
.chip.on{border-color:var(--copper);background:rgba(211,154,94,.14);color:var(--text)}
.btn{padding:9px 15px;border-radius:10px;border:1px solid var(--line-strong);background:var(--surface-2);color:var(--text);cursor:pointer;font-size:.86rem;font-weight:500}
.btn.primary{background:var(--copper);color:#0A0A0A;border-color:var(--copper);font-weight:600}
.input{width:100%;padding:9px 12px;border-radius:8px;border:1px solid var(--line);background:var(--surface-2);color:var(--text);font-size:.88rem}
.bar{height:4px;background:var(--hair);border-radius:2px;overflow:hidden}
.bar b{display:block;height:100%;background:var(--copper)}
.bar.mint b{background:var(--mint)}
.list{list-style:none;margin:0;padding:0}
.list li{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--hair);font-size:.88rem}
.list li:first-child{border-top:0}
.paper{background:var(--paper);color:var(--on-paper);border-radius:var(--r);padding:clamp(20px,4vw,36px);font-family:var(--font-serif);font-size:1.04rem}
.paper h2{font-family:var(--font-display);color:var(--on-paper);margin-bottom:10px}
.notice{border-left:2px solid var(--copper);padding:10px 14px;background:rgba(211,154,94,.07);border-radius:0 8px 8px 0;font-size:.86rem}
.toast{position:fixed;right:24px;bottom:24px;background:var(--surface-3);border:1px solid var(--copper);padding:10px 16px;border-radius:999px;font-size:.85rem;display:none;z-index:99}
</style>
</head>
<body>
<div class="shell">
  <aside class="rail">
    <div class="brand">
      <span class="eyebrow">Personal AI OS · v2.4</span>
      <b>Braille · LifeOS</b>
      <span class="mono" id="week-badge"></span>
    </div>
    <div class="grp">Command Centre</div>
    <button class="nav on" data-tab="today"><span>#today · Focus & Check-in</span><span class="mono">01</span></button>
    <button class="nav" data-tab="tasks"><span>#tasks · All Lanes</span><span class="mono" id="nav-tasks-count"></span></button>
    <div class="grp">Growth & Study</div>
    <button class="nav" data-tab="study"><span>#study · IU & German</span><span class="mono">6 mod</span></button>
    <div class="grp">Machinery & Loops</div>
    <button class="nav" data-tab="agents"><span>#agents · Kernel & Router</span><span class="mono" id="nav-runs-count"></span></button>
    <button class="nav" data-tab="loops"><span>#loops · Kaizen & Code</span><span class="mono">12 laws</span></button>
  </aside>
  <main class="main" id="view"></main>
</div>
<div class="toast" id="toast"></div>
<script>
const DATA = __LIFEOS_DATA_JSON__;
let state = { tab: (location.hash.replace('#','') || 'today'), lane: 'all', status: 'all', checkin: localStorage.getItem('lifeos_checkin_'+new Date().toISOString().slice(0,10)) || '', timerSec: 35*60, timerRunning: false };

function toast(msg){
  const el = document.getElementById('toast');
  el.textContent = msg; el.style.display = 'block';
  setTimeout(()=>{ el.style.display = 'none'; }, 3200);
}

async function apiPost(path, payload){
  try {
    const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const d = await r.json();
    if(!r.ok) throw new Error(d.error || 'Request failed');
    return d;
  } catch(e) {
    toast('Static export mode (run `lifeos cockpit --serve` to write directly): ' + e.message);
    return null;
  }
}

function setTab(tab){
  state.tab = tab; location.hash = '#' + tab;
  document.querySelectorAll('.nav').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
  render();
}

document.querySelectorAll('.nav').forEach(b => b.addEventListener('click', () => setTab(b.dataset.tab)));
document.getElementById('week-badge').textContent = DATA.week.week + ' · ' + DATA.week.from + ' → ' + DATA.week.to;
document.getElementById('nav-tasks-count').textContent = DATA.tasks.length;
document.getElementById('nav-runs-count').textContent = DATA.runs.total_matching;

function renderToday(){
  const w = DATA.week;
  const h = w.health || {};
  const top3 = (DATA.now.top3 || []).map(x => `<li><span>${x}</span><span class="pill copper">Top 3</span></li>`).join('');
  const bets = (DATA.now.bets || []).map(x => `<li><span>${x}</span><span class="pill mint">Gate 2 Bet</span></li>`).join('');
  const dls = (DATA.now.deadlines || []).map(x => `<li><span>${x}</span><span class="pill clay">Deadline</span></li>`).join('');
  return `
    <section class="hero">
      <div class="eyebrow">Law 1 · Proof or it didn’t happen · Law 4 · Hard thing first</div>
      <h1>Are you in at 100 % on your hardest block today, Braille?</h1>
      <p class="mono">Personal · IU Applied AI (6 modules) · German B2 track · LifeOS Engine & iwa · employer Prompt Lab (synthetic only)</p>
      <div class="chips">
        <button class="btn ${state.checkin==='100%'?'primary':''}" onclick="saveCheckin('100%')">Yes — 100 % locked in</button>
        <button class="btn ${state.checkin==='low-energy'?'primary':''}" onclick="saveCheckin('low-energy')">Low energy — protect base & sleep</button>
        <button class="btn ${state.checkin==='exam-mode'?'primary':''}" onclick="saveCheckin('exam-mode')">Exam mode — study & Sunday review only</button>
      </div>
    </section>
    <div class="grid c4">
      <div class="card stat"><span class="eyebrow">Weekly Proofs</span><div class="n">${w.proofs}</div><div class="l">Logged in proofs.csv</div></div>
      <div class="card stat"><span class="eyebrow">Net AI Time Saved</span><div class="n">${w.net_hours_saved} h</div><div class="l">${w.ledger_lines} ledger lines</div></div>
      <div class="card stat"><span class="eyebrow">Focused Hours</span><div class="n">${w.total_hours || 0} h</div><div class="l">hours.csv this week</div></div>
      <div class="card stat"><span class="eyebrow">Health (${h.days || 0} d)</span><div class="n">${h.sleep_avg || '—'} h</div><div class="l">Gym ${h.gym_days || 0} d · Energy ${h.energy_avg || '—'}/5</div></div>
    </div>
    <div class="grid c2" style="margin-top:16px">
      <div class="card">
        <span class="eyebrow">This Week's Top 3 (Gate 0 / Gate 1)</span>
        <h3>Hard Thing First</h3>
        <ul class="list">${top3}</ul>
        <span class="eyebrow" style="margin-top:10px">Quarterly Bets until Gate 2 (17 Jan 2027)</span>
        <ul class="list">${bets}</ul>
      </div>
      <div class="card">
        <span class="eyebrow">Quick Daily Logger (store-locked & guard-checked)</span>
        <h3>Log Hours, Health or Proof</h3>
        <div class="grid c2">
          <select id="q-area" class="input"><option value="study">study (IU)</option><option value="german">german (A1→B2)</option><option value="lab">lab (Engine / iwa)</option><option value="work">work (employer hrs)</option></select>
          <input id="q-hours" class="input" type="number" step="0.5" placeholder="Hours (e.g. 1.5)">
        </div>
        <input id="q-note" class="input" placeholder="What did you prove or practice? (max 200 chars)">
        <button class="btn primary" onclick="submitHours()">Append to logs/hours.csv</button>
        <hr style="border:0;border-top:1px solid var(--hair);width:100%">
        <div class="grid c3">
          <input id="h-sleep" class="input" type="number" step="0.5" placeholder="Sleep h (7.5)">
          <select id="h-gym" class="input"><option value="yes">Gym: yes</option><option value="no">Gym: no</option></select>
          <input id="h-energy" class="input" type="number" min="1" max="5" placeholder="Energy 1-5">
        </div>
        <button class="btn" onclick="submitHealth()">Append to logs/health.csv</button>
      </div>
    </div>
    <div class="card" style="margin-top:16px">
      <span class="eyebrow">Fixed External Deadlines (D20 — no fake self-set dates)</span>
      <ul class="list">${dls}</ul>
    </div>
  `;
}

function renderTasks(){
  const lanes = ['all','personal','study','lab','work'];
  const statuses = ['all','doing','inbox','done'];
  const filtered = DATA.tasks.filter(t => (state.lane==='all' || t.lane===state.lane) && (state.status==='all' || t.status===state.status));
  const cards = filtered.map(t => {
    const pillColor = t.status==='done'?'mint':(t.status==='doing'?'copper':'steel');
    const checks = (t.checklist||[]).map(c => `<li style="justify-content:flex-start"><input type="checkbox" ${c.done?'checked':''} disabled> <span style="${c.done?'text-decoration:line-through;color:var(--dim)':''}">${c.text}</span></li>`).join('');
    return `
      <div class="card">
        <div style="display:flex;justify-content:space-between;gap:8px;align-items:center">
          <span class="mono">${t.id}</span>
          <div style="display:flex;gap:6px">
            <span class="pill">${t.lane}</span>
            <span class="pill">${t.level}</span>
            <span class="pill ${pillColor}">${t.status}</span>
          </div>
        </div>
        <h3>${t.goal}</h3>
        ${t.done_when ? `<div class="notice"><b>Done when:</b> ${t.done_when}</div>` : ''}
        <div class="mono">Route: ${t.route || 'Claude -> Codex'} ${t.due ? ' · Due: '+t.due : ''} · Results: ${t.results_count}</div>
        ${checks ? `<ul class="list">${checks}</ul>` : ''}
      </div>
    `;
  }).join('');
  return `
    <section class="hero">
      <div class="eyebrow">Hand-off Bus · tasks/T-YYMMDD-name.md</div>
      <h1>Unified Task Board (${filtered.length})</h1>
      <div class="chips">
        ${lanes.map(l => `<button class="chip ${state.lane===l?'on':''}" onclick="state.lane='${l}';render()">Lane: ${l}</button>`).join('')}
      </div>
      <div class="chips">
        ${statuses.map(s => `<button class="chip ${state.status===s?'on':''}" onclick="state.status='${s}';render()">Status: ${s}</button>`).join('')}
      </div>
    </section>
    <div class="card" style="margin-bottom:16px">
      <span class="eyebrow">Create Standardized Hand-Off File</span>
      <div class="grid c3">
        <input id="t-sentence" class="input" placeholder="One-sentence task goal...">
        <select id="t-level" class="input"><option value="L2">L2 (branch / PR)</option><option value="L1">L1 (organize)</option><option value="L3">L3 (needs my explicit yes)</option></select>
        <button class="btn primary" onclick="submitNewTask()">+ Create Task File</button>
      </div>
    </div>
    <div class="grid c2">${cards || '<div class="card">No matching tasks.</div>'}</div>
  `;
}

function renderStudy(){
  const mins = String(Math.floor(state.timerSec/60)).padStart(2,'0');
  const secs = String(state.timerSec%60).padStart(2,'0');
  const packs = (DATA.study_packs||[]).map(p => `<li><span><b>${p.title}</b><br><span class="mono">${p.path}</span></span><span class="pill mint">Pack Ready</span></li>`).join('');
  return `
    <section class="hero">
      <div class="eyebrow">Law 3 · Attempt First (25 to 45 min without AI) · IU 6 Modules & German B2</div>
      <h1>Study & Technical German Command</h1>
    </section>
    <div class="grid c2">
      <div class="card">
        <span class="eyebrow">Law 3 · Attempt-First Gate</span>
        <h2>${mins}:${secs}</h2>
        <p class="mono">Work 35 minutes closed-book before asking ChatGPT, Codex or Claude for feedback.</p>
        <div class="chips">
          <button class="btn primary" onclick="toggleTimer()">${state.timerRunning?'Pause Timer':'Start 35-min Attempt Block'}</button>
          <button class="btn" onclick="state.timerSec=35*60;state.timerRunning=false;render()">Reset</button>
        </div>
      </div>
      <div class="card">
        <span class="eyebrow">6 Semester Modules (Exam Window: 1–12 Mar 2027)</span>
        <ul class="list">
          <li><span><b>CSEBDSDSSE01 · Data Science Software Engineering</b><br><span class="mono">90-min written (90 pts: Terminology 20, Processes 25, Testing 20, CI/CD 25) + 48 terms</span></span><span class="pill copper">Pack Complete</span></li>
          <li><span><b>DLBDSNNDL · Neural Nets & Deep Learning</b><br><span class="mono">Oral assignment · backprop & attention</span></span><span class="pill mint">Units Ready</span></li>
          <li><span><b>DLBAIICV + DLBAIPCV · Computer Vision & Project</b><br><span class="mono">90-min written + project report</span></span><span class="pill mint">Units Ready</span></li>
          <li><span><b>DLBDSCC01 · Cloud Computing</b><br><span class="mono">90-min written · IaaS/PaaS/SaaS, containers, serverless</span></span><span class="pill mint">Units Ready</span></li>
          <li><span><b>DLBROIR01 · Introduction to Robotics</b><br><span class="mono">90-min written · kinematics, sensors, SLAM</span></span><span class="pill mint">Units Ready</span></li>
        </ul>
      </div>
    </div>
    <div class="card" style="margin-top:16px">
      <span class="eyebrow">Repository Learning Packs & Answer Keys (${(DATA.study_packs||[]).length} files in learning/)</span>
      <ul class="list">${packs}</ul>
    </div>
  `;
}

function renderAgents(){
  const r = DATA.runs;
  const cards = (DATA.prompt_cards||[]).map(c => `<li><span><b>${c.name} (v${c.version})</b> — ${c.goal}<br><span class="mono">${c.file}</span></span><span class="pill copper">5/5 Offline Runner</span></li>`).join('');
  const runRows = (r.runs||[]).map(x => `<li><span><b class="mono">${x.run_id}</b> · ${x.command} · ${x.model || (x.reviewers||[]).join(',')}<br><span class="mono">${x.task || ''} · ${x.started_at || x.date}</span></span><span class="pill ${x.status==='ok'?'mint':'clay'}">${x.status}</span></li>`).join('');
  return `
    <section class="hero">
      <div class="eyebrow">Execution Kernel Durable · 6-Question Router · Prompt Lab (rule 9)</div>
      <h1>Agents, Audit Trail & Work Prompt Lab</h1>
    </section>
    <div class="grid c3">
      <div class="card stat"><span class="eyebrow">Total Logged Runs</span><div class="n">${r.total_matching}</div><div class="l">Status ok: ${(r.by_status||{}).ok || 0}</div></div>
      <div class="card stat"><span class="eyebrow">Avg Duration</span><div class="n">${r.avg_duration_s || '—'} s</div><div class="l">Across measured runs</div></div>
      <div class="card stat"><span class="eyebrow">Context Tokens</span><div class="n">${r.total_context_tokens}</div><div class="l">Core cap <= 2,000 tok</div></div>
    </div>
    <div class="card" style="margin-top:16px">
      <span class="eyebrow">Work Lane Separation (rule 9) · employer Prompt Lab Cards</span>
      <h3>Synthetic Offline Prompt Cards</h3>
      <ul class="list">${cards}</ul>
    </div>
    <div class="card" style="margin-top:16px">
      <span class="eyebrow">Immutable Execution Kernel Audit (logs/runs.jsonl)</span>
      <ul class="list">${runRows}</ul>
    </div>
  `;
}

function renderLoops(){
  const k = DATA.kaizen;
  const wk = k.weakest_area || {};
  return `
    <section class="hero">
      <div class="eyebrow">Section 10 · Weekly Inner Loop & Monthly Kaizen Outer Loop</div>
      <h1>Self-Improving System Health (${k.month})</h1>
    </section>
    <div class="grid c2">
      <div class="card">
        <span class="eyebrow">Monthly System Health (lifeos kaizen)</span>
        <h3>5-Question Diagnostic (${k.from} to ${k.to})</h3>
        <ul class="list">
          <li><span><b>1. Routing waste:</b> ${k.routing_waste.total_runs} runs; non-ok: ${JSON.stringify(k.routing_waste.non_ok_statuses)}</span></li>
          <li><span><b>2. Move to Tier 0:</b> ${(k.tier0_candidates||[]).map(c=>c.task+' ('+c.count+'x)').join(', ') || 'none'}</span></li>
          <li><span><b>3. Top leverage change:</b> ${k.top_change}</span></li>
          <li><span><b>4. Weakest area (${wk.area}):</b> ${wk.proofs} proofs, ${wk.hours} h -> ${wk.experiment}</span></li>
          <li><span><b>5. Active 4-week trials:</b> ${(k.pending_trials||[]).length} in system/changes.md</span></li>
        </ul>
      </div>
      <div class="paper">
        <span class="eyebrow" style="color:#7A4A1E">Section 2.3 · The Code</span>
        <h2>The Twelve Laws of LifeOS</h2>
        <ol style="padding-left:20px;margin:0;display:grid;gap:6px">
          <li><b>Proof or it didn’t happen.</b> Links, passing tests, scores, recordings.</li>
          <li><b>Numbers decide.</b> The scoreboard, not mood, decides what changes.</li>
          <li><b>Attempt first.</b> 25–45 min without AI in learning blocks.</li>
          <li><b>Hard thing first.</b> First focused block goes to the avoided task.</li>
          <li><b>One flagship, one side project, one learning track.</b></li>
          <li><b>Evidence before confidence.</b> Dated sources + how it could be wrong.</li>
          <li><b>Blind and pre-committed reviews.</b> Reviewer never sees the first answer.</li>
          <li><b>You decide what matters (L3).</b> Money, job, residence, legal, public posts.</li>
          <li><b>Work stays at work; sensitive stays out.</b></li>
          <li><b>Light machinery, heavy standards.</b> Core under 2,000 tokens.</li>
          <li><b>Improve the system every week.</b> One 4-week trial per month.</li>
          <li><b>Recover to perform.</b> Sleep >= 7 h, gym, Saturday afternoon offline.</li>
        </ol>
      </div>
    </div>
  `;
}

function saveCheckin(val){
  state.checkin = val;
  localStorage.setItem('lifeos_checkin_'+new Date().toISOString().slice(0,10), val);
  toast('Check-in recorded: ' + val);
  render();
}

function toggleTimer(){
  state.timerRunning = !state.timerRunning;
  if(window._timerInt) clearInterval(window._timerInt);
  if(state.timerRunning){
    window._timerInt = setInterval(()=>{
      if(state.timerSec > 0){ state.timerSec--; render(); }
      else { state.timerRunning = false; clearInterval(window._timerInt); toast('35-min Attempt-First block complete! AI feedback unlocked.'); render(); }
    }, 1000);
  }
  render();
}

async function submitHours(){
  const area = document.getElementById('q-area').value;
  const hours = document.getElementById('q-hours').value;
  const note = document.getElementById('q-note').value;
  const res = await apiPost('/api/log', {action:'hours', area, hours, note});
  if(res){ toast('Logged to hours.csv: ' + res.line); location.reload(); }
}

async function submitHealth(){
  const sleep = document.getElementById('h-sleep').value;
  const gym = document.getElementById('h-gym').value;
  const energy = document.getElementById('h-energy').value;
  const res = await apiPost('/api/log', {action:'health', sleep, gym, energy});
  if(res){ toast('Logged to health.csv: ' + res.line); location.reload(); }
}

async function submitNewTask(){
  const sentence = document.getElementById('t-sentence').value;
  const level = document.getElementById('t-level').value;
  const res = await apiPost('/api/task', {sentence, level});
  if(res){ toast('Created ' + res.path); location.reload(); }
}

function render(){
  const el = document.getElementById('view');
  if(state.tab === 'tasks') el.innerHTML = renderTasks();
  else if(state.tab === 'study') el.innerHTML = renderStudy();
  else if(state.tab === 'agents') el.innerHTML = renderAgents();
  else if(state.tab === 'loops') el.innerHTML = renderLoops();
  else el.innerHTML = renderToday();
}
render();
</script>
</body>
</html>
"""


def render_cockpit_html(home, week=None, month=None):
    """Render the self-contained Braille × LifeOS cockpit HTML after scanning embedded data with the privacy guard."""
    data = build_cockpit_data(home, week=week, month=month)
    payload_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    findings = scan_text(payload_json, private_patterns(), allow_mark=False)
    blocks = [f for f in findings if f[1] == "BLOCK"]
    if blocks:
        kinds = ", ".join(sorted({f[2] for f in blocks}))
        raise ValueError(f"Cockpit export refused by privacy guard ({kinds}).")
    return COCKPIT_HTML_TEMPLATE.replace("__LIFEOS_DATA_JSON__", payload_json)


def export_cockpit(home, out_path=None, week=None, month=None):
    """Write the self-contained cockpit HTML file atomically."""
    home = Path(home)
    target = Path(out_path) if out_path else (home / "cockpit" / "index.html")
    target.parent.mkdir(parents=True, exist_ok=True)
    html = render_cockpit_html(home, week=week, month=month)
    atomic_write_bytes(target, html.encode("utf-8"))
    return target


def make_cockpit_handler(home):
    """Create a localhost HTTP handler serving the cockpit UI and JSON write endpoints."""
    home = Path(home)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # pragma: no cover - quiet server logs
            return

        def _send_json(self, status, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/state":
                self._send_json(200, build_cockpit_data(home))
                return
            html = render_cockpit_html(home).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        def do_POST(self):
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                body = json.loads(raw)
                if parsed.path == "/api/log":
                    act = body.get("action")
                    if act == "hours":
                        line = log_hours(home, body.get("area", ""), body.get("hours", ""), note=body.get("note", ""))
                    elif act == "health":
                        line = log_health(home, body.get("sleep", ""), body.get("gym", ""), body.get("energy", ""), note=body.get("note", ""))
                    elif act == "proof":
                        line = log_proof(home, body.get("area", ""), body.get("proof", ""), body.get("link", ""))
                    elif act == "ledger":
                        line = log_ledger(home, body.get("task", ""), body.get("model", ""), body.get("minutes", ""), body.get("note", ""))
                    else:
                        raise ValueError(f"Unknown log action '{act}'.")
                    self._send_json(200, {"ok": True, "line": line})
                    return
                if parsed.path == "/api/task":
                    path = new_task(home, body.get("sentence", ""), level=body.get("level", "L2"))
                    self._send_json(200, {"ok": True, "path": path.relative_to(home).as_posix()})
                    return
                self._send_json(404, {"error": "Not found"})
            except Exception as err:
                self._send_json(400, {"error": str(err)})

    return Handler


def serve_cockpit(home, host="127.0.0.1", port=8765):  # pragma: no cover - interactive server loop
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Refused non-local host: cockpit server binds only to localhost.")
    server = HTTPServer((host, int(port)), make_cockpit_handler(home))
    try:
        server.serve_forever()
    finally:
        server.server_close()
