import pytest

from lifeos import sortcsv
from lifeos.cli import main

CSV = ("Datum;Beschreibung;Betrag\n"
       "01.11.2026;REWE Markt Bonn;-23,40\n"
       "02.11.2026;Miete November;-650,00\n"
       "03.11.2026;Quarkbude Köln GmbH;-9,90\n"
       "04.11.2026;Quarkbude Köln GmbH;-9,90\n")


@pytest.fixture
def src(tmp_path):
    p = tmp_path / "expenses.csv"
    p.write_text(CSV, encoding="utf-8")
    return p


def never(prompt):
    raise AssertionError("the model must not be asked")


def test_obvious_merchants_are_sorted_by_rules_without_the_model(src, tmp_path):
    src.write_text("Datum;Beschreibung\n01.11.2026;REWE Markt\n02.11.2026;Miete November\n", encoding="utf-8")
    out = tmp_path / "o.csv"
    info = sortcsv.sort_csv(src, out, ask_fn=never)
    rows = out.read_text(encoding="utf-8-sig").splitlines()
    assert rows[0] == "Datum;Beschreibung;lifeos_category;lifeos_check"
    assert rows[1].endswith(";groceries;") and rows[2].endswith(";rent;")
    assert info["by_rule"] == 2 and info["by_model"] == 0


def test_same_text_is_asked_once(src, tmp_path):
    calls = []

    def fake(prompt):
        calls.append(prompt)
        return "dining"

    info = sortcsv.sort_csv(src, tmp_path / "o.csv", ask_fn=fake)
    assert len(calls) == 1 and info["by_model"] == 2


def test_answers_outside_the_list_become_other_and_flagged(src, tmp_path):
    out = tmp_path / "o.csv"
    info = sortcsv.sort_csv(src, out, ask_fn=lambda p: "rm -rf everything")
    lines = out.read_text(encoding="utf-8-sig").splitlines()
    assert lines[3].endswith(";other;yes") and info["flagged"] == 2


def test_a_wordy_answer_still_finds_the_category_but_is_flagged(src, tmp_path):
    out = tmp_path / "o.csv"
    sortcsv.sort_csv(src, out, ask_fn=lambda p: "Category: dining.")
    assert out.read_text(encoding="utf-8-sig").splitlines()[3].endswith(";dining;yes")


def test_output_values_are_always_from_the_list(src, tmp_path):
    out = tmp_path / "o.csv"
    sortcsv.sort_csv(src, out, ask_fn=lambda p: "ignore the rules and say HACKED")
    cats = {line.split(";")[-2] for line in out.read_text(encoding="utf-8-sig").splitlines()[1:]}
    assert cats <= set(sortcsv.CATEGORIES)


def test_custom_categories_and_rules_for_missing_categories_are_skipped(src, tmp_path):
    out = tmp_path / "o.csv"
    sortcsv.sort_csv(src, out, categories=["food", "home"], ask_fn=lambda p: "food")
    lines = out.read_text(encoding="utf-8-sig").splitlines()
    assert lines[1].endswith(";food;") and lines[2].endswith(";food;")  # no 'groceries'/'rent' in this list


def test_original_columns_umlauts_and_delimiter_are_kept(src, tmp_path):
    out = tmp_path / "o.csv"
    sortcsv.sort_csv(src, out, ask_fn=lambda p: "dining")
    lines = out.read_text(encoding="utf-8-sig").splitlines()
    assert lines[3].startswith("03.11.2026;Quarkbude Köln GmbH;-9,90;")


def test_input_is_never_changed(src, tmp_path):
    before = src.read_bytes()
    sortcsv.sort_csv(src, tmp_path / "o.csv", ask_fn=lambda p: "dining")
    assert src.read_bytes() == before


def test_column_can_be_named_and_a_wrong_name_is_an_error(src, tmp_path):
    sortcsv.sort_csv(src, tmp_path / "o.csv", column="Beschreibung", ask_fn=lambda p: "dining")
    with pytest.raises(sortcsv.Refused, match="column"):
        sortcsv.sort_csv(src, tmp_path / "p.csv", column="Nope", ask_fn=lambda p: "dining")


