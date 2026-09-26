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


def _device_native_samplerate(device: Optional[int], fallback: int) -> int:
    """Prefer the microphone's native rate to avoid driver-side resampling glitches."""
    try:
        info = sd.query_devices(device, "input") if device is not None else sd.query_devices(kind="input")
        rate = int(round(float(info.get("default_samplerate") or 0)))
        if rate >= 8000:
            return rate
    except Exception:
        pass
    return int(fallback)


_RECORDING_LOCK = threading.Lock()


def _resample_recording(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return np.asarray(audio, dtype=np.float32)
    try:
        from scipy.signal import resample_poly
        gcd = int(np.gcd(orig_sr, target_sr))
        return resample_poly(audio, target_sr // gcd, orig_sr // gcd).astype(np.float32)
    except Exception as exc:
        raise RuntimeError("Nie udało się bezpiecznie przeskalować nagrania do 22050 Hz.") from exc


def recording_quality(audio: np.ndarray) -> dict:
    """Return lightweight recording-health metrics used before dataset save."""
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    if not x.size:
        return {"ok": False, "reason": "Puste nagranie.", "peak": 0.0, "rms": 0.0, "clip_ratio": 0.0}
    finite = np.isfinite(x)
    if not bool(np.all(finite)):
        return {"ok": False, "reason": "Nagranie zawiera nieprawidłowe próbki audio.", "peak": 0.0, "rms": 0.0, "clip_ratio": 0.0}
    peak = float(np.max(np.abs(x)))
    rms = float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))
    clip_ratio = float(np.mean(np.abs(x) >= 0.985))
    # Strongly clipped / stuck input is not useful for voice training.
    if clip_ratio >= 0.02 or (peak >= 0.999 and rms >= 0.45):
        return {"ok": False, "reason": "Próbka jest przesterowana — nie została dodana do datasetu.", "peak": peak, "rms": rms, "clip_ratio": clip_ratio}
    if rms < 0.0008:
        return {"ok": False, "reason": "Próbka jest praktycznie cicha — sprawdź mikrofon.", "peak": peak, "rms": rms, "clip_ratio": clip_ratio}
    return {"ok": True, "reason": "OK", "peak": peak, "rms": rms, "clip_ratio": clip_ratio}


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
    """Record one isolated microphone session using an owned InputStream.

    Recording happens at the input device's native sample rate and is resampled
    to ``samplerate`` afterwards. This avoids rapid ``sd.rec()/sd.stop()`` reuse
    in continuous sessions, which can leave WASAPI/PortAudio in a bad state.
    """
    duration = max(float(duration), 0.1)
    extra = max(float(max_extra_seconds), 0.0) if smart_tail else 0.0
    max_duration = duration + extra
    native_sr = _device_native_samplerate(device, samplerate)
    blocksize = max(256, min(2048, int(native_sr * 0.04)))

    # Never overlap microphone capture with another SoundCore capture. Also stop
    # playback before opening the input device; some Windows drivers are fragile
    # when convenience streams overlap.
    try:
        stop_playback(timeout=0.8)
    except Exception:
        pass

    with _RECORDING_LOCK:
        _RECORDING_CANCEL.clear()
        chunks: list[np.ndarray] = []
        start = time.monotonic()
        last_voice_at = duration
        with sd.InputStream(
            samplerate=native_sr,
            channels=channels,
            dtype="float32",
            device=device,
            blocksize=blocksize,
        ) as stream:
            while True:
                if _RECORDING_CANCEL.is_set():
                    _RECORDING_CANCEL.clear()
                    raise RecordingCancelled("Nagrywanie przerwane przez użytkownika.")
                data, overflowed = stream.read(blocksize)
                # Copy immediately; PortAudio owns the source buffer.
                block = np.asarray(data, dtype=np.float32).copy()
                if channels == 1:
                    block = block[:, 0]
                else:
                    block = np.mean(block, axis=1)
                chunks.append(block)

                elapsed = time.monotonic() - start
                if on_progress is not None:
                    on_progress(min(elapsed / duration, 1.0))

                if smart_tail and elapsed >= duration:
                    rms = float(np.sqrt(np.mean(np.square(block, dtype=np.float64)))) if block.size else 0.0
                    if rms >= silence_threshold:
                        last_voice_at = elapsed
                    elif elapsed - last_voice_at >= silence_seconds:
                        break
                if elapsed >= max_duration:
                    break

        raw = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
        # Give WASAPI/PortAudio a short, deterministic release window before a
        # continuous session may open the next InputStream.
        time.sleep(0.18)
        return _resample_recording(raw, native_sr, int(samplerate))

def save_wav(audio: np.ndarray, path: str, samplerate: int = DEFAULT_SAMPLERATE) -> None:
    """Zapisuje dane audio do pliku .wav."""
    sf.write(path, audio, samplerate)


_PLAYBACK_STATE_LOCK = threading.RLock()
_PLAYBACK_TRANSITION_LOCK = threading.Lock()
_PLAYBACK_CURRENT = None


class _PlaybackSession:
    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.done_event = threading.Event()
        self.stream = None


def stop_playback(timeout: float = 1.0) -> None:
    """Safely stop the currently active SoundCore playback, if any."""
    global _PLAYBACK_CURRENT
    with _PLAYBACK_STATE_LOCK:
        current = _PLAYBACK_CURRENT
        if current is None:
            return
        current.stop_event.set()
    # Let the owning playback thread close PortAudio itself. This avoids
    # racing stream.close()/stream.write() from two different threads.
    current.done_event.wait(max(0.0, float(timeout)))


def play_wav(path: str) -> None:
    """Play one WAV safely; a new playback always replaces the previous one."""
    global _PLAYBACK_CURRENT

    data, samplerate = sf.read(path, dtype="float32", always_2d=True)
    if data.size == 0:
        return
    channels = int(data.shape[1])

    session = _PlaybackSession()

    # Starting/stopping playback is serialized. The previous owner gets a
    # chance to close its own stream before a new PortAudio stream is opened.
    with _PLAYBACK_TRANSITION_LOCK:
        with _PLAYBACK_STATE_LOCK:
            previous = _PLAYBACK_CURRENT
            if previous is not None:
                previous.stop_event.set()
        if previous is not None:
            previous.done_event.wait(1.0)

        stream = sd.OutputStream(
            samplerate=int(samplerate),
            channels=channels,
            dtype="float32",
            blocksize=1024,
        )
        session.stream = stream
        with _PLAYBACK_STATE_LOCK:
            _PLAYBACK_CURRENT = session
        stream.start()

    try:
        # Small chunks make A/B switching responsive without issuing
        # concurrent PortAudio calls from multiple playback threads.
        chunk_frames = 1024
        offset = 0
        total = int(data.shape[0])
        while offset < total and not session.stop_event.is_set():
            end = min(total, offset + chunk_frames)
            stream.write(data[offset:end])
            offset = end
    except Exception:
        # If a device disappears or another audio operation interrupts the
        # stream, keep the error local to playback instead of crashing the UI.
        pass
    finally:
        try:
            if session.stop_event.is_set():
                stream.abort()
            else:
                stream.stop()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass
        with _PLAYBACK_STATE_LOCK:
            if _PLAYBACK_CURRENT is session:
                _PLAYBACK_CURRENT = None
        session.done_event.set()
