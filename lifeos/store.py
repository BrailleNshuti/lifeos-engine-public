"""Locked, crash-recoverable multi-file commits shared by LifeOS commands.

All task results, ledger rows, proof rows and execution run records pass through
this module so exclusive OS advisory file locking, write-ahead crash recovery,
fsynced atomic replacement, run_id idempotency, schema versioning, CSV quoting,
line boundaries and the model-call contract cannot drift between features.
"""
import base64
from contextlib import contextmanager
import csv
import datetime as dt
import io
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None

ASK_NOTE_PREFIX = "asked via lifeos ask"
FLAGS_LABEL = "flags"
LOCK_STALE_SECONDS = 30.0
ALLOWED_JOURNAL_LOGS = {"logs/ledger.csv", "logs/proofs.csv", "logs/health.csv", "logs/hours.csv", "logs/runs.jsonl"}
TASK_REL_RE = re.compile(r"^(?:tasks/)?T-[A-Za-z0-9-]+\.md$")
STUDY_ARTIFACT_RE = re.compile(
    r"^(?:reviews/exam-[a-z0-9-]+\.md|learning/exam-keys/exam-[a-z0-9-]+-key\.md)$"
)
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RUN_SCHEMA_VERSION = 2
TERMINAL_RUN_STATUSES = ("ok", "blocked", "failed", "timeout", "tool_missing", "partial")

_LOCK_TLS = threading.local()
_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS = {}


def utc_now_iso():
    """Return current UTC timestamp in ISO-8601 format (YYYY-MM-DDTHH:MM:SSZ)."""
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_all(fd, data):
    """Write every byte from `data` to `fd` via a memoryview loop, raising OSError on a zero-byte write."""
    view = memoryview(data if isinstance(data, (bytes, bytearray, memoryview)) else bytes(data))
    total = 0
    while total < len(view):
        written = os.write(fd, view[total:])
        if written is None or written <= 0:
            raise OSError("Short write returned 0 bytes")
        total += written


_SUPPORTS_DIR_FSYNC = os.name != "nt"


def _fsync_parent_dir(path):
    """Fsync the parent directory on POSIX so rename/unlink directory entries survive sudden power loss.
    On Windows, os.open on a directory raises PermissionError/OSError; NTFS metadata journaling orders renames."""
    if not _SUPPORTS_DIR_FSYNC:
        return
    import errno
    parent = Path(path).resolve().parent
    dfd = os.open(str(parent), os.O_RDONLY)
    try:
        try:
            os.fsync(dfd)
        except OSError as err:
            if err.errno not in (errno.EINVAL, errno.ENOTSUP):
                raise
    finally:
        os.close(dfd)


