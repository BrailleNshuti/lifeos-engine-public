"""Local-first study sources, grounded question banks, spaced practice, and exam composition."""
from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from .guard import private_patterns, scan_text
from .store import atomic_write_bytes, commit_transaction, store_lock

MAX_SOURCE_BYTES = 262_144
MAX_NOTE_CHARS = 200_000
MAX_RESPONSE_CHARS = 12_000
MAX_QUESTIONS_PER_BANK = 60
TRUST_STATES = ("draft", "grounded", "verified", "trusted")
RATINGS = ("again", "hard", "good", "easy")
EXCLUDED_PARTS = {"key", "keys", "answers", "answer-keys", "exam-keys"}


class StudyError(ValueError):
    """Refusal raised for invalid, unsafe, or ungrounded study operations."""


def _slug(value, fallback="note"):
    text = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return (text[:80] or fallback).strip("-")


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _guard_text(text):
    blocks = [f for f in scan_text(text, private_patterns(), allow_mark=False) if f[1] == "BLOCK"]
    if blocks:
        kinds = ", ".join(sorted({f[2] for f in blocks}))
        raise StudyError(f"Study content refused by privacy guard ({kinds}).")


def _safe_existing_path(home, rel_path, allowed_roots=("learning",)):
    home = Path(home).resolve()
    rel = Path(str(rel_path).replace("\\", "/"))
    if rel.is_absolute() or ".." in rel.parts or not rel.parts or rel.parts[0] not in allowed_roots:
        raise StudyError("Study path must stay inside an allowed LifeOS learning folder.")
    path = (home / rel).resolve()
    try:
        path.relative_to(home)
    except ValueError as error:
        raise StudyError("Study path escaped the LifeOS home.") from error
    if not path.is_file():
        raise StudyError(f"Study file not found: {rel.as_posix()}")
    return path


def _read_source(path):
    if path.suffix.lower() not in (".md", ".txt"):
        raise StudyError("Only UTF-8 Markdown and text sources are accepted by the dependency-free core.")
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise StudyError(f"Study source is over {MAX_SOURCE_BYTES // 1024} KiB.")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise StudyError("Study source must be UTF-8 text.") from error


def _frontmatter(text):
    meta = {}
    body = text
    if text.startswith("---\n"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    meta[key.strip().lower()] = value.strip()
            body = parts[2].lstrip("\r\n")
    return meta, body


def _source_title(path, text):
    meta, body = _frontmatter(text)
    if meta.get("title"):
        return meta["title"][:140]
    match = re.search(r"^#\s+(.+)$", body, re.M)
    return (match.group(1).strip() if match else path.stem.replace("-", " ").title())[:140]


def _is_visible_source(path, learning_root):
    rel = path.relative_to(learning_root)
    lower_parts = {p.lower() for p in rel.parts}
    name = path.name.lower()
    if lower_parts & EXCLUDED_PARTS:
        return False
    if any(token in name for token in ("-key.", "answers-", "verification")):
        return False
    return path.suffix.lower() in (".md", ".txt") and name != "readme.md"


def list_sources(home, include_content=False, max_sources=100):
    """Index visible UTF-8 study sources while keeping answer keys out of the learning surface."""
    home = Path(home)
    root = home / "learning"
    if not root.is_dir():
        return []
    rows = []
    for path in sorted(root.rglob("*")):
        if len(rows) >= max_sources or not path.is_file() or not _is_visible_source(path, root):
            continue
        try:
            text = _read_source(path)
        except (OSError, StudyError):
            continue
        meta, body = _frontmatter(text)
        headings = [m.group(1).strip() for m in re.finditer(r"^#{1,4}\s+(.+)$", body, re.M)]
        rel = path.relative_to(home).as_posix()
        row = {
            "path": rel,
            "title": _source_title(path, text),
            "subject": (meta.get("subject") or (path.relative_to(root).parts[0] if path.relative_to(root).parts else "general"))[:80],
            "source_url": meta.get("source_url", ""),
            "sha256": _sha(text),
            "words": len(re.findall(r"\b\w+\b", body, flags=re.UNICODE)),
            "headings": headings[:30],
            "excerpt": re.sub(r"\s+", " ", body).strip()[:360],
        }
        if include_content:
            row["content"] = body[:12_000]
        rows.append(row)
    return rows


def list_curricula(home):
    """Load ordered learning journeys and validate every referenced source."""
    home = Path(home)
    root = home / "learning" / "curricula"
    rows = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("steps"), list):
            continue
        curriculum_id = str(data.get("id", "")).strip()
        if not curriculum_id:
            continue
        clean_steps = []
        for index, step in enumerate(data["steps"], 1):
            if not isinstance(step, dict):
                continue
            source_path = str(step.get("source_path", "")).strip()
            try:
                source = _safe_existing_path(home, source_path)
                _read_source(source)
            except StudyError:
                continue
            clean_steps.append({
                "id": str(step.get("id") or f"{curriculum_id}-{index:02d}")[:80],
                "title": str(step.get("title") or source.stem.replace("-", " ").title())[:140],
                "source_path": source.relative_to(home).as_posix(),
                "outcomes": [str(value)[:180] for value in step.get("outcomes", []) if str(value).strip()][:8],
                "prerequisites": [str(value)[:80] for value in step.get("prerequisites", []) if str(value).strip()][:8],
            })
        if clean_steps:
            rows.append({
                "id": curriculum_id[:80], "title": str(data.get("title") or curriculum_id.replace("-", " ").title())[:140],
                "skill": str(data.get("skill") or data.get("title") or curriculum_id)[:140],
                "description": str(data.get("description") or "")[:500], "steps": clean_steps,
                "path": path.relative_to(home).as_posix(),
            })
    return rows