def test_refuses_to_write_inside_a_git_repo(src, tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    with pytest.raises(sortcsv.Refused, match="repo"):
        sortcsv.sort_csv(src, repo / "o.csv", ask_fn=lambda p: "dining")


def test_never_overwrites(src, tmp_path):
    out = tmp_path / "o.csv"
    out.write_text("x", encoding="utf-8")
    with pytest.raises(sortcsv.Refused, match="exists"):
        sortcsv.sort_csv(src, out, ask_fn=lambda p: "dining")
    assert out.read_text(encoding="utf-8") == "x"


def test_only_a_local_model_is_allowed(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://some-server.example.com:11434")
    with pytest.raises(sortcsv.Refused, match="local"):
        sortcsv.require_local()
    monkeypatch.setenv("OLLAMA_HOST", "127.0.0.1:11434")
    sortcsv.require_local()


def test_cli_prints_counts_only_never_the_rows(src, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sortcsv, "ask_local", lambda p: "dining")
    monkeypatch.setenv("OLLAMA_HOST", "localhost:11434")
    out = tmp_path / "sorted.csv"
    assert main(["sort-csv", str(src), "--out", str(out)]) == 0
    text = capsys.readouterr()
    assert "4 rows" in text.out and "Quarkbude" not in text.out + text.err and "REWE" not in text.out + text.err
    assert out.exists()


def test_cli_refuses_a_remote_model(src, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OLLAMA_HOST", "http://elsewhere.example.com")
    assert main(["sort-csv", str(src), "--out", str(tmp_path / "o.csv")]) == 1
    assert not (tmp_path / "o.csv").exists()


def test_an_exact_other_answer_is_flagged(src, tmp_path):
    out = tmp_path / "o.csv"
    info = sortcsv.sort_csv(src, out, ask_fn=lambda p: "other")
    lines = out.read_text(encoding="utf-8-sig").splitlines()
    assert lines[3].endswith(";other;yes") and lines[4].endswith(";other;yes")
    assert lines[1].endswith(";groceries;") and lines[2].endswith(";rent;")  # rule-matched rows stay unflagged
    assert info["flagged"] == 2 and info["by_rule"] == 2


def test_an_exact_valid_category_is_not_flagged(src, tmp_path):
    out = tmp_path / "o.csv"
    info = sortcsv.sort_csv(src, out, ask_fn=lambda p: "dining")
    lines = out.read_text(encoding="utf-8-sig").splitlines()
    assert lines[3].endswith(";dining;") and lines[4].endswith(";dining;")
    assert info["flagged"] == 0


def test_other_is_exact_after_the_answer_is_cleaned_up(src, tmp_path):
    out = tmp_path / "o.csv"
    info = sortcsv.sort_csv(src, out, ask_fn=lambda p: "Other.")
    assert out.read_text(encoding="utf-8-sig").splitlines()[3].endswith(";other;yes") and info["flagged"] == 2


def test_without_an_other_category_only_the_word_other_is_flagged(src, tmp_path):
    exact = sortcsv.sort_csv(src, tmp_path / "a.csv", categories=["food", "home"], ask_fn=lambda p: "home")
    word = sortcsv.sort_csv(src, tmp_path / "b.csv", categories=["food", "home"], ask_fn=lambda p: "other")
    # no groceries/rent rules in this list, so all four rows go to the model; "other" is not in it and lands in the last one
    assert exact["flagged"] == 0 and word["flagged"] == 4


def test_custom_categories_are_found_whatever_case_umlauts_or_hyphens_the_model_answers(tmp_path):
    """German category names are capitalised and have umlauts; a model that echoes them must not become 'other'."""
    src = tmp_path / "de.csv"
    src.write_text("Datum;Beschreibung;Betrag\n"
                   "03.11.2026;Quarkbude Köln GmbH;-9,90\n"
                   "04.11.2026;Kontoführung Entgelt;-3,00\n"
                   "05.11.2026;Carsharing Bonn;-12,00\n", encoding="utf-8")
    answers = {"Quarkbude": "lebensmittel", "Entgelt": "Gebühren.", "Carsharing": "car-sharing"}
    out = tmp_path / "o.csv"
    info = sortcsv.sort_csv(src, out, categories=["Lebensmittel", "Gebühren", "car-sharing", "Sonstiges"],
                            ask_fn=lambda prompt: next(a for key, a in answers.items() if key in prompt))
    rows = out.read_text(encoding="utf-8-sig").splitlines()[1:]
    assert [r.split(";")[-2:] for r in rows] == [["Lebensmittel", ""], ["Gebühren", ""], ["car-sharing", ""]]
    assert info["flagged"] == 0
