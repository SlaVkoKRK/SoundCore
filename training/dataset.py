from __future__ import annotations

import csv
import json
import os
import random
import shutil
from dataclasses import dataclass
from typing import Iterable

import soundfile as sf

POLISH_PROMPTS = [
    "Dzisiaj rano powietrze było wyjątkowo chłodne i świeże.",
    "Proszę ustaw temperaturę w salonie na dwadzieścia dwa stopnie.",
    "Czy możesz sprawdzić, która jest teraz godzina?",
    "Wieczorem przygotuję herbatę z cytryną i odrobiną miodu.",
    "Na parkingu stoją trzy samochody, rower i czerwony motocykl.",
    "Jutro o ósmej trzydzieści mam ważne spotkanie w centrum miasta.",
    "Za oknem pada deszcz, ale po południu powinno się rozpogodzić.",
    "Włącz światło w kuchni i zamknij rolety w sypialni.",
    "To jest próbka naturalnej mowy używana do treningu mojego głosu.",
    "Nie wiem jeszcze, czy pojedziemy w sobotę, czy dopiero w niedzielę.",
    "Numer zamówienia to tysiąc dwieście czterdzieści osiem.",
    "Temperatura wzrosła z osiemnastu do dwudziestu czterech stopni.",
    "Czasami mówię szybko, a czasami celowo zwalniam tempo wypowiedzi.",
    "Czy to naprawdę działa tak dobrze, jak się spodziewaliśmy?",
    "Świetnie, wszystko wygląda poprawnie i możemy przejść dalej.",
    "Źródło dźwięku znajduje się blisko drzwi wejściowych.",
    "Żółty samochód skręcił w prawo tuż za skrzyżowaniem.",
    "Ćwiczenie czyni mistrza, dlatego nagrywam kolejne zdanie.",
    "Późnym wieczorem ulice są znacznie cichsze niż w ciągu dnia.",
    "Warto zapisać ustawienia przed zamknięciem całego programu.",
    "Mam nadzieję, że syntezowany głos zachowa naturalną intonację.",
    "Raz, dwa, trzy, cztery, pięć, sześć, siedem, osiem, dziewięć, dziesięć.",
    "Poniedziałek, wtorek, środa, czwartek, piątek, sobota i niedziela.",
    "Styczeń, luty, marzec, kwiecień, maj, czerwiec i lipiec.",
    "Sierpień, wrzesień, październik, listopad i grudzień.",
    "Adres IP serwera to dziesięć kropka trzydzieści kropka jeden kropka jeden.",
    "Prędkość sieci wynosi obecnie około dziewięciuset megabitów na sekundę.",
    "Proszę nie wyłączać komputera podczas instalowania aktualizacji.",
    "System zakończył operację poprawnie i nie wykrył żadnych błędów.",
    "Nagranie powinno być czyste, bez pogłosu, muzyki i hałasu w tle.",
    "Mikrofon stoi mniej więcej trzydzieści centymetrów od moich ust.",
    "Mówię normalnym głosem, bez przesadnego akcentowania każdego słowa.",
    "Dłuższe zdania pomagają modelowi nauczyć się rytmu oraz płynności mowy.",
    "Krótkie pytania są przydatne do odwzorowania intonacji wznoszącej.",
    "Naprawdę? Nie spodziewałem się takiego wyniku!",
    "Spokojnie, za chwilę sprawdzimy wszystkie ustawienia jeszcze raz.",
    "W folderze znajdują się pliki audio, konfiguracja oraz zapis modelu.",
    "Procesor może trenować model, jednak karta graficzna zrobi to znacznie szybciej.",
    "Po zakończeniu treningu wykonamy test na zdaniu, którego model wcześniej nie widział.",
    "Najważniejsza jest jakość nagrań, poprawna transkrypcja i różnorodna wymowa.",
]

@dataclass
class DatasetStats:
    samples: int
    seconds: float


def dataset_dir(profile_folder: str) -> str:
    return os.path.join(profile_folder, "dataset")


def init_dataset(profile_folder: str) -> str:
    root = dataset_dir(profile_folder)
    os.makedirs(os.path.join(root, "wavs"), exist_ok=True)
    prompts_path = os.path.join(root, "prompts.json")
    if not os.path.isfile(prompts_path):
        with open(prompts_path, "w", encoding="utf-8") as f:
            json.dump(POLISH_PROMPTS, f, ensure_ascii=False, indent=2)
    return root


def load_prompts(profile_folder: str) -> list[str]:
    root = init_dataset(profile_folder)
    with open(os.path.join(root, "prompts.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def append_sample(profile_folder: str, audio, samplerate: int, text: str) -> str:
    root = init_dataset(profile_folder)
    manifest = os.path.join(root, "samples.jsonl")
    existing = []
    if os.path.isfile(manifest):
        with open(manifest, "r", encoding="utf-8") as f:
            existing = [json.loads(line) for line in f if line.strip()]
    index = len(existing) + 1
    filename = f"sample_{index:04d}.wav"
    sf.write(os.path.join(root, "wavs", filename), audio, samplerate)
    record = {"audio_file": filename, "text": text.strip(), "speaker_name": os.path.basename(profile_folder)}
    with open(manifest, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return filename


def get_stats(profile_folder: str) -> DatasetStats:
    root = init_dataset(profile_folder)
    manifest = os.path.join(root, "samples.jsonl")
    if not os.path.isfile(manifest):
        return DatasetStats(0, 0.0)
    count = 0
    seconds = 0.0
    with open(manifest, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            wav = os.path.join(root, "wavs", rec["audio_file"])
            if os.path.isfile(wav):
                info = sf.info(wav)
                seconds += float(info.frames) / float(info.samplerate)
                count += 1
    return DatasetStats(count, seconds)


def build_ljspeech_metadata(profile_folder: str, eval_ratio: float = 0.1) -> tuple[str, str]:
    root = init_dataset(profile_folder)
    manifest = os.path.join(root, "samples.jsonl")
    if not os.path.isfile(manifest):
        raise ValueError("Brak próbek treningowych.")
    records = []
    with open(manifest, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    if len(records) < 5:
        raise ValueError("Do treningu potrzeba co najmniej 5 nagranych zdań (zalecane 30+).")
    rnd = random.Random(42)
    rnd.shuffle(records)
    eval_count = max(1, min(len(records) - 1, round(len(records) * eval_ratio)))
    eval_records = records[:eval_count]
    train_records = records[eval_count:]

    def write_csv(path: str, rows: Iterable[dict]) -> None:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter="|")
            for rec in rows:
                stem = os.path.splitext(rec["audio_file"])[0]
                text = rec["text"].replace("|", " ").strip()
                writer.writerow([stem, text, text])

    train_csv = os.path.join(root, "metadata_train.csv")
    eval_csv = os.path.join(root, "metadata_eval.csv")
    write_csv(train_csv, train_records)
    write_csv(eval_csv, eval_records)
    return train_csv, eval_csv
