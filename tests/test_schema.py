import csv
from pathlib import Path

from lifeos import schema
from lifeos.cli import main

ROOT = Path(__file__).resolve().parent.parent


def test_the_committed_page_matches_the_code():
    assert (ROOT / "docs" / "LOGS.md").read_text(encoding="utf-8") == schema.page(), "run: lifeos schema --write docs/LOGS.md"


def test_every_csv_in_the_demo_home_has_exactly_the_documented_columns():
    documented = {Path(name).name: list(cols) for name, _w, cols, _n in schema.CSV_LOGS}
    for path in (ROOT / "examples" / "demo-home" / "logs").glob("*.csv"):
        if path.name in documented:
            assert next(csv.reader(path.open(encoding="utf-8"))) == documented[path.name], path.name


def test_cli_write_and_check(tmp_path, capsys):
    out = tmp_path / "LOGS.md"
    assert main(["schema", "--check", str(out)]) == 1
    assert main(["schema", "--write", str(out)]) == 0
    assert main(["schema", "--check", str(out)]) == 0
    out.write_text("old", encoding="utf-8")
    assert main(["schema", "--check", str(out)]) == 1
