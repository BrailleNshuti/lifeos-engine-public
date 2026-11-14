"""Braille × LifeOS Learning Studio: focus, recall, exams, mastery, projects, reflection, and system health.

Supports both static single-file HTML export (`lifeos cockpit --export FILE`) and a live localhost web server
(`lifeos cockpit --serve [--port 8765]`) backed by store_lock and the privacy guard.
"""
import datetime as dt
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import secrets
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


def _parse_skills(home):
    p = Path(home) / "logs" / "skills.md"
    if not p.exists():
        return []
    skills = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6 or cells[0].lower() in ("skill", "---") or set(cells[0]) <= {"-"}:
            continue
        try:
            lvl = int(cells[1]) if cells[1].strip().isdigit() else 0
        except ValueError:
            lvl = 0
        try:
            tgt = int(cells[2]) if cells[2].strip().isdigit() else 4
        except ValueError:
            tgt = 4
        skills.append({
            "skill": cells[0],
            "level": lvl,
            "target": tgt,
            "proof": cells[3],
            "last_practice": cells[4],
            "next_proof": cells[5],
        })
    return skills


def _learning_profile(home, tasks, packs, skills, week):
    """Build a deterministic learning queue from tasks, practice dates and study packs."""
    today = dt.date.today()
    study_tasks = [t for t in tasks if t.get("lane") == "study" and t.get("status") != "done"]
    study_tasks.sort(key=lambda t: (t.get("due") or "9999-99-99", t.get("status") != "doing", t.get("id", "")))

    due_skills = []
    for skill in skills:
        raw = (skill.get("last_practice") or "").strip()
        try:
            practiced = dt.date.fromisoformat(raw[:10])
        except ValueError:
            practiced = None
        days = (today - practiced).days if practiced else None
        gap = max(0, int(skill.get("target", 0)) - int(skill.get("level", 0)))
        if gap and (days is None or days >= 7):
            due_skills.append({**skill, "days_since_practice": days, "gap": gap})
    due_skills.sort(key=lambda s: (-s["gap"], -(s["days_since_practice"] or 9999), s["skill"]))

    groups = {}
    for pack in packs:
        parts = pack["path"].split("/")
        group = parts[1] if len(parts) > 2 else "general"
        groups[group] = groups.get(group, 0) + 1

    exam_dir = Path(home) / "reviews"
    exams = []
    if exam_dir.is_dir():
        for path in sorted(exam_dir.glob("exam-*.md"), reverse=True):
            exams.append({"path": path.relative_to(home).as_posix(), "title": path.stem.replace("exam-", "Exam ")})

    level_total = sum(int(s.get("level", 0)) for s in skills)
    target_total = sum(max(1, int(s.get("target", 0))) for s in skills)
    mastery = round(100 * level_total / target_total) if target_total else 0
    hours_by_area = week.get("hours_by_area") or {}
    return {
        "focus_tasks": study_tasks[:3],
        "open_study_tasks": len(study_tasks),
        "due_skills": due_skills,
        "due_count": len(due_skills),
        "mastery_pct": mastery,
        "pack_groups": [{"name": name, "count": count} for name, count in sorted(groups.items())],
        "exam_drafts": exams,
        "study_hours": float(hours_by_area.get("study", 0) or 0),
        "german_hours": float(hours_by_area.get("german", 0) or 0),
    }


def build_cockpit_data(home, week=None, month=None):
    """Collect structured, privacy-guarded learning data for the LifeOS Cockpit."""
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

    week_data = week_numbers(home, week=week)
    packs = _list_study_packs(home)
    skills = _parse_skills(home)
    return {
        "now": _parse_now_sections(home),
        "week": week_data,
        "kaizen": system_health(home, month=month),
        "runs": summarize_runs(home, limit=15),
        "tasks": detailed_tasks,
        "study_packs": packs,
        "prompt_cards": _list_prompt_cards(home),
        "skills": skills,
        "learning": _learning_profile(home, detailed_tasks, packs, skills, week_data),
    }


