"""
recorder.py
-----------
Moduł odpowiedzialny za nagrywanie próbek głosu z mikrofonu
(wbudowanego lub USB) przy użyciu biblioteki `sounddevice`.

Funkcje:
    list_input_devices()  -> lista dostępnych urządzeń wejściowych
    record_audio(...)     -> nagrywa audio i zwraca dane (numpy array)
    save_wav(...)         -> zapisuje dane audio do pliku .wav
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
import soundfile as sf

DEFAULT_SAMPLERATE = 22050  # zgodne z wymaganiami modeli TTS (XTTS działa na 22050/24000 Hz)
DEFAULT_CHANNELS = 1

_RECORDING_CANCEL = threading.Event()


class RecordingCancelled(RuntimeError):
    pass


def cancel_recording() -> None:
    """Request cancellation of the currently active microphone recording."""
    _RECORDING_CANCEL.set()
    try:
        sd.stop()
    except Exception:
        pass



@dataclass
class InputDevice:
    index: int
    name: str
    max_input_channels: int
    default_samplerate: float

    def __str__(self) -> str:
        return f"[{self.index}] {self.name} ({int(self.default_samplerate)} Hz, {self.max_input_channels} ch)"


def list_input_devices() -> list[InputDevice]:
    """Zwraca listę urządzeń wejściowych (mikrofonów) dostępnych w systemie."""
    devices = sd.query_devices()
    result = []
    for idx, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) > 0:
            result.append(
                InputDevice(
                    index=idx,
                    name=dev["name"],
                    max_input_channels=dev["max_input_channels"],
                    default_samplerate=dev["default_samplerate"],
                )
            )
    return result


def record_audio(
    duration: float,
    samplerate: int = DEFAULT_SAMPLERATE,
    channels: int = DEFAULT_CHANNELS,
    device: Optional[int] = None,
    on_progress: Optional[Callable[[float], None]] = None,
) -> np.ndarray:
    """
    Nagrywa dźwięk z mikrofonu przez `duration` sekund.

    Args:
        duration: długość nagrania w sekundach.
        samplerate: częstotliwość próbkowania.
        channels: liczba kanałów (1 = mono, zalecane dla TTS).
        device: indeks urządzenia wejściowego (None = domyślne).
        on_progress: opcjonalny callback(progress: 0.0-1.0) wywoływany
                     cyklicznie w trakcie nagrywania (przydatne do GUI).

    Returns:
        numpy.ndarray z próbkami audio (float32, zakres [-1, 1]).
    """
    _RECORDING_CANCEL.clear()
    frames = int(duration * samplerate)
    audio = sd.rec(
        frames,
        samplerate=samplerate,
        channels=channels,
        dtype="float32",
        device=device,
    )

    start = time.time()
    while True:
        elapsed = time.time() - start
        progress = min(elapsed / duration, 1.0)
        if on_progress is not None:
            on_progress(progress)
        if _RECORDING_CANCEL.is_set():
            try:
                sd.stop()
            finally:
                _RECORDING_CANCEL.clear()
            raise RecordingCancelled("Nagrywanie przerwane przez użytkownika.")
        if progress >= 1.0:
            break
        time.sleep(0.05)

    sd.wait()
    return np.squeeze(audio)


def save_wav(audio: np.ndarray, path: str, samplerate: int = DEFAULT_SAMPLERATE) -> None:
    """Zapisuje dane audio do pliku .wav."""
    sf.write(path, audio, samplerate)


def play_wav(path: str) -> None:
    """Odtwarza plik .wav (blokująco)."""
    data, samplerate = sf.read(path, dtype="float32")
    sd.play(data, samplerate)
    sd.wait()
