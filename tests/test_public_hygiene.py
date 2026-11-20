import shutil
import subprocess

import pytest

# Built from pieces so this file does not contain the words it forbids.
EMPLOYER = "gan" + "naca"
INTERNAL_ID = "D" + "16"


def tracked_files():
    git = shutil.which("git")
    if not git:
        pytest.skip("git not available")
    here = subprocess.run([git, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if here.returncode != 0:
        pytest.skip("not a git checkout")
    out = subprocess.run([git, "ls-files"], cwd=here.stdout.strip(), capture_output=True, text=True, check=True)
    return here.stdout.strip(), [name for name in out.stdout.splitlines() if name]


# References to a private plan mean nothing to a stranger reading a public repo. Built from pieces for the same reason.
PLAN_REFERENCES = [
    "Sec" + r"tion \d+\.\d+",          # a numbered section of the plan
    "Master" + r" Plan",
    "Appen" + r"dix [A-Z]\d+",         # a lettered appendix of the plan
    r"\bD\d{1,2}\b",                   # short decision ids (a letter D and one or two digits)
    "work" + "-lane",
]
EXEMPT = {"CHANGELOG.md", "STATE.md", "docs/ARCHITECTURE-GRAPH.md"}  # history and notes may name what was removed


@pytest.mark.parametrize("pattern", PLAN_REFERENCES)
def test_no_reference_to_a_private_plan_in_public_files(pattern):
    import re
    root, names = tracked_files()
    found = []
    for name in names:
        if name in EXEMPT:
            continue
        try:
            text = open(f"{root}/{name}", encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(pattern, text):
            found.append(name)
    assert not found, f"'{pattern}' still appears in: {found}"


@pytest.mark.parametrize("word", [EMPLOYER, INTERNAL_ID])
def test_no_employer_name_or_private_decision_id_in_any_tracked_file(word):
    root, names = tracked_files()
    found = []
    for name in names:
        try:
            text = open(f"{root}/{name}", encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        if word.lower() in text.lower():
            found.append(name)
    assert not found, f"remove '{word}' from: {found}"


# Personal study targets, a private side project and a private milestone must not appear in the public repo.
# Terms are built from pieces so this file does not contain what it forbids; the list stays short and generic.
PERSONAL_TERMS = [
    "i" + "wa",                        # a private side project
    "goe" + "the",                     # a named language exam
    "DLB" + "D",                       # a private course-module code prefix
    "CSEB" + "DS",                     # a private course-module code prefix
    "Gate" + r" \d",                  # a private milestone name
    r"\bI" + r"U\b",                   # a private study provider
]


@pytest.mark.parametrize("term", PERSONAL_TERMS)
def test_no_personal_study_target_or_project_in_any_tracked_file(term):
    import re
    root, names = tracked_files()
    found = []
    for name in names:
        try:
            text = open(f"{root}/{name}", encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            continue
        if re.search(term, text, flags=re.I if term != PERSONAL_TERMS[-1] else 0):
            found.append(name)
    assert not found, f"'{term}' still appears in: {found}"