def save_note(home, title, subject, content, source_url=""):
    """Save pasted study notes as a privacy-checked Markdown source with provenance metadata."""
    title = str(title or "").strip()
    subject = str(subject or "general").strip()
    content = str(content or "").strip()
    source_url = str(source_url or "").strip()
    if not title or len(title) > 140:
        raise StudyError("Note title is required and must be at most 140 characters.")
    if not subject or len(subject) > 80:
        raise StudyError("Note subject must be 1 to 80 characters.")
    if not content or len(content) > MAX_NOTE_CHARS:
        raise StudyError(f"Note content must be 1 to {MAX_NOTE_CHARS} characters.")
    if source_url:
        parsed = urlparse(source_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise StudyError("Source URL must be an http(s) URL.")
    _guard_text("\n".join((title, subject, content, source_url)))
    home = Path(home)
    target = home / "learning" / "sources" / f"{_slug(subject, 'general')}--{_slug(title)}.md"
    if target.exists():
        raise StudyError(f"A note already exists at {target.relative_to(home).as_posix()}.")
    lines = ["---", f"title: {title}", f"subject: {subject}", f"created: {date.today().isoformat()}"]
    if source_url:
        lines.append(f"source_url: {source_url}")
    lines.extend(("---", "", f"# {title}", "", content, ""))
    with store_lock(home):
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(target, "\n".join(lines).encode("utf-8"))
    return target


def _clean_answer(lines):
    text = "\n".join(lines)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"!\[[^]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
    return re.sub(r"\s+", " ", text).strip()[:900]


def build_question_candidates(home, source_path):
    """Create source-grounded draft questions; answers are exact source excerpts, never model inventions."""
    home = Path(home)
    path = _safe_existing_path(home, source_path)
    text = _read_source(path)
    _meta, body = _frontmatter(text)
    body_line_offset = 0
    if text.startswith("---\n"):
        frontmatter_end = text.find("\n---", 4)
        if frontmatter_end >= 0:
            body_line_offset = text[:frontmatter_end + 4].count("\n") + 1
    lines = body.splitlines()
    source_sha = _sha(text)
    questions = []

    index = 0
    while index < len(lines) - 1 and len(questions) < MAX_QUESTIONS_PER_BANK:
        q_match = re.match(r"^\s*(?:Q|Question)\s*:\s*(.+)$", lines[index], re.I)
        a_match = re.match(r"^\s*(?:A|Answer)\s*:\s*(.+)$", lines[index + 1], re.I) if q_match else None
        if q_match and a_match:
            key_points = []
            if index + 2 < len(lines):
                key_match = re.match(r"^\s*Key\s*points?\s*:\s*(.+)$", lines[index + 2], re.I)
                if key_match:
                    key_points = [value.strip()[:180] for value in re.split(r"\s*[|;]\s*", key_match.group(1)) if value.strip()][:8]
            questions.append({
                "prompt": q_match.group(1).strip(), "answer": a_match.group(1).strip(),
                "type": "short_answer", "difficulty": 2,
                "line_start": index + 1 + body_line_offset,
                "line_end": index + 2 + body_line_offset,
                "key_points": key_points,
            })
            index += 3 if key_points else 2
            continue
        index += 1

    sections = []
    current = None
    for line_no, line in enumerate(lines, 1):
        match = re.match(r"^(#{2,4})\s+(.+)$", line)
        if match:
            if current:
                sections.append(current)
            current = {"title": match.group(2).strip(), "start": line_no, "body": []}
        elif current:
            current["body"].append((line_no, line))
    if current:
        sections.append(current)

    seen_prompts = {q["prompt"].lower() for q in questions}
    for section in sections:
        if len(questions) >= MAX_QUESTIONS_PER_BANK:
            break
        answer = _clean_answer([line for _n, line in section["body"]])
        title = section["title"]
        if len(answer) < 35 or title.lower() in ("references", "sources", "contents", "table of contents"):
            continue
        prompt = title if title.endswith("?") else f"Explain {title} from memory."
        if prompt.lower() in seen_prompts:
            continue
        end = section["body"][-1][0] if section["body"] else section["start"]
        questions.append({
            "prompt": prompt, "answer": answer, "type": "free_recall", "difficulty": 2,
            "line_start": section["start"] + body_line_offset,
            "line_end": end + body_line_offset,
        })
        seen_prompts.add(prompt.lower())

    rel = path.relative_to(home).as_posix()
    for number, question in enumerate(questions, 1):
        question.update({
            "id": f"{source_sha[:10]}-{number:03d}",
            "trust": "grounded",
            "source_path": rel,
            "source_sha256": source_sha,
            "citation": f"{rel}:L{question['line_start']}-L{question['line_end']}",
            "tags": [],
        })
    return {
        "schema_version": 1,
        "created": date.today().isoformat(),
        "source": {"path": rel, "sha256": source_sha, "title": _source_title(path, text)},
        "questions": questions,
    }


def write_question_bank(home, source_path, overwrite=False):
    """Write a deterministic grounded bank; a human must verify questions before exam use."""
    home = Path(home)
    bank = build_question_candidates(home, source_path)
    if not bank["questions"]:
        raise StudyError("No usable headings or Q:/A: pairs were found in this source.")
    source = Path(bank["source"]["path"])
    target = home / "learning" / "question-banks" / f"{_slug(source.stem)}--{bank['source']['sha256'][:10]}.json"
    if target.exists() and not overwrite:
        raise StudyError(f"Question bank already exists: {target.relative_to(home).as_posix()}.")
    payload = json.dumps(bank, ensure_ascii=False, indent=2) + "\n"
    _guard_text(payload)
    with store_lock(home):
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(target, payload.encode("utf-8"))
    return target


def refresh_question_banks(home, curriculum_id=""):
    """Create missing curriculum banks without auto-promoting question trust."""
    home = Path(home)
    curricula = list_curricula(home)
    if curriculum_id:
        curricula = [row for row in curricula if row["id"] == curriculum_id]
        if not curricula:
            raise StudyError(f"Curriculum not found: {curriculum_id}")
    source_paths = []
    for curriculum in curricula:
        for step in curriculum["steps"]:
            if step["source_path"] not in source_paths:
                source_paths.append(step["source_path"])
    existing = list_banks(home, include_questions=False)
    by_source = {row.get("source", {}).get("path"): row for row in existing}
    result = {"curricula": len(curricula), "sources": len(source_paths), "created": 0, "skipped": 0,
              "stale": 0, "needs_verification": 0, "paths": []}
    for source_path in source_paths:
        source_sha = _sha(_read_source(_safe_existing_path(home, source_path)))
        current = by_source.get(source_path)
        if current and current.get("source", {}).get("sha256") == source_sha:
            result["skipped"] += 1
            result["needs_verification"] += int(current.get("counts", {}).get("grounded", 0))
            continue
        if current:
            result["stale"] += 1
        target = write_question_bank(home, source_path)
        bank = _load_bank(target) or {"questions": []}
        result["created"] += 1
        result["needs_verification"] += len(bank["questions"])
        result["paths"].append(target.relative_to(home).as_posix())
    return result


def _load_bank(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("questions"), list):
        return None
    return data


def list_banks(home, include_questions=True):
    home = Path(home)
    root = home / "learning" / "question-banks"
    rows = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("*.json")):
        data = _load_bank(path)
        if data is None:
            continue
        counts = {state: 0 for state in TRUST_STATES}
        for q in data["questions"]:
            trust = q.get("trust", "draft")
            if trust in counts:
                counts[trust] += 1
        row = {
            "path": path.relative_to(home).as_posix(),
            "source": data.get("source", {}),
            "counts": counts,
            "question_count": len(data["questions"]),
        }
        if include_questions:
            row["questions"] = data["questions"]
        rows.append(row)
    return rows


