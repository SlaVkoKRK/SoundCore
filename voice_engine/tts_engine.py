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
from pathlib import Path
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
        self._model_config = None
        self._model_key = None
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
    def ensure_loaded(self, trained_model: Optional[dict] = None) -> None:
        """Load base XTTS or a profile-specific fine-tuned XTTS checkpoint."""
        key = "base" if not trained_model else f"trained:{trained_model.get('checkpoint_path','')}"
        with self._lock:
            if self._model is not None and self._model_key == key:
                return
            self._loading = True
            self._load_error = None
            try:
                # Release the previous model before switching base/trained checkpoints.
                self._model = None
                self._model_config = None
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
                if not trained_model:
                    from TTS.api import TTS
                    self._model = TTS(MODEL_NAME).to(self._device)
                    self._model_key = "base"
                else:
                    from TTS.tts.configs.xtts_config import XttsConfig
                    from TTS.tts.models.xtts import Xtts
                    config_path = trained_model.get("config_path")
                    checkpoint_path = trained_model.get("checkpoint_path")
                    vocab_path = trained_model.get("vocab_path")
                    for label, path in (("config", config_path), ("checkpoint", checkpoint_path), ("vocab", vocab_path)):
                        if not path or not os.path.isfile(path):
                            raise FileNotFoundError(f"Brak pliku wytrenowanego XTTS ({label}): {path}")
                    config = XttsConfig()
                    config.load_json(config_path)

                    # GPTTrainer stores references to base XTTS assets in its config.
                    # Depending on Coqui version those fields may be missing/None or may
                    # point at a temporary training location.  Xtts.load_checkpoint()
                    # later opens them internally and a None value ends up as the very
                    # unhelpful: "expected str, bytes or os.PathLike object, not NoneType".
                    checkpoint_obj = Path(checkpoint_path).resolve()
                    base_assets = None
                    for parent in (checkpoint_obj.parent, *checkpoint_obj.parents):
                        candidate = parent / "XTTS_v2_original_model_files"
                        if candidate.is_dir():
                            base_assets = candidate
                            break
                    if base_assets is None:
                        raise FileNotFoundError(
                            "Nie znaleziono katalogu XTTS_v2_original_model_files obok wytrenowanego checkpointu."
                        )

                    required_base = {
                        "dvae_checkpoint": "dvae.pth",
                        "mel_norm_file": "mel_stats.pth",
                        "tokenizer_file": "vocab.json",
                        "xtts_checkpoint": "model.pth",
                    }
                    model_args = getattr(config, "model_args", None)
                    if model_args is None:
                        raise RuntimeError("Config wytrenowanego XTTS nie zawiera model_args.")
                    for attr, filename in required_base.items():
                        asset = base_assets / filename
                        if not asset.is_file():
                            raise FileNotFoundError(f"Brak bazowego pliku XTTS: {asset}")
                        current = getattr(model_args, attr, None)
                        if not current or not os.path.isfile(str(current)):
                            setattr(model_args, attr, str(asset))

                    # Always use the verified vocabulary next to the training assets.
                    # This avoids stale paths saved in the trainer config.
                    vocab_path = str(base_assets / "vocab.json")
                    model = Xtts.init_from_config(config)
                    try:
                        model.load_checkpoint(
                            config,
                            checkpoint_path=checkpoint_path,
                            vocab_path=vocab_path,
                            use_deepspeed=False,
                        )
                    except Exception as load_exc:
                        raise RuntimeError(
                            f"Nie udało się załadować wytrenowanego XTTS ({type(load_exc).__name__}): {load_exc}"
                        ) from load_exc
                    if self._device == "cuda":
                        model.cuda()
                    self._model = model
                    self._model_config = config
                    self._model_key = key
            except Exception as exc:
                self._load_error = str(exc)
                self._model_key = None
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
        trained_model: Optional[dict] = None,
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

        self.ensure_loaded(trained_model)

        if not trained_model:
            self._model.tts_to_file(
                text=text,
                speaker_wav=speaker_wav_path,
                language=language,
                file_path=output_path,
            )
        else:
            import soundfile as sf
            gpt_cond_latent, speaker_embedding = self._model.get_conditioning_latents(audio_path=[speaker_wav_path])
            result = self._model.inference(
                text,
                language,
                gpt_cond_latent,
                speaker_embedding,
            )
            wav = result["wav"] if isinstance(result, dict) else result
            sample_rate = int(getattr(getattr(self._model_config, "audio", None), "output_sample_rate", 24000) or 24000)
            sf.write(output_path, wav, sample_rate)
        return output_path


# Pojedyncza, globalna instancja silnika (singleton) - ładowanie modelu
# jest kosztowne, więc nie chcemy tworzyć wielu kopii w ramach aplikacji.
_engine_instance: Optional[VoiceEngine] = None


def get_engine() -> VoiceEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = VoiceEngine()
    return _engine_instance
