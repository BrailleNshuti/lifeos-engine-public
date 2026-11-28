"""`lifeos selfcheck`: damage in your own files is named, never repaired. Made-up data only."""
import json

import pytest

from lifeos import selfcheck
from lifeos.cli import main

TASK = """---
id: T-261201-demo
goal: a made-up goal
done_when: a made-up finish line that can be checked
route: claude
level: L0
status: todo
due: 2026-12-05
---
"""


def home_with_task(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "now.md").write_text("# now", encoding="utf-8")
    (tmp_path / "tasks" / "T-261201-demo.md").write_text(TASK, encoding="utf-8")
    return tmp_path


def test_a_sound_home_has_no_problems(tmp_path, capsys):
    home = home_with_task(tmp_path)
    (home / "logs" / "ratings.csv").write_text("date,task,model,score,kind,note\n2026-12-01,T-261201-demo,claude,4,x,ok\n", encoding="utf-8")
    (home / "waiting.json").write_text(json.dumps([{"item": "one thing", "who": "you", "when": "anytime"}]), encoding="utf-8")
    assert selfcheck.run(home) == []
    assert main(["--home", str(home), "selfcheck"]) == 0
    assert "sound" in capsys.readouterr().out


def test_an_empty_home_is_fine(tmp_path):
    assert selfcheck.run(tmp_path) == []


def test_a_bad_rating_row_is_named_with_its_line(tmp_path):
    home = home_with_task(tmp_path)
    (home / "logs" / "ratings.csv").write_text("date,task,model,score,kind,note\n2026-12-01,T-261201-demo,claude,9,x,n\nnot-a-date,T-261201-demo,claude,3,x,n\nshort,row\n", encoding="utf-8")
    msgs = [(p["where"], p["message"]) for p in selfcheck.check_ratings(home)]
    assert any(w.endswith(":2") and "1 to 5" in m for w, m in msgs)
    assert any(w.endswith(":3") and "not a date" in m for w, m in msgs)
    assert any(w.endswith(":4") and "fewer than four" in m for w, m in msgs)


def test_a_rating_for_an_unknown_task_is_only_a_warning(tmp_path):
    home = home_with_task(tmp_path)
    (home / "logs" / "ratings.csv").write_text("date,task,model,score\n2026-12-01,T-999999-ghost,claude,4\n", encoding="utf-8")
    found = selfcheck.check_ratings(home)
    assert [p["level"] for p in found] == ["warning"]
    assert selfcheck.exit_code(found) == 0


def test_a_wrong_ratings_header_is_an_error(tmp_path):
    home = home_with_task(tmp_path)
    (home / "logs" / "ratings.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    assert selfcheck.exit_code(selfcheck.check_ratings(home)) == 1


def test_a_waiting_list_that_is_not_a_list_or_has_an_empty_item(tmp_path):
    (tmp_path / "waiting.json").write_text("{}", encoding="utf-8")
    assert "list" in selfcheck.check_waiting(tmp_path)[0]["message"]
    (tmp_path / "waiting.json").write_text(json.dumps([{"item": " "}, {"item": "ok"}, 5]), encoding="utf-8")
    assert len(selfcheck.check_waiting(tmp_path)) == 2
    (tmp_path / "waiting.json").write_text("{not json", encoding="utf-8")
    assert "not valid JSON" in selfcheck.check_waiting(tmp_path)[0]["message"]


def test_a_broken_ledger_chain_is_an_error_and_nothing_is_changed(tmp_path, capsys):
    home = home_with_task(tmp_path)
    log = home / "logs" / "runs.jsonl"
    log.write_text('{"command":"ask","prev_hash":"deadbeef"}\n{"command":"ask","prev_hash":"cafebabe"}\n', encoding="utf-8")
    before = log.read_bytes()
    assert main(["--home", str(home), "selfcheck"]) == 1
    assert "chain broken" in capsys.readouterr().out
    assert log.read_bytes() == before


def test_a_task_without_a_finish_line_is_reported(tmp_path):
    home = home_with_task(tmp_path)
    (home / "tasks" / "T-261201-demo.md").write_text(TASK.replace("done_when: a made-up finish line that can be checked", "done_when: TODO"), encoding="utf-8")
    assert any(p["area"] == "tasks" for p in selfcheck.check_tasks(home))


def test_files_with_a_bom_and_bad_bytes_do_not_crash_it(tmp_path):
    home = home_with_task(tmp_path)
    (home / "logs" / "ratings.csv").write_bytes(b"\xef\xbb\xbfdate,task,model,score\n2026-12-01,T-261201-demo,claude,4\n\xff\xfe\n")
    (home / "waiting.json").write_bytes(b"\xef\xbb\xbf[]")
    selfcheck.run(home)


@pytest.mark.parametrize(("area", "name", "content"), [
    ("predictions", "predictions.csv", "when,id,kind,value,text\n2026-12-01,P-001,predict,70,claim\n"),
    ("experiments", "experiments.csv", "date,id,kind,metric,value,text\n2026-12-01,E-001,start\n"),
    ("vocabulary", "vocab.csv", "date,word,kind,value,text\nnot-a-date,Haus,add,house,example\n"),
])
def test_other_csv_data_damage_is_named_and_unchanged(tmp_path, area, name, content):
    home = home_with_task(tmp_path)
    path = home / "logs" / name
    path.write_text(content, encoding="utf-8")
    before = path.read_bytes()
    found = selfcheck.run(home)
    assert any(p["area"] == area and name in p["where"] for p in found)
    assert path.read_bytes() == before


def test_a_damaged_decision_is_named_and_unchanged(tmp_path):
    home = home_with_task(tmp_path)
    folder = home / "decisions"
    folder.mkdir()
    path = folder / "D-261201-demo.md"
    path.write_text("# no front matter\n", encoding="utf-8")
    before = path.read_bytes()
    found = selfcheck.run(home)
    assert any(p["area"] == "decisions" and path.name in p["where"] for p in found)
    assert path.read_bytes() == before


def test_sound_predictions_experiments_vocabulary_and_decisions_pass(tmp_path):
    home = home_with_task(tmp_path)
    (home / "logs" / "predictions.csv").write_text("date,id,kind,value,text\n2026-12-01,P-001,predict,70,claim\n", encoding="utf-8")
    (home / "logs" / "experiments.csv").write_text("date,id,kind,metric,value,text\n2026-12-01,E-001,start,proofs,1,{}\n", encoding="utf-8")
    (home / "logs" / "vocab.csv").write_text("date,word,kind,value,text\n2026-12-01,Haus,add,house,example\n", encoding="utf-8")
    folder = home / "decisions"
    folder.mkdir()
    (folder / "D-261201-demo.md").write_text(
        "---\nid: D-261201-demo\ntitle: Choose a demo\ndate: 2026-12-01\nrevisit: -\nprediction: -\n---\n# Choose a demo\n",
        encoding="utf-8",
    )
    assert selfcheck.run(home) == []
