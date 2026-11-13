import csv
import datetime as dt

from lifeos.store import append_ledger_row, model_call_flags, model_call_note


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
