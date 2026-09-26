from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

# Keep WebView2 diagnostics quiet in normal SoundCore operation.
# The app still surfaces its own actionable errors in the notification center.
os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--log-level=3 --disable-logging")

import webview

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.profile_manager import ProfileManager
from system.cuda_manager import CudaRepairManager
from system.windows_integration import prepare_windows_process, setup_windows_shell_async
from training.manager import TrainingManager
from updater.update_manager import UpdateCancelled, check_for_update, download_update, launch_apply
from voice_engine.external_engines import ExternalEngineManager
from music.song_manager import SongManager

BASE_DIR = Path(__file__).resolve().parents[1]
WEBUI_DIR = BASE_DIR / "webui"
OUTPUT_DIR = BASE_DIR / "output"
APP_ICON = BASE_DIR / "gui" / "assets" / "soundcore.ico"
APP_VERSION = (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip() if (BASE_DIR / "VERSION").exists() else "0.3.9"
CHANNEL_URL = "https://raw.githubusercontent.com/SlaVkoKRK/SoundCore/main/dist/channel.json"
OUTPUT_DIR.mkdir(exist_ok=True)
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)
HARDWARE_CACHE = CACHE_DIR / "hardware.json"
SYNTH_HISTORY_PATH = OUTPUT_DIR / "history.json"


def _default_hardware() -> dict:
    return {
        "cpu": os.environ.get("PROCESSOR_IDENTIFIER", "CPU"),
        "gpu_detected": False,
        "gpu_name": "Wykrywanie...",
        "gpu_memory_mb": None,
        "nvidia_driver": None,
        "torch_cuda_available": False,
        "torch_cuda_version": None,
        "torch_device_name": None,
        "recommended_device": "cpu",
        "note": "Sprzęt jest wykrywany w tle.",
    }


