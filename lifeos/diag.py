"""Failure-only diagnostics for `os.replace`: when it fails with PermissionError, say why and who holds the file.

On Windows, `os.replace` raises PermissionError (winerror 5 or 32) when another process has the destination open without
delete sharing, and that includes short-lived readers such as a virus scanner or an indexer. This module runs ONLY after
such a failure: it writes one line to stderr and, when LIFEOS_REPLACE_DIAG names a file, one JSON line there. It lists the
processes that hold the paths (Windows Restart Manager, standard library `ctypes`) and says whether this process is one of them.
It never raises: a bug here must not hide the real error. The retry itself lives in `store` (a few short pauses, only for
that Windows error); this module only reports how it went. Nothing is sent anywhere.
"""
import datetime as dt
import json
import os
import sys
import threading

ENV = "LIFEOS_REPLACE_DIAG"
ERROR_MORE_DATA = 234


def holders(path):
    """[{pid, name}] of the processes that have `path` open right now (Windows only; [] elsewhere or on any error)."""
    if os.name != "nt":
        return []
    try:
        return _restart_manager(str(path))
    except Exception:
        return []


def _restart_manager(path):
    import ctypes
    from ctypes import wintypes

    class Unique(ctypes.Structure):
        _fields_ = [("pid", wintypes.DWORD), ("started", wintypes.FILETIME)]

    class Info(ctypes.Structure):
        _fields_ = [("process", Unique), ("app", ctypes.c_wchar * 256), ("service", ctypes.c_wchar * 64),
                    ("kind", ctypes.c_int), ("status", ctypes.c_ulong), ("session", wintypes.DWORD),
                    ("restartable", wintypes.BOOL)]

    rm = ctypes.WinDLL("Rstrtmgr")
    session, key = wintypes.DWORD(), ctypes.create_unicode_buffer(33)
    if rm.RmStartSession(ctypes.byref(session), 0, key) != 0:
        return []
    try:
        files = (wintypes.LPCWSTR * 1)(path)
        if rm.RmRegisterResources(session, 1, files, 0, None, 0, None) != 0:
            return []
        needed, have, reasons = wintypes.UINT(0), wintypes.UINT(0), wintypes.DWORD(0)
        code = rm.RmGetList(session, ctypes.byref(needed), ctypes.byref(have), None, ctypes.byref(reasons))
        if code != ERROR_MORE_DATA or not needed.value:
            return []
        found = (Info * needed.value)()
        have = wintypes.UINT(needed.value)
        if rm.RmGetList(session, ctypes.byref(needed), ctypes.byref(have), found, ctypes.byref(reasons)) != 0:
            return []
        return [{"pid": found[i].process.pid, "name": found[i].app} for i in range(have.value)]
    finally:
        rm.RmEndSession(session)


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _append(rec):
    target = os.environ.get(ENV)
    if target:
        with open(target, "a", encoding="utf-8") as out:
            out.write(json.dumps(rec, sort_keys=True) + "\n")


def recovered(err, src, dst, attempts):
    """A replace that failed with a sharing violation and then worked. File only, no noise: it is how the retry is measured."""
    try:
        _append({"event": "os.replace recovered", "time": _now(), "errno": err.errno,
                 "winerror": getattr(err, "winerror", None), "dst": str(dst), "attempts": attempts, "pid": os.getpid()})
    except Exception:
        return None


def describe(err, src, dst, attempts=1):
    """Everything worth knowing about one failed replace, as a plain dict."""
    mine = os.getpid()
    on_dst, on_src = holders(dst), holders(src)
    return {"event": "os.replace failed", "time": _now(), "attempts": attempts,
            "errno": err.errno, "winerror": getattr(err, "winerror", None), "message": str(err.strerror or err),
            "src": str(src), "dst": str(dst), "src_exists": os.path.exists(src), "dst_exists": os.path.exists(dst),
            "pid": mine, "thread": threading.current_thread().name, "threads": threading.active_count(),
            "holders_dst": on_dst, "holders_src": on_src,
            "own_pid_holds": any(h["pid"] == mine for h in on_dst + on_src)}


def report(err, src, dst, attempts=1):
    """Write the diagnostic line(s) for a replace that finally failed. Never raises, never retries."""
    try:
        rec = describe(err, src, dst, attempts)
        names = ", ".join(f"{h['pid']} {h['name']}" for h in rec["holders_dst"] + rec["holders_src"]) or "none seen"
        print(f"lifeos: os.replace failed after {attempts} attempt(s) (errno={rec['errno']} winerror={rec['winerror']}) "
              f"dst={rec['dst']} holders: {names}; own process holds it: {rec['own_pid_holds']}", file=sys.stderr)
        _append(rec)
    except Exception:
        return None
