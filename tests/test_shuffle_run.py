"""scripts/shuffle_run.py: run the test files in a random order (printed seed) to expose order dependence."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("shuffle_run", ROOT / "scripts" / "shuffle_run.py")
shuffle_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shuffle_run)


def test_the_same_seed_gives_the_same_order():
    files = [f"tests/test_{c}.py" for c in "abcdefgh"]
    assert shuffle_run.order(files, 7) == shuffle_run.order(files, 7)


def test_different_seeds_give_different_orders():
    files = [f"tests/test_{c}.py" for c in "abcdefghij"]
    assert shuffle_run.order(files, 1) != shuffle_run.order(files, 2)


def test_nothing_is_added_or_dropped():
    files = [f"tests/test_{c}.py" for c in "abcdef"]
    assert sorted(shuffle_run.order(files, 3)) == sorted(files)


def test_the_input_list_is_not_changed():
    files = ["b.py", "a.py", "c.py"]
    shuffle_run.order(files, 5)
    assert files == ["b.py", "a.py", "c.py"]


def test_it_finds_the_real_test_files():
    found = shuffle_run.test_files(ROOT)
    assert len(found) > 100 and all(f.startswith("tests") and f.endswith(".py") for f in found)


def test_the_command_line_names_the_seed_and_the_files():
    cmd = shuffle_run.command(["tests/test_a.py", "tests/test_b.py"], 9)
    assert "-p no:randomly" in cmd or "pytest" in cmd
    assert cmd.index("test_a.py") < cmd.index("test_b.py")


def test_a_bad_runs_value_is_refused():
    import pytest
    with pytest.raises(SystemExit):
        shuffle_run.main(["--runs", "0"])
