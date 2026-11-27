"""T12: 500 seeded harmless sentences (ordinary words, dates, versions, counts) never produce a BLOCK."""
import random

from lifeos.guard import scan_text

WORDS = ("plan review week task notes budget seat answer check ledger report merge branch test build ship read write sort "
         "light local model free cost limit rest reset rule proof source date count line file page step next risk").split()
SEED = 20261127


def sentence(rng):
    parts = [rng.choice(WORDS) for _ in range(rng.randint(3, 8))]
    kind = rng.randint(0, 5)
    if kind == 0:
        parts.append(f"{rng.randint(2025, 2028)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}")
    elif kind == 1:
        parts.append(f"v{rng.randint(0, 9)}.{rng.randint(0, 20)}.{rng.randint(0, 20)}")
    elif kind == 2:
        parts.append(str(rng.randint(1, 999999)))
    elif kind == 3:
        parts.append(f"{rng.randint(1, 99)}.{rng.randint(0, 99)} s")
    elif kind == 4:
        parts.append(f"{rng.randint(1, 23):02d}:{rng.randint(0, 59):02d}")
    else:
        parts.append(f"{rng.randint(1, 9999)} of {rng.randint(1, 9999)}")
    rng.shuffle(parts)
    return " ".join(parts)


def test_five_hundred_harmless_sentences_have_no_block():
    rng = random.Random(SEED)
    for _ in range(500):
        text = sentence(rng)
        blocks = [f for f in scan_text(text) if f[1] == "BLOCK"]
        assert not blocks, (text, blocks)


def test_the_sweep_is_deterministic():
    first = [sentence(random.Random(SEED)) for _ in range(3)]
    assert first == [sentence(random.Random(SEED)) for _ in range(3)]
