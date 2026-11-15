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
from . import study
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


def _load_project_chamber(home):
    """Load the versioned, user-owned career project roadmap without coupling it to the engine."""
    path = Path(home) / "learning" / "career-mastery" / "project-building-chamber.json"
    empty = {
        "schema_version": 1,
        "updated": "",
        "region": "",
        "market_signals": [],
        "build_method": [],
        "projects": [],
        "interview_rubric": [],
        "sources": [],
    }
    if not path.is_file():
        return empty
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return empty
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return empty
    for key in ("market_signals", "build_method", "projects", "interview_rubric", "sources"):
        if not isinstance(payload.get(key), list):
            payload[key] = []
    payload["updated"] = str(payload.get("updated", ""))
    payload["region"] = str(payload.get("region", ""))
    return {**empty, **payload}


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


def _load_communications(home):
    """Load a credential-free channel manifest; secrets never enter the Cockpit export."""
    default = {
        "schema_version": 1,
        "channels": [
            {"id": "gmail", "label": "Gmail", "status": "setup", "detail": "ChatGPT connector available; account authorization still required."},
            {"id": "outlook", "label": "Outlook", "status": "setup", "detail": "ChatGPT connector available; account authorization still required."},
            {"id": "whatsapp", "label": "WhatsApp Business", "status": "planned", "detail": "Requires an official Meta business number, Cloud API and HTTPS webhooks."},
        ],
        "policy": {"read": "manual", "draft": "allowed", "send": "explicit_confirmation", "delete": "never"},
    }
    path = Path(home) / "system" / "communications.json"
    if not path.is_file():
        return default
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    if not isinstance(payload, dict) or not isinstance(payload.get("channels"), list):
        return default
    return {**default, **payload}


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
        "study_engine": study.study_snapshot(home, include_content=True),
        "project_chamber": _load_project_chamber(home),
        "communications": _load_communications(home),
    }


