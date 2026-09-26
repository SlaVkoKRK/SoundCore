"""
profile_manager.py
-------------------
Zarządzanie profilami głosowymi użytkowników. Każdy profil to folder
zawierający:
    - reference.wav  -> oczyszczona próbka referencyjna głosu
    - metadata.json   -> metadane (nazwa, data utworzenia, długość próbki...)

Struktura na dysku:
    voice_profiles/
        Jan/
            reference.wav
            metadata.json
        Anna/
            reference.wav
            metadata.json
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "voice_profiles")


@dataclass
class VoiceProfile:
    name: str
    created_at: str
    duration_seconds: float
    samplerate: int
    rvc_model_path: Optional[str] = None
    rvc_index_path: Optional[str] = None
    xtts_mode: str = "base"
    xtts_checkpoint_path: Optional[str] = None
    xtts_config_path: Optional[str] = None
    xtts_vocab_path: Optional[str] = None
    xtts_trained_at: Optional[str] = None

    @property
    def folder(self) -> str:
        return os.path.join(BASE_DIR, self.name)

    @property
    def wav_path(self) -> str:
        return os.path.join(self.folder, "reference.wav")

    @property
    def has_rvc_model(self) -> bool:
        return bool(self.rvc_model_path) and os.path.isfile(self.rvc_model_path)


class ProfileManager:
    def __init__(self, base_dir: str = BASE_DIR) -> None:
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    @staticmethod
    def _sanitize_name(name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Nazwa profilu nie może być pusta.")
        # tylko litery, cyfry, spacje, myślniki, podkreślenia
        if not re.match(r"^[\w\- ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+$", name):
            raise ValueError("Nazwa profilu zawiera niedozwolone znaki.")
        return name

    def save_profile(
        self,
        name: str,
        audio_data,  # numpy.ndarray
        samplerate: int,
        overwrite: bool = False,
    ) -> VoiceProfile:
        """Zapisuje nowy profil głosowy (próbkę referencyjną + metadane)."""
        import soundfile as sf
        import numpy as np

        name = self._sanitize_name(name)
        folder = os.path.join(self.base_dir, name)

        if os.path.exists(folder) and not overwrite:
            raise FileExistsError(f"Profil '{name}' już istnieje.")

        os.makedirs(folder, exist_ok=True)
        wav_path = os.path.join(folder, "reference.wav")
        sf.write(wav_path, audio_data, samplerate)

        duration = float(len(audio_data)) / samplerate

        profile = VoiceProfile(
            name=name,
            created_at=datetime.now().isoformat(timespec="seconds"),
            duration_seconds=round(duration, 2),
            samplerate=samplerate,
        )

        with open(os.path.join(folder, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(asdict(profile), f, ensure_ascii=False, indent=2)

        return profile

    def list_profiles(self) -> list[VoiceProfile]:
        """Zwraca listę wszystkich zapisanych profili głosowych."""
        profiles = []
        if not os.path.isdir(self.base_dir):
            return profiles

        for entry in sorted(os.listdir(self.base_dir)):
            folder = os.path.join(self.base_dir, entry)
            metadata_path = os.path.join(folder, "metadata.json")
            if os.path.isfile(metadata_path):
                with open(metadata_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                profiles.append(VoiceProfile(**data))
        return profiles

    def get_profile(self, name: str) -> Optional[VoiceProfile]:
        for profile in self.list_profiles():
            if profile.name == name:
                return profile
        return None

    def set_rvc_model(
        self, name: str, model_path: str, index_path: Optional[str] = None
    ) -> VoiceProfile:
        """Podpina wytrenowany model RVC (.pth, opcjonalnie .index) pod istniejący profil."""
        profile = self.get_profile(name)
        if profile is None:
            raise ValueError(f"Nie znaleziono profilu '{name}'.")
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"Nie znaleziono pliku modelu: {model_path}")
        if index_path and not os.path.isfile(index_path):
            raise FileNotFoundError(f"Nie znaleziono pliku indeksu: {index_path}")

        profile.rvc_model_path = model_path
        profile.rvc_index_path = index_path

        metadata_path = os.path.join(profile.folder, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(asdict(profile), f, ensure_ascii=False, indent=2)

        return profile


    def find_trained_xtts(self, name: str) -> Optional[dict]:
        """Find the newest usable XTTS GPTTrainer checkpoint for a profile."""
        profile = self.get_profile(name)
        if profile is None:
            return None
        root = Path(profile.folder) / "model" / "xtts_gpt"
        if not root.exists():
            return None
        candidates = list(root.rglob("best_model.pth"))
        if not candidates:
            candidates = list(root.rglob("checkpoint_*.pth")) + list(root.rglob("*.pth"))
            candidates = [x for x in candidates if x.name not in {"dvae.pth", "mel_stats.pth", "model.pth"}]
        if not candidates:
            return None
        checkpoint = max(candidates, key=lambda x: x.stat().st_mtime)
        config_candidates = list(checkpoint.parent.glob("config.json")) or list(root.rglob("config.json"))
        if not config_candidates:
            return None
        config = max(config_candidates, key=lambda x: x.stat().st_mtime)
        vocab_candidates = list(root.rglob("vocab.json"))
        if not vocab_candidates:
            return None
        vocab = max(vocab_candidates, key=lambda x: x.stat().st_mtime)
        return {
            "checkpoint_path": str(checkpoint),
            "config_path": str(config),
            "vocab_path": str(vocab),
            "trained_at": datetime.fromtimestamp(checkpoint.stat().st_mtime).isoformat(timespec="seconds"),
            "checkpoint_name": checkpoint.name,
        }

    def set_xtts_mode(self, name: str, mode: str) -> VoiceProfile:
        profile = self.get_profile(name)
        if profile is None:
            raise ValueError(f"Nie znaleziono profilu '{name}'.")
        mode = (mode or "base").lower()
        if mode not in {"base", "trained"}:
            raise ValueError("Nieprawidłowy tryb XTTS.")
        if mode == "trained":
            info = self.find_trained_xtts(name)
            if not info:
                raise FileNotFoundError("Nie znaleziono kompletnego wytrenowanego modelu XTTS dla tego profilu.")
            profile.xtts_checkpoint_path = info["checkpoint_path"]
            profile.xtts_config_path = info["config_path"]
            profile.xtts_vocab_path = info["vocab_path"]
            profile.xtts_trained_at = info["trained_at"]
        profile.xtts_mode = mode
        metadata_path = os.path.join(profile.folder, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(asdict(profile), f, ensure_ascii=False, indent=2)
        return profile

    def delete_profile(self, name: str) -> None:
        folder = os.path.join(self.base_dir, name)
        if os.path.isdir(folder):
            shutil.rmtree(folder)
