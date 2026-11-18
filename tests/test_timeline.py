import datetime as dt

from lifeos import timeline
from lifeos.cli import main

D = dt.date(2026, 11, 18)  # a Wednesday, ISO week 47


def logs(home, proofs, ledger):
    (home / "logs").mkdir(exist_ok=True)
    (home / "logs" / "proofs.csv").write_text("date,area,proof,link\n" + "".join(f"{d},lab,p,l\n" for d in proofs), encoding="utf-8")
    (home / "logs" / "ledger.csv").write_text("date,task,model,minutes_saved,note\n" + "".join(f"{d},T,m,{m},\n" for d, m in ledger), encoding="utf-8")


def test_weeks_are_counted_oldest_first_with_empty_weeks_kept(tmp_path):
    logs(tmp_path, ["2026-11-02", "2026-11-03", "2026-11-17"], [("2026-11-17", 30), ("2026-11-04", 10)])
    rows = timeline.weeks(tmp_path, today=D, count=4)
    assert [r["week"] for r in rows] == ["2026-W44", "2026-W45", "2026-W46", "2026-W47"]
    assert [r["proofs"] for r in rows] == [0, 2, 0, 1]
    assert [r["minutes"] for r in rows] == [0, 10, 0, 30]


def test_damaged_dates_are_ignored_and_render_has_a_bar_per_week(tmp_path):
    logs(tmp_path, ["not-a-date", "2026-11-17"], [])
    out = timeline.render(timeline.weeks(tmp_path, today=D, count=3))
    assert out.count("\n") >= 3 and "2026-W47" in out and "#" in out


def test_cli(tmp_path, capsys):
    (tmp_path / "now.md").write_text("# now\n", encoding="utf-8")
    assert main(["--home", str(tmp_path), "timeline", "--weeks", "3"]) == 0
    assert "proofs" in capsys.readouterr().out
