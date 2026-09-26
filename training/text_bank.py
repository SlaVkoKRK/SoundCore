from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path

BANK_PATH = Path(__file__).with_name("prompts_pl.json")
WORDS_PER_SECOND = 2.15
HISTORY_FILE = "prompt_history.json"
MAX_HISTORY = 500


def _load_bank() -> dict:
    with BANK_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _word_count(text: str) -> int:
    return len([w for w in text.replace("—", " ").split() if w.strip()])


def _history_path(profile_folder: str | Path) -> Path:
    return Path(profile_folder) / HISTORY_FILE


def load_prompt_history(profile_folder: str | Path | None) -> dict:
    if not profile_folder:
        return {"used_prompts": [], "used_sentences": []}
    path = _history_path(profile_folder)
    if not path.exists():
        return {"used_prompts": [], "used_sentences": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "used_prompts": list(data.get("used_prompts", []))[-MAX_HISTORY:],
            "used_sentences": list(data.get("used_sentences", []))[-MAX_HISTORY:],
        }
    except Exception:
        return {"used_prompts": [], "used_sentences": []}


def remember_prompt(profile_folder: str | Path | None, text: str, purpose: str) -> None:
    if not profile_folder or not text.strip():
        return
    path = _history_path(profile_folder)
    history = load_prompt_history(profile_folder)
    prompt_entry = {
        "text": text.strip(),
        "purpose": purpose,
        "used_at": datetime.now().isoformat(timespec="seconds"),
    }
    history["used_prompts"].append(prompt_entry)

    bank = _load_bank()
    for category in bank.values():
        if not isinstance(category, list):
            continue
        for sentence in category:
            if sentence and sentence in text:
                history["used_sentences"].append(sentence)

    # stable de-duplication while keeping the newest occurrences
    seen: set[str] = set()
    deduped_sentences: list[str] = []
    for sentence in reversed(history["used_sentences"]):
        if sentence in seen:
            continue
        seen.add(sentence)
        deduped_sentences.append(sentence)
    history["used_sentences"] = list(reversed(deduped_sentences))[-MAX_HISTORY:]
    history["used_prompts"] = history["used_prompts"][-MAX_HISTORY:]
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def build_prompt(
    duration_seconds: int,
    purpose: str = "training",
    nonce: int | None = None,
    profile_folder: str | Path | None = None,
) -> dict:
    """Build a Polish reading prompt roughly matching the requested duration.

    Per-profile prompt history is persisted in voice_profiles/<profile>/prompt_history.json.
    Sentences already used by that profile are avoided until the local bank is exhausted.
    """
    bank = _load_bank()
    duration = max(5, min(int(duration_seconds), 90))
    target_words = max(10, round(duration * WORDS_PER_SECOND))
    rng = random.Random(nonce if nonce is not None else random.SystemRandom().randrange(1 << 30))

    history = load_prompt_history(profile_folder)
    previously_used = set(history.get("used_sentences", []))
    all_bank_sentences = {sentence for values in bank.values() if isinstance(values, list) for sentence in values if sentence}
    fresh_remaining_before = len(all_bank_sentences - previously_used)

    if purpose == "profile":
        category_order = ["natural", "phonetic", "numbers", "questions", "prosody"]
    else:
        category_order = ["phonetic", "natural", "questions", "numbers", "prosody", "technical"]
    rng.shuffle(category_order)

    chosen: list[str] = []
    used_this_prompt: set[str] = set()
    words = 0
    rounds = 0
    reused = 0
    while words < target_words and rounds < 120:
        cat = category_order[rounds % len(category_order)]
        all_candidates = list(bank.get(cat, []))
        fresh = [x for x in all_candidates if x not in previously_used and x not in used_this_prompt]
        candidates = fresh or [x for x in all_candidates if x not in used_this_prompt]
        if not candidates:
            rounds += 1
            continue
        if not fresh:
            reused += 1
        remaining = max(1, target_words - words)
        shuffled = list(candidates)
        rng.shuffle(shuffled)
        shuffled.sort(key=lambda item: abs(_word_count(item) - remaining))
        sentence = shuffled[0]
        sw = _word_count(sentence)
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
        used_this_prompt.add(sentence)
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
        "history_count": len(previously_used),
        "reused_sentences": reused,
        "bank_total_sentences": len(all_bank_sentences),
        "fresh_sentences_remaining": fresh_remaining_before,
    }