def set_question_trust(home, bank_path, question_id, trust):
    """Record explicit human verification state for one grounded question."""
    trust = str(trust or "").lower()
    if trust not in TRUST_STATES:
        raise StudyError(f"Trust must be one of: {', '.join(TRUST_STATES)}.")
    home = Path(home)
    path = _safe_existing_path(home, bank_path)
    if path.parent.name != "question-banks" or path.suffix.lower() != ".json":
        raise StudyError("Only files in learning/question-banks can be verified.")
    bank = _load_bank(path)
    if bank is None:
        raise StudyError("Invalid question bank.")
    if trust in ("verified", "trusted"):
        source = _safe_existing_path(home, bank.get("source", {}).get("path", ""))
        if _sha(_read_source(source)) != bank.get("source", {}).get("sha256"):
            raise StudyError("Source changed after this bank was grounded; regenerate it before verification.")
    changed = False
    for q in bank["questions"]:
        if q.get("id") == question_id:
            q["trust"] = trust
            q["verified_on"] = date.today().isoformat() if trust in ("verified", "trusted") else ""
            changed = True
            break
    if not changed:
        raise StudyError(f"Question not found: {question_id}")
    payload = json.dumps(bank, ensure_ascii=False, indent=2) + "\n"
    with store_lock(home):
        atomic_write_bytes(path, payload.encode("utf-8"))
    return {"question_id": question_id, "trust": trust}


