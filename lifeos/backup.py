"""`lifeos backup --out DIR`: copy logs/ to a dated folder with a MANIFEST of SHA-256 hashes; `--check DIR` verifies it.

Logs are the part of your home that cannot be rebuilt (runs, ratings, predictions, proofs). The copy stays on disk where
you point it: nothing is uploaded. The manifest also records the run-ledger head hash, which you can pass to
`lifeos verify --anchor`. A backup is never overwritten and never written inside the home.
"""
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath

from . import verify

MANIFEST = "MANIFEST.json"
STAMP = ".last-backup"


class BackupError(Exception):
    pass


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _files(root):
    base = Path(root) / "logs"
    return sorted(p for p in base.rglob("*") if p.is_file()) if base.exists() else []


def make(home, out, today=None):
    home, out = Path(home).resolve(), Path(out).resolve()
    if out == home or home in out.parents:
        raise BackupError("Write the backup outside your home (not inside it).")
    today = today or dt.date.today()
    folder = out / f"lifeos-backup-{today:%Y%m%d}"
    if folder.exists():
        raise BackupError(f"{folder} exists: a backup is never overwritten. Pick another --out.")
    files = _files(home)
    if not files:
        raise BackupError("No logs to back up.")
    hashes = {}
    for src in files:
        rel = src.relative_to(home).as_posix()
        dest = folder / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        hashes[rel] = _sha(dest)
    manifest = {"date": today.isoformat(), "head": verify.verify_chain(home)["head"], "files": hashes}
    (folder / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    try:  # remember the day, so `today` can say when a backup is overdue; never fails the backup
        (home / STAMP).write_text(today.isoformat() + chr(10), encoding="utf-8")
    except OSError:
        pass
    return folder


def age_days(home, today=None):
    """Days since the last `backup --out` made from this home, or None when none was ever made. Never raises."""
    try:
        last = dt.date.fromisoformat((Path(home) / STAMP).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return ((today or dt.date.today()) - last).days


def check(folder):
    folder = Path(folder).resolve()
    path = folder / MANIFEST
    if not path.exists():
        return {"ok": False, "files": 0, "errors": [f"no {MANIFEST} in {folder}"]}
    try:
        man = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        return {"ok": False, "files": 0, "errors": [f"manifest cannot be read: {err}"]}
    files = man.get("files") if isinstance(man, dict) else None
    if not isinstance(files, dict):
        return {"ok": False, "files": 0, "errors": ["manifest must contain a files object"]}
    errors = []
    known = set()
    for rel, digest in files.items():
        parts = PurePosixPath(rel.replace("\\", "/")) if isinstance(rel, str) else PurePosixPath()
        f = (folder / Path(*parts.parts)).resolve()
        if (not parts.parts or parts.is_absolute() or parts.parts[0] != "logs" or ".." in parts.parts
                or folder not in f.parents):
            errors.append(f"{rel}: unsafe path in manifest")
            continue
        known.add(parts.as_posix())
        if not f.is_file():
            errors.append(f"{rel}: missing")
        else:
            try:
                if _sha(f) != digest:
                    errors.append(f"{rel}: changed since the backup")
            except OSError as err:
                errors.append(f"{rel}: cannot be read: {err}")
    errors += [f"{p.relative_to(folder).as_posix()}: not in the manifest" for p in _files(folder)
               if p.relative_to(folder).as_posix() not in known]
    return {"ok": not errors, "files": len(files), "head": man.get("head"), "errors": errors}


def restore(home, folder, now=None):
    """Put a checked backup's logs/ back into the home. The backup must pass `check` first; the logs/ it replaces are moved to
    `logs.before-restore-<time>` inside the home, never deleted, so a restore can itself be undone. Returns the moved folder
    (or None when the home had no logs/)."""
    home, folder = Path(home).resolve(), Path(folder).resolve()
    if folder == home or home in folder.parents:
        raise BackupError("The backup folder must be outside your home.")
    res = check(folder)
    if not res["ok"]:
        raise BackupError("The backup does not match its manifest, so nothing was restored: " + "; ".join(res["errors"][:3]))
    stamp = (now or dt.datetime.now()).strftime("%Y%m%d-%H%M%S")
    aside = None
    live = home / "logs"
    if live.exists():
        aside = home / f"logs.before-restore-{stamp}"
        if aside.exists():
            raise BackupError(f"{aside.name} already exists; try again in a second.")
        live.rename(aside)
    try:
        shutil.copytree(folder / "logs", live)
        copied = {p.relative_to(home).as_posix(): _sha(p) for p in _files(home)}
        wanted = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))["files"]
        if copied != wanted:
            raise BackupError("The restored files do not match the manifest.")
    except Exception:
        shutil.rmtree(live, ignore_errors=True)
        if aside is not None:
            aside.rename(live)
        raise
    return aside
