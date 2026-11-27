"""Run the test files in a random order, N times, each with its own printed seed, to expose tests that depend on order.

Usage: python scripts/shuffle_run.py [--runs 3] [--seed 12345]
Standard library only. Exit code is 0 when every run passed, 1 otherwise. A failing seed can be replayed with --seed.
"""
import argparse
import random
import subprocess
import sys
from pathlib import Path


def test_files(root):
    return sorted(p.relative_to(root).as_posix() for p in (Path(root) / "tests").glob("test_*.py"))


def order(files, seed):
    shuffled = list(files)
    random.Random(seed).shuffle(shuffled)
    return shuffled


def command(files, seed):
    return f'"{sys.executable}" -m pytest -q -p no:cacheprovider {" ".join(files)}'


def positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("--runs must be at least 1")
    return value


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--runs", type=positive_int, default=3)
    p.add_argument("--seed", type=int, help="replay one order (runs once)")
    a = p.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    files = test_files(root)
    seeds = [a.seed] if a.seed is not None else [random.randrange(10**6) for _ in range(a.runs)]
    failed = []
    for seed in seeds:
        print(f"seed {seed}: {len(files)} test files in a shuffled order", flush=True)
        code = subprocess.run(command(order(files, seed), seed), shell=True, cwd=root).returncode
        print(f"seed {seed}: exit {code}", flush=True)
        if code:
            failed.append(seed)
    print("all orders passed" if not failed else f"FAILED seeds: {failed} (replay: python scripts/shuffle_run.py --seed N)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
