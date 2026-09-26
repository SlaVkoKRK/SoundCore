from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from training.dataset import dataset_paths

SUPPORTED_MEDIA = {'.wav', '.mp3', '.flac', '.m4a', '.aac', '.ogg', '.wma', '.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v'}
SESSIONS: dict[str, dict[str, Any]] = {}


def _ffmpeg_exe() -> str:
    exe = shutil.which('ffmpeg')
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError('Brak FFmpeg. Uruchom aktualizację zależności SoundCore (imageio-ffmpeg) albo zainstaluj FFmpeg.') from exc


def _convert_to_wav(source: str, target: Path, sample_rate: int = 24000) -> None:
    cmd = [
        _ffmpeg_exe(), '-y', '-hide_banner', '-loglevel', 'error',
        '-i', source, '-vn', '-ac', '1', '-ar', str(sample_rate), '-c:a', 'pcm_s16le', str(target),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f'Nie udało się wyciągnąć audio z pliku. FFmpeg: {p.stderr.strip()}')


def _waveform_peaks(wav_path: Path, points: int = 900) -> list[float]:
    audio, _sr = sf.read(str(wav_path), dtype='float32', always_2d=False)
    if getattr(audio, 'ndim', 1) > 1:
        audio = audio.mean(axis=1)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.size == 0:
        return []
    step = max(1, int(np.ceil(audio.size / points)))
    vals = []
    for i in range(0, audio.size, step):
        chunk = np.abs(audio[i:i + step])
        vals.append(float(chunk.max()) if chunk.size else 0.0)
    peak = max(vals) if vals else 1.0
    if peak <= 1e-9:
        return [0.0 for _ in vals]
    return [round(min(1.0, v / peak), 4) for v in vals[:points]]


def begin_import(source_path: str) -> dict:
    src = Path(source_path)
    if not src.is_file():
        raise FileNotFoundError(source_path)
    if src.suffix.lower() not in SUPPORTED_MEDIA:
        raise ValueError(f'Nieobsługiwany format: {src.suffix}')
    work = Path(tempfile.mkdtemp(prefix='soundcore-media-'))
    wav = work / 'source.wav'
    _convert_to_wav(str(src), wav)
    info = sf.info(str(wav))
    sid = uuid.uuid4().hex
    data = {
        'session_id': sid,
        'source_path': str(src),
        'source_name': src.name,
        'wav_path': str(wav),
        'work_dir': str(work),
        'duration_seconds': round(float(info.duration), 3),
        'sample_rate': int(info.samplerate),
        'peaks': _waveform_peaks(wav),
    }
    SESSIONS[sid] = data
    return {k: v for k, v in data.items() if k not in {'wav_path', 'work_dir'}}


def _session(session_id: str) -> dict:
    data = SESSIONS.get(session_id)
    if not data:
        raise ValueError('Sesja importu wygasła. Wybierz plik ponownie.')
    return data


def make_preview(session_id: str, start: float, end: float) -> str:
    data = _session(session_id)
    duration = float(data['duration_seconds'])
    start = max(0.0, min(float(start), duration))
    end = max(start + 0.05, min(float(end), duration))
    preview = Path(data['work_dir']) / 'preview.wav'
    cmd = [
        _ffmpeg_exe(), '-y', '-hide_banner', '-loglevel', 'error',
        '-ss', f'{start:.3f}', '-to', f'{end:.3f}', '-i', data['wav_path'],
        '-ac', '1', '-ar', '24000', '-c:a', 'pcm_s16le', str(preview),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or 'Nie udało się utworzyć podglądu.')
    return str(preview)


def save_clip(profile_folder: str, session_id: str, start: float, end: float, text: str = '') -> dict:
    data = _session(session_id)
    duration = float(data['duration_seconds'])
    start = max(0.0, min(float(start), duration))
    end = max(start + 0.1, min(float(end), duration))
    root, wavs, meta = dataset_paths(profile_folder)
    rows = []
    if meta.exists():
        with meta.open('r', encoding='utf-8', newline='') as f:
            rows = list(csv.reader(f, delimiter='|'))
    idx = 1
    used = {row[0] for row in rows if row}
    while f'sc_{idx:05d}' in used:
        idx += 1
    stem = f'sc_{idx:05d}'
    dest = wavs / f'{stem}.wav'
    cmd = [
        _ffmpeg_exe(), '-y', '-hide_banner', '-loglevel', 'error',
        '-ss', f'{start:.3f}', '-to', f'{end:.3f}', '-i', data['wav_path'],
        '-ac', '1', '-ar', '24000', '-c:a', 'pcm_s16le', str(dest),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or 'Nie udało się zapisać wycinka.')
    clean_text = ' '.join((text or '').strip().split())
    with meta.open('a', encoding='utf-8', newline='') as f:
        csv.writer(f, delimiter='|', lineterminator='\n').writerow([stem, clean_text, clean_text])
    extras_path = root / 'samples.json'
    extras = {}
    if extras_path.exists():
        try:
            extras = json.loads(extras_path.read_text(encoding='utf-8'))
        except Exception:
            extras = {}
    info = sf.info(str(dest))
    extras[stem] = {
        'source_name': data['source_name'],
        'source_path': data['source_path'],
        'imported': True,
        'trim_start': round(start, 3),
        'trim_end': round(end, 3),
        'duration_seconds': round(float(info.duration), 3),
        'text': clean_text,
    }
    extras_path.write_text(json.dumps(extras, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'id': stem, 'wav_path': str(dest), **extras[stem]}


def close_session(session_id: str) -> None:
    data = SESSIONS.pop(session_id, None)
    if data:
        shutil.rmtree(data['work_dir'], ignore_errors=True)
