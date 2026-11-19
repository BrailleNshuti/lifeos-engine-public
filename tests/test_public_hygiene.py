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