def _load_hardware_cache() -> dict:
    try:
        data = json.loads(HARDWARE_CACHE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data["note"] = "Ostatnio wykryty sprzęt — odświeżanie w tle…"
            return {**_default_hardware(), **data}
    except Exception:
        pass
    return _default_hardware()



class SoundCoreApi:
    def __init__(self) -> None:
        # Fast-start: only lightweight objects are created before WebUI is visible.
        self._profile_manager = ProfileManager()
        self._training = TrainingManager(str(BASE_DIR))
        self._cuda_repair = CudaRepairManager(BASE_DIR / "training_runtime")
        self._engine = None
        self._rvc_engine = None
        self._external_engines = ExternalEngineManager(BASE_DIR)
        self._songs = SongManager(BASE_DIR)
        self._rvc_install_status: dict = {"state": "idle", "progress": 0, "message": "RVC nie jest instalowane."}
        self._hardware: dict = _load_hardware_cache()
        self._devices: list[dict] = []
        self._profiles_cache: list[dict] | None = None
        self._background_started = False
        self._background_lock = threading.Lock()
        self._services = {
            "interface": {"state": "ready", "label": "Interfejs", "message": "Gotowy"},
            "hardware": {"state": "pending", "label": "GPU", "message": "Oczekuje"},
            "audio": {"state": "pending", "label": "Audio", "message": "Oczekuje"},
            "profiles": {"state": "pending", "label": "Profile", "message": "Oczekuje"},
            "xtts": {"state": "lazy", "label": "XTTS", "message": "Ładowany przy pierwszej syntezie"},
            "rvc": {"state": "lazy", "label": "RVC", "message": "Ładowany tylko gdy używany"},
        }
        self._notifications: list[dict] = []
        self._last_generated: str | None = None
        self._update_cache: dict | None = None
        self._update_install_status: dict = {"state": "idle", "progress": 0, "message": "Brak aktywnej aktualizacji."}
        self._update_cancel = threading.Event()

    def _notify(self, title: str, message: str, level: str = "info") -> None:
        self._notifications.insert(0, {
            "id": f"n{datetime.now().timestamp()}",
            "title": title,
            "message": message,
            "level": level,
            "time": datetime.now().strftime("%H:%M"),
            "read": False,
        })
        self._notifications = self._notifications[:40]

    def get_state(self) -> dict:
        profiles = self._profiles_cache if self._profiles_cache is not None else self._profiles_payload_light()
        return {
            "version": APP_VERSION,
            "user": {"name": getpass.getuser(), "role": "Użytkownik"},
            "hardware": dict(self._hardware),
            "profiles": profiles,
            "devices": list(self._devices),
            "notifications": self._notifications,
            "training": self._training.status(),
            "last_generated": self._last_generated,
            "cuda_repair": self._cuda_repair.status(),
            "services": self.startup_status()["services"],
            "voice_engines": self._external_engines.status(),
            "rvc_install": dict(self._rvc_install_status),
        }

    def startup_status(self) -> dict:
        return {
            "started": self._background_started,
            "services": {k: dict(v) for k, v in self._services.items()},
            "ready": all(v["state"] in {"ready", "lazy", "error"} for v in self._services.values()),
        }

    def start_background_services(self) -> dict:
        with self._background_lock:
            if self._background_started:
                return self.startup_status()
            self._background_started = True
            threading.Thread(target=self._background_initialize, name="SoundCoreWarmup", daemon=True).start()
        return self.startup_status()

    def _background_initialize(self) -> None:
        # Hardware/Torch is intentionally first background task, never a startup blocker.
        self._services["hardware"].update(state="loading", message="Wykrywanie GPU / CUDA…")
        try:
            from system.hardware import detect_hardware
            hw = detect_hardware().to_dict()
            self._hardware = hw
            HARDWARE_CACHE.write_text(json.dumps(hw, ensure_ascii=False, indent=2), encoding="utf-8")
            self._cuda_repair.reconcile(bool(hw.get("torch_cuda_available")))
            self._services["hardware"].update(state="ready", message=("CUDA gotowa" if hw.get("torch_cuda_available") else (hw.get("gpu_name") or "CPU")))
            self._notify("Sprzęt wykryty", hw.get("note", "Sprzęt gotowy."), "success" if hw.get("torch_cuda_available") else "info")
        except Exception as exc:
            self._services["hardware"].update(state="error", message=str(exc))

        self._services["audio"].update(state="loading", message="Wykrywanie mikrofonów…")
        try:
            self._devices = self._load_devices()
            self._services["audio"].update(state="ready", message=f"{len(self._devices)} urządzeń")
        except Exception as exc:
            self._services["audio"].update(state="error", message=str(exc))

        self._services["profiles"].update(state="loading", message="Odświeżanie biblioteki…")
        try:
            self._profiles_cache = self._profiles_payload_full()
            self._services["profiles"].update(state="ready", message=f"{len(self._profiles_cache)} profili")
        except Exception as exc:
            self._services["profiles"].update(state="error", message=str(exc))

    def _load_devices(self) -> list[dict]:
        from recorder.recorder import list_input_devices
        return [{"index": d.index, "name": d.name, "channels": getattr(d, "max_input_channels", None)} for d in list_input_devices()]

    def _profiles_payload_light(self) -> list[dict]:
        rows = []
        for p in self._profile_manager.list_profiles():
            meta = Path(p.folder) / "dataset" / "metadata.csv"
            samples = 0
            if meta.exists():
                try:
                    samples = sum(1 for line in meta.read_text(encoding="utf-8").splitlines() if line.strip())
                except Exception:
                    pass
            trained = self._profile_manager.find_trained_xtts(p.name)
            rows.append({
                "name": p.name, "created_at": p.created_at, "duration_seconds": p.duration_seconds,
                "has_rvc_model": p.has_rvc_model, "rvc_model_path": p.rvc_model_path, "rvc_index_path": p.rvc_index_path, "xtts_mode": p.xtts_mode,
                "has_trained_xtts": bool(trained), "trained_xtts": trained,
                "dataset": {"samples": samples, "duration_seconds": 0.0, "duration_minutes": 0.0},
            })
        return rows

    def _profiles_payload_full(self) -> list[dict]:
        from training.dataset import get_stats
        rows = []
        for p in self._profile_manager.list_profiles():
            stats = get_stats(p.folder)
            trained = self._profile_manager.find_trained_xtts(p.name)
            rows.append({
                "name": p.name, "created_at": p.created_at, "duration_seconds": p.duration_seconds,
                "has_rvc_model": p.has_rvc_model, "rvc_model_path": p.rvc_model_path, "rvc_index_path": p.rvc_index_path, "xtts_mode": p.xtts_mode,
                "has_trained_xtts": bool(trained), "trained_xtts": trained,
                "dataset": stats.to_dict(),
            })
        return rows

    def refresh_hardware(self) -> dict:
        from system.hardware import detect_hardware
        hw = detect_hardware().to_dict()
        self._hardware = hw
        HARDWARE_CACHE.write_text(json.dumps(hw, ensure_ascii=False, indent=2), encoding="utf-8")
        self._cuda_repair.reconcile(bool(hw.get("torch_cuda_available")))
        self._services["hardware"].update(state="ready", message=("CUDA gotowa" if hw.get("torch_cuda_available") else hw.get("gpu_name", "CPU")))
        self._notify("Ponowne wykrywanie GPU", hw.get("note", ""), "success" if hw.get("torch_cuda_available") else "warning")
        return hw

    def get_reading_prompt(self, duration: int, purpose: str = "training", nonce: int = 0, profile_name: str = "") -> dict:
        profile_folder = None
        if profile_name:
            profile = self._profile_manager.get_profile(profile_name)
            if profile is not None:
                profile_folder = profile.folder
        from training.text_bank import build_prompt
        return build_prompt(duration, purpose, nonce, profile_folder=profile_folder)

    def get_devices(self) -> list[dict]:
        if not self._devices:
            try:
                self._devices = self._load_devices()
            except Exception as exc:
                self._notify("Mikrofon", f"Nie udało się pobrać listy urządzeń: {exc}", "error")
        return list(self._devices)

    def _profiles_payload(self) -> list[dict]:
        self._profiles_cache = self._profiles_payload_full()
        return self._profiles_cache

    def notifications_state(self) -> list[dict]:
        return self._notifications

    def mark_notifications_read(self) -> dict:
        for n in self._notifications:
            n["read"] = True
        return {"ok": True}

    def record_profile(self, name: str, duration: int, device_index: int, reading_text: str = "") -> dict:
        name = (name or "").strip()
        if not name:
            raise ValueError("Podaj nazwę profilu.")
        from recorder.recorder import DEFAULT_SAMPLERATE, record_audio
        from preprocessing.audio_utils import preprocess_pipeline
        from training.text_bank import remember_prompt
        duration = max(5, min(int(duration), 120))
        audio = record_audio(duration=duration, device=int(device_index))
        cleaned = preprocess_pipeline(audio, DEFAULT_SAMPLERATE)
        profile = self._profile_manager.save_profile(name, cleaned, DEFAULT_SAMPLERATE, overwrite=True)
        if reading_text.strip():
            remember_prompt(profile.folder, reading_text, "profile")
        self._notify("Profil zapisany", f"Profil '{name}' jest gotowy do użycia.", "success")
        return {"ok": True, "profile": profile.name, "duration": profile.duration_seconds, "profiles": self._profiles_payload()}

    def record_training_sample(self, profile_name: str, text: str, duration: int, device_index: int) -> dict:
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        from recorder.recorder import DEFAULT_SAMPLERATE, record_audio
        from preprocessing.audio_utils import preprocess_pipeline
        from training.dataset import add_sample, get_stats
        from training.text_bank import remember_prompt
        duration = max(3, min(int(duration), 30))
        audio = record_audio(duration=duration, device=int(device_index))
        cleaned = preprocess_pipeline(audio, DEFAULT_SAMPLERATE)
        sample = add_sample(profile.folder, cleaned, DEFAULT_SAMPLERATE, text)
        remember_prompt(profile.folder, text, "training")
        stats = get_stats(profile.folder)
        # Fast-start keeps a profile cache; refresh it after every dataset mutation.
        self._profiles_cache = self._profiles_payload_full()
        self._notify("Próbka treningowa", f"Dodano próbkę {sample['id']} do profilu {profile_name}.", "success")
        return {"ok": True, "sample": sample, "dataset": stats.to_dict(), "profiles": self._profiles_cache}

    def play_profile(self, profile_name: str) -> dict:
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        from recorder.recorder import play_wav
        threading.Thread(target=lambda: play_wav(profile.wav_path), daemon=True).start()
        return {"ok": True}

    def delete_profile(self, profile_name: str) -> dict:
        self._profile_manager.delete_profile(profile_name)
        self._notify("Profil usunięty", f"Usunięto profil '{profile_name}'.", "info")
        return {"ok": True, "profiles": self._profiles_payload()}

    def _load_synthesis_history(self) -> list[dict]:
        try:
            rows = json.loads(SYNTH_HISTORY_PATH.read_text(encoding="utf-8"))
            if isinstance(rows, list):
                return [x for x in rows if isinstance(x, dict)]
        except Exception:
            pass
        return []

    def _save_synthesis_history(self, rows: list[dict]) -> None:
        SYNTH_HISTORY_PATH.write_text(json.dumps(rows[-500:], ensure_ascii=False, indent=2), encoding="utf-8")

    def _add_synthesis_history(self, *, path: Path, text: str, profile_name: str, language: str,
                               style: str, speed: float, model_mode: str, use_rvc: bool, ab_group: str = "", engine: str = "xtts") -> dict:
        duration = 0.0
        try:
            import soundfile as sf
            duration = round(float(sf.info(str(path)).duration), 2)
        except Exception:
            pass
        row = {
            "id": path.stem, "name": path.name, "path": str(path),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "text": text, "profile": profile_name, "language": language,
            "style": style, "speed": float(speed), "model_mode": model_mode, "engine": engine,
            "rvc": bool(use_rvc), "duration_seconds": duration, "ab_group": ab_group or "",
        }
        rows = self._load_synthesis_history()
        rows.append(row)
        self._save_synthesis_history(rows)
        return row

    def list_synthesis_history(self, limit: int = 100) -> dict:
        rows = [x for x in self._load_synthesis_history() if os.path.isfile(str(x.get("path", "")))]
        rows = list(reversed(rows[-max(1, min(int(limit), 500)):]))
        return {"ok": True, "items": rows}

    def play_synthesis(self, item_id: str) -> dict:
        item = next((x for x in self._load_synthesis_history() if x.get("id") == item_id), None)
        if not item or not os.path.isfile(str(item.get("path", ""))):
            raise FileNotFoundError("Nie znaleziono wygenerowanego nagrania.")
        from recorder.recorder import play_wav
        threading.Thread(target=lambda: play_wav(item["path"]), daemon=True).start()
        return {"ok": True}

    def delete_synthesis(self, item_id: str) -> dict:
        rows = self._load_synthesis_history()
        kept = []
        for item in rows:
            if item.get("id") == item_id:
                try:
                    Path(str(item.get("path", ""))).unlink(missing_ok=True)
                except Exception:
                    pass
            else:
                kept.append(item)
        self._save_synthesis_history(kept)
        return self.list_synthesis_history()

    def export_synthesis(self, item_id: str = "") -> dict:
        item = None
        rows = self._load_synthesis_history()
        if item_id:
            item = next((x for x in rows if x.get("id") == item_id), None)
        elif self._last_generated:
            item = {"path": self._last_generated, "name": Path(self._last_generated).name}
        if not item or not os.path.isfile(str(item.get("path", ""))):
            raise FileNotFoundError("Brak pliku do zapisania.")
        win = webview.active_window()
        if win is None:
            raise RuntimeError("Okno SoundCore nie jest gotowe.")
        save_dialog = getattr(webview.FileDialog, "SAVE", None)
        if save_dialog is None:
            raise RuntimeError("Ta wersja pywebview nie obsługuje okna zapisu.")
        selected = win.create_file_dialog(save_dialog, save_filename=item.get("name") or Path(item["path"]).name, file_types=("WAV (*.wav)",))
        if not selected:
            return {"ok": False, "cancelled": True}
        dest = selected[0] if isinstance(selected, (list, tuple)) else selected
        dest_path = Path(str(dest))
        if dest_path.suffix.lower() != ".wav":
            dest_path = dest_path.with_suffix(".wav")
        shutil.copy2(item["path"], dest_path)
        return {"ok": True, "path": str(dest_path)}

    def synthesize(self, text: str, profile_name: str, language: str = "pl", use_rvc: bool = False,
                   style: str = "natural", speed: float = 1.0, model_mode: str = "active", ab_group: str = "",
                   engine_id: str = "xtts") -> dict:
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        if not text.strip():
            raise ValueError("Wpisz tekst do syntezy.")
        if use_rvc and not profile.has_rvc_model:
            raise ValueError("Profil nie ma podpiętego modelu RVC.")
        engine_id = (engine_id or "xtts").lower()
        if engine_id not in {"xtts", "f5", "qwen"}:
            raise ValueError("Ten silnik nie jest jeszcze dostępny do syntezy lokalnej.")
        if engine_id == "xtts" and self._engine is None:
            self._services["xtts"].update(state="loading", message="Ładowanie XTTS…")
            from voice_engine.tts_engine import get_engine
            self._engine = get_engine()

        requested = (model_mode or "active").lower()
        if requested not in {"active", "base", "trained"}:
            requested = "active"
        actual_mode = getattr(profile, "xtts_mode", "base") if requested == "active" else requested
        trained_model = None
        if engine_id == "xtts" and actual_mode == "trained":
            trained_model = self._profile_manager.find_trained_xtts(profile_name)
            if not trained_model:
                raise FileNotFoundError("Nie znaleziono kompletnego wytrenowanego modelu XTTS dla tego profilu.")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        safe_style = (style or "natural").lower()
        engine_tag = {"xtts":"xtts", "f5":"f5", "qwen":"qwen"}[engine_id]
        mode_tag = actual_mode if engine_id == "xtts" else engine_tag
        raw = OUTPUT_DIR / f"speech_{profile_name}_{stamp}_{mode_tag}_{safe_style}.wav"
        if engine_id == "xtts":
            self._engine.clone_and_speak(
                text=text, speaker_wav_path=profile.wav_path, output_path=str(raw), language=language,
                trained_model=trained_model, style=safe_style, speed=float(speed or 1.0),
            )
            self._services["xtts"].update(state="ready", message=("Wytrenowany model profilu" if trained_model else "Bazowy XTTS v2"))
        else:
            self._external_engines.synthesize(engine_id, text, profile.wav_path, str(raw), language, float(speed or 1.0))
        final = raw
        if use_rvc:
            if self._rvc_engine is None:
                self._services["rvc"].update(state="loading", message="Ładowanie RVC…")
                from voice_engine.rvc_engine import get_rvc_engine
                self._rvc_engine = get_rvc_engine()
            rvc = OUTPUT_DIR / f"speech_{profile_name}_{stamp}_{mode_tag}_{safe_style}_rvc.wav"
            self._rvc_engine.load_model(profile.rvc_model_path, profile.rvc_index_path)
            self._rvc_engine.convert(str(raw), str(rvc))
            self._services["rvc"].update(state="ready", message="Gotowy")
            final = rvc
        self._last_generated = str(final)
        history = self._add_synthesis_history(
            path=final, text=text.strip(), profile_name=profile_name, language=language, style=safe_style,
            speed=float(speed or 1.0), model_mode=(actual_mode if engine_id == "xtts" else engine_id), use_rvc=use_rvc, ab_group=ab_group, engine=engine_id,
        )
        self._notify("Synteza zakończona", f"Gotowy plik: {final.name}", "success")
        return {"ok": True, "path": str(final), "name": final.name, "item": history, "model_mode": (actual_mode if engine_id == "xtts" else engine_id), "engine": engine_id}

    def synthesize_ab(self, text: str, profile_name: str, language: str = "pl", style: str = "natural", speed: float = 1.0,
                      engine_a: str = "xtts_base", engine_b: str = "xtts_trained") -> dict:
        group = datetime.now().strftime("ab_%Y%m%d_%H%M%S_%f")
        def run(spec: str) -> dict:
            spec = (spec or "xtts_base").lower()
            if spec == "xtts_base":
                return self.synthesize(text, profile_name, language, False, style, speed, "base", group, "xtts")
            if spec == "xtts_trained":
                if not self._profile_manager.find_trained_xtts(profile_name):
                    raise FileNotFoundError("Profil nie ma kompletnego wytrenowanego XTTS.")
                return self.synthesize(text, profile_name, language, False, style, speed, "trained", group, "xtts")
            if spec in {"f5", "qwen"}:
                return self.synthesize(text, profile_name, language, False, style, speed, "active", group, spec)
            raise ValueError(f"Nieznany wariant A/B: {spec}")
        a = run(engine_a)
        b = run(engine_b)
        return {"ok": True, "group": group, "base": a, "trained": b, "engine_a": engine_a, "engine_b": engine_b}

    def play_last_generated(self) -> dict:
        if not self._last_generated or not os.path.isfile(self._last_generated):
            raise ValueError("Brak wygenerowanego pliku.")
        from recorder.recorder import play_wav
        threading.Thread(target=lambda: play_wav(self._last_generated), daemon=True).start()
        return {"ok": True}



    def voice_engine_status(self) -> dict:
        return self._external_engines.status()

    def install_voice_engine(self, engine_id: str) -> dict:
        return self._external_engines.install_async(engine_id)

    def voice_engine_install_status(self, engine_id: str) -> dict:
        return self._external_engines.install_status(engine_id)

    def rvc_status(self, profile_name: str = "") -> dict:
        available = False
        error = ""
        try:
            from voice_engine.rvc_engine import get_rvc_engine
            available = get_rvc_engine().is_available()
        except Exception as exc:
            error = str(exc)
        profile = self._profile_manager.get_profile(profile_name) if profile_name else None
        return {
            "ok": True, "available": available, "error": error,
            "profile": profile_name,
            "has_model": bool(profile and profile.has_rvc_model),
            "model_path": getattr(profile, "rvc_model_path", None) if profile else None,
            "index_path": getattr(profile, "rvc_index_path", None) if profile else None,
            "install": dict(self._rvc_install_status),
        }

    def install_rvc_runtime(self) -> dict:
        if self._rvc_install_status.get("state") in {"starting", "installing"}:
            return dict(self._rvc_install_status)
        self._rvc_install_status = {"state": "starting", "progress": 3, "message": "Przygotowanie instalacji RVC…"}
        threading.Thread(target=self._install_rvc_worker, daemon=True, name="RVCInstall").start()
        return dict(self._rvc_install_status)

    def _install_rvc_worker(self) -> None:
        try:
            self._rvc_install_status = {"state": "installing", "progress": 15, "message": "Instalacja rvc-python…"}
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            p = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(BASE_DIR / "requirements-rvc.txt")],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags)
            if p.returncode != 0:
                tail = "\n".join((p.stdout or "").splitlines()[-25:])
                raise RuntimeError(tail or f"pip exit {p.returncode}")
            self._rvc_engine = None
            self._rvc_install_status = {"state": "completed", "progress": 100, "message": "RVC zainstalowane. Uruchom ponownie SoundCore, jeśli status nie odświeży się automatycznie."}
        except Exception as exc:
            self._rvc_install_status = {"state": "error", "progress": 0, "message": str(exc)}

    def rvc_install_status(self) -> dict:
        return dict(self._rvc_install_status)

    def select_rvc_model(self, profile_name: str) -> dict:
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Wybierz profil.")
        win = webview.active_window()
        if win is None:
            raise RuntimeError("Okno SoundCore nie jest gotowe.")
        dialog = getattr(webview.FileDialog, "OPEN", None) or getattr(webview.FileDialog, "LOAD")
        selected = win.create_file_dialog(dialog, allow_multiple=False, file_types=("Model RVC (*.pth)", "Wszystkie pliki (*.*)"))
        if not selected:
            return {"ok": False, "cancelled": True}
        path = selected[0]
        updated = self._profile_manager.set_rvc_model(profile_name, path, profile.rvc_index_path)
        self._profiles_cache = self._profiles_payload_full()
        return {"ok": True, "profile": profile_name, "model_path": updated.rvc_model_path, "index_path": updated.rvc_index_path, "profiles": self._profiles_cache}

    def select_rvc_index(self, profile_name: str) -> dict:
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Wybierz profil.")
        if not profile.rvc_model_path:
            raise ValueError("Najpierw wybierz model RVC .pth.")
        win = webview.active_window()
        dialog = getattr(webview.FileDialog, "OPEN", None) or getattr(webview.FileDialog, "LOAD")
        selected = win.create_file_dialog(dialog, allow_multiple=False, file_types=("Indeks RVC (*.index)", "Wszystkie pliki (*.*)"))
        if not selected:
            return {"ok": False, "cancelled": True}
        updated = self._profile_manager.set_rvc_model(profile_name, profile.rvc_model_path, selected[0])
        self._profiles_cache = self._profiles_payload_full()
        return {"ok": True, "profile": profile_name, "model_path": updated.rvc_model_path, "index_path": updated.rvc_index_path, "profiles": self._profiles_cache}

    def clear_rvc_model(self, profile_name: str) -> dict:
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Wybierz profil.")
        profile.rvc_model_path = None
        profile.rvc_index_path = None
        meta = Path(profile.folder) / "metadata.json"
        meta.write_text(json.dumps(profile.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
        self._profiles_cache = self._profiles_payload_full()
        return {"ok": True, "profiles": self._profiles_cache}

    def profile_model_info(self, profile_name: str) -> dict:
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        trained = self._profile_manager.find_trained_xtts(profile_name)
        return {
            "ok": True, "profile": profile_name, "mode": getattr(profile, "xtts_mode", "base"),
            "has_trained_model": bool(trained), "trained_model": trained,
            "active_checkpoint": getattr(profile, "xtts_checkpoint_path", None),
        }

    def activate_trained_xtts(self, profile_name: str) -> dict:
        profile = self._profile_manager.set_xtts_mode(profile_name, "trained")
        self._profiles_cache = self._profiles_payload_full()
        # force lazy re-load on the next synthesis; the engine switches model keys safely.
        self._notify("Model profilu", f"Wytrenowany XTTS jest aktywny dla profilu {profile_name}.", "success")
        return {"ok": True, "profile": profile_name, "mode": profile.xtts_mode, "profiles": self._profiles_cache, "model": self._profile_manager.find_trained_xtts(profile_name)}

    def use_base_xtts(self, profile_name: str) -> dict:
        profile = self._profile_manager.set_xtts_mode(profile_name, "base")
        self._profiles_cache = self._profiles_payload_full()
        self._notify("Model profilu", f"Profil {profile_name} używa bazowego XTTS v2.", "info")
        return {"ok": True, "profile": profile_name, "mode": profile.xtts_mode, "profiles": self._profiles_cache}


    def list_profile_recordings(self, profile_name: str) -> dict:
        from training.dataset import get_stats, list_samples
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        rows = [{
            "id": "reference",
            "kind": "reference",
            "name": "Próbka referencyjna",
            "text": "",
            "duration_seconds": profile.duration_seconds,
            "source_name": "Nagranie profilu",
            "wav_path": profile.wav_path,
            "deletable": False,
        }]
        for sample in list_samples(profile.folder):
            rows.append({
                **sample,
                "kind": "dataset",
                "name": sample["id"],
                "deletable": True,
            })
        return {"ok": True, "profile": profile_name, "recordings": rows, "stats": get_stats(profile.folder).to_dict()}

    def play_profile_recording(self, profile_name: str, recording_id: str) -> dict:
        from training.dataset import list_samples
        from recorder.recorder import play_wav
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        if recording_id == "reference":
            path = profile.wav_path
        else:
            item = next((x for x in list_samples(profile.folder) if x["id"] == recording_id), None)
            if item is None:
                raise ValueError("Nie znaleziono nagrania.")
            path = item["wav_path"]
        threading.Thread(target=lambda: play_wav(path), daemon=True).start()
        return {"ok": True}

    def delete_profile_recording(self, profile_name: str, recording_id: str) -> dict:
        from training.dataset import delete_sample
        if recording_id == "reference":
            raise ValueError("Próbki referencyjnej nie można usunąć. Nagraj nową referencję dla profilu.")
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        if not delete_sample(profile.folder, recording_id):
            raise ValueError("Nie znaleziono nagrania.")
        self._profiles_cache = self._profiles_payload_full()
        self._notify("Próbka usunięta", f"Usunięto {recording_id} z profilu {profile_name}.", "info")
        result = self.list_profile_recordings(profile_name)
        result["profiles"] = self._profiles_cache
        return result

    def update_profile_recording_text(self, profile_name: str, recording_id: str, text: str) -> dict:
        from training.dataset import update_sample_text
        if recording_id == "reference":
            raise ValueError("Referencja profilu nie używa transkrypcji datasetu.")
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        update_sample_text(profile.folder, recording_id, text)
        self._profiles_cache = self._profiles_payload_full()
        result = self.list_profile_recordings(profile_name)
        result["profiles"] = self._profiles_cache
        return result

    def begin_media_import(self, profile_name: str) -> dict:
        from training.media_library import begin_import
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        win = webview.active_window()
        if win is None:
            raise RuntimeError("Okno SoundCore nie jest gotowe.")
        dialog_open = getattr(webview.FileDialog, "OPEN", None) or getattr(webview.FileDialog, "LOAD")
        selected = win.create_file_dialog(
            dialog_open,
            allow_multiple=False,
            file_types=(
                "Audio i wideo (*.wav;*.mp3;*.flac;*.m4a;*.aac;*.ogg;*.wma;*.mp4;*.mov;*.mkv;*.avi;*.webm;*.m4v)",
                "Wszystkie pliki (*.*)",
            ),
        )
        if not selected:
            return {"ok": False, "cancelled": True}
        data = begin_import(selected[0])
        data["ok"] = True
        data["profile"] = profile_name
        return data

    def preview_media_clip(self, session_id: str, start: float, end: float) -> dict:
        from training.media_library import make_preview
        from recorder.recorder import play_wav
        path = make_preview(session_id, start, end)
        threading.Thread(target=lambda: play_wav(path), daemon=True).start()
        return {"ok": True}

    def save_media_clip(self, profile_name: str, session_id: str, start: float, end: float, text: str = "") -> dict:
        from training.media_library import save_clip
        from training.dataset import get_stats
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        sample = save_clip(profile.folder, session_id, start, end, text)
        self._profiles_cache = self._profiles_payload_full()
        self._notify("Zaimportowano próbkę", f"{sample['id']} · {sample['duration_seconds']} s z pliku {sample['source_name']}", "success")
        return {"ok": True, "sample": sample, "recordings": self.list_profile_recordings(profile_name)["recordings"], "stats": get_stats(profile.folder).to_dict(), "profiles": self._profiles_cache}

    def close_media_import(self, session_id: str) -> dict:
        from training.media_library import close_session
        close_session(session_id)
        return {"ok": True}

    def cuda_repair_status(self) -> dict:
        hw = self.refresh_hardware()
        data = self._cuda_repair.status()
        data["torch_cuda_available"] = bool(hw.get("torch_cuda_available"))
        data["torch_cuda_version"] = hw.get("torch_cuda_version")
        return data

    def install_cuda_runtime(self) -> dict:
        hw = self.refresh_hardware()
        if not hw.get("gpu_detected"):
            raise RuntimeError("Nie wykryto karty NVIDIA. Instalacja PyTorch CUDA nie ma sensu.")
        if hw.get("torch_cuda_available"):
            return {"state": "completed", "progress": 100, "message": "CUDA jest już aktywna.", "restart_required": False}
        status = self._cuda_repair.start()
        self._notify("Naprawa CUDA", "Rozpoczęto instalację oficjalnego PyTorch 2.5.1 z CUDA 12.4.", "info")
        return status


    def open_data_folder(self) -> dict:
        path = str(BASE_DIR)
        if os.name == "nt":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])
        return {"ok": True, "path": path}

    def get_user_menu_info(self) -> dict:
        return {
            "name": getpass.getuser(),
            "role": "Użytkownik lokalny",
            "version": APP_VERSION,
            "base_dir": str(BASE_DIR),
        }

    def restart_app(self) -> dict:
        subprocess.Popen([sys.executable, str(BASE_DIR / "main.py")], cwd=str(BASE_DIR), creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0))
        threading.Timer(0.6, lambda: os._exit(0)).start()
        return {"ok": True}

    def start_training(self, profile_name: str, language: str, epochs: int, device: str, batch_size: int = 2) -> dict:
        from training.dataset import get_stats, list_samples
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        stats = get_stats(profile.folder)
        transcribed = [x for x in list_samples(profile.folder) if (x.get("text") or "").strip()]
        if len(transcribed) < 3:
            raise ValueError("Dodaj co najmniej 3 próbki z transkrypcją. Próbki audio bez tekstu zostają w bibliotece, ale XTTS nie może na nich trenować.")
        requested = (device or "auto").lower()
        if requested == "auto":
            requested = "gpu" if self._hardware.get("torch_cuda_available") else "cpu"
        status = self._training.start(profile.folder, profile.name, language or "pl", int(epochs), requested, int(batch_size))
        self._notify("Trening uruchomiony", f"Profil {profile_name}, urządzenie: {requested.upper()}.", "success")
        return status

    def training_status(self) -> dict:
        return self._training.status()

    def stop_training(self) -> dict:
        data = self._training.stop()
        self._notify("Trening zatrzymany", "Proces treningowy został zatrzymany.", "warning")
        return data

    def check_updates(self) -> dict:
        try:
            result = check_for_update(APP_VERSION, CHANNEL_URL)
            self._update_cache = result
            if result["update_available"]:
                self._notify("Dostępna aktualizacja", f"SoundCore {result['latest_version']} jest gotowy do pobrania.", "success")
            else:
                self._notify("Aktualizacje", "Masz najnowszą wersję SoundCore.", "info")
            return result
        except Exception as exc:
            self._notify("Błąd aktualizacji", str(exc), "error")
            return {"ok": False, "error": str(exc), "current_version": APP_VERSION}

    def update_install_status(self) -> dict:
        return dict(self._update_install_status)

    def _install_update_worker(self) -> None:
        try:
            self._update_install_status = {"state": "downloading", "progress": 8, "message": "Pobieranie paczki aktualizacji…"}

            def on_progress(done: int, total: int, frac: float) -> None:
                progress = 8 + int(max(0.0, min(1.0, frac)) * 62) if total else 25
                if total:
                    mb_done = done / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    message = f"Pobieranie aktualizacji… {mb_done:.1f} / {mb_total:.1f} MB"
                else:
                    message = f"Pobieranie aktualizacji… {done / (1024 * 1024):.1f} MB"
                self._update_install_status = {"state": "downloading", "progress": progress, "message": message}

            payload = download_update(
                self._update_cache["channel"],
                on_progress=on_progress,
                cancel_event=self._update_cancel,
            )
            if self._update_cancel.is_set():
                raise UpdateCancelled("Aktualizacja została przerwana przez użytkownika.")
            self._update_install_status = {"state": "verified", "progress": 78, "message": "SHA256 poprawne. Przygotowanie aktualizacji…"}
            self._notify("Aktualizacja pobrana", "SHA256 poprawne. Przygotowuję restart SoundCore.", "success")
            launch_apply(payload["payload"], str(BASE_DIR))
            self._update_install_status = {"state": "restarting", "progress": 100, "message": "Aktualizacja gotowa. Restart SoundCore…"}
            threading.Timer(1.2, lambda: os._exit(0)).start()
        except UpdateCancelled as exc:
            self._update_install_status = {"state": "cancelled", "progress": 0, "message": str(exc)}
            self._notify("Aktualizacja przerwana", str(exc), "warning")
        except Exception as exc:
            self._update_install_status = {"state": "error", "progress": 0, "message": str(exc)}
            self._notify("Błąd aktualizacji", str(exc), "error")

    def install_update(self) -> dict:
        if self._update_install_status.get("state") in {"downloading", "verified", "restarting"}:
            return self.update_install_status()
        if not self._update_cache or not self._update_cache.get("update_available"):
            self._update_cache = self.check_updates()
        if not self._update_cache.get("update_available"):
            return {"ok": True, "state": "idle", "progress": 0, "message": "Brak aktualizacji."}
        self._update_cancel.clear()
        self._update_install_status = {"state": "starting", "progress": 5, "message": "Uruchamianie aktualizacji w tle…"}
        threading.Thread(target=self._install_update_worker, name="SoundCoreUpdater", daemon=True).start()
        return {"ok": True, **self._update_install_status}

    def cancel_update(self) -> dict:
        state = self._update_install_status.get("state")
        if state in {"starting", "downloading"}:
            self._update_cancel.set()
            self._update_install_status = {"state": "cancelling", "progress": self._update_install_status.get("progress", 0), "message": "Przerywanie aktualizacji…"}
        return self.update_install_status()

    # ------------------------------- Song Studio -------------------------------
    def song_projects(self) -> dict:
        return {"ok": True, "projects": self._songs.list_projects()}

    def new_song_project(self, title: str = "Nowa piosenka") -> dict:
        project = self._songs.new_project(title)
        return {"ok": True, "project": project, "projects": self._songs.list_projects()}

    def get_song_project(self, project_id: str) -> dict:
        return {"ok": True, "project": self._songs.get_project(project_id)}

    def save_song_project(self, project: dict) -> dict:
        return self._songs.save_project(project)

    def delete_song_project(self, project_id: str) -> dict:
        return self._songs.delete_project(project_id)

    def song_lrc_preview(self, project: dict) -> dict:
        return self._songs.lrc_preview(project)

    def music_engine_status(self) -> dict:
        return self._songs.engine_status()

    def install_music_engine(self) -> dict:
        return self._songs.install_engine()

    def music_engine_install_status(self) -> dict:
        return self._songs.install_status()

    def cancel_music_engine_install(self) -> dict:
        return self._songs.cancel_install()

    def select_song_audio_file(self) -> dict:
        win = webview.active_window()
        if win is None:
            raise RuntimeError("Okno SoundCore nie jest gotowe.")
        dialog_open = getattr(webview.FileDialog, "OPEN", None) or getattr(webview.FileDialog, "LOAD")
        selected = win.create_file_dialog(dialog_open, allow_multiple=False, file_types=("Audio (*.wav;*.mp3;*.flac;*.m4a;*.ogg)", "Wszystkie pliki (*.*)"))
        if not selected:
            return {"ok": False, "cancelled": True}
        path = selected[0] if isinstance(selected, (list, tuple)) else selected
        return {"ok": True, "path": str(path)}

    def start_song_generation(self, project: dict) -> dict:
        return self._songs.start_generation(project)

    def song_generation_status(self) -> dict:
        return self._songs.generation_status()

    def cancel_song_generation(self) -> dict:
        return self._songs.cancel_generation()

    def play_song_render(self, path: str) -> dict:
        target = Path(path)
        if not target.is_file() or self._songs.projects_dir not in target.resolve().parents:
            raise ValueError("Nieprawidłowy plik renderu.")
        from recorder.recorder import play_wav
        threading.Thread(target=lambda: play_wav(str(target)), daemon=True).start()
        return {"ok": True}

    def export_song_render(self, path: str) -> dict:
        source = Path(path)
        if not source.is_file() or self._songs.projects_dir not in source.resolve().parents:
            raise ValueError("Nieprawidłowy plik renderu.")
        win = webview.active_window()
        if win is None:
            raise RuntimeError("Okno SoundCore nie jest gotowe.")
        dialog_save = getattr(webview.FileDialog, "SAVE", None)
        if dialog_save is None:
            raise RuntimeError("Ta wersja pywebview nie obsługuje dialogu zapisu.")
        chosen = win.create_file_dialog(dialog_save, save_filename=source.name, file_types=("WAV (*.wav)",))
        if not chosen:
            return {"ok": False, "cancelled": True}
        dest = Path(chosen if isinstance(chosen, str) else chosen[0])
        shutil.copy2(source, dest)
        return {"ok": True, "path": str(dest)}

    def cancel_recording(self) -> dict:
        from recorder.recorder import cancel_recording
        cancel_recording()
        return {"ok": True, "message": "Przerwano nagrywanie."}