COCKPIT_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1B2821">
<meta name="color-scheme" content="light dark">
<title>Braille × LifeOS · cockpit</title>
<style>
:root{
  color-scheme:light;
  --desk:#F2F5F8;--paper:#FFFFFF;--paper-2:#E9EEF4;--ink:#141A23;--muted:#536071;--faint:#778397;
  --rail:#101723;--rail-2:#182233;--rail-text:#F7F9FC;--line:#D5DCE6;--line-strong:#AAB5C5;
  --blue:#5046E5;--red:#C43E4D;--moss:#087F72;--ochre:#B65B12;--shadow:0 24px 60px rgba(22,34,52,.10);
  --text:var(--ink);--mute:var(--muted);--dim:var(--faint);--surface:var(--paper);--surface-2:var(--paper-2);--surface-3:#232A25;
  --hair:rgba(28,26,23,.13);--copper:var(--ochre);--copper-ink:#704512;--mint:var(--moss);--steel:var(--blue);--clay:var(--red);
  --on-paper:var(--ink);--on-paper-dim:var(--muted);--font-display:'Segoe UI Variable Display','Segoe UI',Arial,sans-serif;
  --font-serif:'Segoe UI Variable Text','Segoe UI',Arial,sans-serif;--font-sans:'Segoe UI Variable Text','Segoe UI',Arial,sans-serif;--font-mono:'Cascadia Mono',Consolas,monospace;
  --r:14px;--r-s:9px;--gutter:clamp(18px,3.2vw,52px);
}
body.night{color-scheme:dark;--desk:#080B12;--paper:#111722;--paper-2:#182131;--ink:#F4F7FB;--muted:#B9C3D2;--faint:#8D99AB;--rail:#070A10;--rail-2:#101722;--rail-text:#F8FAFD;--line:#2E3A4C;--line-strong:#58677D;--blue:#9B96FF;--red:#FF8D9B;--moss:#55D6C2;--ochre:#FFB067;--shadow:0 28px 72px rgba(0,0,0,.45);--hair:rgba(244,247,251,.14);--text:#F4F7FB;--mute:#B9C3D2;--dim:#8D99AB;--surface:#111722;--surface-2:#182131;--on-paper:#F4F7FB;--on-paper-dim:#B9C3D2}
*,*::before,*::after{box-sizing:border-box}
html{scroll-behavior:smooth} body{margin:0;background:radial-gradient(circle at 72% -10%,color-mix(in srgb,var(--blue) 9%,transparent),transparent 35rem),var(--desk);color:var(--text);font-family:var(--font-sans);line-height:1.58;min-height:100dvh}
button,input,select,textarea{font:inherit} button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid color-mix(in srgb,var(--blue) 55%,transparent);outline-offset:2px}
h1,h2,h3{margin:0;line-height:1.12} h1{font:680 clamp(2.15rem,4.8vw,4.5rem)/.98 var(--font-display);letter-spacing:-.055em} h2{font:650 clamp(1.35rem,2.4vw,2.05rem)/1.1 var(--font-display);letter-spacing:-.025em} h3{font-size:1rem;font-weight:700}
.eyebrow{font:600 .68rem/1.4 var(--font-mono);letter-spacing:.13em;text-transform:uppercase;color:var(--ochre)} .mono{font:400 .72rem/1.55 var(--font-mono);color:var(--mute)}
.shell{display:grid;min-height:100dvh}.rail{padding:24px 15px;background:linear-gradient(180deg,var(--rail),var(--rail-2));color:var(--rail-text);position:sticky;top:0;height:100dvh;overflow:auto;z-index:5;border-right:1px solid rgba(255,255,255,.09)}
@media (min-width:920px){.shell{grid-template-columns:248px minmax(0,1fr)}}
.brand{padding:4px 10px 22px;border-bottom:1px solid rgba(255,255,255,.12);margin-bottom:11px}.brand b{font:700 1.25rem/1.2 var(--font-display);letter-spacing:-.035em;display:block;margin:3px 0}.brand .mono{color:rgba(247,249,252,.68)}
.rail-tools{display:flex;gap:6px;margin-top:13px}.rail-tool{border:1px solid rgba(255,255,255,.22);background:rgba(255,255,255,.04);color:var(--rail-text);padding:7px 10px;border-radius:8px;cursor:pointer;font-size:.72rem}
.grp{padding:17px 11px 6px;font:600 .62rem/1 var(--font-mono);letter-spacing:.14em;text-transform:uppercase;color:rgba(238,232,218,.43)}
.nav{display:flex;align-items:center;justify-content:space-between;padding:10px 11px;text-decoration:none;color:rgba(247,249,252,.72);font-size:.84rem;cursor:pointer;border:0;border-left:3px solid transparent;background:transparent;width:100%;text-align:left;border-radius:8px}
.nav:hover{background:rgba(255,255,255,.07);color:var(--rail-text)}.nav.on{background:linear-gradient(90deg,rgba(155,150,255,.20),rgba(155,150,255,.06));color:#fff;border-left-color:#A6A1FF}.nav .mono{color:rgba(247,249,252,.50)}
.main{padding:var(--gutter);max-width:1540px;width:100%;min-width:0}.hero{padding:clamp(20px,3vw,38px);border:1px solid var(--line);border-radius:22px;margin-bottom:24px;background:linear-gradient(135deg,color-mix(in srgb,var(--paper) 97%,var(--blue)),var(--paper));box-shadow:0 1px 0 rgba(255,255,255,.35)}.hero h1{max-width:920px;margin:10px 0 13px}.hero p{max-width:76ch;color:var(--muted);font-size:1.02rem}
.grid{display:grid;gap:15px}@media (min-width:700px){.grid.c2{grid-template-columns:repeat(2,minmax(0,1fr))}.grid.c3{grid-template-columns:repeat(3,minmax(0,1fr))}.grid.c4{grid-template-columns:repeat(4,minmax(0,1fr))}}
.card{background:var(--paper);color:var(--text);border:1px solid var(--line);border-radius:var(--r);padding:20px;display:grid;gap:11px;align-content:start;box-shadow:0 1px 2px rgba(22,34,52,.05)}.card:hover{border-color:var(--line-strong)}
.stat{box-shadow:none;border-width:0 0 1px;background:transparent;padding:14px 2px}.stat .n{font:400 2.4rem/1 var(--font-display)}.stat .l{color:var(--mute);font-size:.8rem}
.pill{display:inline-flex;align-items:center;gap:6px;padding:3px 8px;border-radius:2px;font:600 .62rem/1.4 var(--font-mono);letter-spacing:.055em;text-transform:uppercase;border:1px solid var(--line);color:var(--mute)}.pill.copper{color:var(--ochre);border-color:color-mix(in srgb,var(--ochre) 45%,var(--line))}.pill.mint{color:var(--moss);border-color:color-mix(in srgb,var(--moss) 45%,var(--line))}.pill.steel{color:var(--blue);border-color:color-mix(in srgb,var(--blue) 45%,var(--line))}.pill.clay{color:var(--red);border-color:color-mix(in srgb,var(--red) 45%,var(--line))}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin:9px 0}.chip{padding:7px 11px;border:1px solid var(--line);border-radius:2px;font-size:.78rem;cursor:pointer;background:transparent;color:var(--mute)}.chip:hover,.chip.on{border-color:var(--blue);color:var(--blue);background:color-mix(in srgb,var(--blue) 7%,transparent)}
.btn{padding:10px 15px;border-radius:9px;border:1px solid var(--line-strong);background:var(--paper);color:var(--text);cursor:pointer;font-size:.82rem;font-weight:700}.btn:hover{transform:translateY(-1px);border-color:var(--blue);box-shadow:0 6px 18px rgba(40,48,72,.12)}.btn.primary{background:var(--blue);color:#fff;border-color:var(--blue)}body.night .btn.primary{color:#0A0C12}.btn.danger{color:var(--red);border-color:var(--red)}
.input{width:100%;padding:11px 12px;border-radius:9px;border:1px solid var(--line);background:var(--paper);color:var(--text);font-size:.86rem}.input::placeholder{color:var(--faint);opacity:1}select.input option{background:var(--paper);color:var(--text)}textarea.input{resize:vertical;line-height:1.55}
.bar{height:5px;background:var(--line);overflow:hidden}.bar b{display:block;height:100%;background:var(--ochre)}.bar.mint b{background:var(--moss)}
.list{list-style:none;margin:0;padding:0}.list li{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;padding:11px 0;border-top:1px solid var(--hair);font-size:.86rem}.list li:first-child{border-top:0}
.paper,.desk-paper{background:var(--paper);color:var(--on-paper);border:1px solid var(--line);border-radius:18px;padding:clamp(25px,4vw,54px);font:400 1.01rem/1.75 var(--font-serif);box-shadow:var(--shadow)}.paper h2,.desk-paper h2{font-family:var(--font-display);color:var(--on-paper);margin-bottom:10px}
.notice{border-left:3px solid var(--ochre);padding:10px 14px;background:color-mix(in srgb,var(--ochre) 8%,transparent);font-size:.84rem}.learning-loop{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--line);margin-top:18px}.learning-step{padding:11px;border-right:1px solid var(--line);font-size:.73rem;color:var(--mute)}.learning-step:last-child{border-right:0}.learning-step b{display:block;color:var(--text);font:650 .65rem var(--font-mono);margin-bottom:4px}
.focus-card{background:linear-gradient(160deg,var(--paper),color-mix(in srgb,var(--paper) 90%,var(--blue)));border-top:5px solid var(--blue);box-shadow:var(--shadow)}.session-clock{font:720 clamp(3.6rem,8vw,6.8rem)/.9 var(--font-display);letter-spacing:-.075em;color:var(--blue)}.soft{background:var(--paper-2)}
.atelier{display:grid;gap:18px;align-items:start}.syllabus{background:transparent;border:0;border-right:1px solid var(--line);padding-right:15px}.work-surface{min-width:0}.evidence-margin{border-left:1px solid var(--line);padding-left:16px;position:sticky;top:20px}.book-spine{display:block;width:100%;text-align:left;padding:11px 10px;border:0;border-bottom:1px solid var(--line);background:transparent;color:var(--mute);cursor:pointer}.book-spine:hover,.book-spine.on{color:var(--text);border-left:3px solid var(--blue);padding-left:13px;background:color-mix(in srgb,var(--blue) 10%,transparent)}
.note-body{white-space:pre-wrap;word-wrap:break-word;font:400 1rem/1.72 var(--font-serif);max-width:78ch;margin:0}.margin-note{padding:12px 0;border-bottom:1px solid var(--line);font-size:.8rem}.margin-note b{display:block;color:var(--blue)}
.trust-pipeline{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);margin:12px 0}.trust-step{padding:12px;border-right:1px solid var(--line);font-size:.75rem}.trust-step:last-child{border:0}.trust-step strong{display:block;font-family:var(--font-mono);font-size:.66rem;text-transform:uppercase;color:var(--blue)}
.review-prompt{font:400 clamp(1.55rem,3.2vw,2.55rem)/1.2 var(--font-display);max-width:26ch}.answer-sheet{border-left:4px solid var(--moss);background:color-mix(in srgb,var(--moss) 8%,var(--paper));padding:20px;font-family:var(--font-serif);line-height:1.7}.exam-seal{border:1px dashed var(--red);padding:14px;color:var(--red);font-family:var(--font-mono)}
.project-card summary{cursor:pointer;list-style:none}.project-card summary::-webkit-details-marker{display:none}.project-meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}.steps{counter-reset:build-step;list-style:none;margin:0;padding:0;display:grid;gap:8px}.steps li{counter-increment:build-step;padding:10px 12px 10px 40px;border-top:1px solid var(--line);position:relative;font-size:.84rem}.steps li::before{content:counter(build-step);position:absolute;left:10px;color:var(--ochre);font-family:var(--font-mono)}.interview{border-top:4px solid var(--blue)}.rubric{display:grid;gap:7px}.rubric label{display:flex;gap:8px;align-items:flex-start;font-size:.82rem;color:var(--mute)}
.channel-grid{display:grid;gap:13px}.channel{display:grid;grid-template-columns:42px minmax(0,1fr) auto;gap:13px;align-items:start}.channel-mark{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;background:color-mix(in srgb,var(--blue) 12%,var(--paper));color:var(--blue);font:750 .78rem var(--font-mono)}.channel p{margin:4px 0 0;color:var(--muted);font-size:.82rem}.permission-ladder{counter-reset:permission;list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line)}.permission-ladder li{counter-increment:permission;padding:15px;border-right:1px solid var(--line);font-size:.78rem}.permission-ladder li:last-child{border-right:0}.permission-ladder li::before{content:'0' counter(permission);display:block;color:var(--ochre);font:650 .66rem var(--font-mono);margin-bottom:7px}.reply-studio{border-top:5px solid var(--moss)}.reply-actions{display:flex;flex-wrap:wrap;gap:8px}.privacy-note{display:flex;gap:10px;align-items:flex-start;color:var(--muted);font-size:.78rem}.privacy-note b{color:var(--moss)}
.journey-tabs{display:flex;gap:7px;overflow:auto;padding-bottom:8px}.journey-step{position:relative;padding:14px 14px 14px 48px;border:1px solid var(--line);border-radius:12px;margin:9px 0;background:var(--paper);cursor:pointer;color:var(--text);width:100%;text-align:left}.journey-step::before{content:attr(data-step);position:absolute;left:13px;top:13px;width:24px;height:24px;border-radius:50%;display:grid;place-items:center;background:var(--paper-2);color:var(--muted);font:650 .65rem var(--font-mono)}.journey-step.complete::before{content:'✓';background:var(--moss);color:#07110F}.journey-step.current{border-color:var(--blue);box-shadow:0 0 0 3px color-mix(in srgb,var(--blue) 12%,transparent)}.journey-step.current::before{background:var(--blue);color:#0A0C12}.journey-step small{display:block;color:var(--muted);margin-top:3px}.streak-card{background:linear-gradient(140deg,color-mix(in srgb,var(--ochre) 14%,var(--paper)),var(--paper));border-color:color-mix(in srgb,var(--ochre) 45%,var(--line))}.streak-number{font:750 3.4rem/.9 var(--font-display);color:var(--ochre)}.gap-card{border-left:4px solid var(--red)}.score-badge{font:700 1.1rem var(--font-mono);color:var(--moss)}
.focus-mode .rail{display:none}.focus-mode .shell{display:block}.focus-mode .main{max-width:1100px;margin:auto}.focus-mode .evidence-margin,.focus-mode .syllabus{display:none}.focus-mode .atelier{display:block}.theme-toggle{margin-left:auto}
.toast{position:fixed;right:22px;bottom:22px;background:var(--rail);color:var(--rail-text);border-left:4px solid var(--ochre);padding:11px 16px;font-size:.82rem;display:none;z-index:99;box-shadow:var(--shadow)}
@media (min-width:1120px){.atelier{grid-template-columns:220px minmax(0,1fr) 290px}}@media (min-width:760px) and (max-width:1119px){.atelier{grid-template-columns:190px minmax(0,1fr)}.evidence-margin{grid-column:2;position:static;border-left:0;padding-left:0}}
@media (max-width:759px){.shell{display:block;width:100%;max-width:100vw}.rail{position:relative;height:auto;width:100vw;max-width:100vw;padding:14px 12px 10px;white-space:nowrap;overflow-x:auto}.brand{white-space:normal;padding:0 2px 12px;margin-bottom:9px}.brand b{font-size:1.2rem}.grp{display:none}.nav{display:inline-flex;width:auto;min-width:max-content;padding:9px 10px;border-left:0;border-bottom:2px solid transparent}.nav.on{border-left:0;border-bottom-color:var(--blue)}.nav .mono{display:none}.main{padding:22px 16px;overflow:hidden;width:100vw;max-width:100vw}.hero,.atelier,.work-surface{width:100%;max-width:100%;min-width:0}.hero{padding-top:6px}.hero h1,.hero p{max-width:100%;overflow-wrap:anywhere}.atelier{display:block}.syllabus{border-right:0;padding:0;margin-bottom:14px;min-width:0}.book-spine{white-space:normal;overflow-wrap:anywhere}.evidence-margin{position:static;border-left:0;padding:0;margin-top:14px}.learning-loop,.trust-pipeline,.permission-ladder{grid-template-columns:1fr}.learning-step,.trust-step,.permission-ladder li{border-right:0;border-bottom:1px solid var(--line)}.channel{grid-template-columns:42px minmax(0,1fr)}.channel>.pill{grid-column:2;justify-self:start}h1{font-size:2.45rem;overflow-wrap:anywhere}.paper,.desk-paper{padding:24px 18px;max-width:100%}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}.btn:hover{transform:none}}
</style>
</head>
<body>
<div class="shell">
  <aside class="rail">
    <div class="brand">
      <span class="eyebrow">Private Study Atelier</span>
      <b>Braille · LifeOS</b>
      <span class="mono" id="week-badge"></span>
      <div class="rail-tools"><button class="rail-tool" onclick="toggleFocus()">Focus</button><button class="rail-tool" id="theme-toggle" onclick="toggleTheme()">Use dark</button></div>
    </div>
    <div class="grp">Study Atelier</div>
    <button class="nav on" data-tab="learning"><span>01 · Study Desk</span><span class="mono">today</span></button>
    <button class="nav" data-tab="study"><span>02 · Source Library</span><span class="mono" id="nav-source-count"></span></button>
    <button class="nav" data-tab="practice"><span>03 · Recall Studio</span><span class="mono" id="nav-recall-count"></span></button>
    <button class="nav" data-tab="exam"><span>04 · Exam Forge</span><span class="mono" id="nav-exam-count"></span></button>
    <button class="nav" data-tab="mastery"><span>05 · Knowledge Map</span><span class="mono" id="nav-mastery"></span></button>
    <button class="nav" data-tab="build"><span>#build · Project Chamber</span><span class="mono" id="nav-project-count"></span></button>
    <div class="grp">Plan & Reflect</div>
    <button class="nav" data-tab="projects"><span>#projects · Tasks</span><span class="mono" id="nav-tasks-count"></span></button>
    <button class="nav" data-tab="reflection"><span>#reflect · Weekly Loop</span><span class="mono">review</span></button>
    <button class="nav" data-tab="communications"><span>#reply · Communication Hub</span><span class="mono">draft-first</span></button>
    <div class="grp">System (secondary)</div>
    <button class="nav" data-tab="system"><span>#system · Reliability</span><span class="mono" id="nav-runs-count"></span></button>
  </aside>
  <main class="main" id="view"></main>
