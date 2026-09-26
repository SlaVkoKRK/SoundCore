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
    smart_tail: bool = True,
    max_extra_seconds: float = 3.0,
    silence_seconds: float = 0.75,
    silence_threshold: float = 0.008,
) -> np.ndarray:
    """
    Nagrywa głos przez co najmniej ``duration`` sekund.

    W trybie ``smart_tail`` po osiągnięciu czasu docelowego SoundCore nie
    ucina użytkownika w połowie słowa: nagranie trwa jeszcze maksymalnie
    ``max_extra_seconds`` i kończy się po wykryciu krótkiej ciszy.
    """
    _RECORDING_CANCEL.clear()
    duration = max(float(duration), 0.1)
    extra = max(float(max_extra_seconds), 0.0) if smart_tail else 0.0
    max_duration = duration + extra
    total_frames = int(max_duration * samplerate)
    audio = sd.rec(
        total_frames,
        samplerate=samplerate,
        channels=channels,
        dtype="float32",
        device=device,
    )

    start = time.time()
    last_voice_at = duration
    ended_early = False
    used_elapsed = max_duration
    window_seconds = 0.25
    while True:
        elapsed = time.time() - start
        used_elapsed = min(elapsed, max_duration)
        if on_progress is not None:
            on_progress(min(elapsed / duration, 1.0))
        if _RECORDING_CANCEL.is_set():
            try:
                sd.stop()
            finally:
                _RECORDING_CANCEL.clear()
            raise RecordingCancelled("Nagrywanie przerwane przez użytkownika.")

        if smart_tail and elapsed >= duration:
            end_frame = min(int(elapsed * samplerate), total_frames)
            begin_frame = max(0, end_frame - int(window_seconds * samplerate))
            if end_frame > begin_frame:
                block = np.asarray(audio[begin_frame:end_frame], dtype=np.float32)
                rms = float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0
                if rms >= silence_threshold:
                    last_voice_at = elapsed
                elif elapsed - last_voice_at >= silence_seconds:
                    ended_early = True
                    break

        if elapsed >= max_duration:
            break
        time.sleep(0.05)

    if ended_early:
        sd.stop()
    else:
        sd.wait()
    used_frames = min(max(1, int(used_elapsed * samplerate)), total_frames)
    return np.squeeze(audio[:used_frames]).copy()


def save_wav(audio: np.ndarray, path: str, samplerate: int = DEFAULT_SAMPLERATE) -> None:
    """Zapisuje dane audio do pliku .wav."""
    sf.write(path, audio, samplerate)


def play_wav(path: str) -> None:
    """Odtwarza plik .wav (blokująco)."""
    data, samplerate = sf.read(path, dtype="float32")
    sd.play(data, samplerate)
    sd.wait()