def _attempt_path(home):
    return Path(home) / "logs" / "study-attempts.jsonl"


def _read_attempts(home):
    path = _attempt_path(home)
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("question_id"):
            rows.append(row)
    return rows


def _question_catalog(home):
    out = {}
    for bank in list_banks(home, include_questions=True):
        for question in bank["questions"]:
            out[question.get("id")] = {**question, "bank_path": bank["path"]}
    return out


def get_question_answer(home, question_id):
    """Return a verified answer only to the authorized localhost study session."""
    question = _question_catalog(home).get(str(question_id))
    if not question or question.get("trust") not in ("verified", "trusted"):
        raise StudyError("Verified question not found.")
    return {
        "question_id": question["id"],
        "answer": question.get("answer", ""),
        "citation": question.get("citation", ""),
        "source_sha256": question.get("source_sha256", ""),
    }


def _normalized_words(value):
    return re.findall(r"[a-z0-9]+", str(value or "").lower())


def grade_response(question, response):
    """Score only explicit author-written key points; broad recall stays learner-rated."""
    key_points = [str(value).strip() for value in question.get("key_points", []) if str(value).strip()]
    if not key_points:
        return {"graded": False, "score": None, "matched_concepts": [], "missing_concepts": []}
    response_words = set(_normalized_words(response))
    matched, missing = [], []
    for point in key_points:
        words = [word for word in _normalized_words(point) if len(word) > 2]
        coverage = (sum(word in response_words for word in words) / len(words)) if words else 0
        (matched if coverage >= 0.7 else missing).append(point)
    return {"graded": True, "score": round(len(matched) / len(key_points), 2),
            "matched_concepts": matched, "missing_concepts": missing}