</div>
<div class="toast" id="toast"></div>
<script>
const DATA = __LIFEOS_DATA_JSON__;
const WRITE_NONCE = "__LIFEOS_WRITE_NONCE__";
let state = { tab: (location.hash.replace('#','') || 'learning'), lane: 'study', status: 'all', projectTrack: 'all', projectStage: 'all', interviewProject: 0, interviewQuestion: 0, sourceQuery: '', selectedSource: 0, selectedCurriculum: 0, practiceIndex: 0, revealedAnswer: null, committedResponse: '', practiceStartedAt: Date.now(), examSession: null, examResults: [], checkin: localStorage.getItem('lifeos_checkin_'+new Date().toISOString().slice(0,10)) || '', timerSec: 35*60, plannedMin: 35, timerRunning: false };
if(localStorage.getItem('lifeos_theme') === 'night') document.body.classList.add('night');

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

function toggleFocus(){
  document.body.classList.toggle('focus-mode');
  toast(document.body.classList.contains('focus-mode') ? 'Focus mode · the desk is now quiet' : 'Atelier navigation restored');
}

function toggleTheme(){
  document.body.classList.toggle('night');
  localStorage.setItem('lifeos_theme', document.body.classList.contains('night') ? 'night' : 'day');
  syncThemeButton();
}

function syncThemeButton(){
  const button = document.getElementById('theme-toggle');
  if(button){
    const night = document.body.classList.contains('night');
    button.textContent = night ? 'Use light' : 'Use dark';
    button.setAttribute('aria-pressed', night ? 'true' : 'false');
  }
}

