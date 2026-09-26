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


def list_samples(profile_folder: str) -> list[dict]:
    root, wavs, meta = dataset_paths(profile_folder)
    extras_path = root / "samples.json"
    extras = {}
    if extras_path.exists():
        try:
            extras = json.loads(extras_path.read_text(encoding="utf-8"))
        except Exception:
            extras = {}
    rows = []
    if meta.exists():
        with meta.open("r", encoding="utf-8", newline="") as f:
            for row in csv.reader(f, delimiter="|"):
                if not row:
                    continue
                stem = row[0]
                wav = wavs / f"{stem}.wav"
                duration = 0.0
                if wav.exists():
                    try:
                        duration = round(float(sf.info(str(wav)).duration), 2)
                    except Exception:
                        pass
                extra = extras.get(stem, {})
                rows.append({
                    "id": stem,
                    "text": row[1] if len(row) > 1 else "",
                    "wav_path": str(wav),
                    "duration_seconds": duration,
                    "source_name": extra.get("source_name", "Nagranie SoundCore"),
                    "imported": bool(extra.get("imported", False)),
                    "trim_start": extra.get("trim_start"),
                    "trim_end": extra.get("trim_end"),
                })
    return rows


def delete_sample(profile_folder: str, sample_id: str) -> bool:
    root, wavs, meta = dataset_paths(profile_folder)
    rows = []
    removed = False
    if meta.exists():
        with meta.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f, delimiter="|"))
        kept = []
        for row in rows:
            if row and row[0] == sample_id:
                removed = True
            else:
                kept.append(row)
        with meta.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter="|", lineterminator="\n")
            writer.writerows(kept)
    wav = wavs / f"{sample_id}.wav"
    if wav.exists():
        wav.unlink()
        removed = True
    extras_path = root / "samples.json"
    if extras_path.exists():
        try:
            extras = json.loads(extras_path.read_text(encoding="utf-8"))
            if sample_id in extras:
                extras.pop(sample_id, None)
                extras_path.write_text(json.dumps(extras, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return removed


def update_sample_text(profile_folder: str, sample_id: str, text: str) -> dict:
    root, wavs, meta = dataset_paths(profile_folder)
    clean = " ".join((text or "").strip().split())
    if not meta.exists():
        raise ValueError("Brak metadanych datasetu.")
    with meta.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter="|"))
    found = False
    for row in rows:
        if row and row[0] == sample_id:
            while len(row) < 3:
                row.append("")
            row[1] = clean
            row[2] = clean
            found = True
            break
    if not found:
        raise ValueError("Nie znaleziono próbki.")
    with meta.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter="|", lineterminator="\n").writerows(rows)
    extras_path = root / "samples.json"
    if extras_path.exists():
        try:
            extras = json.loads(extras_path.read_text(encoding="utf-8"))
            if sample_id in extras:
                extras[sample_id]["text"] = clean
                extras_path.write_text(json.dumps(extras, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return {"id": sample_id, "text": clean, "wav_path": str(wavs / f"{sample_id}.wav")}