def submit_answer(home, question_id, response, elapsed_seconds=0):
    """Commit an answer before feedback and persist objective rubric gaps when available."""
    response = str(response or "").strip()
    if len(response) < 12 or len(response) > MAX_RESPONSE_CHARS:
        raise StudyError(f"Answer must be 12 to {MAX_RESPONSE_CHARS} characters.")
    _guard_text(response)
    question = _question_catalog(home).get(str(question_id))
    if not question or question.get("trust") not in ("verified", "trusted"):
        raise StudyError("Verified question not found.")
    evaluation = grade_response(question, response)
    attempt = None
    if evaluation["graded"]:
        score = evaluation["score"]
        rating = "good" if score >= 0.75 else ("hard" if score >= 0.5 else "again")
        attempt = record_attempt(home, question_id, rating, elapsed_seconds=elapsed_seconds, response=response,
                                 score=score, matched_concepts=evaluation["matched_concepts"],
                                 missing_concepts=evaluation["missing_concepts"])
    return {"question_id": question["id"], "answer": question.get("answer", ""),
            "citation": question.get("citation", ""), "evaluation": evaluation,
            "recorded": attempt is not None, "attempt": attempt}


def get_question_for_review(home, question_id):
    """Return a grounded question to the authorized localhost verification desk."""
    question = _question_catalog(home).get(str(question_id))
    if not question or question.get("trust") not in ("grounded", "verified", "trusted"):
        raise StudyError("Grounded question not found.")
    source = _safe_existing_path(home, question.get("source_path", ""))
    if _sha(_read_source(source)) != question.get("source_sha256"):
        raise StudyError("Source changed after this question was grounded; regenerate its bank.")
    return {
        "question_id": question["id"],
        "prompt": question.get("prompt", ""),
        "answer": question.get("answer", ""),
        "citation": question.get("citation", ""),
        "source_sha256": question.get("source_sha256", ""),
        "bank_path": question.get("bank_path", ""),
        "trust": question.get("trust", "grounded"),
    }