document.querySelectorAll('.nav').forEach(b => b.addEventListener('click', () => setTab(b.dataset.tab)));
document.addEventListener('keydown', event => {
  if(event.key === 'Escape' && document.body.classList.contains('focus-mode')) toggleFocus();
  if((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k'){
    event.preventDefault(); setTab('study'); setTimeout(()=>document.getElementById('source-search')?.focus(), 0);
  }
});
document.getElementById('week-badge').textContent = DATA.week.week + ' · ' + DATA.week.from + ' → ' + DATA.week.to;
document.getElementById('nav-tasks-count').textContent = DATA.tasks.length;
document.getElementById('nav-runs-count').textContent = DATA.runs.total_matching;
document.getElementById('nav-source-count').textContent = DATA.study_engine.source_count;
document.getElementById('nav-recall-count').textContent = DATA.study_engine.due_count;
document.getElementById('nav-exam-count').textContent = DATA.study_engine.exams.length;
document.getElementById('nav-mastery').textContent = DATA.learning.mastery_pct + '%';
document.getElementById('nav-project-count').textContent = (DATA.project_chamber.projects || []).length;
syncThemeButton();

function renderLearning(){
  const l = DATA.learning;
  const s = DATA.study_engine;
  const focus = (l.focus_tasks || []).map((t, i) => `
    <li><span><b>${i+1}. ${esc(t.goal)}</b><br><span class="mono">${esc(t.id)}${t.due ? ' · due '+esc(t.due) : ''}</span></span><span class="pill copper">${esc(t.status)}</span></li>
  `).join('') || '<li><span>No open study task. Choose one source and define a proof.</span></li>';
  const mins = String(Math.floor(state.timerSec/60)).padStart(2,'0');
  const secs = String(state.timerSec%60).padStart(2,'0');
  const verified = (s.trust_counts.verified || 0) + (s.trust_counts.trusted || 0);
  const streak = s.streak || {current:0,longest:0,active_days_7:0,nudge:'Complete one recall today.'};
  const weather = verified >= 10 && s.due_count <= 8 ? 'Clear for a timed mock' : verified ? 'Building — verify more coverage' : 'No trusted questions yet';
  return `
    <section class="hero">
      <div class="eyebrow">Study Atelier · Capture → Learn → Recall → Exam → Reflect</div>
      <h1>Make one idea yours today.</h1>
      <p>You do not need a perfect day. Choose one meaningful proof, attempt it without help, then leave the desk knowing exactly what changed.</p>
      <div class="learning-loop">
        <div class="learning-step"><b>01 · CAPTURE</b>Keep the source and its origin</div>
        <div class="learning-step"><b>02 · LEARN</b>Read for one clear outcome</div>
        <div class="learning-step"><b>03 · RECALL</b>Commit before revealing</div>
        <div class="learning-step"><b>04 · EXAM</b>Reproduce under constraints</div>
        <div class="learning-step"><b>05 · REFLECT</b>Name the misconception</div>
      </div>
    </section>
    <div class="atelier">
      <aside class="syllabus">
        <span class="eyebrow">Today’s choices</span>
        <ul class="list">${focus}</ul>
        <button class="book-spine" onclick="setTab('practice')"><b>Retrieve what is due</b><br><span class="mono">${s.due_count} question${s.due_count===1?'':'s'}</span></button>
        <button class="book-spine" onclick="setTab('study')"><b>Open the library</b><br><span class="mono">${s.source_count} grounded sources</span></button>
        <button class="book-spine" onclick="recoveryMode()"><b>Recovery mode</b><br><span class="mono">10 quiet minutes · no debt</span></button>
      </aside>
      <section class="work-surface desk-paper focus-card">
        <span class="eyebrow">Focus contract · AI stays closed until the attempt ends</span>
        <div class="session-clock" id="session-clock">${mins}:${secs}</div>
        <h2>What will exist when this block ends?</h2>
        <select id="session-topic" class="input">${(l.focus_tasks||[]).map(t=>`<option value="${esc(t.goal)}">${esc(t.goal)}</option>`).join('')}<option value="Independent recall practice">Independent recall practice</option></select>
        <input id="session-proof" class="input" placeholder="One proof: solved query, derivation, explanation, code or corrected error">
        <div class="chips">${[10,25,35,45].map(n=>`<button class="chip ${state.plannedMin===n?'on':''}" onclick="setSessionLength(${n})">${n} min</button>`).join('')}</div>
        <div class="chips"><button class="btn primary" id="timer-toggle" onclick="toggleTimer()">${state.timerRunning?'Pause':'Begin the contract'}</button><button class="btn" onclick="finishStudySession()">Finish with proof</button><button class="btn" onclick="toggleFocus()">Quiet the room</button></div>
      </section>
      <aside class="evidence-margin">
        <span class="eyebrow">Evidence margin</span>
        <div class="margin-note"><b>Exam weather</b>${esc(weather)}</div>
        <div class="margin-note"><b>Question trust</b>${verified} verified · ${s.trust_counts.grounded || 0} waiting for review</div>
        <div class="margin-note"><b>Learning rhythm</b>${l.study_hours} h technical · ${l.german_hours} h German this week</div>
        <div class="margin-note"><b>Proof shelf</b>${l.mastery_pct}% re-proved after the reset</div>
        <div class="margin-note"><b>Study streak</b>${streak.current} day${streak.current===1?'':'s'} · best ${streak.longest}</div>
        <p class="mono">Ctrl+K opens the source library. Escape leaves focus mode.</p>
      </aside>
    </div>
    <div class="grid c3" style="margin-top:22px">
      <section class="card streak-card"><span class="eyebrow">Evidence streak</span><div class="streak-number">${streak.current}</div><h3>${streak.active_days_7}/7 active days this week</h3><p>${esc(streak.nudge)}</p><button class="btn" onclick="setTab('practice')">Protect the chain</button></section>
      <section class="card soft"><span class="eyebrow">Quick evidence log</span><select id="q-area" class="input"><option value="study">IU / technical study</option><option value="german">German</option><option value="lab">learning project</option></select><input id="q-hours" class="input" type="number" step="0.25" placeholder="Focused hours"><input id="q-note" class="input" placeholder="What can you now reproduce without help?"><button class="btn primary" onclick="submitHours()">Place proof on the shelf</button></section>
      <section class="card"><span class="eyebrow">A useful ending</span><ul class="list"><li><span>Retrieve before rereading</span><span class="pill mint">Memory</span></li><li><span>Check against an exact source</span><span class="pill steel">Truth</span></li><li><span>Name the error, not your mood</span><span class="pill clay">Reflect</span></li><li><span>Choose the next smallest proof</span><span class="pill copper">Return</span></li></ul></section>
    </div>
  `;
}

function renderPractice(){
  const s = DATA.study_engine;
  const due = s.due || [];
  const q = due[Math.min(state.practiceIndex, Math.max(0,due.length-1))];
  const grounded = [];
  (s.banks||[]).forEach(bank=>(bank.questions||[]).forEach(question=>{ if(question.trust==='grounded') grounded.push({...question,bank_path:bank.path}); }));
  if(!q){
    return `<section class="hero"><div class="eyebrow">Recall Studio · commitment before feedback</div><h1>Your memory desk is clear.</h1><p>No verified question is due. Review grounded drafts below or open a source and create a bank.</p></section><div class="atelier"><aside class="syllabus"><span class="eyebrow">Trust queue</span>${grounded.slice(0,20).map((x,i)=>`<button class="book-spine" onclick="reviewGrounded('${esc(x.bank_path)}','${esc(x.id)}',${i})">${esc(x.prompt)}</button>`).join('')||'<p class="mono">No grounded drafts yet.</p>'}</aside><section class="desk-paper work-surface" id="grounded-review"><h2>Verification is part of learning.</h2><p>Select a grounded draft. Check its prompt, exact source answer and citation before promoting it to verified.</p></section><aside class="evidence-margin"><div class="margin-note"><b>Draft</b>Unusable for scoring</div><div class="margin-note"><b>Grounded</b>Exact source span exists</div><div class="margin-note"><b>Verified</b>You checked prompt and answer</div><div class="margin-note"><b>Trusted</b>Clean practice history</div></aside></div>`;
  }
  const evaluation = state.revealedAnswer?.evaluation;
  const feedback = state.revealedAnswer ? `<div class="answer-sheet"><span class="eyebrow">Corrective feedback</span>${evaluation?.graded?`<div class="score-badge">${Math.round((evaluation.score||0)*100)}% rubric coverage</div>${(evaluation.missing_concepts||[]).length?`<p><b>Repair these ideas:</b> ${(evaluation.missing_concepts||[]).map(esc).join(' · ')}</p>`:'<p>All explicit key points were present.</p>'}`:''}<p>${esc(state.revealedAnswer.answer)}</p><span class="mono">${esc(state.revealedAnswer.citation)}</span></div>${state.revealedAnswer.recorded?`<button class="btn primary" onclick="location.reload()">Continue to the next due item</button>`:`<div class="chips"><button class="chip" onclick="ratePractice('again')">Again · missed</button><button class="chip" onclick="ratePractice('hard')">Hard · partial</button><button class="chip" onclick="ratePractice('good')">Good · correct</button><button class="chip" onclick="ratePractice('easy')">Easy · fluent</button></div>`}` : `<button class="btn primary" onclick="revealPractice('${esc(q.id)}')">Commit answer & reveal source</button>`;
  return `
    <section class="hero"><div class="eyebrow">Recall Studio · ${state.practiceIndex+1} of ${due.length}</div><h1>Answer before you look.</h1><p class="mono">Source and answer remain sealed until you commit. “Good” means substantially correct without notes.</p></section>
    <div class="atelier">
      <aside class="syllabus"><span class="eyebrow">Due queue</span>${due.map((x,i)=>`<button class="book-spine ${i===state.practiceIndex?'on':''}" onclick="selectPractice(${i})"><b>${esc(x.prompt)}</b><br><span class="mono">${esc(x.trust)} · ${esc(x.due)}</span></button>`).join('')}</aside>
      <section class="desk-paper work-surface"><span class="eyebrow">Closed source · ${esc(q.type)} · difficulty ${Number(q.difficulty)||2}</span><div class="review-prompt">${esc(q.prompt)}</div><textarea id="recall-draft" class="input" rows="8" ${state.revealedAnswer?'disabled':''} placeholder="Commit your explanation, code outline or derivation here before revealing...">${esc(state.committedResponse)}</textarea>${feedback}</section>
      <aside class="evidence-margin"><div class="margin-note"><b>Source seal</b>${esc(q.source_path)}</div><div class="margin-note"><b>Trust</b>${esc(q.trust)} · SHA ${esc((q.source_sha256||'').slice(0,10))}</div><div class="margin-note"><b>Last result</b>${esc(q.last_rating || 'first retrieval')}</div><p class="mono">Answers are fetched only from the nonce-protected localhost server. Static exports never contain them.</p></aside>
    </div>`;
}

function renderRecall(){ return renderPractice(); }

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
  const s = DATA.study_engine;
  const sources = s.sources || [];
  const curricula = s.curricula || [];
  const curriculum = curricula[state.selectedCurriculum] || curricula[0];
  const candidate = sources[state.selectedSource];
  const selected = (candidate && curriculum?.steps?.some(step=>step.source_path===candidate.path)) ? candidate : sources.find(source=>source.path===curriculum?.steps?.[0]?.source_path) || sources[0];
  const bank = selected ? (s.banks||[]).find(b=>b.source && b.source.path===selected.path) : null;
  const steps = (curriculum?.steps || []).map((step,index)=>`<button class="journey-step ${esc(step.status)}" data-step="${String(index+1).padStart(2,'0')}" onclick="openJourneyStep('${esc(step.source_path)}')"><b>${esc(step.title)}</b><small>${(step.outcomes||[]).map(esc).join(' · ')}</small></button>`).join('');
  return `
    <section class="hero">
      <div class="eyebrow">Learning Journey · lesson → attempt → feedback → gap repair → exam</div>
      <h1>See where you came from and what comes next.</h1>
      <p>Choose a path, study the current lesson, generate grounded questions and prove recall. Progress moves only when an evidence-bearing attempt succeeds.</p>
      <div class="journey-tabs">${curricula.map((row,index)=>`<button class="chip ${index===state.selectedCurriculum?'on':''}" onclick="selectCurriculum(${index})">${esc(row.title)} · ${row.progress_pct}%</button>`).join('')}</div>
    </section>
    <div class="atelier">
      <aside class="syllabus">
        <span class="eyebrow">${esc(curriculum?.skill || 'Study path')}</span>
        <div class="bar" style="margin:10px 0"><b style="width:${Number(curriculum?.progress_pct)||0}%"></b></div>
        <span class="mono">${Number(curriculum?.completed_steps)||0} / ${curriculum?.steps?.length||0} lessons proved</span>
        <div style="margin-top:12px">${steps||'<p class="mono">Add a curriculum manifest to begin.</p>'}</div>
        <button class="btn" onclick="refreshCurriculum('${esc(curriculum?.id||'')}')">Generate missing questions</button>
      </aside>
      <section class="work-surface desk-paper">
        ${selected ? `<span class="eyebrow">${esc(selected.subject)} · source SHA ${esc(selected.sha256.slice(0,10))}</span><h2>${esc(selected.title)}</h2><pre class="note-body">${esc(selected.content || selected.excerpt)}</pre>` : '<h2>The desk is waiting.</h2><p>Paste a note in the capture margin, or add Markdown under learning/sources.</p>'}
      </section>
      <aside class="evidence-margin">
        <span class="eyebrow">Lesson evidence</span>
        ${selected ? `<div class="margin-note"><b>Path</b>${esc(selected.path)}</div><div class="margin-note"><b>Outline</b>${(selected.headings||[]).slice(0,8).map(h=>esc(h)).join('<br>') || 'No headings found'}</div><div class="margin-note"><b>Question bank</b>${bank ? bank.question_count+' questions · '+(bank.counts.verified||0)+' verified' : 'Not created yet'}</div><button class="btn primary" onclick="createQuestionBank('${esc(selected.path)}')">${bank?'Regenerate grounded bank':'Create grounded questions'}</button>` : ''}
        <hr style="border:0;border-top:1px solid var(--line);margin:18px 0">
        <span class="eyebrow">Capture a note</span>
        <input id="note-title" class="input" placeholder="Title">
        <input id="note-subject" class="input" placeholder="Subject, e.g. Cloud Computing">
        <input id="note-url" class="input" placeholder="Optional source URL">
        <textarea id="note-content" class="input" rows="8" placeholder="Paste trusted notes here. Markdown headings become grounded recall prompts."></textarea>
        <button class="btn" onclick="saveStudyNote()">Save to the local library</button>
      </aside>
    </div>
  `;
}

