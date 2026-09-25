"""
rvc_engine.py
-------------
Opcjonalny moduł konwersji barwy głosu (post-processing) przy użyciu
biblioteki `rvc-python` (RVC - Retrieval-based Voice Conversion).

Różnica względem voice_engine/tts_engine.py (XTTS):
    - XTTS klonuje głos "w locie" (zero-shot) z jednej krótkiej próbki,
      bez treningu. Wygodne, ale ograniczona wierność barwy głosu.
    - RVC wymaga JEDNORAZOWEGO wytrenowania małego modelu na dłuższym
      zbiorze nagrań danej osoby (zalecane 5-15+ minut czystego audio).
      Taki model (.pth + opcjonalnie .index) trenuje się OSOBNO, przy
      użyciu dedykowanego narzędzia treningowego (patrz README.md,
      sekcja "Trenowanie własnego modelu RVC").

Ten moduł odpowiada WYŁĄCZNIE za inferencję: bierze gotowy plik audio
(np. wygenerowany przez XTTS) i "przepuszcza" go przez wytrenowany
model RVC, zamieniając barwę głosu na tę, na której model był
trenowany. Efekt jest zwykle zauważalnie bliższy oryginalnemu głosowi
niż sam zero-shot cloning z XTTS, bo model RVC jest realnie
douczony na konkretnej osobie, a nie tylko warunkowany embeddingiem.

Instalacja (opcjonalna, osobno od głównych zależności projektu):
    pip install -r requirements-rvc.txt
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Optional


@dataclass
class RVCParams:
    """
    Parametry konwersji głosu RVC.

    f0method: metoda ekstrakcji wysokości dźwięku (pitch) - "rmvpe" jest
        zwykle najlepszym kompromisem jakość/szybkość na CPU.
    f0up_key: przesunięcie tonacji w półtonach (np. +12 = oktawa wyżej,
        przydatne przy konwersji między głosami o różnej wysokości).
    index_rate: 0.0-1.0, jak mocno korzystać z pliku .index (wyższe
        wartości = bliżej oryginalnej barwy, ale czasem mniej naturalnie).
    protect: 0.0-0.5, chroni spółgłoski bezdźwięczne (np. "s", "f")
        przed zniekształceniem przy konwersji.
    """
    f0method: str = "rmvpe"
    f0up_key: int = 0
    index_rate: float = 0.5
    filter_radius: int = 3
    resample_sr: int = 0
    rms_mix_rate: float = 0.25
    protect: float = 0.33


class RVCEngine:
    """Wrapper na bibliotekę rvc-python, do konwersji barwy głosu (inferencja)."""

    def __init__(self) -> None:
        self._rvc = None
        self._device = self._detect_device()
        self._loaded_model_path: Optional[str] = None
        self._lock = threading.Lock()
        self._import_error: Optional[str] = None

    @staticmethod
    def _detect_device() -> str:
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda:0"
        except ImportError:
            pass
        return "cpu"

    @property
    def device(self) -> str:
        return self._device

    def is_available(self) -> bool:
        """Sprawdza, czy biblioteka rvc-python jest zainstalowana."""
        try:
            import rvc_python.infer  # noqa: F401

            return True
        except ImportError as exc:
            self._import_error = str(exc)
            return False

    def _ensure_backend(self) -> None:
        if self._rvc is None:
            try:
                from rvc_python.infer import RVCInference
            except ImportError as exc:
                raise RuntimeError(
                    "Biblioteka 'rvc-python' nie jest zainstalowana. "
                    "Zainstaluj: pip install -r requirements-rvc.txt"
                ) from exc
            self._rvc = RVCInference(device=self._device)

    def load_model(
        self,
        model_path: str,
        index_path: Optional[str] = None,
        params: Optional[RVCParams] = None,
    ) -> None:
        """Ładuje model RVC (.pth), jeśli jeszcze nie jest załadowany."""
        with self._lock:
            if not os.path.isfile(model_path):
                raise FileNotFoundError(f"Nie znaleziono modelu RVC: {model_path}")

            self._ensure_backend()

            if self._loaded_model_path == model_path:
                if params:
                    self._apply_params(params)
                return  # model już załadowany, nic nie rób

            self._rvc.load_model(model_path)

            if index_path and os.path.isfile(index_path):
                # Nazwa atrybutu zależy od wersji biblioteki - próbujemy
                # bezpiecznie, ale nie przerywamy działania, jeśli się nie uda
                # (konwersja zadziała też bez pliku .index, tylko nieco mniej
                # precyzyjnie pod względem barwy).
                for attr in ("index_path", "file_index", "index_file"):
                    if hasattr(self._rvc, attr):
                        setattr(self._rvc, attr, index_path)
                        break

            self._apply_params(params or RVCParams())
            self._loaded_model_path = model_path

    def _apply_params(self, params: RVCParams) -> None:
        try:
            self._rvc.set_params(
                f0method=params.f0method,
                f0up_key=params.f0up_key,
                index_rate=params.index_rate,
                filter_radius=params.filter_radius,
                resample_sr=params.resample_sr,
                rms_mix_rate=params.rms_mix_rate,
                protect=params.protect,
            )
        except Exception:
            # Różne wersje rvc-python mogą mieć nieco inne API do ustawiania
            # parametrów - brak tej metody nie powinien blokować konwersji,
            # zadziała wtedy z wartościami domyślnymi biblioteki.
            pass

    def convert(self, input_wav_path: str, output_wav_path: str) -> str:
        """
        Konwertuje barwę głosu w pliku `input_wav_path` przy użyciu
        aktualnie załadowanego modelu RVC i zapisuje wynik do
        `output_wav_path`.
        """
        if self._rvc is None or self._loaded_model_path is None:
            raise RuntimeError("Najpierw załaduj model RVC (load_model).")
        self._rvc.infer_file(input_wav_path, output_wav_path)
        return output_wav_path


_engine_instance: Optional[RVCEngine] = None


def get_rvc_engine() -> RVCEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = RVCEngine()
    return _engine_instance
