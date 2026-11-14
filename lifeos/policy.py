"""5-tier data classification policy and enforceable provider-locality rules."""
import re

TIERS = ("PUBLIC", "INTERNAL", "PERSONAL", "SENSITIVE", "SECRET")
TIER_RANK = {name: idx for idx, name in enumerate(TIERS)}
LOCAL_PROVIDERS = frozenset({"ollama", "qwen"})
REMOTE_PROVIDERS = frozenset({"claude", "codex", "gemini"})

# These expressions intentionally favor privacy over convenience. They identify
# natural-language content that the byte-pattern guard cannot reliably classify.
# Actual credentials and identity numbers remain the guard's responsibility.
SENSITIVE_CONTENT = re.compile(
    r"\b(?:bank(?:ing)?\s+(?:csv|statement|account|transaction)|"
    r"my\s+health|health\s+(?:record|data|condition|diagnosis|note)|medical|diagnos(?:is|ed)|"
    r"residence\s+permit(?:\s+(?:number|document|scan|application))?|"
    r"passport(?:\s+(?:number|document|scan))?|tenant\s+(?:data|record|name)|"
    r"tax\s+(?:record|return|id)|salary\s+(?:statement|slip))\b",
    re.IGNORECASE,
)


def normalize_tier(tier):
    """Validate and normalize a data classification tier name."""
    cleaned = str(tier or "").strip().upper()
    if cleaned not in TIER_RANK:
        raise ValueError(f"Unknown data tier '{tier}'. Allowed: {', '.join(TIERS)}.")
    return cleaned


def provider_locality(model):
    """Return 'local' for local Ollama models and 'remote' for cloud CLI models."""
    name = str(model or "").strip().lower()
    if name in LOCAL_PROVIDERS:
        return "local"
    if name in REMOTE_PROVIDERS:
        return "remote"
    raise ValueError(f"Unknown provider '{model}'.")


def classify_path(rel_path):
    """Return the default data classification tier for a relative repository or workspace path."""
    raw = str(rel_path or "").replace("\\", "/").strip()
    if raw.startswith("./"):
        raw = raw[2:]
    lower = raw.lower()
    if not lower:
        return "INTERNAL"
    if any(tok in lower for tok in (".env", "private-patterns", "secret", "id_rsa", "id_ed25519", "credentials")):
        return "SECRET"
    if any(tok in lower for tok in ("bank", "health.csv", "residence", "permit", "medical", "tax", "iban")):
        return "SENSITIVE"
    if lower in ("me.md", "now.md") or lower.startswith(("logs/", "reviews/", "tasks/")):
        return "PERSONAL"
    if lower.startswith(("examples/", "docs/", "skills/")) or lower in ("readme.md", "claude.md", "agents.md", "rules.md"):
        return "PUBLIC"
    return "INTERNAL"


def classify_content(text, rel_path=""):
    """Classify a file plus its natural-language content conservatively.

    Path classification supplies the baseline. Recognizable health, banking,
    identity-document, tenant, tax, or salary context promotes the result to
    SENSITIVE so remote execution cannot depend on a human remembering to run
    the router first.
    """
    base = classify_path(rel_path)
    if base == "SECRET":
        return base
    if SENSITIVE_CONTENT.search(str(text or "")):
        return "SENSITIVE"
    return base


def check_provider_allowed(tier, model, full=False):
    """Return (allowed: bool, reason: str) for sending data of `tier` to `model`.

    Policy rules:
    - SECRET data is never allowed to be sent to any model (local or remote).
    - SENSITIVE data (bank CSVs, health, IDs) is allowed ONLY on local providers (ollama, qwen).
    - PERSONAL data with `full=True` (me.md + now.md) is allowed on remote providers only when explicitly requested,
      while `SENSITIVE` and `SECRET` are blocked on remote providers regardless of flags.
    """
    norm_tier = normalize_tier(tier)
    locality = provider_locality(model)
    if norm_tier == "SECRET":
        return False, "SECRET data (keys, credentials, private-patterns) cannot be sent to any model."
    if norm_tier == "SENSITIVE" and locality != "local":
        return False, f"SENSITIVE data requires a local provider; '{model}' is {locality} (use qwen or ollama)."
    if norm_tier == "PERSONAL" and locality == "remote" and not full:
        return True, f"PERSONAL task pack allowed on {model} (me.md and now.md excluded unless --full is set)."
    return True, f"{norm_tier} data allowed on {locality} provider '{model}'."
