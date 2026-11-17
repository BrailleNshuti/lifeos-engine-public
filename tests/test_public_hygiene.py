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