COCKPIT_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0A0A0A">
<meta name="color-scheme" content="dark">
<title>Braille × LifeOS · cockpit</title>
<style>
:root{
  --ink:#0A0A0A;--surface:#111;--surface-2:#161513;--surface-3:#1D1B18;
  --line:rgba(255,255,255,.18);--line-strong:rgba(255,255,255,.30);--hair:rgba(255,255,255,.10);
  --text:rgba(255,255,255,.96);--mute:rgba(255,255,255,.70);--dim:rgba(255,255,255,.55);
  --copper:#D39A5E;--copper-ink:#7A4A1E;--mint:#7FB8A8;--steel:#8B9EB8;--clay:#B0746A;
  --paper:#EDEAE4;--on-paper:#1A1815;--on-paper-dim:#67604D;
  --font-display:Georgia,'Times New Roman',serif;--font-serif:Georgia,'Times New Roman',serif;
  --font-sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;
  --font-mono:ui-monospace,'Cascadia Mono',Consolas,monospace;
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
.learning-loop{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:12px}
.learning-step{padding:12px 8px;border:1px solid var(--hair);border-radius:10px;text-align:center;font-size:.78rem;color:var(--mute)}
.learning-step b{display:block;color:var(--text);font-family:var(--font-mono);font-size:.7rem;margin-bottom:4px}
.focus-card{background:linear-gradient(145deg,rgba(211,154,94,.16),rgba(127,184,168,.06));border-color:rgba(211,154,94,.42)}
.session-clock{font-family:var(--font-display);font-size:clamp(3.2rem,8vw,5.5rem);line-height:1;color:var(--copper)}
.soft{background:var(--surface-2)}
@media (max-width:679px){.learning-loop{grid-template-columns:1fr}.rail{position:relative;height:auto}.shell{display:block}}
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
    <div class="grp">Learning Studio</div>
    <button class="nav on" data-tab="learning"><span>#focus · Learn Today</span><span class="mono">01</span></button>
    <button class="nav" data-tab="study"><span>#library · IU & German</span><span class="mono">packs</span></button>
    <button class="nav" data-tab="recall"><span>#recall · Exams & Review</span><span class="mono" id="nav-recall-count"></span></button>
    <button class="nav" data-tab="mastery"><span>#mastery · Skill Map</span><span class="mono" id="nav-mastery"></span></button>
    <div class="grp">Plan & Reflect</div>
    <button class="nav" data-tab="projects"><span>#projects · Tasks</span><span class="mono" id="nav-tasks-count"></span></button>
    <button class="nav" data-tab="reflection"><span>#reflect · Weekly Loop</span><span class="mono">review</span></button>
    <div class="grp">System (secondary)</div>
    <button class="nav" data-tab="system"><span>#system · Reliability</span><span class="mono" id="nav-runs-count"></span></button>
  </aside>
  <main class="main" id="view"></main>
</div>
<div class="toast" id="toast"></div>
<script>
const DATA = __LIFEOS_DATA_JSON__;
const WRITE_NONCE = "__LIFEOS_WRITE_NONCE__";
let state = { tab: (location.hash.replace('#','') || 'learning'), lane: 'study', status: 'all', checkin: localStorage.getItem('lifeos_checkin_'+new Date().toISOString().slice(0,10)) || '', timerSec: 35*60, plannedMin: 35, timerRunning: false };

function esc(value){
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

function toast(msg){
  const el = document.getElementById('toast');
  el.textContent = msg; el.style.display = 'block';
  setTimeout(()=>{ el.style.display = 'none'; }, 3200);
}

async function apiPost(path, payload){
  try {
    const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json','X-LifeOS-Nonce':WRITE_NONCE}, body:JSON.stringify(payload)});
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
document.getElementById('nav-recall-count').textContent = DATA.learning.due_count;
document.getElementById('nav-mastery').textContent = DATA.learning.mastery_pct + '%';

function renderLearning(){
  const l = DATA.learning;
  const w = DATA.week;
  const focus = (l.focus_tasks || []).map((t, i) => `
    <li><span><b>${i+1}. ${esc(t.goal)}</b><br><span class="mono">${esc(t.id)}${t.due ? ' · due '+esc(t.due) : ''}</span></span><span class="pill copper">${esc(t.status)}</span></li>
  `).join('') || '<li><span>No open study task. Create one in #projects.</span></li>';
  const due = (l.due_skills || []).slice(0,5).map(s => `
    <li><span><b>${esc(s.skill)}</b><br><span class="mono">Level ${s.level} → ${s.target} · ${s.days_since_practice == null ? 'never practiced' : s.days_since_practice+' days ago'}</span></span><button class="chip" onclick="setTab('recall')">Retrieve</button></li>
  `).join('') || '<li><span>Nothing overdue. Use the exam draft for mixed retrieval.</span></li>';
  const mins = String(Math.floor(state.timerSec/60)).padStart(2,'0');
  const secs = String(state.timerSec%60).padStart(2,'0');
  return `
    <section class="hero">
      <div class="eyebrow">Learning Studio · Attempt → Retrieve → Explain → Test → Reflect</div>
      <h1>Learn something you can reproduce without AI.</h1>
      <p class="mono">The Cockpit now starts with study. Projects and system machinery stay secondary.</p>
      <div class="learning-loop">
        <div class="learning-step"><b>01 · ATTEMPT</b>Closed-book first</div>
        <div class="learning-step"><b>02 · RETRIEVE</b>Recall from memory</div>
        <div class="learning-step"><b>03 · EXPLAIN</b>Teach it aloud</div>
        <div class="learning-step"><b>04 · TEST</b>Solve or build</div>
        <div class="learning-step"><b>05 · REFLECT</b>Log the weak point</div>
      </div>
    </section>
    <div class="grid c4">
      <div class="card stat"><span class="eyebrow">Study This Week</span><div class="n">${l.study_hours} h</div><div class="l">IU / technical study</div></div>
      <div class="card stat"><span class="eyebrow">German This Week</span><div class="n">${l.german_hours} h</div><div class="l">Attempt-first practice</div></div>
      <div class="card stat"><span class="eyebrow">Recall Queue</span><div class="n">${l.due_count}</div><div class="l">Skills due for retrieval</div></div>
      <div class="card stat"><span class="eyebrow">Mastery</span><div class="n">${l.mastery_pct}%</div><div class="l">Verified level / target</div></div>
    </div>
    <div class="grid c2" style="margin-top:16px">
      <div class="card focus-card">
        <span class="eyebrow">Deep Study Session · AI stays closed until the attempt ends</span>
        <div class="session-clock" id="session-clock">${mins}:${secs}</div>
        <select id="session-topic" class="input">
          ${(l.focus_tasks||[]).map(t=>`<option value="${esc(t.goal)}">${esc(t.goal)}</option>`).join('')}
          <option value="Independent recall practice">Independent recall practice</option>
        </select>
        <input id="session-proof" class="input" placeholder="Proof goal: what will you solve, explain, or reproduce?">
        <div class="chips">
          ${[25,35,45].map(n=>`<button class="chip ${state.plannedMin===n?'on':''}" onclick="setSessionLength(${n})">${n} min</button>`).join('')}
        </div>
        <div class="chips">
          <button class="btn primary" id="timer-toggle" onclick="toggleTimer()">${state.timerRunning?'Pause':'Start closed-book block'}</button>
          <button class="btn" onclick="finishStudySession()">Finish & log learning</button>
        </div>
      </div>
      <div class="card">
        <span class="eyebrow">Hard Thing First · Study Queue</span>
        <h3>Your next three learning outcomes</h3>
        <ul class="list">${focus}</ul>
        <span class="eyebrow" style="margin-top:10px">Due for active recall</span>
        <ul class="list">${due}</ul>
      </div>
    </div>
    <div class="grid c2" style="margin-top:16px">
      <div class="card soft">
        <span class="eyebrow">Quick Learning Log</span>
        <select id="q-area" class="input"><option value="study">IU / technical study</option><option value="german">German</option><option value="lab">learning project</option></select>
        <input id="q-hours" class="input" type="number" step="0.25" placeholder="Focused hours">
        <input id="q-note" class="input" placeholder="What can you now do without help?">
        <button class="btn primary" onclick="submitHours()">Log deliberate practice</button>
      </div>
      <div class="card">
        <span class="eyebrow">Evidence, not activity</span>
        <h3>A strong study session ends with one proof</h3>
        <ul class="list">
          <li><span>Closed-book answer or derivation</span><span class="pill mint">Recall</span></li>
          <li><span>Passing test or working query</span><span class="pill mint">Apply</span></li>
          <li><span>Five-minute explanation aloud</span><span class="pill mint">Explain</span></li>
          <li><span>One error written for the next review</span><span class="pill copper">Reflect</span></li>
        </ul>
      </div>
    </div>
  `;
}

function renderRecall(){
  const l = DATA.learning;
  const due = (l.due_skills || []).map((s, idx) => `
    <div class="card">
      <div style="display:flex;justify-content:space-between;gap:8px"><h3>${esc(s.skill)}</h3><span class="pill copper">gap ${s.gap}</span></div>
      <div class="mono">Last practice: ${s.days_since_practice == null ? 'not recorded' : s.days_since_practice+' days ago'} · Current ${s.level}, target ${s.target}</div>
      <div class="notice"><b>Next proof:</b> ${esc(s.next_proof || 'Explain it, then solve one unseen problem.')}</div>
      <div class="chips"><button class="chip" onclick="markRecall(${idx},'again')">Again</button><button class="chip" onclick="markRecall(${idx},'hard')">Hard</button><button class="chip" onclick="markRecall(${idx},'good')">Good</button></div>
    </div>`).join('') || '<div class="card">No overdue skill. Run a mixed no-AI exam.</div>';
  const exams = (l.exam_drafts || []).map(e=>`<li><span><b>${esc(e.title)}</b><br><span class="mono">${esc(e.path)}</span></span><span class="pill mint">Ready</span></li>`).join('');
  return `
    <section class="hero"><div class="eyebrow">Active Recall · Spaced Review · No-AI Exams</div><h1>Prove what stayed in memory.</h1><p class="mono">Rate retrieval honestly. “Good” means you produced the answer before checking notes.</p></section>
    <div class="grid c3">
      <div class="card stat"><span class="eyebrow">Due Now</span><div class="n">${l.due_count}</div><div class="l">skill reviews</div></div>
      <div class="card stat"><span class="eyebrow">Exam Drafts</span><div class="n">${(l.exam_drafts||[]).length}</div><div class="l">offline, timed</div></div>
      <div class="card stat"><span class="eyebrow">Rule</span><div class="n">70%</div><div class="l">below this returns next month</div></div>
    </div>
    <h2 style="margin:22px 0 12px">Retrieval queue</h2><div class="grid c2">${due}</div>
    <div class="card" style="margin-top:16px"><span class="eyebrow">Monthly No-AI Exam</span><ul class="list">${exams || '<li>No exam draft found yet.</li>'}</ul><p class="mono">Open the file locally, disconnect AI help, use 60–90 minutes, then record the score with lifeos exam --score-skill.</p></div>
  `;
}

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
    const checks = (t.checklist||[]).map(c => `<li style="justify-content:flex-start"><input type="checkbox" ${c.done?'checked':''} disabled> <span style="${c.done?'text-decoration:line-through;color:var(--dim)':''}">${esc(c.text)}</span></li>`).join('');
    return `
      <div class="card">
        <div style="display:flex;justify-content:space-between;gap:8px;align-items:center">
          <span class="mono">${esc(t.id)}</span>
          <div style="display:flex;gap:6px">
            <span class="pill">${esc(t.lane)}</span>
            <span class="pill">${esc(t.level)}</span>
            <span class="pill ${pillColor}">${esc(t.status)}</span>
          </div>
        </div>
        <h3>${esc(t.goal)}</h3>
        ${t.done_when ? `<div class="notice"><b>Done when:</b> ${esc(t.done_when)}</div>` : ''}
        <div class="mono">Route: ${esc(t.route || 'Claude -> Codex')} ${t.due ? ' · Due: '+esc(t.due) : ''} · Results: ${Number(t.results_count)||0}</div>
        ${checks ? `<ul class="list">${checks}</ul>` : ''}
      </div>
    `;
  }).join('');
  return `
    <section class="hero">
      <div class="eyebrow">Hand-off Bus · tasks/T-YYMMDD-name.md</div>
      <h1>Study & Project Plan (${filtered.length})</h1>
      <p class="mono">Study is the default lane. Personal projects remain available without taking over the learning space.</p>
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
  const packs = (DATA.study_packs||[]).map(p => `<li><span><b>${esc(p.title)}</b><br><span class="mono">${esc(p.path)}</span></span><span class="pill mint">Pack Ready</span></li>`).join('');
  return `
    <section class="hero">
      <div class="eyebrow">Law 3 · Attempt First (25 to 45 min without AI) · IU 6 Modules & German B2</div>
      <h1>Curriculum Library & Technical German</h1>
      <p class="mono">Choose a pack only after defining the question you want to answer from memory.</p>
    </section>
    <div class="grid c2">
      <div class="card">
        <span class="eyebrow">Law 3 · Attempt-First Gate</span>
        <h2 id="session-clock">${mins}:${secs}</h2>
        <p class="mono">Work 35 minutes closed-book before asking ChatGPT, Codex or Claude for feedback.</p>
        <div class="chips">
          <button class="btn primary" id="timer-toggle" onclick="toggleTimer()">${state.timerRunning?'Pause Timer':'Start 35-min Attempt Block'}</button>
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

function renderCareer(){
  const skills = (DATA.skills||[]).map(s => {
    const pct = Math.min(100, Math.round((s.level / 5) * 100));
    return `
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <h3>${esc(s.skill)}</h3>
          <span class="pill ${s.level>=3?'mint':'copper'}">Lvl ${s.level} → Target ${s.target}</span>
        </div>
        <div class="bar ${s.level>=3?'mint':''}"><b style="width:${pct}%"></b></div>
        <div class="mono"><b>Verified Proof:</b> ${esc(s.proof || 'pending')}</div>
        <div class="notice"><b>Next Small Proof:</b> ${esc(s.next_proof || 'See learning/career-mastery/README.md')}</div>
      </div>
    `;
  }).join('');
  return `
    <section class="hero">
      <div class="eyebrow">Verified mastery · Evidence replaces course completion</div>
      <h1>Skill Map & Learning Progression</h1>
      <p class="mono">Full reference packs in learning/career-mastery/: README.md · certifications-and-prep.md · sql-and-data-engineering-lab.md · ml-dl-and-ai-engineering-lab.md</p>
    </section>
    <div class="grid c3">
      <div class="card">
        <span class="eyebrow">Track A · Data Engineer</span>
        <h3>Pipelines, SQL & Cloud IaC</h3>
        <p class="mono">SQL Window Functions · OLTP vs Star Schema · SCD Type 2 · Data Quality Contracts · Docker & Scheduled Pipelines · AWS S3/CloudFront/Terraform</p>
        <span class="pill mint">8-Step Ladder Ready</span>
      </div>
      <div class="card">
        <span class="eyebrow">Track B · ML Engineer</span>
        <h3>PyTorch, Vision & MLOps</h3>
        <p class="mono">Leakage-Free Pipelines · PyTorch Autograd & Training Loops · MobileNetV2/ResNet Vision (P3 SDNET2018) · FastAPI Serving & PSI Drift Monitoring</p>
        <span class="pill copper">Blueprints Ready</span>
      </div>
      <div class="card">
        <span class="eyebrow">Track C · AI Engineer</span>
        <h3>RAG, Agents & MCP</h3>
        <p class="mono">Hybrid Search (BM25 + Dense RRF) · Citation Faithfulness & Recall@k (P2 Docs) · Multi-Agent Orchestration & 13 MCP Tools (LifeOS Engine)</p>
        <span class="pill mint">Flagship Live</span>
      </div>
    </div>
    <div class="card" style="margin-top:16px">
      <span class="eyebrow">High-ROI Certifications & Exam Roadmap (learning/career-mastery/certifications-and-prep.md)</span>
      <ul class="list">
        <li><span><b>1. Goethe-Zertifikat B1 → B2 (D10 Language Gate)</b><br><span class="mono">B1 Target: May/Jun 2027 · B2 Target: Nov/Dec 2027 · Technical German (heise/golem) + 5-min monthly recordings</span></span><span class="pill copper">Priority 1</span></li>
        <li><span><b>2. AWS Certified Solutions Architect – Associate (SAA-C03) / CLF-C02</b><br><span class="mono">Target: Apr/May 2027 (right after DLBDSCC01 Cloud Computing exam) · IAM, VPC, S3 OAC, RDS Multi-AZ, FinOps</span></span><span class="pill mint">Prep Pack Ready</span></li>
        <li><span><b>3. HashiCorp Certified: Terraform Associate (003)</b><br><span class="mono">Target: May/Jun 2027 · State locking (S3+DynamoDB), modules, lifecycle, validates AWS Terraform repo</span></span><span class="pill mint">Prep Pack Ready</span></li>
        <li><span><b>4. AWS Machine Learning Engineer Associate (MLA-C01) / Databricks Data Engineer Associate</b><br><span class="mono">Target: Aug/Sep 2027 (after P2 & P3) · Medallion Lakehouse, Delta Lake, Point-in-Time Feature Joins, PSI Drift</span></span><span class="pill steel">Prep Pack Ready</span></li>
      </ul>
    </div>
    <h2 style="margin:22px 0 12px">12 Core Skills Ledger (logs/skills.md · Level 3 = Timed No-AI · Level 4 = Shipped)</h2>
    <div class="grid c2">${skills}</div>
  `;
}

function renderAgents(){
  const r = DATA.runs;
  const cards = (DATA.prompt_cards||[]).map(c => `<li><span><b>${esc(c.name)} (v${esc(c.version)})</b> — ${esc(c.goal)}<br><span class="mono">${esc(c.file)}</span></span><span class="pill copper">5/5 Offline Runner</span></li>`).join('');
  const runRows = (r.runs||[]).map(x => `<li><span><b class="mono">${esc(x.run_id)}</b> · ${esc(x.command)} · ${esc(x.model || (x.reviewers||[]).join(','))}<br><span class="mono">${esc(x.task || '')} · ${esc(x.started_at || x.date)}</span></span><span class="pill ${x.status==='ok'?'mint':'clay'}">${esc(x.status)}</span></li>`).join('');
  return `
    <section class="hero">
      <div class="eyebrow">Secondary system view · Reliability supports learning</div>
      <h1>System Health, Agents & Audit Trail</h1>
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
      <div class="eyebrow">Learning reflection · Weekly inner loop & monthly Kaizen</div>
      <h1>Reflect, Adjust, Repeat (${k.month})</h1>
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
  const button = document.getElementById('timer-toggle');
  if(button) button.textContent = state.timerRunning ? 'Pause' : 'Start closed-book block';
  if(state.timerRunning){
    window._timerInt = setInterval(()=>{
      if(state.timerSec > 0){
        state.timerSec--;
        const clock = document.getElementById('session-clock');
        if(clock){
          const mins = String(Math.floor(state.timerSec/60)).padStart(2,'0');
          const secs = String(state.timerSec%60).padStart(2,'0');
          clock.textContent = mins + ':' + secs;
        }
      } else {
        state.timerRunning = false;
        clearInterval(window._timerInt);
        if(button) button.textContent = 'Start closed-book block';
        toast('Attempt-first block complete. Explain the answer before opening AI feedback.');
      }
    }, 1000);
  }
}

function setSessionLength(minutes){
  if(state.timerRunning){ toast('Pause the current block before changing its length.'); return; }
  state.plannedMin = minutes;
  state.timerSec = minutes * 60;
  render();
}

async function finishStudySession(){
  const elapsedMin = state.plannedMin - (state.timerSec / 60);
  if(elapsedMin < 1){ toast('Study for at least one minute before logging the session.'); return; }
  const topicEl = document.getElementById('session-topic');
  const proofEl = document.getElementById('session-proof');
  const topic = topicEl ? topicEl.value : 'Study session';
  const proof = proofEl ? proofEl.value.trim() : '';
  const hours = Math.round((elapsedMin / 60) * 100) / 100;
  const note = (topic + (proof ? ' · proof: ' + proof : ' · recall proof pending')).slice(0,200);
  state.timerRunning = false;
  if(window._timerInt) clearInterval(window._timerInt);
  const res = await apiPost('/api/log', {action:'hours', area:'study', hours, note});
  if(res){ toast('Learning session logged: ' + elapsedMin.toFixed(0) + ' min'); location.reload(); }
}

function markRecall(index, rating){
  const skill = ((DATA.learning.due_skills || [])[index] || {}).skill || 'skill';
  const key = 'lifeos_recall_' + new Date().toISOString().slice(0,10);
  const rows = JSON.parse(localStorage.getItem(key) || '[]');
  rows.push({skill, rating, at:new Date().toISOString()});
  localStorage.setItem(key, JSON.stringify(rows));
  toast('Recall rated ' + rating + '. Log a proof after solving or explaining it.');
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
  if(state.tab === 'projects' || state.tab === 'tasks') el.innerHTML = renderTasks();
  else if(state.tab === 'study') el.innerHTML = renderStudy();
  else if(state.tab === 'recall') el.innerHTML = renderRecall();
  else if(state.tab === 'mastery' || state.tab === 'career') el.innerHTML = renderCareer();
  else if(state.tab === 'system' || state.tab === 'agents') el.innerHTML = renderAgents();
  else if(state.tab === 'reflection' || state.tab === 'loops') el.innerHTML = renderLoops();
  else el.innerHTML = renderLearning();
}
render();
</script>
</body>
</html>
"""


def render_cockpit_html(home, week=None, month=None, write_nonce=""):
    """Render the self-contained Braille × LifeOS cockpit HTML after scanning embedded data with the privacy guard."""
    data = build_cockpit_data(home, week=week, month=month)
    payload_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    findings = scan_text(payload_json, private_patterns(), allow_mark=False)
    blocks = [f for f in findings if f[1] == "BLOCK"]
    if blocks:
        kinds = ", ".join(sorted({f[2] for f in blocks}))
        raise ValueError(f"Cockpit export refused by privacy guard ({kinds}).")
    return (COCKPIT_HTML_TEMPLATE
            .replace("__LIFEOS_DATA_JSON__", payload_json)
            .replace("__LIFEOS_WRITE_NONCE__", write_nonce))


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
    write_nonce = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # pragma: no cover - quiet server logs
            return

        def _send_json(self, status, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _trusted_host(self):
            host = (self.headers.get("Host") or "").lower()
            name = host.rsplit(":", 1)[0].strip("[]")
            return name in ("127.0.0.1", "localhost", "::1")

        def _authorized_write(self):
            return secrets.compare_digest(self.headers.get("X-LifeOS-Nonce") or "", write_nonce)

        def _send_html(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._trusted_host():
                self._send_json(403, {"error": "Localhost access required."})
                return
            parsed = urlparse(self.path)
            if parsed.path == "/api/state":
                self._send_json(200, build_cockpit_data(home))
                return
            if parsed.path != "/":
                self._send_json(404, {"error": "Not found"})
                return
            self._send_html(render_cockpit_html(home, write_nonce=write_nonce).encode("utf-8"))

        def do_POST(self):
            if not self._trusted_host() or not self._authorized_write():
                self._send_json(403, {"error": "Local cockpit authorization required."})
                return
            parsed = urlparse(self.path)
            if (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower() != "application/json":
                self._send_json(415, {"error": "JSON request required."})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > 16_384:
                self._send_json(413, {"error": "Request too large."})
                return
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError("JSON object required")
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
            except Exception:
                self._send_json(400, {"error": "Invalid or unsafe request."})

    Handler.lifeos_write_nonce = write_nonce
    return Handler


def serve_cockpit(home, host="127.0.0.1", port=8765):  # pragma: no cover - interactive server loop
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Refused non-local host: cockpit server binds only to localhost.")
    server = HTTPServer((host, int(port)), make_cockpit_handler(home))
    try:
        server.serve_forever()
    finally:
        server.server_close()
