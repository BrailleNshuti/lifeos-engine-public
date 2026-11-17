"""Release hygiene for v0.3: licence, security policy, version, changelog, ignore rules."""
import re
from pathlib import Path

import lifeos

ROOT = Path(__file__).resolve().parent.parent
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_licence_is_mit_with_owner_name():
    text = read("LICENSE")
    assert text.startswith("MIT License")
    assert "Copyright (c) 2026 Braille Nshuti Rusingiza" in text
    assert "Permission is hereby granted, free of charge" in text


def test_version_is_030_in_both_places():
    toml = read("pyproject.toml")
    match = re.search(r'^version = "([^"]+)"', toml, re.M)
    assert match and match.group(1) == lifeos.__version__ == "0.3.0"


def test_changelog_top_entry_matches_version():
    entries = re.findall(r"^## \[([^\]]+)\]", read("CHANGELOG.md"), re.M)
    assert entries[0] == lifeos.__version__


def test_security_policy_has_no_email_and_points_to_github_reporting():
    text = read("SECURITY.md")
    assert not EMAIL.search(text)
    assert "private vulnerability reporting" in text.lower()


def test_contributing_and_checklist_exist_without_emails():
    for name in ("CONTRIBUTING.md", "docs/RELEASE-CHECKLIST.md"):
        text = read(name)
        assert text.strip(), name
        assert not EMAIL.search(text), name


def test_gitignore_covers_ide_folders():
    lines = read(".gitignore").splitlines()
    assert ".idea/" in lines and ".vscode/" in lines


def test_readme_names_the_licence():
    text = read("README.md")
    assert "Licence: MIT" in text
    assert "to be chosen" not in text
