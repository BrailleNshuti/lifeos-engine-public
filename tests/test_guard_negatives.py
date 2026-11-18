"""Things that look like identifiers but are not: the guard must stay quiet, or people learn to ignore it."""
import pytest

from lifeos import guard

HARMLESS = [
    "commit 215f41c4ee77a0b6c3d1e9f2a4b5c6d7e8f90123 fixes the bug",
    "id 550e8400-e29b-41d4-a716-446655440000 is a uuid",
    "started 2026-11-18T02:55:00+01:00 and ended 2026-11-18T03:10:12Z",
    "size 1234567890123 bytes",
    "version 3.12.1 build 20261118",
    "the run took 12.5 s and cost 0.0042",
    "task T-261116-demo-cli, run R-261118-1a2b3c4d",
    "see https://example.org/path/to/page?x=1&y=2",
    "sha256 " + "ab" * 32,
    "range 100-200 and 300-400-500",
    "Zimmer 4a, Haus 12b, Flur 7",
    "pytest -q passed 643 tests in 40.05s",
    "model claude-sonnet-5-5 at 80 % of the weekly limit",
    "cd C:\\Users\\Admin\\lifeos-engine-public",
    "B2 Zertifikat bis Ende 2027, telc oder Goethe",
    "x = 1000000 * 3600",
]


@pytest.mark.parametrize("line", HARMLESS)
def test_harmless_lines_produce_no_findings(line):
    assert guard.scan_text(line) == [], line


def test_a_whole_document_of_harmless_lines_is_clean():
    assert guard.scan_text("\n".join(HARMLESS)) == []
