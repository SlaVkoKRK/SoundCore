from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class ComputeDevice:
    code: str
    label: str


def available_devices() -> list[ComputeDevice]:
    result = [ComputeDevice("cpu", "CPU")]
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            result.insert(0, ComputeDevice("cuda", f"GPU / CUDA — {name}"))
    except Exception:
        pass
    return result


class TrainingProcess:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self, profile_folder: str, device: str, epochs: int, on_line: Callable[[str], None], on_done: Callable[[int], None]):
        if self.running:
            raise RuntimeError("Trening już działa.")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = [sys.executable, "-u", "-m", "training.train_xtts", "--profile", profile_folder, "--device", device, "--epochs", str(epochs)]
        env = os.environ.copy()
        if device == "cpu":
            env["CUDA_VISIBLE_DEVICES"] = ""
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        self.process = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, env=env, creationflags=creationflags)

        import threading
        def reader():
            assert self.process and self.process.stdout
            for line in self.process.stdout:
                on_line(line.rstrip())
            code = self.process.wait()
            on_done(code)
        threading.Thread(target=reader, daemon=True).start()

    def stop(self):
        if self.running:
            self.process.terminate()
