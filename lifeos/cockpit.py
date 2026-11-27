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
from .log import VALID_HOURS_AREAS, log_health, log_hours, log_ledger, log_proof
from .runs import summarize_runs
from .store import atomic_write_bytes
from . import study
from .tasks import list_tasks, new_task
from .week import week_numbers
from .cockpit_page import COCKPIT_HTML_TEMPLATE


def _classify_lane(task_id, goal):
    combined = f"{task_id} {goal}".lower()
    if any(k in combined for k in ("prompt", "lab", "card", "console")):
        return "work"
    if any(k in combined for k in ("study", "exam", "language", "course", "math", "stats", "python")):
        return "study"
    if any(k in combined for k in ("engine", "kernel", "ask", "mcp", "github", "plugin")):
        return "lab"
    return "personal"


DEFAULT_AREAS = [{"id": "study", "label": "study"}, {"id": "lab", "label": "lab"}, {"id": "work", "label": "work"}]


def _load_profile(home):
    """Read the owner's own labels and targets from `cockpit.json` in the data home; a missing or bad file means neutral defaults."""
    profile = {"owner": "", "focus": "", "horizon": "", "targets": [], "areas": [dict(a) for a in DEFAULT_AREAS]}
    try:
        raw = json.loads((Path(home) / "cockpit.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return profile
    if not isinstance(raw, dict):
        return profile
    for key in ("owner", "focus", "horizon"):
        if isinstance(raw.get(key), str):
            profile[key] = raw[key][:200]
    targets = raw.get("targets")
    if isinstance(targets, list):
        profile["targets"] = [
            {k: str(t.get(k, ""))[:300] for k in ("title", "when", "detail")}
            for t in targets if isinstance(t, dict) and t.get("title")
        ][:12]
    areas = raw.get("areas")
    if isinstance(areas, list):
        clean, seen = [], set()
        for a in areas:
            aid = a["id"].strip().lower() if isinstance(a, dict) and isinstance(a.get("id"), str) else ""
            if aid in VALID_HOURS_AREAS and aid not in seen:
                seen.add(aid)
                label = a.get("label").strip() if isinstance(a.get("label"), str) else ""
                clean.append({"id": aid, "label": (label or aid)[:40]})
        if clean:
            profile["areas"] = clean
    return profile


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
        "profile": _load_profile(home),
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
