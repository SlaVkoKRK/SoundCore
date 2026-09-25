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

    @property
    def folder(self) -> str:
        return os.path.join(BASE_DIR, self.name)

    @property
    def wav_path(self) -> str:
        return os.path.join(self.folder, "reference.wav")

    @property
    def trained_model_result_path(self) -> str:
        return os.path.join(self.folder, "model", "training_result.json")

    @property
    def trained_model_info(self) -> Optional[dict]:
        path = self.trained_model_result_path
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("checkpoint") and os.path.isfile(data["checkpoint"]):
                return data
        except (OSError, ValueError, TypeError):
            pass
        return None

    @property
    def has_trained_model(self) -> bool:
        return self.trained_model_info is not None

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

    def delete_profile(self, name: str) -> None:
        folder = os.path.join(self.base_dir, name)
        if os.path.isdir(folder):
            shutil.rmtree(folder)
