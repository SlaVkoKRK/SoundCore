from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path

import soundfile as sf


@dataclass
class DatasetStats:
    samples: int
    duration_seconds: float
    metadata_path: str
    wavs_dir: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["duration_minutes"] = round(self.duration_seconds / 60.0, 2)
        return data


def dataset_paths(profile_folder: str) -> tuple[Path, Path, Path]:
    root = Path(profile_folder) / "dataset"
    wavs = root / "wavs"
    meta = root / "metadata.csv"
    wavs.mkdir(parents=True, exist_ok=True)
    return root, wavs, meta


def add_sample(profile_folder: str, audio, sample_rate: int, text: str) -> dict:
    text = " ".join(text.strip().split())
    if not text:
        raise ValueError("Tekst próbki nie może być pusty.")
    root, wavs, meta = dataset_paths(profile_folder)
    existing = []
    if meta.exists():
        with meta.open("r", encoding="utf-8", newline="") as f:
            existing = list(csv.reader(f, delimiter="|"))
    idx = len(existing) + 1
    stem = f"sc_{idx:05d}"
    wav_path = wavs / f"{stem}.wav"
    sf.write(str(wav_path), audio, sample_rate)
    with meta.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="|", lineterminator="\n")
        writer.writerow([stem, text, text])
    return {"id": stem, "wav_path": str(wav_path), "text": text}


def get_stats(profile_folder: str) -> DatasetStats:
    root, wavs, meta = dataset_paths(profile_folder)
    samples = 0
    duration = 0.0
    if meta.exists():
        with meta.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f, delimiter="|"))
        samples = len(rows)
        for row in rows:
            if not row:
                continue
            path = wavs / f"{row[0]}.wav"
            if path.exists():
                try:
                    info = sf.info(str(path))
                    duration += float(info.duration)
                except Exception:
                    pass
    return DatasetStats(samples=samples, duration_seconds=round(duration, 2), metadata_path=str(meta), wavs_dir=str(wavs))
