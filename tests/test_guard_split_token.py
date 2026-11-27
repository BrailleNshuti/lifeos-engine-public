"""A token split over two lines (wrapped by an editor or a chat) is still found; ordinary wrapped prose is not flagged."""
import pytest

from lifeos.guard import scan_text

TOKEN = "ghp_" + "a1B2" * 9  # assembled at run time
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"


def blocked(text):
    return [f for f in scan_text(text) if f[1] == "BLOCK"]


@pytest.mark.parametrize("cut", [8, 14, 20, 30])
def test_a_github_token_wrapped_at_any_point_is_blocked(cut):
    text = f"the token is\n{TOKEN[:cut]}\n{TOKEN[cut:]}\nplease keep it"
    assert blocked(text), cut


def test_an_aws_key_wrapped_in_a_paragraph_is_blocked():
    assert blocked(f"key {AWS[:9]}\n{AWS[9:]} was used")


def test_the_finding_names_the_line_where_the_token_starts():
    found = blocked(f"line one\n{TOKEN[:12]}\n{TOKEN[12:]}\n")
    assert found and found[0][0] == 2


def test_the_same_token_on_one_line_is_reported_once():
    assert len(blocked(f"x {TOKEN} y")) == 1


@pytest.mark.parametrize("text", [
    "a long paragraph about planning\nthat is wrapped by the editor\nat about seventy characters per line",
    "ghp is a prefix\n_ and 36 more characters follow in the docs",
    "version 3.12\n.1 is out",
    "see the notes\nfor 2026-11-27",
    "AKIA is the prefix of an access key id\nthe rest has sixteen characters",
])
def test_ordinary_wrapped_text_is_not_flagged(text):
    assert not blocked(text), text


def test_a_blank_line_between_the_parts_breaks_the_token():
    assert not blocked(f"{TOKEN[:12]}\n\n{TOKEN[12:]}")
