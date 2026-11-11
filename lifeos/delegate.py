"""lifeos delegate: Claude is the lead. A task goes to the model that fits it, and the answer comes back.

Routing follows rules.md (code -> Codex, long reading -> Gemini, private sorting -> local Qwen, plans -> Claude).
Grok is not wired yet, so live facts go to Gemini. If a tool is missing, the next model in the chain takes over.
A failed call is never retried on another model: the error is shown instead.
"""
import re

from . import ask
from .ask import ADAPTERS, run_ask  # noqa: F401  (ADAPTERS is patched in tests)
from .check import check_answer
from .context import _task_file

# First match wins, so private work stays local before anything else is looked at.
ROUTES = [
    ("qwen", "private or simple sorting stays on this laptop",
     r"private|local(ly)?|csv|sort|classify|categori[sz]e|rename|tidy|offline"),
    ("gemini", "live facts and long reading go to Gemini (Grok is not wired yet)",
     r"price|news|latest|today|job posting|long|pdf|paper|research|summari[sz]e|bulk|read all"),
    ("codex", "testing, review and learning go to the ChatGPT seat (Codex)",
     r"bug|test|pytest|review|adversarial|ship|merge|command|german|exam|quiz|learn|teach|vocabulary"),
    ("claude", "Claude writes the code (Codex checks it afterwards)",
     r"code|implement|refactor|script|python|function|module|cli|\.py\b|\.js\b|\.ts\b"),
    ("claude", "plans, writing and decisions stay with Claude",
     r"plan|write|draft|decide|decision|memo|strategy|email"),
]
DEFAULT = ("claude", "no clear kind of work, so Claude takes it")
FALLBACK = {"qwen": ["ollama", "claude"], "ollama": ["claude"], "codex": ["claude"], "gemini": ["claude"], "claude": []}


def pick(text):
    """Return (model, reason) for the text of a task."""
    for model, reason, words in ROUTES:
        if re.search(rf"(?<![a-z])({words})", text, re.I):
            return model, reason
    return DEFAULT


def task_text(path):
    """Goal, context and task only: not the template's route line and not earlier results."""
    raw = path.read_text(encoding="utf-8")
    goal = re.search(r"^goal:\s*(.+)$", raw, re.M)
    body = raw.split("## Result", 1)[0].split("---", 2)[-1]
    return f"{goal.group(1) if goal else ''}\n{body}"


def last_result(path):
    parts = re.split(r"^## Result · .*$", path.read_text(encoding="utf-8"), flags=re.M)
    return parts[-1].strip() if len(parts) > 1 else ""


def run_delegate(home, task_id, model=None, budget=6000, full=False, adapters=None, today=None, dry_run=False):
    """Run the task on the best model. Returns model, reason, tried, path and the answer text."""
    adapters = adapters if adapters is not None else ADAPTERS
    path = _task_file(home, task_id)
    if model:
        if model not in adapters:
            raise ValueError(f"Unknown model '{model}'. Choose one of: {', '.join(sorted(adapters))}.")
        chosen, reason = model, "chosen by you"
    else:
        chosen, reason = pick(task_text(path))
    chain = [chosen] + [m for m in FALLBACK.get(chosen, []) if m in adapters]
    if dry_run:
        return {"model": chosen, "reason": reason, "tried": [], "path": path, "text": "", "flags": []}
    tried = []
    for name in chain:
        tried.append(name)
        try:
            path = run_ask(home, name, task_id, budget, adapters=adapters, today=today, full=full)
        except ask.ToolMissing as error:
            if name == chain[-1]:
                raise
            reason += f" · {name} is not available ({error}); fell back"
            continue
        return {"model": name, "reason": reason, "tried": tried, "path": path, "text": last_result(path),
                "flags": check_answer(last_result(path))}