def run() -> None:
    prepare_windows_process()
    api = SoundCoreApi()
    window = webview.create_window(
        "SoundCore",
        str(WEBUI_DIR / "index.html"),
        width=1540,
        height=930,
        min_size=(1180, 720),
        background_color="#F6F8FC",
        maximized=True,
    )
    # Do not pass a Python object as js_api. pywebview reflects object attributes
    # and on Windows this can walk into native WinForms/WebView2 COM objects.
    # Expose an explicit allow-list of plain bound methods only.
    window.expose(
        api.get_state,
        api.startup_status,
        api.start_background_services,
        api.refresh_hardware,
        api.get_devices,
        api.get_reading_prompt,
        api.notifications_state,
        api.mark_notifications_read,
        api.record_profile,
        api.record_training_sample,
        api.play_profile,
        api.delete_profile,
        api.synthesize,
        api.synthesize_ab,
        api.voice_engine_status,
        api.install_voice_engine,
        api.voice_engine_install_status,
        api.list_synthesis_history,
        api.play_synthesis,
        api.delete_synthesis,
        api.export_synthesis,
        api.play_last_generated,
        api.profile_model_info,
        api.activate_trained_xtts,
        api.use_base_xtts,
        api.rvc_status,
        api.install_rvc_runtime,
        api.rvc_install_status,
        api.select_rvc_model,
        api.select_rvc_index,
        api.clear_rvc_model,
        api.list_profile_recordings,
        api.play_profile_recording,
        api.delete_profile_recording,
        api.update_profile_recording_text,
        api.begin_media_import,
        api.preview_media_clip,
        api.save_media_clip,
        api.close_media_import,
        api.cuda_repair_status,
        api.install_cuda_runtime,
        api.open_data_folder,
        api.get_user_menu_info,
        api.restart_app,
        api.start_training,
        api.training_status,
        api.stop_training,
        api.check_updates,
        api.install_update,
        api.update_install_status,
        api.cancel_update,
        api.song_projects,
        api.new_song_project,
        api.get_song_project,
        api.save_song_project,
        api.delete_song_project,
        api.song_lrc_preview,
        api.music_engine_status,
        api.install_music_engine,
        api.music_engine_install_status,
        api.cancel_music_engine_install,
        api.select_song_audio_file,
        api.start_song_generation,
        api.song_generation_status,
        api.cancel_song_generation,
        api.play_song_render,
        api.export_song_render,
        api.cancel_recording,
    )
    setup_windows_shell_async(BASE_DIR, APP_ICON)
    webview.start(debug=False)


if __name__ == "__main__":
    run()
