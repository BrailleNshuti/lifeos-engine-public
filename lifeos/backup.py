"""`lifeos backup --out DIR`: copy logs/ to a dated folder with a MANIFEST of SHA-256 hashes; `--check DIR` verifies it.

Logs are the part of your home that cannot be rebuilt (runs, ratings, predictions, proofs). The copy stays on disk where
you point it: nothing is uploaded. The manifest also records the run-ledger head hash, which you can pass to
`lifeos verify --anchor`. A backup is never overwritten and never written inside the home.
"""
import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path

from . import verify

MANIFEST = "MANIFEST.json"


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
    return folder


def check(folder):
    folder = Path(folder)
    path = folder / MANIFEST
    if not path.exists():
        return {"ok": False, "files": 0, "errors": [f"no {MANIFEST} in {folder}"]}
    man = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    for rel, digest in man["files"].items():
        f = folder / rel
        if not f.exists():
            errors.append(f"{rel}: missing")
        elif _sha(f) != digest:
            errors.append(f"{rel}: changed since the backup")
    known = set(man["files"])
    errors += [f"{p.relative_to(folder).as_posix()}: not in the manifest" for p in _files(folder)
               if p.relative_to(folder).as_posix() not in known]
    return {"ok": not errors, "files": len(man["files"]), "head": man.get("head"), "errors": errors}
