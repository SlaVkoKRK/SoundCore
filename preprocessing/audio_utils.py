"""
audio_utils.py
--------------
Funkcje do wstępnego przetwarzania próbek głosu przed użyciem
ich w silniku TTS/voice-cloning:

    - normalize_audio     -> normalizacja głośności (peak normalization)
    - trim_silence        -> obcinanie ciszy z początku/końca nagrania
    - remove_dc_offset    -> usuwanie składowej stałej (DC offset)
    - to_mono             -> konwersja wielokanałowego audio do mono
    - resample_audio      -> zmiana częstotliwości próbkowania
    - preprocess_pipeline  -> pełny pipeline czyszczenia próbki głosu

Uwaga projektowa: zamiast ciężkiej zależności (np. webrtcvad, którego
kompilacja bywa problematyczna na niektórych systemach), przycinanie
ciszy oparte jest o prosty detektor energetyczny (RMS w oknach), co
jest w pełni wystarczające do przygotowania próbki referencyjnej głosu
i nie wymaga dodatkowych zależności binarnych.
"""

from __future__ import annotations

import numpy as np

try:
    from scipy.signal import resample_poly
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover
    _HAS_SCIPY = False


def remove_dc_offset(audio: np.ndarray) -> np.ndarray:
    """Usuwa składową stałą (DC offset) z sygnału."""
    return audio - np.mean(audio)


def to_mono(audio: np.ndarray) -> np.ndarray:
    """Konwertuje audio wielokanałowe do mono (uśrednianie kanałów)."""
    if audio.ndim == 1:
        return audio
    return np.mean(audio, axis=1)


def normalize_audio(audio: np.ndarray, target_peak: float = 0.95) -> np.ndarray:
    """
    Normalizuje amplitudę sygnału tak, aby maksymalna wartość bezwzględna
    osiągnęła `target_peak` (peak normalization). Zapobiega zbyt cichym
    lub przesterowanym próbkom referencyjnym.
    """
    peak = np.max(np.abs(audio))
    if peak < 1e-8:
        return audio  # cisza - nic do normalizacji
    return audio * (target_peak / peak)


def _rms_energy(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))


def trim_silence(
    audio: np.ndarray,
    samplerate: int,
    frame_ms: int = 30,
    energy_threshold_ratio: float = 0.02,
    padding_ms: int = 100,
) -> np.ndarray:
    """
    Obcina ciszę z początku i końca nagrania na podstawie prostego
    detektora energetycznego (RMS w oknach czasowych).

    Args:
        audio: sygnał wejściowy (mono).
        samplerate: częstotliwość próbkowania.
        frame_ms: długość okna analizy w milisekundach.
        energy_threshold_ratio: próg energii względem energii maksymalnej
            w sygnale (0.0-1.0). Wyższa wartość = bardziej agresywne cięcie.
        padding_ms: ile milisekund ciszy zostawić na brzegach (dla naturalności).

    Returns:
        Przycięty sygnał audio.
    """
    if len(audio) == 0:
        return audio

    frame_len = max(int(samplerate * frame_ms / 1000), 1)
    n_frames = int(np.ceil(len(audio) / frame_len))

    energies = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * frame_len
        end = min(start + frame_len, len(audio))
        energies[i] = _rms_energy(audio[start:end])

    max_energy = np.max(energies) if len(energies) else 0.0
    if max_energy < 1e-8:
        return audio  # cały sygnał to cisza, nie ma czego przycinać

    threshold = max_energy * energy_threshold_ratio
    voiced_frames = np.where(energies > threshold)[0]

    if len(voiced_frames) == 0:
        return audio

    first_voiced = voiced_frames[0]
    last_voiced = voiced_frames[-1]

    padding_samples = int(samplerate * padding_ms / 1000)
    start_sample = max(first_voiced * frame_len - padding_samples, 0)
    end_sample = min((last_voiced + 1) * frame_len + padding_samples, len(audio))

    return audio[start_sample:end_sample]


def resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Zmienia częstotliwość próbkowania sygnału (wymaga scipy)."""
    if orig_sr == target_sr:
        return audio
    if not _HAS_SCIPY:
        raise RuntimeError(
            "Zmiana częstotliwości próbkowania wymaga pakietu 'scipy'. "
            "Zainstaluj: pip install scipy"
        )
    gcd = np.gcd(orig_sr, target_sr)
    up = target_sr // gcd
    down = orig_sr // gcd
    return resample_poly(audio, up, down).astype(np.float32)


def preprocess_pipeline(
    audio: np.ndarray,
    samplerate: int,
    target_samplerate: int | None = None,
) -> np.ndarray:
    """
    Pełny pipeline czyszczenia próbki głosu:
    mono -> usunięcie DC offset -> przycięcie ciszy -> normalizacja -> resampling.
    """
    audio = to_mono(audio)
    audio = remove_dc_offset(audio)
    audio = trim_silence(audio, samplerate)
    audio = normalize_audio(audio)
    if target_samplerate is not None and target_samplerate != samplerate:
        audio = resample_audio(audio, samplerate, target_samplerate)
    return audio.astype(np.float32)