def record_attempt(home, question_id, rating, elapsed_seconds=0, exam_id="", response="", score=None,
                   matched_concepts=None, missing_concepts=None):
    """Append a retrieval result and compute a simple, transparent next-review interval."""
    rating = str(rating or "").lower()
    if rating not in RATINGS:
        raise StudyError(f"Rating must be one of: {', '.join(RATINGS)}.")
    catalog = _question_catalog(home)
    question = catalog.get(str(question_id))
    if not question or question.get("trust") not in ("verified", "trusted"):
        raise StudyError("Only verified or trusted questions can enter the practice schedule.")
    try:
        elapsed = int(elapsed_seconds)
    except (TypeError, ValueError) as error:
        raise StudyError("Elapsed seconds must be an integer.") from error
    if elapsed < 0 or elapsed > 14_400:
        raise StudyError("Elapsed seconds must be between 0 and 14400.")
    response = str(response or "").strip()
    if len(response) > MAX_RESPONSE_CHARS:
        raise StudyError(f"Answer must be at most {MAX_RESPONSE_CHARS} characters.")
    if response:
        _guard_text(response)
    attempts = _read_attempts(home)
    previous = next((r for r in reversed(attempts) if r.get("question_id") == question_id), None)
    prior = int((previous or {}).get("interval_days", 0) or 0)
    if rating == "again":
        interval = 1
    elif rating == "hard":
        interval = max(2, round(prior * 1.5)) if prior else 2
    elif rating == "good":
        interval = max(4, round(prior * 2.5)) if prior else 4
    else:
        interval = max(7, round(prior * 4)) if prior else 7
    interval = min(interval, 120)
    today = date.today()
    row = {
        "schema_version": 2,
        "date": today.isoformat(),
        "question_id": question_id,
        "rating": rating,
        "elapsed_seconds": elapsed,
        "interval_days": interval,
        "due": (today + timedelta(days=interval)).isoformat(),
        "source_sha256": question.get("source_sha256", ""),
        "exam_id": str(exam_id or "")[:100],
        "response": response,
        "score": score if isinstance(score, (int, float)) else None,
        "matched_concepts": [str(value)[:180] for value in (matched_concepts or [])][:8],
        "missing_concepts": [str(value)[:180] for value in (missing_concepts or [])][:8],
    }
    path = _attempt_path(home)
    with store_lock(home):
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        atomic_write_bytes(path, (existing + json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
    return row


def study_snapshot(home, include_content=False):
    """Return the source library, trust pipeline, due queue, and exam history for the Cockpit."""
    home = Path(home)
    sources = list_sources(home, include_content=include_content)
    raw_banks = list_banks(home, include_questions=True)
    attempts = _read_attempts(home)
    last_attempt = {}
    for row in attempts:
        last_attempt[row["question_id"]] = row
    today = date.today().isoformat()
    due = []
    counts = {state: 0 for state in TRUST_STATES}
    banks = []
    for raw_bank in raw_banks:
        visible_questions = []
        for question in raw_bank["questions"]:
            trust = question.get("trust", "draft")
            if trust in counts:
                counts[trust] += 1
            visible = {key: value for key, value in question.items() if key not in ("answer", "key_points")}
            visible_questions.append(visible)
            if trust not in ("verified", "trusted"):
                continue
            prior = last_attempt.get(question.get("id"))
            due_date = (prior or {}).get("due", today)
            if due_date <= today:
                due.append({**visible, "bank_path": raw_bank["path"], "last_rating": (prior or {}).get("rating"), "due": due_date})
        banks.append({**raw_bank, "questions": visible_questions})
    due.sort(key=lambda q: (q.get("due", today), q.get("last_rating") not in (None, "again"), q.get("id", "")))
    exams = []
    reviews = home / "reviews"
    if reviews.is_dir():
        for path in sorted(reviews.glob("exam-*.md"), reverse=True):
            exams.append({"path": path.relative_to(home).as_posix(), "title": path.stem.replace("-", " ").title()})
    activity = {date.fromisoformat(str(row["date"])) for row in attempts
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row.get("date", "")))}
    today_date = date.today()
    current_streak, cursor = 0, today_date
    while cursor in activity:
        current_streak += 1
        cursor -= timedelta(days=1)
    longest_streak = run = 0
    previous = None
    for active in sorted(activity):
        run = run + 1 if previous and active == previous + timedelta(days=1) else 1
        longest_streak = max(longest_streak, run)
        previous = active
    last_active = max(activity) if activity else None
    days_since = (today_date - last_active).days if last_active else None
    latest_by_question = {}
    for row in attempts:
        latest_by_question[row.get("question_id")] = row
    catalog = _question_catalog(home)
    gaps = []
    for question_id, attempt in latest_by_question.items():
        score = attempt.get("score")
        weak = attempt.get("rating") in ("again", "hard") or (isinstance(score, (int, float)) and score < 0.7)
        if not weak:
            continue
        question = catalog.get(question_id, {})
        gaps.append({"question_id": question_id, "prompt": question.get("prompt", "Review this concept"),
                     "source_path": question.get("source_path", ""), "citation": question.get("citation", ""),
                     "rating": attempt.get("rating"), "score": score,
                     "missing_count": len(attempt.get("missing_concepts") or [])})
    curricula = list_curricula(home)
    for curriculum in curricula:
        completed = 0
        for step in curriculum["steps"]:
            question_ids = [qid for qid, question in catalog.items() if question.get("source_path") == step["source_path"]]
            successful = any((latest_by_question.get(qid) or {}).get("rating") in ("good", "easy") for qid in question_ids)
            step["status"] = "complete" if successful else "upcoming"
            completed += int(successful)
        first_open = next((step for step in curriculum["steps"] if step["status"] != "complete"), None)
        if first_open:
            first_open["status"] = "current"
        curriculum["completed_steps"] = completed
        curriculum["progress_pct"] = round(100 * completed / len(curriculum["steps"])) if curriculum["steps"] else 0
    return {
        "sources": sources,
        "source_count": len(sources),
        "banks": banks,
        "trust_counts": counts,
        "due": due,
        "due_count": len(due),
        "attempt_count": len(attempts),
        "exams": exams,
        "curricula": curricula,
        "gaps": gaps[:20],
        "streak": {"current": current_streak, "longest": longest_streak,
                   "active_days_7": sum((today_date - timedelta(days=offset)) in activity for offset in range(7)),
                   "last_active": last_active.isoformat() if last_active else "", "days_since": days_since,
                   "nudge": ("Start with one 10-minute recall to rebuild the chain." if days_since and days_since > 0
                             else "Protect the chain with one evidence-bearing recall today.")},
    }


