"""Tests for lifeos/policy.py (5-tier data classification and provider locality rules)."""
import pytest

from lifeos import policy


def test_five_tiers_order_and_normalization():
    assert policy.TIERS == ("PUBLIC", "INTERNAL", "PERSONAL", "SENSITIVE", "SECRET")
    assert policy.normalize_tier(" personal ") == "PERSONAL"
    with pytest.raises(ValueError, match="Unknown data tier"):
        policy.normalize_tier("TOP_SECRET")


def test_provider_locality_classification():
    assert policy.provider_locality("qwen") == "local"
    assert policy.provider_locality("ollama") == "local"
    assert policy.provider_locality("claude") == "remote"
    assert policy.provider_locality("codex") == "remote"
    assert policy.provider_locality("gemini") == "remote"
    with pytest.raises(ValueError, match="Unknown provider"):
        policy.provider_locality("unknown_llm")


def test_classify_path_across_five_tiers():
    assert policy.classify_path("README.md") == "PUBLIC"
    assert policy.classify_path("examples/demo/rules.md") == "PUBLIC"
    assert policy.classify_path("lifeos/store.py") == "INTERNAL"
    assert policy.classify_path("tasks/T-261116-demo-cli.md") == "PERSONAL"
    assert policy.classify_path("me.md") == "PERSONAL"
    assert policy.classify_path("logs/health.csv") == "SENSITIVE"
    assert policy.classify_path("exports/bank-2026.csv") == "SENSITIVE"
    assert policy.classify_path(".env") == "SECRET"
    assert policy.classify_path("~/.lifeos/private-patterns.txt") == "SECRET"


def test_classify_content_promotes_natural_language_sensitive_data():
    assert policy.classify_content("Study Python iterators", "tasks/T-demo.md") == "PERSONAL"
    assert policy.classify_content("Review my health condition notes", "tasks/T-demo.md") == "SENSITIVE"
    assert policy.classify_content("Sort a bank CSV locally", "tasks/T-demo.md") == "SENSITIVE"
    assert policy.classify_content("Check a residence permit document", "tasks/T-demo.md") == "SENSITIVE"
    assert policy.classify_content("anything", ".env") == "SECRET"


def test_check_provider_allowed_enforces_local_only_for_sensitive_and_blocks_secret():
    ok, _ = policy.check_provider_allowed("PUBLIC", "codex")
    assert ok is True
    ok, _ = policy.check_provider_allowed("PERSONAL", "claude", full=False)
    assert ok is True
    ok, _ = policy.check_provider_allowed("SENSITIVE", "qwen")
    assert ok is True
    ok, reason = policy.check_provider_allowed("SENSITIVE", "claude")
    assert ok is False and "local" in reason
    for model in ("qwen", "ollama", "claude", "codex", "gemini"):
        ok, reason = policy.check_provider_allowed("SECRET", model)
        assert ok is False and "SECRET" in reason