function renderExam(){
  const s = DATA.study_engine;
  const verified = (s.trust_counts.verified||0) + (s.trust_counts.trusted||0);
  const subjects = [...new Set((s.sources||[]).map(x=>x.subject).filter(Boolean))];
  const exams = (s.exams||[]).map(e=>`<li><span><b>${esc(e.title)}</b><br><span class="mono">${esc(e.path)}</span></span><button class="chip" onclick="copyText('${esc(e.path)}')">Copy path</button></li>`).join('');
  if(state.examSession){
    const session=state.examSession, q=session.questions[session.index];
    if(!q){
      const graded=state.examResults.filter(x=>x.evaluation?.graded), score=graded.length?Math.round(100*graded.reduce((sum,x)=>sum+(x.evaluation.score||0),0)/graded.length):0;
      return `<section class="hero"><div class="eyebrow">Quick test complete</div><h1>${score}% rubric coverage</h1><p>${graded.length} answers scored and added to your gap model. Weak concepts now return to Recall Studio and the source journey.</p></section><div class="grid c2"><section class="card"><h2>Result</h2><div class="streak-number">${score}%</div><p>${state.examResults.filter(x=>(x.evaluation?.score||0)<.7).length} answer(s) need repair.</p></section><section class="card gap-card"><h2>Next move</h2><p>Open Recall Studio for spaced repair, or revisit the cited lesson before trying a new test.</p><button class="btn primary" onclick="state.examSession=null;state.examResults=[];setTab('practice')">Open gap clinic</button></section></div>`;
    }
    return `<section class="hero"><div class="eyebrow">Interactive test · ${session.index+1} of ${session.questions.length}</div><h1>Commit before feedback.</h1><p>The answer stays sealed until submission. Each rubric-scored answer updates your gap and streak evidence.</p></section><section class="desk-paper" style="max-width:900px;margin:auto"><div class="bar"><b style="width:${Math.round(100*session.index/session.questions.length)}%"></b></div><div class="review-prompt" style="margin:30px 0">${esc(q.prompt)}</div><textarea id="exam-answer" class="input" rows="10" placeholder="Write the complete answer from memory..."></textarea><button class="btn primary" onclick="submitExamAnswer()">Lock answer and grade</button></section>`;
  }
  return `
    <section class="hero"><div class="eyebrow">Exam Forge · blueprint before questions · separate sealed key</div><h1>Practise the exam you will actually face.</h1><p>Only human-verified, source-grounded questions can enter a mock. The printable paper contains no answers; its key is written separately under learning/exam-keys.</p></section>
    <div class="trust-pipeline"><div class="trust-step"><strong>Draft · ${s.trust_counts.draft||0}</strong>Not eligible</div><div class="trust-step"><strong>Grounded · ${s.trust_counts.grounded||0}</strong>Exact source span</div><div class="trust-step"><strong>Verified · ${s.trust_counts.verified||0}</strong>Human checked</div><div class="trust-step"><strong>Trusted · ${s.trust_counts.trusted||0}</strong>Clean practice history</div></div>
    <div class="atelier">
      <aside class="syllabus"><span class="eyebrow">Blueprint coverage</span>${subjects.map(subject=>`<div class="margin-note"><b>${esc(subject)}</b>${(s.sources||[]).filter(x=>x.subject===subject).length} source(s)</div>`).join('')||'<p class="mono">Capture sources first.</p>'}</aside>
      <section class="desk-paper work-surface"><span class="eyebrow">Test now or freeze a paper</span><h2>Exam Blueprint</h2><label class="mono">Name</label><input id="exam-title" class="input" value="Practice Exam"><label class="mono">Subject or module</label><select id="exam-subject" class="input"><option value="">Mixed verified questions</option>${subjects.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('')}</select><div class="grid c2"><div><label class="mono">Questions</label><input id="exam-count" class="input" type="number" min="1" max="50" value="10"></div><div><label class="mono">Minutes</label><input id="exam-minutes" class="input" type="number" min="5" max="240" value="60"></div></div><div class="exam-seal">${verified} verified questions currently available. The engine refuses an exam larger than verified coverage.</div><div class="chips"><button class="btn primary" onclick="startQuickExam()">Start interactive test</button><button class="btn" onclick="forgeExam()">Create printable paper & key</button></div></section>
      <aside class="evidence-margin"><span class="eyebrow">Exam weather</span><div class="margin-note"><b>${verified>=10?'Ready for a mixed mock':'Coverage still building'}</b>${verified>=10?'You have enough verified items for a ten-question paper.':'Verify grounded questions in Recall Studio first.'}</div><div class="margin-note"><b>Realism rule</b>Match the IU format, points, allowed aids and time before treating a score as evidence.</div><button class="btn" onclick="setTab('practice')">Review question trust</button></aside>
    </div>
    <section class="card" style="margin-top:20px"><span class="eyebrow">Frozen exam papers</span><ul class="list">${exams||'<li>No frozen source-grounded exam yet.</li>'}</ul></section>`;
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
    <h2 style="margin:22px 0 12px">19-Skill Reset Ledger (Level 0 = fresh baseline · Level 3 = timed no-AI · Level 4 = shipped)</h2>
    <div class="notice" style="margin-bottom:12px"><b>Fresh start:</b> every progress bar is deliberately at zero. Old projects are study material; mastery returns only when you re-prove the skill from the basics.</div>
    <div class="grid c2">${skills}</div>
  `;
}

function renderProjectChamber(){
  const c = DATA.project_chamber || {};
  const projects = c.projects || [];
  const tracks = ['all', ...new Set(projects.map(p=>p.track).filter(Boolean))];
  const stages = ['all', ...new Set(projects.map(p=>p.stage).filter(Boolean))];
  const filtered = projects.filter(p => (state.projectTrack==='all' || p.track===state.projectTrack) && (state.projectStage==='all' || p.stage===state.projectStage));
  const signals = (c.market_signals || []).map(s => `
    <div class="card"><span class="eyebrow">${esc(s.name || s.signal)}</span><h3>${esc(s.demand || s.why || '')}</h3><p class="mono">${esc(s.proof || s.evidence || '')}</p></div>
  `).join('');
  const method = (c.build_method || []).map(s => `<li><b>${esc(s.stage || s.name)}</b><br><span class="mono">${esc(s.done_when || s.outcome || '')}</span></li>`).join('');
  const cards = filtered.map((p, projectIndex) => {
    const procedure = (p.procedure || []).map(step=>`<li>${esc(step)}</li>`).join('');
    const proofs = (p.proofs || []).map(x=>`<li><span>${esc(x)}</span><span class="pill mint">Evidence</span></li>`).join('');
    const metrics = (p.metrics || []).map(x=>`<span class="pill steel">${esc(x)}</span>`).join('');
    const questions = (p.interview_questions || []).map((q, questionIndex)=>`<button class="chip" onclick="beginInterview(${projects.indexOf(p)},${questionIndex})">${esc(q)}</button>`).join('');
    return `<details class="card project-card">
      <summary><span class="eyebrow">${esc(p.id)} · ${esc(p.stage)}</span><h3>${esc(p.title)}</h3><div class="project-meta"><span class="pill copper">${esc(p.track)}</span><span class="pill">${esc(p.scope || 'portfolio build')}</span>${(p.skills||[]).slice(0,4).map(x=>`<span class="pill">${esc(x)}</span>`).join('')}</div></summary>
      <div class="notice"><b>Why this shapes you:</b> ${esc(p.why)}</div>
      <p><b>Finished outcome:</b> ${esc(p.outcome)}</p>
      <span class="eyebrow">Build procedure</span><ol class="steps">${procedure}</ol>
      <span class="eyebrow">Proof required</span><ul class="list">${proofs}</ul>
      <div class="chips">${metrics}</div>
      <span class="eyebrow">Recruiter drill</span><div class="chips">${questions}</div>
    </details>`;
  }).join('');
  const project = projects[Math.min(state.interviewProject, Math.max(0, projects.length-1))] || {};
  const questions = project.interview_questions || ['What problem did you solve and why did it matter?'];
  const question = questions[state.interviewQuestion % questions.length];
  const rubric = (c.interview_rubric || ['Problem', 'Ownership', 'Metric', 'Trade-off', 'Learning']).map((x,i)=>`<label><input type="checkbox" class="interview-check" value="${i}"> ${esc(x)}</label>`).join('');
  return `
    <section class="hero">
      <div class="eyebrow">Market → Fundamentals → Build → Measure → Explain</div>
      <h1>Project Building Chamber</h1>
      <p class="mono">A ${esc(c.region || 'Germany / EU')} career forge, refreshed ${esc(c.updated || 'when market evidence changes')}. Build fewer shallow demos; build cumulative systems you can defend without AI.</p>
    </section>
    <h2 style="margin-bottom:12px">What the market is asking you to prove</h2>
    <div class="grid c3">${signals || '<div class="card">Market evidence is being prepared.</div>'}</div>
    <div class="grid c2" style="margin-top:16px">
      <div class="card"><span class="eyebrow">The production build method</span><ol class="steps">${method}</ol></div>
      <div class="card interview">
        <span class="eyebrow">Recruiter Room · Explain it without hiding behind the code</span>
        <select class="input" onchange="state.interviewProject=Number(this.value);state.interviewQuestion=0;render()">${projects.map((p,i)=>`<option value="${i}" ${i===state.interviewProject?'selected':''}>${esc(p.id)} · ${esc(p.title)}</option>`).join('')}</select>
        <h3>${esc(question)}</h3>
        <textarea id="interview-answer" class="input" rows="7" placeholder="Answer aloud first, then write: problem → your decision → evidence → trade-off → lesson."></textarea>
        <div class="rubric">${rubric}</div>
        <div class="chips"><button class="btn primary" onclick="saveInterviewAnswer()">Score & save locally</button><button class="btn" onclick="nextInterviewQuestion()">Next question</button></div>
        <p class="mono">Target: 90 seconds for a recruiter, 5 minutes for a hiring manager. Saved only in this browser.</p>
      </div>
    </div>
    <section class="hero" style="margin-top:22px"><div class="eyebrow">Cumulative portfolio roadmap · ${filtered.length} of ${projects.length}</div><h2>Choose the next proof, not the next tutorial</h2>
      <div class="chips">${tracks.map(x=>`<button class="chip ${state.projectTrack===x?'on':''}" onclick="state.projectTrack='${esc(x)}';render()">${esc(x)}</button>`).join('')}</div>
      <div class="chips">${stages.map(x=>`<button class="chip ${state.projectStage===x?'on':''}" onclick="state.projectStage='${esc(x)}';render()">${esc(x)}</button>`).join('')}</div>
    </section>
    <div class="grid c2">${cards || '<div class="card">No projects match these filters.</div>'}</div>
    <div class="card" style="margin-top:16px"><span class="eyebrow">Evidence sources</span><ul class="list">${(c.sources||[]).map(s=>`<li><span>${esc(s.label)}</span><a href="${esc(s.url)}" target="_blank" rel="noreferrer" class="mono">source ↗</a></li>`).join('')}</ul></div>
  `;
}

function beginInterview(projectIndex, questionIndex){
  state.interviewProject = projectIndex; state.interviewQuestion = questionIndex; setTab('build');
}

function nextInterviewQuestion(){
  const projects = (DATA.project_chamber || {}).projects || [];
  const p = projects[state.interviewProject] || {};
  state.interviewQuestion = (state.interviewQuestion + 1) % Math.max(1, (p.interview_questions || []).length);
  render();
}

function saveInterviewAnswer(){
  const answer = (document.getElementById('interview-answer') || {}).value || '';
  const checks = [...document.querySelectorAll('.interview-check')].filter(x=>x.checked).length;
  if(answer.trim().length < 40){ toast('Explain with enough detail to show ownership (at least 40 characters).'); return; }
  const key = 'lifeos_project_interviews';
  const rows = JSON.parse(localStorage.getItem(key) || '[]');
  const projects = (DATA.project_chamber || {}).projects || [];
  rows.push({project:(projects[state.interviewProject]||{}).id || '', question:state.interviewQuestion, score:checks, answer, at:new Date().toISOString()});
  localStorage.setItem(key, JSON.stringify(rows.slice(-50)));
  toast('Interview answer saved locally · self-score '+checks+'/'+document.querySelectorAll('.interview-check').length);
}

function recoveryMode(){
  state.plannedMin = 10;
  state.timerSec = 10 * 60;
  state.timerRunning = false;
  setTab(DATA.study_engine.due_count ? 'practice' : 'learning');
  toast('Recovery mode · one small proof, no backlog debt');
}

function filterSourceList(value){
  const query = String(value || '').trim().toLowerCase();
  document.querySelectorAll('[data-search]').forEach(node => {
    node.hidden = query && !String(node.dataset.search || '').includes(query);
  });
}

function selectCurriculum(index){
  state.selectedCurriculum = index;
  const curriculum = (DATA.study_engine.curricula || [])[index];
  const firstPath = curriculum?.steps?.[0]?.source_path;
  const sourceIndex = (DATA.study_engine.sources || []).findIndex(source=>source.path===firstPath);
  state.selectedSource = Math.max(0, sourceIndex);
  render();
}

function openJourneyStep(sourcePath){
  const sourceIndex = (DATA.study_engine.sources || []).findIndex(source=>source.path===sourcePath);
  if(sourceIndex >= 0){ state.selectedSource=sourceIndex; render(); }
}

async function refreshCurriculum(curriculum){
  const result = await apiPost('/api/study/refresh', {curriculum});
  if(result){ toast(`${result.created} bank(s) created · ${result.needs_verification} question(s) need review`); setTimeout(()=>location.reload(),600); }
}

async function saveStudyNote(){
  const title = (document.getElementById('note-title') || {}).value || '';
  const subject = (document.getElementById('note-subject') || {}).value || '';
  const source_url = (document.getElementById('note-url') || {}).value || '';
  const content = (document.getElementById('note-content') || {}).value || '';
  if(!title.trim() || !content.trim()){ toast('Give the note a title and useful content first.'); return; }
  const result = await apiPost('/api/study/note', {title, subject, source_url, content});
  if(result){ toast('Source saved · '+result.path); setTimeout(()=>location.reload(), 450); }
}

async function createQuestionBank(source){
  const existing = (DATA.study_engine.banks || []).find(bank => bank.source && bank.source.path === source);
  let overwrite = false;
  if(existing){
    overwrite = confirm('Regenerating replaces this bank, including its verification states. Continue only if the source changed.');
    if(!overwrite) return;
  }
  const result = await apiPost('/api/study/bank', {source, overwrite});
  if(result){ toast('Grounded question bank created · verify it in Recall Studio'); setTimeout(()=>{ location.hash='#practice'; location.reload(); }, 350); }
}

function selectPractice(index){
  state.practiceIndex = index;
  state.revealedAnswer = null;
  state.committedResponse = '';
  state.practiceStartedAt = Date.now();
  render();
}

async function revealPractice(questionId){
  const draft = ((document.getElementById('recall-draft') || {}).value || '').trim();
  if(draft.length < 12){ toast('Commit a real answer before opening the source.'); return; }
  const elapsed_seconds = Math.max(0, Math.round((Date.now() - state.practiceStartedAt) / 1000));
  const result = await apiPost('/api/study/submit', {question_id:questionId, response:draft, elapsed_seconds});
  if(result){ state.committedResponse=draft; state.revealedAnswer = result; render(); }
}

async function ratePractice(rating){
  const due = DATA.study_engine.due || [];
  const question = due[Math.min(state.practiceIndex, Math.max(0,due.length-1))];
  if(!question) return;
  const elapsed_seconds = Math.max(0, Math.round((Date.now() - state.practiceStartedAt) / 1000));
  const result = await apiPost('/api/study/attempt', {question_id:question.id, rating, elapsed_seconds, response:state.committedResponse});
  if(result){ toast('Review recorded · next due '+result.due); setTimeout(()=>location.reload(), 450); }
}

async function reviewGrounded(bankPath, questionId){
  const result = await apiPost('/api/study/review-answer', {question_id:questionId});
  if(!result) return;
  const desk = document.getElementById('grounded-review');
  if(!desk) return;
  desk.innerHTML = `<span class="eyebrow">Human verification · compare every word</span><h2>${esc(result.prompt)}</h2><div class="answer-sheet"><p>${esc(result.answer)}</p><span class="mono">${esc(result.citation)} · SHA ${esc((result.source_sha256||'').slice(0,12))}</span></div><p>Promote only when the prompt is clear, the answer is correct, and the citation really supports it.</p><div class="chips"><button class="btn primary" id="verify-question">Mark verified</button><button class="btn" id="reject-question">Return to draft</button></div>`;
  document.getElementById('verify-question').onclick = () => verifyGrounded(bankPath, questionId, 'verified');
  document.getElementById('reject-question').onclick = () => verifyGrounded(bankPath, questionId, 'draft');
}

async function verifyGrounded(bankPath, questionId, trust){
  const result = await apiPost('/api/study/trust', {bank:bankPath, question_id:questionId, trust});
  if(result){ toast('Question trust changed to '+trust); setTimeout(()=>location.reload(), 450); }
}

async function forgeExam(){
  const title = (document.getElementById('exam-title') || {}).value || 'Practice Exam';
  const subject = (document.getElementById('exam-subject') || {}).value || '';
  const count = Number((document.getElementById('exam-count') || {}).value || 10);
  const minutes = Number((document.getElementById('exam-minutes') || {}).value || 60);
  const result = await apiPost('/api/study/exam', {title, subject, count, minutes});
  if(result){ toast('Exam frozen · paper '+result.exam_path); setTimeout(()=>location.reload(), 600); }
}

function startQuickExam(){
  const count=Math.max(1,Math.min(20,Number((document.getElementById('exam-count')||{}).value||10)));
  const subject=((document.getElementById('exam-subject')||{}).value||'').toLowerCase();
  const questions=[];
  for(const bank of (DATA.study_engine.banks||[])){
    const sourceText=((bank.source||{}).title+' '+(bank.source||{}).path).toLowerCase();
    if(subject && !sourceText.includes(subject)) continue;
    for(const q of (bank.questions||[])) if(['verified','trusted'].includes(q.trust)) questions.push(q);
  }
  if(questions.length<count){ toast(`Only ${questions.length} verified questions match. Choose fewer or generate and verify more.`); return; }
  state.examSession={questions:questions.slice(0,count),index:0,started:Date.now()}; state.examResults=[]; render();
}

async function submitExamAnswer(){
  const session=state.examSession, q=session?.questions?.[session.index]; if(!q) return;
  const response=((document.getElementById('exam-answer')||{}).value||'').trim();
  if(response.length<12){toast('Write a complete attempt before grading.');return;}
  const result=await apiPost('/api/study/submit',{question_id:q.id,response,elapsed_seconds:Math.round((Date.now()-session.started)/1000)});
  if(result){state.examResults.push(result);session.index+=1;session.started=Date.now();render();}
}

async function copyText(value){
  try { await navigator.clipboard.writeText(value); toast('Path copied'); }
  catch(_error){ toast(value); }
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

function renderCommunications(){
  const c = DATA.communications || {channels:[],policy:{}};
  const marks = {gmail:'G',outlook:'O',whatsapp:'WA'};
  const labels = {ready:'ready',setup:'setup needed',planned:'planned'};
  const tones = ['Clear and warm','Short and direct','Professional','Friendly'];
  const channels = (c.channels || []).map(ch => `
    <article class="card channel">
      <div class="channel-mark">${esc(marks[ch.id] || ch.label.slice(0,2).toUpperCase())}</div>
      <div><h3>${esc(ch.label)}</h3><p>${esc(ch.detail)}</p></div>
      <span class="pill ${ch.status==='ready'?'mint':ch.status==='setup'?'copper':'steel'}">${esc(labels[ch.status] || ch.status)}</span>
    </article>`).join('');
  return `
    <section class="hero">
      <div class="eyebrow">Communication Hub · calm, deliberate, supervised</div>
      <h1>Reply well without giving away control.</h1>
      <p>Bring email and WhatsApp Business into one safe flow: inspect only when you ask, prepare a draft, let you edit it, and send only after an explicit confirmation.</p>
    </section>
    <div class="grid c2">
      <section class="channel-grid">${channels}</section>
      <section class="card reply-studio">
        <span class="eyebrow">Reply studio</span>
        <h2>Shape a reply before sending</h2>
        <label class="mono" for="reply-channel">Channel</label>
        <select class="input" id="reply-channel">${(c.channels||[]).map(ch=>`<option>${esc(ch.label)}</option>`).join('')}</select>
        <label class="mono" for="reply-tone">Tone</label>
        <select class="input" id="reply-tone">${tones.map(t=>`<option>${t}</option>`).join('')}</select>
        <label class="mono" for="reply-context">What must the reply achieve?</label>
        <textarea class="input" id="reply-context" rows="3" placeholder="Example: confirm Tuesday at 14:00, thank them, ask for the agenda"></textarea>
        <label class="mono" for="reply-draft">Your draft</label>
        <textarea class="input" id="reply-draft" rows="7" placeholder="Draft here, or ask your connected assistant to prepare one."></textarea>
        <div class="reply-actions"><button class="btn primary" onclick="copyReply()">Copy draft</button><button class="btn" onclick="saveReplyDraft()">Save on this device</button><button class="btn" onclick="clearReplyDraft()">Clear</button></div>
        <div class="privacy-note"><b>PRIVATE</b><span>Drafts stay in this browser. They are not added to the static export or Git repository.</span></div>
      </section>
    </div>
    <section class="card" style="margin-top:15px">
      <span class="eyebrow">Permission ladder</span><h2>You remain the final sender.</h2>
      <ol class="permission-ladder"><li><b>Read on request</b><br>Never monitor silently.</li><li><b>Summarize</b><br>Surface urgency and action.</li><li><b>Prepare a draft</b><br>Match your tone and facts.</li><li><b>Confirm, then send</b><br>No autonomous sending.</li></ol>
    </section>
    <section class="notice" style="margin-top:15px"><b>WhatsApp boundary:</b> LifeOS will use Meta's official WhatsApp Business Platform only. Personal-account scraping or browser automation is too fragile and risks account suspension.</section>`;
}

