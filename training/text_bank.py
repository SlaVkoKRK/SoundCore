from __future__ import annotations

import json
import random
from pathlib import Path

BANK_PATH = Path(__file__).with_name("prompts_pl.json")
WORDS_PER_SECOND = 2.15


def _load_bank() -> dict:
    with BANK_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _word_count(text: str) -> int:
    return len([w for w in text.replace("—", " ").split() if w.strip()])


def build_prompt(duration_seconds: int, purpose: str = "training", nonce: int | None = None) -> dict:
    """Build a Polish reading prompt roughly matching the requested duration.

    The local bank is intentionally data-driven so it can be expanded independently
    from the UI. Training prompts rotate categories to improve phonetic/prosodic
    diversity; reference prompts favour natural continuous speech.
    """
    bank = _load_bank()
    duration = max(5, min(int(duration_seconds), 90))
    target_words = max(10, round(duration * WORDS_PER_SECOND))
    rng = random.Random(nonce if nonce is not None else random.SystemRandom().randrange(1 << 30))

    if purpose == "profile":
        category_order = ["natural", "phonetic", "numbers", "questions", "prosody"]
    else:
        category_order = ["phonetic", "natural", "questions", "numbers", "prosody", "technical"]
    rng.shuffle(category_order)

    chosen: list[str] = []
    used: set[str] = set()
    words = 0
    rounds = 0
    while words < target_words and rounds < 100:
        cat = category_order[rounds % len(category_order)]
        candidates = [x for x in bank.get(cat, []) if x not in used]
        if not candidates:
            candidates = list(bank.get(cat, []))
        if not candidates:
            rounds += 1
            continue
        remaining = max(1, target_words - words)
        # Prefer a sentence whose length best matches the remaining target.
        shuffled = list(candidates)
        rng.shuffle(shuffled)
        shuffled.sort(key=lambda item: abs(_word_count(item) - remaining))
        sentence = shuffled[0]
        sw = _word_count(sentence)
        # Once we already have enough material, do not append a sentence that
        # would push the reading time far beyond the selected recording length.
        if chosen and words >= target_words * 0.88:
            break
        if chosen and words + sw > target_words * 1.12:
            fitting = [item for item in shuffled if words + _word_count(item) <= target_words * 1.12]
            if fitting:
                sentence = fitting[0]
                sw = _word_count(sentence)
            elif words >= target_words * 0.72:
                break
        chosen.append(sentence)
        used.add(sentence)
        words += sw
        rounds += 1

    text = " ".join(chosen).strip()
    estimated = round(words / WORDS_PER_SECOND, 1) if words else 0.0
    return {
        "text": text,
        "target_seconds": duration,
        "estimated_seconds": estimated,
        "word_count": words,
        "purpose": purpose,
    }
