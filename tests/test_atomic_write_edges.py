"""Edges of atomic_write_bytes found in a Codex review (2026-11-26) and checked against the code."""
import os
import stat

import pytest

from lifeos import store


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_a_private_file_stays_private_after_a_rewrite(tmp_path):
    path = tmp_path / "ledger.csv"
    path.write_bytes(b"old")
    os.chmod(path, 0o600)
    old_umask = os.umask(0o022)
    try:
        store.atomic_write_bytes(path, b"new")
    finally:
        os.umask(old_umask)
    assert path.read_bytes() == b"new"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_new_file_is_still_created(tmp_path):
    path = tmp_path / "fresh.csv"
    store.atomic_write_bytes(path, b"x")
    assert path.read_bytes() == b"x"
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_a_failed_cleanup_never_hides_the_real_error(tmp_path, monkeypatch):
    """The replace fails; removing the temp file then fails too (a scanner holds it). The caller must see the replace error."""
    path = tmp_path / "ledger.csv"
    path.write_bytes(b"old")

    def boom(tmp, dst):
        raise PermissionError(13, "replace denied")

    monkeypatch.setattr(store, "_replace", boom)
    real_unlink = type(path).unlink

    def stuck_unlink(self, *args, **kwargs):
        if self.name.endswith(".tmp"):
            raise PermissionError(13, "cleanup denied")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(type(path), "unlink", stuck_unlink)
    with pytest.raises(PermissionError, match="replace denied"):
        store.atomic_write_bytes(path, b"new")
    assert path.read_bytes() == b"old"
