from __future__ import annotations

import json
import os
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
        self.log_path: Optional[Path] = None
        self._log_handle = None

    def _close_log(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.flush(); self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None

    def start(self, profile_folder: str, profile_name: str, language: str, epochs: int, device: str, batch_size: int = 2) -> dict:
        if self.process and self.process.poll() is None:
            raise RuntimeError("Trening już trwa.")
        self._close_log()
        self.log_path = Path(profile_folder) / "training.log"
        job = {
            "profile_folder": profile_folder, "profile_name": profile_name, "language": language,
            "epochs": int(epochs), "device": device, "batch_size": int(batch_size),
            "status_path": str(self.status_path), "log_path": str(self.log_path),
        }
        self.config_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        self.status_path.write_text(json.dumps({"state":"starting","progress":0,"message":"Uruchamianie treningu…","events":[],"loss_history":[],"log_path":str(self.log_path)}, ensure_ascii=False), encoding="utf-8")
        worker = Path(__file__).with_name("worker.py")
        env = os.environ.copy(); env["PYTHONUNBUFFERED"] = "1"
        if device.lower() == "cpu": env["CUDA_VISIBLE_DEVICES"] = ""
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        self._log_handle = self.log_path.open("w", encoding="utf-8", buffering=1)
        self.process = subprocess.Popen([sys.executable, str(worker), str(self.config_path)], env=env, creationflags=creationflags, stdout=self._log_handle, stderr=subprocess.STDOUT, text=True)
        return self.status()

    def stop(self) -> dict:
        if self.process and self.process.poll() is None:
            try: self.process.terminate()
            except Exception: pass
        data = {"state":"stopped","progress":0,"message":"Trening zatrzymany przez użytkownika."}
        self.status_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return self.status()

    def _tail_log(self, max_lines: int = 120) -> list[str]:
        if not self.log_path or not self.log_path.exists(): return []
        try:
            return self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
        except Exception:
            return []

    def status(self) -> dict:
        if self.status_path.exists():
            try: data = json.loads(self.status_path.read_text(encoding="utf-8"))
            except Exception: data = {"state":"unknown","progress":0}
        else:
            data = {"state":"idle","progress":0,"message":"Brak aktywnego treningu."}
        if self.process is not None:
            data["pid"] = self.process.pid
            running = self.process.poll() is None
            data["running"] = running
            if not running: self._close_log()
        else:
            data["running"] = False
        data["log_tail"] = self._tail_log()
        if self.log_path: data["log_path"] = str(self.log_path)
        return data