def compose_exam(home, title="Practice Exam", subject="", count=10, minutes=60):
    """Create a printable exam and separate key from verified/trusted source-grounded questions."""
    home = Path(home)
    try:
        count = int(count)
        minutes = int(minutes)
    except (TypeError, ValueError) as error:
        raise StudyError("Exam count and minutes must be integers.") from error
    if count < 1 or count > 50 or minutes < 5 or minutes > 240:
        raise StudyError("Exam count must be 1-50 and minutes 5-240.")
    subject_l = str(subject or "").strip().lower()
    snapshot = study_snapshot(home)
    questions = []
    for bank in list_banks(home, include_questions=True):
        source_title = str(bank.get("source", {}).get("title", ""))
        source_path = str(bank.get("source", {}).get("path", ""))
        if subject_l and subject_l not in f"{source_title} {source_path}".lower():
            continue
        for q in bank["questions"]:
            if q.get("trust") in ("verified", "trusted"):
                questions.append(q)
    if len(questions) < count:
        raise StudyError(f"Only {len(questions)} verified questions match; verify at least {count} first.")
    due_ids = {q["id"] for q in snapshot["due"]}
    questions.sort(key=lambda q: (q.get("id") not in due_ids, q.get("type", ""), q.get("difficulty", 2), q.get("id", "")))
    chosen = questions[:count]
    exam_id = f"{date.today().isoformat()}-{_slug(title, 'practice-exam')}"
    exam_path = home / "reviews" / f"exam-{exam_id}.md"
    key_path = home / "learning" / "exam-keys" / f"exam-{exam_id}-key.md"
    if exam_path.exists() or key_path.exists():
        raise StudyError(f"Exam already exists for this title and date: {exam_id}")
    exam_lines = [
        f"# {title}", "",
        f"> {minutes} minutes · {count} questions · closed notes · no AI · generated {date.today().isoformat()}",
        f"> Subject filter: {subject or 'mixed'} · Every item is human-verified and source-grounded.", "",
    ]
    key_lines = [f"# {title} · answer key", "", "> Open only after saving your answers.", ""]
    for index, q in enumerate(chosen, 1):
        exam_lines.extend((f"## {index}. {q['prompt']}", "", "Your answer:", "", "", f"Source after grading: `{q['citation']}`", ""))
        key_lines.extend((f"## {index}. {q['prompt']}", "", q["answer"], "", f"Source: `{q['citation']}`", ""))
    exam_lines.extend(("---", "## Score and misconception ledger", "", "| Question | Score 0-2 | Error or missing idea | Next review |", "|---|---:|---|---|"))
    exam_lines.extend(f"| {i} | | | |" for i in range(1, count + 1))
    exam_lines.extend(("", f"Total: __ / {count * 2}", ""))
    _guard_text("\n".join(exam_lines + key_lines))
    with store_lock(home):
        exam_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        commit_transaction(home, [
            (exam_path, ("\n".join(exam_lines) + "\n").encode("utf-8")),
            (key_path, ("\n".join(key_lines) + "\n").encode("utf-8")),
        ])
    return {"exam_id": exam_id, "exam_path": exam_path, "key_path": key_path, "question_count": count, "minutes": minutes}


def attempts(home):
    """All recorded retrieval attempts, oldest first (public read for other modules)."""
    return _read_attempts(home)
