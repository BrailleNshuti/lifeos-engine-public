"""Free notes around one `lifeos ask` call: what the seat cannot do (before) and the CHECK line (after). No model call."""
from .check import check_answer, task_check_inputs


def pre_notes(home, model, task):
    """Hints printed before a call (never blocks): what this seat cannot do. Never raises."""
    try:
        from .context import task_file
        from .delegate import task_text
        from .seats import seat_warning
        hint = seat_warning(model, task_text(task_file(home, task)))
        return [hint] if hint else []
    except Exception:
        return []


def post_notes(path):
    """The free CHECK line for the answer just written to the task file (same as delegate prints). Never raises."""
    try:
        from .delegate import last_result
        found = check_answer(last_result(path), *task_check_inputs(path))
        return ["CHECK (free, no model): " + "; ".join(found)] if found else []
    except Exception:
        return []


def pre_notes(home, model, task):
    """Hints printed before a call (never blocks): what this seat cannot do. Never raises."""
    try:
        from .context import task_file
        from .delegate import task_text
        from .seats import seat_warning
        hint = seat_warning(model, task_text(task_file(home, task)))
        return [hint] if hint else []
    except Exception:
        return []


def post_notes(path):
    """The free CHECK line for the answer just written to the task file (same as delegate prints). Never raises."""
    try:
        from .delegate import last_result
        found = check_answer(last_result(path), *task_check_inputs(path))
        return ["CHECK (free, no model): " + "; ".join(found)] if found else []
    except Exception:
        return []
