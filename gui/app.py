from __future__ import annotations

import getpass
import json
import os
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

from preprocessing.audio_utils import preprocess_pipeline
from recorder.recorder import DEFAULT_SAMPLERATE, list_input_devices, play_wav, record_audio
from storage.profile_manager import ProfileManager
from system.hardware import detect_hardware
from system.cuda_manager import CudaRepairManager
from system.windows_integration import prepare_windows_process, setup_windows_shell_async
from training.dataset import add_sample, get_stats, list_samples, delete_sample, update_sample_text
from training.media_library import begin_import, make_preview, save_clip, close_session
from training.text_bank import build_prompt, remember_prompt
from training.manager import TrainingManager
from updater.update_manager import check_for_update, download_update, launch_apply
from voice_engine.rvc_engine import get_rvc_engine
from voice_engine.tts_engine import get_engine

BASE_DIR = Path(__file__).resolve().parents[1]
WEBUI_DIR = BASE_DIR / "webui"
OUTPUT_DIR = BASE_DIR / "output"
APP_ICON = BASE_DIR / "gui" / "assets" / "soundcore.ico"
APP_VERSION = (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip() if (BASE_DIR / "VERSION").exists() else "0.3.6"
CHANNEL_URL = "https://raw.githubusercontent.com/SlaVkoKRK/SoundCore/main/dist/channel.json"
OUTPUT_DIR.mkdir(exist_ok=True)


class SoundCoreApi:
    def __init__(self) -> None:
        self._profile_manager = ProfileManager()
        self._engine = get_engine()
        self._rvc_engine = get_rvc_engine()
        self._training = TrainingManager(str(BASE_DIR))
        self._cuda_repair = CudaRepairManager(BASE_DIR / "training_runtime")
        self._hardware = detect_hardware()
        self._cuda_repair.reconcile(self._hardware.torch_cuda_available)
        self._notifications: list[dict] = []
        self._last_generated: str | None = None
        self._update_cache: dict | None = None
        self._notify(
            "Sprzęt wykryty",
            self._hardware.note,
            "success" if self._hardware.torch_cuda_available else ("warning" if self._hardware.gpu_detected else "info"),
        )

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
        profiles = self._profiles_payload()
        return {
            "version": APP_VERSION,
            "user": {"name": getpass.getuser(), "role": "Użytkownik"},
            "hardware": self._hardware.to_dict(),
            "profiles": profiles,
            "devices": self.get_devices(),
            "notifications": self._notifications,
            "training": self._training.status(),
            "last_generated": self._last_generated,
            "cuda_repair": self._cuda_repair.status(),
        }

    def refresh_hardware(self) -> dict:
        self._hardware = detect_hardware()
        self._cuda_repair.reconcile(self._hardware.torch_cuda_available)
        self._notify("Ponowne wykrywanie GPU", self._hardware.note, "success" if self._hardware.torch_cuda_available else "warning")
        return self._hardware.to_dict()

    def get_reading_prompt(self, duration: int, purpose: str = "training", nonce: int = 0, profile_name: str = "") -> dict:
        profile_folder = None
        if profile_name:
            profile = self._profile_manager.get_profile(profile_name)
            if profile is not None:
                profile_folder = profile.folder
        return build_prompt(duration, purpose, nonce, profile_folder=profile_folder)

    def get_devices(self) -> list[dict]:
        result = []
        try:
            for d in list_input_devices():
                result.append({"index": d.index, "name": d.name, "channels": getattr(d, "max_input_channels", None)})
        except Exception as exc:
            self._notify("Mikrofon", f"Nie udało się pobrać listy urządzeń: {exc}", "error")
        return result

    def _profiles_payload(self) -> list[dict]:
        rows = []
        for p in self._profile_manager.list_profiles():
            stats = get_stats(p.folder)
            rows.append({
                "name": p.name,
                "created_at": p.created_at,
                "duration_seconds": p.duration_seconds,
                "has_rvc_model": p.has_rvc_model,
                "dataset": stats.to_dict(),
            })
        return rows

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
        duration = max(3, min(int(duration), 30))
        audio = record_audio(duration=duration, device=int(device_index))
        cleaned = preprocess_pipeline(audio, DEFAULT_SAMPLERATE)
        sample = add_sample(profile.folder, cleaned, DEFAULT_SAMPLERATE, text)
        remember_prompt(profile.folder, text, "training")
        stats = get_stats(profile.folder)
        self._notify("Próbka treningowa", f"Dodano próbkę {sample['id']} do profilu {profile_name}.", "success")
        return {"ok": True, "sample": sample, "dataset": stats.to_dict()}

    def play_profile(self, profile_name: str) -> dict:
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        threading.Thread(target=lambda: play_wav(profile.wav_path), daemon=True).start()
        return {"ok": True}

    def delete_profile(self, profile_name: str) -> dict:
        self._profile_manager.delete_profile(profile_name)
        self._notify("Profil usunięty", f"Usunięto profil '{profile_name}'.", "info")
        return {"ok": True, "profiles": self._profiles_payload()}

    def synthesize(self, text: str, profile_name: str, language: str = "pl", use_rvc: bool = False) -> dict:
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        if not text.strip():
            raise ValueError("Wpisz tekst do syntezy.")
        if use_rvc and not profile.has_rvc_model:
            raise ValueError("Profil nie ma podpiętego modelu RVC.")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        raw = OUTPUT_DIR / f"speech_{profile_name}_{stamp}_raw.wav"
        self._engine.clone_and_speak(text=text, speaker_wav_path=profile.wav_path, output_path=str(raw), language=language)
        final = raw
        if use_rvc:
            rvc = OUTPUT_DIR / f"speech_{profile_name}_{stamp}_rvc.wav"
            self._rvc_engine.load_model(profile.rvc_model_path, profile.rvc_index_path)
            self._rvc_engine.convert(str(raw), str(rvc))
            final = rvc
        self._last_generated = str(final)
        self._notify("Synteza zakończona", f"Gotowy plik: {final.name}", "success")
        return {"ok": True, "path": str(final), "name": final.name}

    def play_last_generated(self) -> dict:
        if not self._last_generated or not os.path.isfile(self._last_generated):
            raise ValueError("Brak wygenerowanego pliku.")
        threading.Thread(target=lambda: play_wav(self._last_generated), daemon=True).start()
        return {"ok": True}



    def list_profile_recordings(self, profile_name: str) -> dict:
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
        if recording_id == "reference":
            raise ValueError("Próbki referencyjnej nie można usunąć. Nagraj nową referencję dla profilu.")
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        if not delete_sample(profile.folder, recording_id):
            raise ValueError("Nie znaleziono nagrania.")
        self._notify("Próbka usunięta", f"Usunięto {recording_id} z profilu {profile_name}.", "info")
        return self.list_profile_recordings(profile_name)

    def update_profile_recording_text(self, profile_name: str, recording_id: str, text: str) -> dict:
        if recording_id == "reference":
            raise ValueError("Referencja profilu nie używa transkrypcji datasetu.")
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        update_sample_text(profile.folder, recording_id, text)
        return self.list_profile_recordings(profile_name)

    def begin_media_import(self, profile_name: str) -> dict:
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
        path = make_preview(session_id, start, end)
        threading.Thread(target=lambda: play_wav(path), daemon=True).start()
        return {"ok": True}

    def save_media_clip(self, profile_name: str, session_id: str, start: float, end: float, text: str = "") -> dict:
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        sample = save_clip(profile.folder, session_id, start, end, text)
        self._notify("Zaimportowano próbkę", f"{sample['id']} · {sample['duration_seconds']} s z pliku {sample['source_name']}", "success")
        return {"ok": True, "sample": sample, "recordings": self.list_profile_recordings(profile_name)["recordings"], "stats": get_stats(profile.folder).to_dict()}

    def close_media_import(self, session_id: str) -> dict:
        close_session(session_id)
        return {"ok": True}

    def cuda_repair_status(self) -> dict:
        self._hardware = detect_hardware()
        self._cuda_repair.reconcile(self._hardware.torch_cuda_available)
        data = self._cuda_repair.status()
        data["torch_cuda_available"] = bool(self._hardware.torch_cuda_available)
        data["torch_cuda_version"] = self._hardware.torch_cuda_version
        return data

    def install_cuda_runtime(self) -> dict:
        self._hardware = detect_hardware()
        if not self._hardware.gpu_detected:
            raise RuntimeError("Nie wykryto karty NVIDIA. Instalacja PyTorch CUDA nie ma sensu.")
        if self._hardware.torch_cuda_available:
            return {"state": "completed", "progress": 100, "message": "CUDA jest już aktywna.", "restart_required": False}
        status = self._cuda_repair.start()
        self._notify("Naprawa CUDA", "Rozpoczęto instalację oficjalnego PyTorch 2.5.1 z CUDA 12.4. SoundCore może działać w tle podczas pobierania.", "info")
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
        profile = self._profile_manager.get_profile(profile_name)
        if profile is None:
            raise ValueError("Nie znaleziono profilu.")
        stats = get_stats(profile.folder)
        transcribed = [x for x in list_samples(profile.folder) if (x.get("text") or "").strip()]
        if len(transcribed) < 3:
            raise ValueError("Dodaj co najmniej 3 próbki z transkrypcją. Próbki audio bez tekstu zostają w bibliotece, ale XTTS nie może na nich trenować.")
        requested = (device or "auto").lower()
        if requested == "auto":
            requested = "gpu" if self._hardware.torch_cuda_available else "cpu"
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

    def install_update(self) -> dict:
        if not self._update_cache or not self._update_cache.get("update_available"):
            self._update_cache = self.check_updates()
        if not self._update_cache.get("update_available"):
            return {"ok": True, "message": "Brak aktualizacji."}
        payload = download_update(self._update_cache["channel"])
        self._notify("Aktualizacja pobrana", "SHA256 poprawne. SoundCore uruchomi instalator i zrestartuje aplikację.", "success")
        launch_apply(payload["payload"], str(BASE_DIR))
        threading.Timer(0.8, lambda: os._exit(0)).start()
        return {"ok": True, "restarting": True}


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
        api.play_last_generated,
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
    )
    setup_windows_shell_async(BASE_DIR, APP_ICON)
    webview.start(debug=False)


if __name__ == "__main__":
    run()
