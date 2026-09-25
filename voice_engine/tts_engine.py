"""
tts_engine.py
-------------
Silnik syntezy mowy z klonowaniem głosu (voice cloning), oparty
o model Coqui XTTS-v2. Model ten pozwala na klonowanie barwy głosu
i sposobu mówienia (dykcji, intonacji) na podstawie krótkiej próbki
referencyjnej (kilkanaście-kilkadziesiąt sekund nagrania), bez
potrzeby pełnego treningu sieci od zera.

Silnik automatycznie wykrywa dostępność GPU (CUDA) i korzysta z niego,
jeśli jest dostępne - w przeciwnym razie działa na CPU (wolniej, ale
w pełni funkcjonalnie).

Model jest ładowany leniwie (lazy loading) - dopiero przy pierwszym
użyciu, aby aplikacja startowała szybko i nie zużywała pamięci, jeśli
użytkownik jeszcze nie generuje mowy.

Uwaga: pierwsze uruchomienie wymaga połączenia z internetem - biblioteka
`TTS` pobiera wagi modelu (ok. 1.5-2 GB) z repozytorium Coqui/HuggingFace
i zapisuje je lokalnie w cache (~/.local/share/tts). Kolejne uruchomienia
działają już offline.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Optional

MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"


@dataclass
class EngineStatus:
    device: str
    model_loaded: bool
    loading: bool
    error: Optional[str] = None


class VoiceEngine:
    """
    Wrapper na model Coqui XTTS-v2, udostępniający prosty interfejs
    do klonowania głosu i syntezy tekstu na mowę.
    """

    def __init__(self) -> None:
        self._model = None
        self._device = self._detect_device()
        self._loading = False
        self._load_error: Optional[str] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Wykrywanie urządzenia obliczeniowego (CPU/GPU)
    # ------------------------------------------------------------------
    @staticmethod
    def _detect_device() -> str:
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"

    @property
    def device(self) -> str:
        return self._device

    def status(self) -> EngineStatus:
        return EngineStatus(
            device=self._device,
            model_loaded=self._model is not None,
            loading=self._loading,
            error=self._load_error,
        )

    # ------------------------------------------------------------------
    # Ładowanie modelu (lazy loading, thread-safe)
    # ------------------------------------------------------------------
    def ensure_loaded(self) -> None:
        """Ładuje model TTS, jeśli jeszcze nie jest załadowany. Blokujące."""
        with self._lock:
            if self._model is not None:
                return
            self._loading = True
            self._load_error = None
            try:
                from TTS.api import TTS  # import lokalny - ciężka zależność

                self._model = TTS(MODEL_NAME).to(self._device)
            except Exception as exc:  # noqa: BLE001
                self._load_error = str(exc)
                raise
            finally:
                self._loading = False

    # ------------------------------------------------------------------
    # Klonowanie głosu + synteza tekstu
    # ------------------------------------------------------------------
    def clone_and_speak(
        self,
        text: str,
        speaker_wav_path: str,
        output_path: str,
        language: str = "pl",
    ) -> str:
        """
        Generuje plik audio z wypowiedzianym `text`, w głosie sklonowanym
        z próbki referencyjnej `speaker_wav_path`.

        Args:
            text: tekst do wypowiedzenia.
            speaker_wav_path: ścieżka do pliku .wav z próbką głosu (referencja).
            output_path: ścieżka, gdzie zapisać wygenerowany plik .wav.
            language: kod języka (np. "pl", "en", "de"...).

        Returns:
            Ścieżka do wygenerowanego pliku audio (output_path).
        """
        if not text.strip():
            raise ValueError("Tekst do syntezy nie może być pusty.")
        if not os.path.isfile(speaker_wav_path):
            raise FileNotFoundError(f"Nie znaleziono próbki głosu: {speaker_wav_path}")

        self.ensure_loaded()

        self._model.tts_to_file(
            text=text,
            speaker_wav=speaker_wav_path,
            language=language,
            file_path=output_path,
        )
        return output_path


# Pojedyncza, globalna instancja silnika (singleton) - ładowanie modelu
# jest kosztowne, więc nie chcemy tworzyć wielu kopii w ramach aplikacji.
_engine_instance: Optional[VoiceEngine] = None


def get_engine() -> VoiceEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = VoiceEngine()
    return _engine_instance
