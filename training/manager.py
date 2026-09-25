from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional


class TrainingManager:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)
        self.run_dir = self.base_dir / "training_runtime"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.process: Optional[subprocess.Popen] = None
        self.status_path = self.run_dir / "status.json"
        self.config_path = self.run_dir / "job.json"

    def start(self, profile_folder: str, profile_name: str, language: str, epochs: int, device: str, batch_size: int = 2) -> dict:
        if self.process and self.process.poll() is None:
            raise RuntimeError("Trening już trwa.")
        job = {
            "profile_folder": profile_folder,
            "profile_name": profile_name,
            "language": language,
            "epochs": int(epochs),
            "device": device,
            "batch_size": int(batch_size),
            "status_path": str(self.status_path),
        }
        self.config_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        self.status_path.write_text(json.dumps({"state": "starting", "progress": 0, "message": "Uruchamianie treningu…"}, ensure_ascii=False), encoding="utf-8")
        worker = Path(__file__).with_name("worker.py")
        env = os.environ.copy()
        if device.lower() == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = ""
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        self.process = subprocess.Popen([sys.executable, str(worker), str(self.config_path)], env=env, creationflags=creationflags)
        return self.status()

    def stop(self) -> dict:
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass
        data = {"state": "stopped", "progress": 0, "message": "Trening zatrzymany przez użytkownika."}
        self.status_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def status(self) -> dict:
        if self.status_path.exists():
            try:
                data = json.loads(self.status_path.read_text(encoding="utf-8"))
            except Exception:
                data = {"state": "unknown", "progress": 0}
        else:
            data = {"state": "idle", "progress": 0, "message": "Brak aktywnego treningu."}
        if self.process is not None:
            data["pid"] = self.process.pid
            data["running"] = self.process.poll() is None
        else:
            data["running"] = False
        return data