function replyDraftKey(){ return 'lifeos_reply_draft_v1'; }
function restoreReplyDraft(){
  const el=document.getElementById('reply-draft'); if(!el) return;
  try { const d=JSON.parse(localStorage.getItem(replyDraftKey())||'{}'); el.value=d.draft||''; document.getElementById('reply-context').value=d.context||''; } catch(_e){}
}
function saveReplyDraft(){
  localStorage.setItem(replyDraftKey(),JSON.stringify({draft:document.getElementById('reply-draft').value,context:document.getElementById('reply-context').value,updated:new Date().toISOString()})); toast('Draft saved privately on this device.');
}
function clearReplyDraft(){ localStorage.removeItem(replyDraftKey()); document.getElementById('reply-draft').value=''; document.getElementById('reply-context').value=''; toast('Local draft cleared.'); }
async function copyReply(){ const value=document.getElementById('reply-draft').value.trim(); if(!value){toast('Write or paste a draft first.');return;} try{await navigator.clipboard.writeText(value);toast('Draft copied. Nothing was sent.');}catch(_e){toast('Clipboard access was blocked; select the draft and copy it manually.');} }

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
  else if(state.tab === 'recall' || state.tab === 'practice') el.innerHTML = renderPractice();
  else if(state.tab === 'exam') el.innerHTML = renderExam();
  else if(state.tab === 'mastery' || state.tab === 'career') el.innerHTML = renderCareer();
  else if(state.tab === 'build') el.innerHTML = renderProjectChamber();
  else if(state.tab === 'system' || state.tab === 'agents') el.innerHTML = renderAgents();
  else if(state.tab === 'reflection' || state.tab === 'loops') el.innerHTML = renderLoops();
  else if(state.tab === 'communications' || state.tab === 'reply') { el.innerHTML = renderCommunications(); restoreReplyDraft(); }
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
            max_length = 262_144 if parsed.path == "/api/study/note" else 16_384
            if length < 0 or length > max_length:
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
                if parsed.path == "/api/study/note":
                    path = study.save_note(
                        home, body.get("title", ""), body.get("subject", "general"),
                        body.get("content", ""), source_url=body.get("source_url", ""),
                    )
                    self._send_json(200, {"ok": True, "path": path.relative_to(home).as_posix()})
                    return
                if parsed.path == "/api/study/bank":
                    path = study.write_question_bank(home, body.get("source", ""), overwrite=bool(body.get("overwrite")))
                    self._send_json(200, {"ok": True, "path": path.relative_to(home).as_posix()})
                    return
                if parsed.path == "/api/study/refresh":
                    self._send_json(200, {"ok": True, **study.refresh_question_banks(home, body.get("curriculum", ""))})
                    return
                if parsed.path == "/api/study/trust":
                    result = study.set_question_trust(
                        home, body.get("bank", ""), body.get("question_id", ""), body.get("trust", "verified"),
                    )
                    self._send_json(200, {"ok": True, **result})
                    return
                if parsed.path == "/api/study/answer":
                    self._send_json(200, {"ok": True, **study.get_question_answer(home, body.get("question_id", ""))})
                    return
                if parsed.path == "/api/study/submit":
                    self._send_json(200, {"ok": True, **study.submit_answer(
                        home, body.get("question_id", ""), body.get("response", ""),
                        elapsed_seconds=body.get("elapsed_seconds", 0),
                    )})
                    return
                if parsed.path == "/api/study/review-answer":
                    self._send_json(200, {"ok": True, **study.get_question_for_review(home, body.get("question_id", ""))})
                    return
                if parsed.path == "/api/study/attempt":
                    result = study.record_attempt(
                        home, body.get("question_id", ""), body.get("rating", ""),
                        elapsed_seconds=body.get("elapsed_seconds", 0), exam_id=body.get("exam_id", ""),
                        response=body.get("response", ""),
                    )
                    self._send_json(200, {"ok": True, **result})
                    return
                if parsed.path == "/api/study/exam":
                    result = study.compose_exam(
                        home, title=body.get("title", "Practice Exam"), subject=body.get("subject", ""),
                        count=body.get("count", 10), minutes=body.get("minutes", 60),
                    )
                    self._send_json(200, {
                        "ok": True, "exam_id": result["exam_id"],
                        "exam_path": result["exam_path"].relative_to(home).as_posix(),
                        "key_path": result["key_path"].relative_to(home).as_posix(),
                    })
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
