"""Round 3 item 8: ratings, predictions, experiments and vocabulary survive damaged files (CRLF, BOM, NUL bytes, broken
quotes, short and long rows, binary junk, a header only, an empty file): every reader returns, none raises."""
import random
import shutil

import pytest

from lifeos import calibrate, earn, experiment, learn, sunday, vocab

CASES = {
    "empty": b"",
    "header_only": b"date,task,model,score,kind,note\n",
    "bom_crlf": b"\xef\xbb\xbfdate,task,model,score,kind,note\r\n2026-11-27,T-1,claude,4,code,ok\r\n",
    "nul_bytes": b"date,task,model,score,kind,note\n2026-11-27,T-1,cla\x00ude,4,code,o\x00k\n",
    "broken_quote": b'date,task,model,score,kind,note\n2026-11-27,T-1,claude,4,code,"never closed\n2026-11-28,T-2,codex,3,code,fine\n',
    "short_row": b"date,task,model,score,kind,note\n2026-11-27,T-1\n",
    "long_row": b"date,task,model,score,kind,note\n2026-11-27,T-1,claude,4,code,a,b,c,d,e,f\n",
    "binary": bytes(random.Random(5).randrange(256) for _ in range(2000)),
    "latin1": "date,task,model,score,kind,note\n2026-11-27,T-1,claude,4,code,Müller\n".encode("latin-1"),
    "huge_cell": b"date,task,model,score,kind,note\n2026-11-27,T-1,claude,4,code," + b"x" * 200000 + b"\n",
    "bad_score": b"date,task,model,score,kind,note\n2026-11-27,T-1,claude,many,code,x\n2026-11-27,T-1,claude,,code,x\n",
    "bad_date": b"date,task,model,score,kind,note\nnot-a-date,T-1,claude,4,code,x\n",
}
FILES = {"ratings.csv": learn.read_ratings, "predictions.csv": calibrate.report, "experiments.csv": experiment.list_all,
         "vocab.csv": vocab.stats}


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


@pytest.mark.parametrize("case", sorted(CASES))
@pytest.mark.parametrize("name", sorted(FILES))
def test_each_reader_survives_each_damaged_file(home, name, case):
    (home / "logs" / name).write_bytes(CASES[case])
    FILES[name](home)  # must not raise


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_reports_survive_damaged_logs(home, case):
    for name in FILES:
        (home / "logs" / name).write_bytes(CASES[case])
    (home / "logs" / "runs.jsonl").write_bytes(CASES[case])
    import datetime as dt
    earn.review(home, today=dt.date(2026, 11, 27))
    sunday.build(home, today=dt.date(2026, 11, 27))
    learn.report(home)


@pytest.mark.parametrize("case", ["bom_crlf", "broken_quote", "short_row", "latin1"])
def test_adding_a_rating_to_a_damaged_file_still_works(home, case):
    (home / "logs" / "ratings.csv").write_bytes(CASES[case])
    learn.add_rating(home, "T-9", "claude", 3, "implement a python module", note="after damage")
    assert any(r.get("note") == "after damage" for r in learn.read_ratings(home))
