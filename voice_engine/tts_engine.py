"""SoundCore XTTS-v2 inference engine: zero-shot and local fine-tuned models."""
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
    def __init__(self) -> None:
        self._model = None
        self._custom_model = None
        self._custom_key = None
        self._device = self._detect_device()
        self._loading = False
        self._load_error: Optional[str] = None
        self._lock = threading.Lock()

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
        return EngineStatus(self._device, self._model is not None, self._loading, self._load_error)

    def ensure_loaded(self) -> None:
        with self._lock:
            if self._model is not None:
                return
            self._loading = True
            self._load_error = None
            try:
                from TTS.api import TTS
                self._model = TTS(MODEL_NAME).to(self._device)
            except Exception as exc:
                self._load_error = str(exc)
                raise
            finally:
                self._loading = False

    def clone_and_speak(self, text: str, speaker_wav_path: str, output_path: str, language: str = "pl") -> str:
        if not text.strip():
            raise ValueError("Tekst do syntezy nie może być pusty.")
        if not os.path.isfile(speaker_wav_path):
            raise FileNotFoundError(f"Nie znaleziono próbki głosu: {speaker_wav_path}")
        self.ensure_loaded()
        self._model.tts_to_file(text=text, speaker_wav=speaker_wav_path, language=language, file_path=output_path)
        return output_path

    def _load_finetuned(self, checkpoint: str, config_path: str, vocab_path: str):
        key = (os.path.abspath(checkpoint), os.path.abspath(config_path), os.path.abspath(vocab_path), self._device)
        with self._lock:
            if self._custom_model is not None and self._custom_key == key:
                return self._custom_model
            import torch
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import Xtts
            cfg = XttsConfig()
            cfg.load_json(config_path)
            model = Xtts.init_from_config(cfg)
            model.load_checkpoint(cfg, checkpoint_path=checkpoint, vocab_path=vocab_path, use_deepspeed=False)
            model.to(self._device)
            model.eval()
            self._custom_model = model
            self._custom_key = key
            return model

    def finetuned_speak(self, text: str, speaker_wav_path: str, output_path: str, model_info: dict, language: str = "pl") -> str:
        import torch
        import torchaudio
        checkpoint = model_info.get("checkpoint", "")
        config_path = model_info.get("config", "")
        vocab_path = model_info.get("vocab", "")
        for label, path in (("checkpoint", checkpoint), ("config", config_path), ("vocab", vocab_path), ("reference", speaker_wav_path)):
            if not path or not os.path.isfile(path):
                raise FileNotFoundError(f"Brak pliku {label} wytrenowanego modelu: {path}")
        model = self._load_finetuned(checkpoint, config_path, vocab_path)
        gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(audio_path=[speaker_wav_path])
        out = model.inference(text, language, gpt_cond_latent, speaker_embedding, temperature=0.7)
        wav = torch.tensor(out["wav"]).unsqueeze(0).cpu()
        torchaudio.save(output_path, wav, 24000)
        return output_path

_engine_instance: Optional[VoiceEngine] = None

def get_engine() -> VoiceEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = VoiceEngine()
    return _engine_instance
