from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional


class ExternalEngineManager:
    """Manage optional TTS engines in isolated runtimes.

    XTTS remains in the main SoundCore environment. Experimental engines live
    below engine_runtime/ so their dependencies cannot mutate the working XTTS
    stack. Each inference runs in a child process and releases VRAM afterwards.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.runtime_dir = self.base_dir / "engine_runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._install: dict[str, dict] = {}
        self._locks: dict[str, threading.Lock] = {}

    @staticmethod
    def _venv_python(root: Path) -> Path:
        return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    @staticmethod
    def _venv_exe(root: Path, name: str) -> Path:
        if os.name == "nt":
            return root / "Scripts" / f"{name}.exe"
        return root / "bin" / name

    def _engine_root(self, engine: str) -> Path:
        return self.runtime_dir / engine

    def _status_one(self, engine: str) -> dict:
        engine = engine.lower()
        if engine == "xtts":
            return {
                "id": "xtts", "name": "XTTS v2", "installed": True,
                "available": True, "experimental": False, "polish": "stable",
                "detail": "Wbudowany · stabilny silnik polski · fine-tuning per profil",
            }
        if engine == "cosyvoice":
            return {
                "id": "cosyvoice", "name": "CosyVoice 3", "installed": False,
                "available": False, "experimental": True, "polish": "unsupported",
                "detail": "Eksperymentalny · oficjalny stack nie deklaruje polskiego · instalacja manualna",
            }
        root = self._engine_root(engine)
        py = self._venv_python(root / "venv")
        package = "f5_tts" if engine == "f5" else "qwen_tts"
        installed = False
        if py.exists():
            try:
                r = subprocess.run(
                    [str(py), "-c", f"import {package}; print('ok')"],
                    capture_output=True, text=True, timeout=25,
                    creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0),
                )
                installed = r.returncode == 0
            except Exception:
                installed = False
        if engine == "f5":
            return {
                "id": "f5", "name": "F5-TTS v1", "installed": installed,
                "available": installed, "experimental": True, "polish": "experimental",
                "detail": "Zero-shot · oficjalny model bazowy zh/en; polski tylko eksperymentalnie",
            }
        if engine == "qwen":
            py312 = self._find_python312()
            return {
                "id": "qwen", "name": "Qwen3-TTS 0.6B Base", "installed": installed,
                "available": installed, "experimental": True, "polish": "experimental",
                "python312": bool(py312),
                "detail": "Voice clone · Auto language · polski nie jest oficjalnie deklarowany",
            }
        raise ValueError(f"Nieznany silnik: {engine}")

    def status(self) -> dict:
        rows = [self._status_one(x) for x in ("xtts", "f5", "qwen", "cosyvoice")]
        return {"ok": True, "engines": rows, "install": dict(self._install)}

    def _find_python312(self) -> Optional[list[str]]:
        if os.name == "nt" and shutil.which("py"):
            try:
                r = subprocess.run(["py", "-3.12", "-c", "import sys; print(sys.executable)"], capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    return ["py", "-3.12"]
            except Exception:
                pass
        for cmd in ("python3.12", "python312"):
            if shutil.which(cmd):
                return [cmd]
        return None

    def install_async(self, engine: str) -> dict:
        engine = (engine or "").lower()
        if engine not in {"f5", "qwen"}:
            raise ValueError("Automatyczna instalacja jest dostępna dla F5-TTS i Qwen3-TTS.")
        current = self._install.get(engine, {})
        if current.get("state") in {"starting", "installing"}:
            return current
        self._install[engine] = {"state": "starting", "progress": 2, "message": "Przygotowanie środowiska…"}
        threading.Thread(target=self._install_worker, args=(engine,), daemon=True, name=f"EngineInstall-{engine}").start()
        return dict(self._install[engine])

    def install_status(self, engine: str) -> dict:
        return dict(self._install.get(engine, {"state": "idle", "progress": 0, "message": "Gotowy."}))

    def _run_install(self, args: list[str], engine: str, progress: int, message: str) -> None:
        self._install[engine] = {"state": "installing", "progress": progress, "message": message}
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags)
        if p.returncode != 0:
            tail = "\n".join((p.stdout or "").splitlines()[-20:])
            raise RuntimeError(f"{message} nie powiodło się.\n{tail}")

    def _install_worker(self, engine: str) -> None:
        try:
            root = self._engine_root(engine)
            venv = root / "venv"
            root.mkdir(parents=True, exist_ok=True)
            if engine == "f5":
                if not self._venv_python(venv).exists():
                    self._run_install([sys.executable, "-m", "venv", "--system-site-packages", str(venv)], engine, 12, "Tworzenie środowiska F5-TTS")
                py = self._venv_python(venv)
                self._run_install([str(py), "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"], engine, 25, "Aktualizacja pip")
                self._run_install([str(py), "-m", "pip", "install", "f5-tts"], engine, 48, "Instalacja F5-TTS")
            else:
                launcher = self._find_python312()
                if not launcher:
                    raise RuntimeError("Qwen3-TTS wymaga osobnego Python 3.12. Zainstaluj Python 3.12 z python.org (z Python Launcher), potem spróbuj ponownie.")
                if not self._venv_python(venv).exists():
                    self._run_install([*launcher, "-m", "venv", str(venv)], engine, 12, "Tworzenie środowiska Qwen3-TTS")
                py = self._venv_python(venv)
                self._run_install([str(py), "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"], engine, 25, "Aktualizacja pip")
                self._run_install([str(py), "-m", "pip", "install", "qwen-tts"], engine, 50, "Instalacja Qwen3-TTS")
            self._install[engine] = {"state": "completed", "progress": 100, "message": "Silnik zainstalowany. Pierwsza synteza pobierze model."}
        except Exception as exc:
            self._install[engine] = {"state": "error", "progress": 0, "message": str(exc)}

    def synthesize(self, engine: str, text: str, ref_audio: str, output_path: str, language: str = "pl", speed: float = 1.0) -> str:
        engine = (engine or "").lower()
        if engine == "f5":
            return self._synthesize_f5(text, ref_audio, output_path, speed)
        if engine == "qwen":
            return self._synthesize_qwen(text, ref_audio, output_path, language)
        raise ValueError(f"Silnik {engine} nie jest dostępny do lokalnej syntezy.")

    def _synthesize_f5(self, text: str, ref_audio: str, output_path: str, speed: float) -> str:
        root = self._engine_root("f5") / "venv"
        exe = self._venv_exe(root, "f5-tts_infer-cli")
        if not exe.exists():
            raise RuntimeError("F5-TTS nie jest zainstalowany. Użyj przycisku Zainstaluj w Laboratorium silników.")
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        args = [
            str(exe), "--model", "F5TTS_v1_Base", "--ref_audio", str(ref_audio),
            "--ref_text", "", "--gen_text", text, "--output_dir", str(out.parent),
            "--output_file", out.name, "--speed", str(max(0.5, min(float(speed or 1.0), 2.0))),
        ]
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags)
        if p.returncode != 0 or not out.exists():
            tail = "\n".join((p.stdout or "").splitlines()[-30:])
            raise RuntimeError(f"F5-TTS nie wygenerował audio.\n{tail}")
        return str(out)

    def _synthesize_qwen(self, text: str, ref_audio: str, output_path: str, language: str) -> str:
        root = self._engine_root("qwen")
        py = self._venv_python(root / "venv")
        if not py.exists():
            raise RuntimeError("Qwen3-TTS nie jest zainstalowany. Użyj przycisku Zainstaluj w Laboratorium silników.")
        runner = self.base_dir / "voice_engine" / "qwen_runner.py"
        payload = root / "job.json"
        payload.write_text(json.dumps({
            "text": text, "ref_audio": str(ref_audio), "output": str(output_path),
            "language": "Auto", "model": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        p = subprocess.run([str(py), str(runner), str(payload)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=flags)
        if p.returncode != 0 or not Path(output_path).exists():
            tail = "\n".join((p.stdout or "").splitlines()[-30:])
            raise RuntimeError(f"Qwen3-TTS nie wygenerował audio.\n{tail}")
        return output_path
