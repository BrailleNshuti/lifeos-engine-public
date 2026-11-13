import csv
import datetime as dt
import json

from lifeos.store import append_ledger_row, append_run_record, model_call_flags, model_call_note, new_run_id, record_result



def test_model_call_note_round_trips_without_string_contract_drift():
    note = model_call_note(3)
    assert note == "asked via lifeos ask; flags: 3"
    assert model_call_flags(note) == 3
    assert model_call_flags("old row without flags") == 0


def test_ledger_writer_quotes_commas_and_repairs_missing_newline(tmp_path):
    ledger = tmp_path / "ledger.csv"
    ledger.write_text("date,task,model,minutes_saved,note", encoding="utf-8")
    append_ledger_row(ledger, dt.date(2026, 11, 20), "T-1", "chat", "written, checked")
    with ledger.open(newline="", encoding="utf-8") as handle:
        assert list(csv.reader(handle))[-1] == ["2026-11-20", "T-1", "chat", "", "written, checked"]
    raw = ledger.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r\n" not in raw


def test_record_result_is_idempotent_on_duplicate_retry(tmp_path):
    (tmp_path / "logs").mkdir()
    ledger = tmp_path / "logs" / "ledger.csv"
    ledger.write_text("date,task,model,minutes_saved,note\n", encoding="utf-8")
    task = tmp_path / "T-261120-demo.md"
    task.write_text("# Task\n", encoding="utf-8")
    day = dt.date(2026, 11, 20)
    rid = new_run_id(day)
    record_result(tmp_path, task, "codex", "Fixed in store.py. Next step: merge.", day, "asked via lifeos ask; flags: 0", run_id=rid)
    append_run_record(tmp_path, {"run_id": rid, "model": "codex", "status": "ok"})
    record_result(tmp_path, task, "codex", "Fixed in store.py. Next step: merge.", day, "asked via lifeos ask; flags: 0", run_id=rid)
    append_run_record(tmp_path, {"run_id": rid, "model": "codex", "status": "ok"})
    assert task.read_text(encoding="utf-8").count("## Result · codex · 2026-11-20") == 1
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 2
    assert len((tmp_path / "logs" / "runs.jsonl").read_text(encoding="utf-8").splitlines()) == 1



def test_append_run_record_writes_valid_jsonl(tmp_path):
    (tmp_path / "logs").mkdir()
    rid = new_run_id(dt.date(2026, 11, 20))
    assert rid.startswith("R-261120-")
    path = append_run_record(tmp_path, {"run_id": rid, "model": "qwen:qwen2.5:3b", "locality": "local", "status": "ok"})
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["run_id"] == rid and row["locality"] == "local"


