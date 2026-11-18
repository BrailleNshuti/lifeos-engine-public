import datetime as dt
import shutil

import pytest

from lifeos import calibrate
from lifeos.cli import main

D = dt.date(2026, 11, 22)


@pytest.fixture
def home(tmp_path, demo):
    target = tmp_path / "home"
    shutil.copytree(demo, target)
    return target


def test_predict_gives_sequential_ids_and_log_only_grows(home):
    a = calibrate.predict(home, "Engine merges by Friday", 70, today=D)
    b = calibrate.predict(home, "German A1.2 by March", 40, today=D)
    assert (a, b) == ("P-001", "P-002")
    assert len((home / "logs" / "predictions.csv").read_text().splitlines()) == 3


@pytest.mark.parametrize("p", [0, 100, -5, 101])
def test_certainty_is_refused(home, p):
    with pytest.raises(calibrate.CalibrationError):
        calibrate.predict(home, "x happens", p, today=D)


def test_resolve_once_only(home):
    pid = calibrate.predict(home, "it rains", 60, today=D)
    calibrate.resolve(home, pid, True, today=D)
    with pytest.raises(calibrate.CalibrationError):
        calibrate.resolve(home, pid, False, today=D)
    with pytest.raises(calibrate.CalibrationError):
        calibrate.resolve(home, "P-099", True, today=D)


def test_private_claim_is_refused(home):
    with pytest.raises(calibrate.CalibrationError):
        calibrate.predict(home, "key sk-ant-api03-" + "a1B2c3D4" * 5, 50, today=D)


def test_brier_and_bins(home):
    for text, p, ok in [("a", 90, True), ("b", 90, False), ("c", 10, False), ("d", 10, False), ("e", 10, False)]:
        calibrate.resolve(home, calibrate.predict(home, text + " happens", p, today=D), ok, today=D)
    calibrate.predict(home, "still open thing", 50, today=D)
    rep = calibrate.report(home)
    assert rep["resolved"] == 5 and rep["open"] == 1
    assert rep["brier"] == pytest.approx((0.01 + 0.81 + 0.01 + 0.01 + 0.01) / 5)
    high = next(b for b in rep["bins"] if b["label"] == "80-100")
    assert high["n"] == 2 and high["said"] == 90 and high["happened"] == 50
    assert "overconfident" in rep["verdict"]


def test_report_with_too_few_results_says_so(home):
    calibrate.resolve(home, calibrate.predict(home, "one happens", 60, today=D), True, today=D)
    assert "too few" in calibrate.report(home)["verdict"]


def test_cli(home, capsys, monkeypatch):
    monkeypatch.setenv("LIFEOS_HOME", str(home))
    assert main(["predict", "Engine ships", "--p", "70"]) == 0
    assert "P-001" in capsys.readouterr().out
    assert main(["resolve", "P-001", "yes"]) == 0
    assert main(["resolve", "P-001", "no"]) == 2
    assert main(["predict", "sure thing", "--p", "100"]) == 2
    assert main(["calibration"]) == 0
    assert "Brier" in capsys.readouterr().out
