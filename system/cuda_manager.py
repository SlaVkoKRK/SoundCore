from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

# TTS 0.22 / current SoundCore stack requires torch < 2.6.
# PyTorch publishes official CUDA 12.4 wheels for 2.5.1.
TORCH_VERSION = "2.5.1"
TORCHAUDIO_VERSION = "2.5.1"
TORCHVISION_VERSION = "0.20.1"
CUDA_INDEX = "https://download.pytorch.org/whl/cu124"


class CudaRepairManager:
    def __init__(self, runtime_dir: str | Path) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.status_path = self.runtime_dir / "cuda_repair.json"
        self.log_path = self.runtime_dir / "cuda_repair.log"
        self.process: subprocess.Popen | None = None
        if not self.status_path.exists():
            self._write_status({"state": "idle", "progress": 0, "message": "CUDA repair nie jest uruchomiony."})

    def _write_status(self, data: dict) -> None:
        tmp = self.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.status_path)

    def status(self) -> dict:
        try:
            data = json.loads(self.status_path.read_text(encoding="utf-8"))
        except Exception:
            data = {"state": "unknown", "progress": 0, "message": "Brak statusu instalacji CUDA."}
        if self.process is not None:
            data["running"] = self.process.poll() is None
            data["pid"] = self.process.pid
        else:
            data["running"] = False
        data["log_path"] = str(self.log_path)
        return data


    def reconcile(self, torch_cuda_available: bool) -> dict:
        """Clear stale restart/install state once CUDA is verifiably active."""
        data = self.status()
        if torch_cuda_available and data.get("state") in {"starting", "installing", "completed", "error", "unknown"}:
            data = {
                "state": "verified",
                "progress": 100,
                "message": "PyTorch CUDA jest aktywna i gotowa do użycia.",
                "restart_required": False,
            }
            self._write_status(data)
        return data

    def start(self) -> dict:
        if self.process and self.process.poll() is None:
            return self.status()
        self._write_status({
            "state": "starting",
            "progress": 3,
            "message": "Przygotowanie instalacji PyTorch z CUDA 12.4…",
        })
        helper = self.runtime_dir / "cuda_repair_worker.py"
        helper.write_text(self._worker_source(), encoding="utf-8")
        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW
        self.process = subprocess.Popen(
            [sys.executable, str(helper), str(self.status_path), str(self.log_path)],
            cwd=str(self.runtime_dir),
            creationflags=creationflags,
        )
        return self.status()

    @staticmethod
    def _worker_source() -> str:
        return f'''from __future__ import annotations
import json, subprocess, sys, traceback
from pathlib import Path

status_path=Path(sys.argv[1]); log_path=Path(sys.argv[2])

def write(state, progress, message, **extra):
    data={{"state":state,"progress":progress,"message":message,**extra}}
    tmp=status_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(status_path)

def run(cmd, label, progress):
    write("installing", progress, label)
    with log_path.open("a",encoding="utf-8") as log:
        log.write("\\n$ "+" ".join(cmd)+"\\n")
        p=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Polecenie zakończyło się kodem {{p.returncode}}. Szczegóły: {{log_path}}")

try:
    log_path.write_text("SoundCore CUDA repair\\n",encoding="utf-8")
    run([sys.executable,"-m","pip","install","--upgrade","pip"],"Aktualizacja pip…",10)
    run([
        sys.executable,"-m","pip","install","--upgrade","--force-reinstall","--no-deps",
        "torch=={TORCH_VERSION}","torchvision=={TORCHVISION_VERSION}","torchaudio=={TORCHAUDIO_VERSION}",
        "--index-url","{CUDA_INDEX}"
    ],"Pobieranie i instalacja PyTorch {TORCH_VERSION} + CUDA 12.4…",35)
    run([
        sys.executable,"-m","pip","install","--force-reinstall","--no-deps",
        "numpy==1.22.0","scipy==1.10.1"
    ],"Przywracanie zgodnych wersji NumPy i SciPy…",82)
    write("completed",100,"PyTorch CUDA zainstalowany. Uruchom ponownie SoundCore, aby aktywować GPU.",restart_required=True)
except Exception as exc:
    with log_path.open("a",encoding="utf-8") as log:
        log.write("\\nERROR\\n"+traceback.format_exc())
    write("error",0,str(exc),restart_required=False)
'''
