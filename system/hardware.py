from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, asdict


@dataclass
class HardwareInfo:
    cpu: str
    gpu_detected: bool
    gpu_name: str
    gpu_memory_mb: int | None
    nvidia_driver: str | None
    torch_cuda_available: bool
    torch_cuda_version: str | None
    torch_device_name: str | None
    recommended_device: str
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


def _cpu_name() -> str:
    name = platform.processor().strip()
    if name:
        return name
    return os.environ.get("PROCESSOR_IDENTIFIER", "CPU")


def _nvidia_smi() -> tuple[bool, str, int | None, str | None]:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return False, "", None, None
    try:
        cmd = [
            exe,
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
        if result.returncode != 0 or not result.stdout.strip():
            return False, "", None, None
        first = result.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in first.split(",")]
        name = parts[0] if parts else "NVIDIA GPU"
        memory = int(float(parts[1])) if len(parts) > 1 and parts[1] else None
        driver = parts[2] if len(parts) > 2 else None
        return True, name, memory, driver
    except Exception:
        return False, "", None, None


def detect_hardware() -> HardwareInfo:
    gpu_detected, gpu_name, gpu_memory, driver = _nvidia_smi()
    torch_cuda_available = False
    torch_cuda_version = None
    torch_device_name = None
    try:
        import torch

        torch_cuda_available = bool(torch.cuda.is_available())
        torch_cuda_version = getattr(torch.version, "cuda", None)
        if torch_cuda_available:
            torch_device_name = torch.cuda.get_device_name(0)
            gpu_detected = True
            gpu_name = torch_device_name or gpu_name
            try:
                props = torch.cuda.get_device_properties(0)
                gpu_memory = int(props.total_memory / (1024 * 1024))
            except Exception:
                pass
    except Exception:
        pass

    if torch_cuda_available:
        recommended = "cuda"
        note = "CUDA jest gotowa. Trening i synteza mogą używać GPU."
    elif gpu_detected:
        recommended = "cpu"
        note = "Wykryto kartę NVIDIA, ale bieżący PyTorch nie ma aktywnej CUDA. Zainstaluj build PyTorch z CUDA, aby używać GPU."
    else:
        recommended = "cpu"
        note = "Nie wykryto kompatybilnego GPU NVIDIA. Dostępny jest tryb CPU."

    return HardwareInfo(
        cpu=_cpu_name(),
        gpu_detected=gpu_detected,
        gpu_name=gpu_name or "Brak NVIDIA GPU",
        gpu_memory_mb=gpu_memory,
        nvidia_driver=driver,
        torch_cuda_available=torch_cuda_available,
        torch_cuda_version=torch_cuda_version,
        torch_device_name=torch_device_name,
        recommended_device=recommended,
        note=note,
    )