def atomic_write_bytes(path, data):
    """Write bytes to a sibling temp file via _write_all, fsync file, atomically replace target, and fsync parent dir."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(str(tmp), flags)
        try:
            _write_all(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
        _fsync_parent_dir(path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


_atomic_write_bytes = atomic_write_bytes


def _get_thread_lock(lock_path):
    with _THREAD_LOCKS_GUARD:
        tlock = _THREAD_LOCKS.get(lock_path)
        if tlock is None:
            tlock = threading.Lock()
            _THREAD_LOCKS[lock_path] = tlock
        return tlock


def _try_os_lock(fd):
    """Attempt a non-blocking exclusive OS advisory lock on `fd` (byte 0 on Windows, flock on POSIX)."""
    if msvcrt is not None:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    if fcntl is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
    return True


def _os_unlock(fd):
    """Release the OS advisory lock on `fd` before closing it."""
    if msvcrt is not None:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    elif fcntl is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


def _read_lock_meta(lock_path):
    """Return (owner_token, pid, timestamp) from a lockfile, or (None, None, None)."""
    try:
        lines = Path(lock_path).read_text(encoding="ascii").splitlines()
        if len(lines) >= 3:
            return lines[0].strip(), int(lines[1].strip()), float(lines[2].strip())
    except (OSError, ValueError):
        pass
    return None, None, None


@contextmanager
def _advisory_lock_file(lock_path, timeout=10.0):
    """Acquire an exclusive cross-process (OS advisory lock) and cross-thread lock on `lock_path`,
    holding the file descriptor on a persistent inode for the context lifetime. Pass `timeout=None` to wait indefinitely."""
    lock_path = Path(lock_path).resolve()
    held = getattr(_LOCK_TLS, "held", None)
    if held is None:
        held = {}
        _LOCK_TLS.held = held
    if held.get(lock_path, 0) > 0:
        held[lock_path] += 1
        try:
            yield
        finally:
            held[lock_path] -= 1
        return

    owner_token = f"{os.getpid()}:{uuid.uuid4().hex}"
    deadline = None if timeout is None else (time.monotonic() + timeout)
    tlock = _get_thread_lock(lock_path)

    while True:
        if deadline is None:
            if tlock.acquire(timeout=0.05):
                break
        else:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for store lock: {lock_path}")
            if tlock.acquire(timeout=min(remaining, 0.05)):
                break

    fd = None
    try:
        open_flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_BINARY", 0)
        while True:
            try:
                fd = os.open(str(lock_path), open_flags)
            except OSError:
                fd = None
            if fd is not None and _try_os_lock(fd):
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    payload = f"{owner_token}\n{os.getpid()}\n{time.time()}\n".encode("ascii")
                    _write_all(fd, payload)
                    os.ftruncate(fd, len(payload))
                except OSError:
                    pass
                break
            if fd is not None:
                os.close(fd)
                fd = None
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for store lock: {lock_path}")
            time.sleep(0.01)

        held[lock_path] = 1
        try:
            yield
        finally:
            held.pop(lock_path, None)
    finally:
        # Never unlink the lockfile: keeping a single persistent inode prevents two processes on POSIX from
        # locking old and new inodes concurrently during lock handoff.
        if fd is not None:
            _os_unlock(fd)
            os.close(fd)
        tlock.release()


@contextmanager
def store_lock(home, timeout=10.0):
    """Acquire an exclusive cross-process (OS advisory lock) and cross-thread lock on <home>/logs/.store.lock."""
    if home is None or not (Path(home) / "logs").is_dir():
        yield
        return
    with _advisory_lock_file(Path(home) / "logs" / ".store.lock", timeout=timeout):
        yield


@contextmanager
def run_lock(home, run_id, timeout=None):
    """Serialize concurrent executions sharing the same `run_id` from initial lookup through terminal record commit.
    Defaults to `timeout=None` (indefinite advisory-lock wait) so duplicate requests wait for slow provider runs."""
    if not run_id or home is None or not (Path(home) / "logs").is_dir():
        yield
        return
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(run_id))[:64]
    with _advisory_lock_file(Path(home) / "logs" / f".run.{safe}.lock", timeout=timeout):
        yield


def _journal_path(home):
    if home is None:
        return None
    logs = Path(home) / "logs"
    return logs / ".store.journal.json" if logs.is_dir() else None


def _validate_journal_target(home, rel_or_abs_path):
    """Validate that a journal target resolves strictly inside `home` and matches the write allowlist."""
    if home is None:
        raise ValueError("Cannot validate journal target without a LifeOS home.")
    home_root = Path(home).resolve()
    candidate = Path(rel_or_abs_path)
    target = (home_root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    try:
        rel = target.relative_to(home_root).as_posix()
    except ValueError as err:
        raise ValueError(f"Refused journal target outside LifeOS home: {rel_or_abs_path}") from err
    if rel not in ALLOWED_JOURNAL_LOGS and not TASK_REL_RE.fullmatch(rel) and not STUDY_ARTIFACT_RE.fullmatch(rel):
        raise ValueError(f"Refused journal target outside store allowlist: {rel}")
    return target, rel


def _quarantine_journal(jpath):
    """Preserve a corrupted or unsafe journal under logs/.store.journal.corrupt.<pid>.<id>.json for investigation."""
    if jpath is None or not jpath.exists():
        return None
    corrupt_path = jpath.with_name(f".store.journal.corrupt.{os.getpid()}.{uuid.uuid4().hex[:6]}.json")
    try:
        os.replace(jpath, corrupt_path)
        _fsync_parent_dir(jpath)
        return corrupt_path
    except OSError:
        jpath.unlink(missing_ok=True)
        _fsync_parent_dir(jpath)
        return None


def recover_journal(home):
    """Replay any uncommitted multi-file commit left by an interrupted process after validating every target."""
    jpath = _journal_path(home)
    if jpath is None or not jpath.exists():
        return False
    try:
        payload = json.loads(jpath.read_text(encoding="utf-8"))
        entries = payload["operations"]
        if not isinstance(entries, list) or not entries:
            raise ValueError("Malformed journal operations list")
        validated = []
        for entry in entries:
            target, _ = _validate_journal_target(home, entry["path"])
            data = base64.b64decode(entry["b64"], validate=True)
            validated.append((target, data))
    except Exception as err:
        _quarantine_journal(jpath)
        raise ValueError(f"Refused unsafe or corrupted store journal: {err}") from err
    for target, data in validated:
        atomic_write_bytes(target, data)
    jpath.unlink(missing_ok=True)
    _fsync_parent_dir(jpath)
    return True


def commit_transaction(home, operations):
    """Commit one or more (path, bytes) updates as a locked, crash-recoverable multi-file commit."""
    jpath = _journal_path(home)
    if jpath is not None and len(operations) > 1:
        journal_ops = []
        for p, data in operations:
            _, rel = _validate_journal_target(home, p)
            journal_ops.append({"path": rel, "b64": base64.b64encode(data).decode("ascii")})
        journal_bytes = json.dumps({"operations": journal_ops}, sort_keys=True).encode("utf-8")
        atomic_write_bytes(jpath, journal_bytes)
    for target, data in operations:
        atomic_write_bytes(Path(target), data)
    if jpath is not None and jpath.exists():
        jpath.unlink(missing_ok=True)
        _fsync_parent_dir(jpath)


def validate_run_id(run_id):
    """Validate an explicit run_id string (1..128 safe ASCII characters, no path separators or whitespace)."""
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        raise ValueError(
            "run_id must be a 1-128 character string using only ASCII letters, digits, '.', '_', or '-'."
        )
    return run_id


def new_run_id(today=None):
    """Return a unique, sortable run identifier (R-YYMMDD-xxxxxxxx)."""
    day = today or dt.date.today()
    return f"R-{day:%y%m%d}-{uuid.uuid4().hex[:8]}"


def model_call_note(flag_count):
    """Return the stable ledger note for one model call."""
    return f"{ASK_NOTE_PREFIX}; {FLAGS_LABEL}: {int(flag_count)}"


def model_call_flags(note):
    """Return the recorded flag count, or zero for old/malformed rows."""
    if not (note or "").strip().startswith(ASK_NOTE_PREFIX):
        return 0
    found = re.search(rf"{re.escape(FLAGS_LABEL)}:\s*(\d+)", note)
    return int(found.group(1)) if found else 0


def normalize_run_record(record):
    """Upgrade a v1 or v2 run record dict in memory with explicit schema_version, UTC timestamps, and terminal semantics.
    Any historical record lacking `schema_version` is classified as schema_version=1 regardless of digest length."""
    out = dict(record)
    digest = str(out.get("context_sha256") or "")
    out["schema_version"] = int(out["schema_version"]) if "schema_version" in out else 1
    if "hash_format" not in out:
        out["hash_format"] = "sha256_64" if len(digest) == 64 else ("sha256_prefix_12" if len(digest) == 12 else "none")
    fallback_ts = f"{out.get('date', '1970-01-01')}T00:00:00Z"
    out.setdefault("started_at", fallback_ts)
    out.setdefault("finished_at", out["started_at"])
    out["terminal"] = out.get("status") in TERMINAL_RUN_STATUSES
    ms = out.get("duration_ms")
    if "duration_s" not in out and isinstance(ms, (int, float)) and not isinstance(ms, bool):
        out["duration_s"] = round(ms / 1000, 3)
    amount = out.get("tokens")
    if "context_tokens" not in out and isinstance(amount, int) and not isinstance(amount, bool):
        out["context_tokens"] = amount
    return out


_HEX_CHARS = frozenset("0123456789abcdefABCDEF")


def is_valid_git_oid(val):
    """Return True if val is a full 40-char (SHA-1) or 64-char (SHA-256) hexadecimal Git object ID."""
    return isinstance(val, str) and len(val) in (40, 64) and all(c in _HEX_CHARS for c in val)


def _stamp_v2_run_record(record):
    """Ensure a newly written run record carries v2 schema fields (forced schema_version=2), mandatory identity fields,
    and a valid terminal status."""
    rec = dict(record)
    status = rec.get("status")
    if status not in TERMINAL_RUN_STATUSES:
        raise ValueError(f"Invalid non-terminal run status '{status}'. Allowed: {', '.join(TERMINAL_RUN_STATUSES)}")
    cmd = rec.get("command")
    if cmd == "ask":
        if any(k not in rec for k in ("budget", "full", "parent_run_id")):
            raise ValueError("v2 ask run record is missing mandatory identity fields (budget, full, parent_run_id).")
        if (
            isinstance(rec["budget"], bool)
            or not isinstance(rec["budget"], int)
            or not (1 <= rec["budget"] <= 50000)
            or not isinstance(rec["full"], bool)
        ):
            raise ValueError("v2 ask run record requires integer budget (1..50000) and boolean full.")
    elif cmd in ("review", "review_group"):
        req_keys = ("budget", "diff_sha256", "requested_commit", "repo", "commit_sha")
        if any(k not in rec for k in req_keys):
            raise ValueError(
                f"v2 {cmd} run record is missing mandatory identity fields ({', '.join(req_keys)})."
            )
        if isinstance(rec["budget"], bool) or not isinstance(rec["budget"], int) or not (1 <= rec["budget"] <= 50000):
            raise ValueError(f"v2 {cmd} run record requires integer budget (1..50000).")
        rec_repo = rec["repo"]
        rec_req = rec["requested_commit"]
        rec_sha = rec["commit_sha"]
        if rec_repo is None:
            if rec_req is not None or rec_sha is not None:
                raise ValueError(
                    f"v2 {cmd} run record without repo requires repo=None, requested_commit=None, and commit_sha=None."
                )
        else:
            if not isinstance(rec_repo, str) or not rec_repo.strip():
                raise ValueError(f"v2 {cmd} run record requires non-empty string repo or None.")
            if not isinstance(rec_req, str) or not rec_req.strip():
                raise ValueError(f"v2 {cmd} run record with repo requires non-empty string requested_commit.")
            allow_null_sha = cmd == "review_group" and status == "failed"
            if rec_sha is None:
                if not allow_null_sha:
                    raise ValueError(f"v2 {cmd} run record with repo requires a 40- or 64-hex commit_sha.")
            elif not is_valid_git_oid(rec_sha):
                raise ValueError(f"v2 {cmd} run record requires a 40- or 64-hex commit_sha (got {rec_sha!r}).")
        if cmd == "review" and any(k not in rec for k in ("parent_run_id", "context_sha256", "repo", "commit_sha")):
            raise ValueError("v2 review child record is missing mandatory child identity fields.")
    now_iso = utc_now_iso()
    rec["schema_version"] = RUN_SCHEMA_VERSION
    rec.setdefault("started_at", now_iso)
    rec.setdefault("finished_at", now_iso)
    rec["terminal"] = True
    return rec


def read_run_records(home, normalize=True):
    """Read all run records from logs/runs.jsonl under the store lock, optionally normalizing v1/v2 schema fields."""
    if home is None:
        return []
    runs = Path(home) / "logs" / "runs.jsonl"
    with store_lock(home):
        recover_journal(home)
        if not runs.exists():
            return []
        rows = [json.loads(line) for line in runs.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [normalize_run_record(r) for r in rows] if normalize else rows


def get_run_record(home, run_id, normalize=True):
    """Return a single persisted run record by run_id under the store lock, or None."""
    if not run_id or home is None:
        return None
    for rec in read_run_records(home, normalize=normalize):
        if rec.get("run_id") == run_id:
            return rec
    return None


def _prepare_task_result_bytes(path, model, text, today):
    path = Path(path)
    block = f"\n## Result · {model} · {today:%Y-%m-%d}\n{text}\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    return (existing + block).encode("utf-8")


def _prepare_csv_row_bytes(path, values):
    path = Path(path)
    raw = path.read_bytes()
    if raw and raw[-1:] not in (b"\n", b"\r"):
        raw += b"\n"
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerow(values)
    return raw + buf.getvalue().encode("utf-8")


def _prepare_run_record_bytes(runs_path, record):
    runs_path = Path(runs_path)
    stamped = _stamp_v2_run_record(record)
    raw = runs_path.read_bytes() if runs_path.exists() else b""
    if raw and raw[-1:] not in (b"\n", b"\r"):
        raw += b"\n"
    line = (json.dumps(stamped, sort_keys=True) + "\n").encode("utf-8")
    return raw + line


def append_task_result(path, model, text, today):
    """Atomically append a result block to a task file."""
    path = Path(path)
    atomic_write_bytes(path, _prepare_task_result_bytes(path, model, text, today))
    return True


def append_task_note(home, path, heading, body):
    """Append an operational note to a task file. Not a model result and not a ledger row."""
    path = Path(path)
    heading = " ".join(str(heading or "").split())
    if not heading.startswith("## "):
        raise ValueError("A task note heading must start with '## '.")
    text = str(body or "").strip()
    if not text:
        raise ValueError("A task note needs a body.")
    with store_lock(home):
        if home is not None:
            recover_journal(home)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        block = f"\n{heading}\n{text}\n"
        commit_transaction(home, [(path, (existing.rstrip() + block).encode("utf-8"))])
    return path


def append_csv_row(path, values):
    """Atomically append one valid CSV row, repairing a missing final newline first."""
    path = Path(path)
    if not path.exists():
        return False
    atomic_write_bytes(path, _prepare_csv_row_bytes(path, values))
    return True


def append_ledger_row(ledger, today, task_id, model, note):
    """Atomically append one valid CSV row, repairing a missing final newline first."""
    append_csv_row(ledger, [today.isoformat(), task_id, model, "", note])


def append_proof_row(proofs, date_str, area, proof, link, dedupe_token=None, home=None):
    """Under the store lock, deduplicate and append one row to logs/proofs.csv."""
    proofs = Path(proofs)
    effective_home = Path(home) if home is not None else (proofs.parent.parent if proofs.parent.name == "logs" else None)
    with store_lock(effective_home):
        recover_journal(effective_home)
        if not proofs.exists():
            return False
        if dedupe_token and dedupe_token in proofs.read_text(encoding="utf-8"):
            return False
        data = _prepare_csv_row_bytes(proofs, [str(date_str), area, proof, str(link)])
        if effective_home is not None:
            commit_transaction(effective_home, [(proofs, data)])
        else:
            atomic_write_bytes(proofs, data)
        return True


def _has_run_id_unlocked(home, run_id):
    if not run_id or home is None:
        return False
    runs = Path(home) / "logs" / "runs.jsonl"
    if not runs.exists():
        return False
    for line in runs.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line).get("run_id") == run_id:
            return True
    return False


def has_run_id(home, run_id):
    """Return True if a run_id is already recorded in logs/runs.jsonl (after replaying any uncommitted journal)."""
    if not run_id or home is None:
        return False
    with store_lock(home):
        recover_journal(home)
        return _has_run_id_unlocked(home, run_id)


def append_run_record(home, record):
    """Atomically append one immutable JSONL run record to logs/runs.jsonl if logs/ exists."""
    if home is None:
        return None
    logs = Path(home) / "logs"
    if not logs.is_dir():
        return None
    with store_lock(home):
        recover_journal(home)
        if _has_run_id_unlocked(home, record.get("run_id")):
            return logs / "runs.jsonl"
        runs = logs / "runs.jsonl"
        commit_transaction(home, [(runs, _prepare_run_record_bytes(runs, record))])
        return runs


def record_result(home, path, model, text, today, note="written via lifeos mcp", run_id=None, run_record=None):
    """Commit task result, ledger row and optional run record as one locked, crash-recoverable multi-file commit."""
    path = Path(path)
    effective_id = run_id or (run_record.get("run_id") if isinstance(run_record, dict) else None)
    with store_lock(home):
        recover_journal(home)
        if _has_run_id_unlocked(home, effective_id):
            return False
        ops = [(path, _prepare_task_result_bytes(path, model, text, today))]
        if home is not None:
            ledger = Path(home) / "logs" / "ledger.csv"
            if ledger.exists():
                ops.append((ledger, _prepare_csv_row_bytes(ledger, [today.isoformat(), path.stem, model, "", note])))
            logs = Path(home) / "logs"
            if isinstance(run_record, dict) and logs.is_dir():
                runs = logs / "runs.jsonl"
                ops.append((runs, _prepare_run_record_bytes(runs, run_record)))
        commit_transaction(home, ops)
        return True
