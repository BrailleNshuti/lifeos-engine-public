import datetime as dt

import pytest

from lifeos import export
from lifeos.cli import main

D = dt.date(2026, 11, 18)
KEY = "sk-ant-api03-" + "a1B2c3D4" * 5


def home_with(tmp_path, proof="Shipped lifeos earn"):
    (tmp_path / "logs").mkdir()
    (tmp_path / "now.md").write_text("# now\n", encoding="utf-8")
    (tmp_path / "logs" / "proofs.csv").write_text(f"date,area,proof,link\n2026-11-17,lab,{proof},https://example.org/pr/1\n", encoding="utf-8")
    (tmp_path / "logs" / "ledger.csv").write_text("date,task,model,minutes_saved,note\n2026-11-17,T,claude,40,\n", encoding="utf-8")
    return tmp_path


def test_the_bundle_has_proofs_numbers_and_the_ledger_head(tmp_path):
    text = export.build(home_with(tmp_path), today=D)
    assert "Shipped lifeos earn" in text and "https://example.org/pr/1" in text
    assert "Minutes saved: 40" in text and "Ledger head" in text and "2026-11-18" in text


def test_secrets_never_reach_the_bundle(tmp_path):
    text = export.build(home_with(tmp_path, proof=f"key {KEY}"), today=D)
    assert KEY not in text and "[redacted:" in text


def test_write_never_overwrites(tmp_path):
    home = home_with(tmp_path)
    out = tmp_path / "evidence.md"
    export.write(home, out, today=D)
    with pytest.raises(export.ExportError, match="exists"):
        export.write(home, out, today=D)


def test_cli(tmp_path, capsys):
    home = home_with(tmp_path)
    out = tmp_path / "e.md"
    assert main(["--home", str(home), "export", "--out", str(out)]) == 0
    assert out.exists()
    assert main(["--home", str(home), "export", "--out", str(out)]) == 2
