from pathlib import Path
import pytest

@pytest.fixture
def demo():
    return Path(__file__).resolve().parents[1] / "examples" / "demo-home"
