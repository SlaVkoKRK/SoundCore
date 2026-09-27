from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).resolve().parents[1]

DEFAULT_STRUCTURE = """[Intro]\n\n[Verse 1]\n\n[Pre-Chorus]\n\n[Chorus]\n\n[Verse 2]\n\n[Chorus]\n\n[Bridge]\n\n[Final Chorus]\n\n[Outro]\n"""


def _safe_id(name: str) -> str:
    base = re.sub(r"[^\w\-]+", "-", (name or "song").strip().lower(), flags=re.UNICODE).strip("-") or "song"
    return f"{base}-{int(time.time())}"


def _ts(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    sec = seconds - minutes * 60
    return f"[{minutes:02d}:{sec:05.2f}]"


def lyrics_to_lrc(lyrics: str, duration_seconds: int) -> str:
    """Convert sectioned/plain lyrics into a conservative evenly-spaced LRC.

    Section labels ([Verse], [Chorus]...) create breathing gaps and are not sung.
    This is intentionally deterministic so the user can edit the generated LRC later.
    """
    lines = [x.strip() for x in (lyrics or "").splitlines()]
    sung = [x for x in lines if x and not (x.startswith("[") and x.endswith("]"))]
    if not sung:
        return ""
    # Keep intro/outro room and avoid placing lyrics in the final 5 seconds.
    start = 8.0
    usable = max(10.0, float(duration_seconds) - start - 6.0)
    step = usable / max(1, len(sung))
    out = []
    current = start
    for line in lines:
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            # Structural break. DiffRhythm understands timestamps, not labels.
            current += min(3.0, step * 0.45)
            continue
        out.append(f"{_ts(current)}{line}")
        current += step
    return "\n".join(out) + "\n"


class SongManager:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.root = self.base_dir / "songs"
        self.projects_dir = self.root / "projects"
        self.runtime_dir = self.base_dir / "engine_runtime" / "music" / "diffrhythm"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._install_status = {"state": "idle", "progress": 0, "message": "DiffRhythm nie jest instalowany."}
        self._generation_status = {"state": "idle", "progress": 0, "message": "Brak aktywnego renderu."}
        self._espeak_install_status = {"state": "idle", "progress": 0, "message": "eSpeak NG nie jest instalowany."}
        self._install_lock = threading.Lock()
        self._generation_lock = threading.Lock()
        self._install_cancel = threading.Event()
        self._install_process: Optional[subprocess.Popen] = None
        self._install_started_at: Optional[float] = None
        self._install_last_activity: Optional[float] = None
        self._cancel = threading.Event()
        self._process: Optional[subprocess.Popen] = None
        self._composer_process: Optional[subprocess.Popen] = None
        self._composer_lock = threading.Lock()
        self._composer_cancel = threading.Event()
        self._composer_status = {"state":"idle","progress":0,"message":"AUTO COMPOSER gotowy."}
        self._model_download = {"state": "idle", "stage": "", "file": "", "downloaded_bytes": 0, "expected_bytes": 0, "speed_bps": 0, "items": {}}

    @property
    def repo_dir(self) -> Path:
        return self.runtime_dir / "repo"

    @property
    def venv_python(self) -> Path:
        return self.runtime_dir / "venv" / "Scripts" / "python.exe"

    @property
    def log_path(self) -> Path:
        return self.runtime_dir / "engine.log"

    def _espeak(self) -> dict:
        candidates = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "eSpeak NG",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "eSpeak NG",
        ]
        for folder in candidates:
            dll = folder / "libespeak-ng.dll"
            if dll.exists():
                return {"ok": True, "path": str(folder), "dll": str(dll)}
        return {"ok": False, "path": None, "dll": None}

    def espeak_install_status(self) -> dict:
        return {"ok": True, **self._espeak_install_status, "detected": self._espeak()["ok"]}

    def install_espeak_ng(self) -> dict:
        if self._espeak()["ok"]:
            self._espeak_install_status = {"state": "completed", "progress": 100, "message": "eSpeak NG jest już zainstalowany."}
            return self.espeak_install_status()
        if self._espeak_install_status.get("state") in {"resolving", "downloading", "installing"}:
            return self.espeak_install_status()
        self._espeak_install_status = {"state": "resolving", "progress": 5, "message": "Szukam oficjalnego instalatora eSpeak NG dla Windows…"}
        threading.Thread(target=self._install_espeak_worker, name="SoundCoreEspeakInstall", daemon=True).start()
        return self.espeak_install_status()

    def _install_espeak_worker(self) -> None:
        try:
            api_url = "https://api.github.com/repos/espeak-ng/espeak-ng/releases/latest"
            req = urllib.request.Request(api_url, headers={"User-Agent": "SoundCore/0.7.4", "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                release = json.loads(resp.read().decode("utf-8"))
            assets = release.get("assets") or []
            
            # eSpeak NG 1.52.0 publishes the Windows installer simply as
            # "espeak-ng.msi". Older releases used names containing "x64".
            # Prefer the canonical current name, then an x64 MSI, then any MSI.
            def _asset_name(a):
                return str(a.get("name", "")).lower()
            asset = next((a for a in assets if _asset_name(a) == "espeak-ng.msi"), None)
            if asset is None:
                asset = next((a for a in assets if _asset_name(a).endswith(".msi") and "x64" in _asset_name(a)), None)
            if asset is None:
                asset = next((a for a in assets if _asset_name(a).endswith(".msi")), None)
            if not asset:
                raise RuntimeError("Nie znaleziono oficjalnego instalatora eSpeak NG x64 w najnowszym wydaniu GitHub.")
            url = asset.get("browser_download_url")
            if not url:
                raise RuntimeError("GitHub nie zwrócił adresu instalatora eSpeak NG.")
            target = self.runtime_dir / str(asset.get("name") or "espeak-ng.msi")
            self._espeak_install_status = {"state": "downloading", "progress": 20, "message": "Pobieranie oficjalnego instalatora eSpeak NG…"}
            req = urllib.request.Request(url, headers={"User-Agent": "SoundCore/0.7.4"})
            with urllib.request.urlopen(req, timeout=120) as src, target.open("wb") as dst:
                total = int(src.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    chunk = src.read(1024 * 256)
                    if not chunk:
                        break
                    dst.write(chunk)
                    done += len(chunk)
                    pct = 20 + int((done / total) * 45) if total else 45
                    self._espeak_install_status = {"state": "downloading", "progress": min(65, pct), "message": "Pobieranie eSpeak NG…"}
            if os.name != "nt":
                raise RuntimeError("Automatyczna instalacja eSpeak NG jest dostępna tylko w Windows.")
            self._espeak_install_status = {"state": "installing", "progress": 70, "message": "Uruchomiono instalator eSpeak NG. Dokończ instalację w oknie Windows."}
            proc = subprocess.Popen(["msiexec.exe", "/i", str(target)])
            code = proc.wait()
            if code not in (0, 3010):
                raise RuntimeError(f"Instalator eSpeak NG zakończył się kodem {code}.")
            # MSI może potrzebować chwili, zanim pliki będą widoczne.
            for _ in range(20):
                if self._espeak()["ok"]:
                    break
                time.sleep(0.5)
            if not self._espeak()["ok"]:
                raise RuntimeError("Instalacja zakończyła się, ale SoundCore nadal nie widzi libespeak-ng.dll. Uruchom ponownie SoundCore.")
            self._espeak_install_status = {"state": "completed", "progress": 100, "message": "eSpeak NG zainstalowany i wykryty. DiffRhythm jest gotowy do użycia."}
        except Exception as exc:
            self._espeak_install_status = {"state": "error", "progress": 0, "message": str(exc)}


    def _torch_runtime_status(self) -> dict:
        py = self.venv_python
        if not py.exists():
            return {"ok": False, "installed": False, "cuda": False, "torch": None, "cuda_version": None, "device": None}
        code = (
            "import json, torch; "
            "print(json.dumps({'torch':torch.__version__,'cuda':bool(torch.cuda.is_available()),"
            "'cuda_version':torch.version.cuda,'device':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}))"
        )
        try:
            r = self._run_hidden([str(py), '-c', code], cwd=str(self.repo_dir), capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return {"ok": False, "installed": True, "cuda": False, "torch": None, "cuda_version": None, "device": None, "error": (r.stderr or r.stdout or '').strip()}
            data = json.loads((r.stdout or '{}').strip().splitlines()[-1])
            return {"ok": True, "installed": True, **data}
        except Exception as exc:
            return {"ok": False, "installed": True, "cuda": False, "torch": None, "cuda_version": None, "device": None, "error": str(exc)}

    def _nvidia_present(self) -> bool:
        if os.name != 'nt':
            return False
        try:
            r = self._run_hidden(['nvidia-smi', '-L'], capture_output=True, text=True, timeout=10)
            return r.returncode == 0 and bool((r.stdout or '').strip())
        except Exception:
            return False

    def _stop_diffrhythm_runtime_processes(self) -> None:
        """Stop renderer/runtime Python processes that can keep torch DLL/PYD files locked."""
        self._cancel.set()

        # Stop processes we own directly first.
        for attr in ("_process", "_install_process"):
            proc = getattr(self, attr, None)
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=8)
                except Exception:
                    try:
                        proc.kill()
                        proc.wait(timeout=5)
                    except Exception:
                        pass
            setattr(self, attr, None)

        if os.name != "nt":
            time.sleep(1.0)
            return

        # Kill processes that belong to DiffRhythm by executable path OR command line.
        # Do not escape backslashes for PowerShell single-quoted strings; doubled
        # backslashes caused 0.8.0 to match nothing on Windows.
        runtime_root = str(self.runtime_dir.resolve())
        ps = (
            "$root='" + runtime_root.replace("'", "''") + "'; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { "
            " ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($root,[System.StringComparison]::OrdinalIgnoreCase)) -or "
            " ($_.CommandLine -and $_.CommandLine.IndexOf($root,[System.StringComparison]::OrdinalIgnoreCase) -ge 0) "
            "} | ForEach-Object { "
            "  try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} "
            "}"
        )
        try:
            self._run_hidden(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps],
                cwd=str(self.repo_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
        except Exception:
            pass

        # Windows/AV can keep extension modules mapped for a brief moment after process exit.
        time.sleep(2.5)

    def _torch_file_unlock_probe(self) -> bool:
        """Windows-safe lock test: rename the loaded extension and immediately restore it."""
        torch_dir = self.runtime_dir / "venv" / "Lib" / "site-packages" / "torch"
        candidates = list(torch_dir.glob("_C*.pyd"))
        if not candidates:
            return True
        target = candidates[0]
        probe = target.with_name(target.name + ".soundcore_unlock_test")
        try:
            if probe.exists():
                probe.unlink()
            target.rename(probe)
            probe.rename(target)
            return True
        except (PermissionError, OSError):
            try:
                if probe.exists() and not target.exists():
                    probe.rename(target)
            except Exception:
                pass
            return False

    def repair_cuda_runtime(self) -> dict:
        st = self._torch_runtime_status()
        if st.get('cuda'):
            return {"ok": True, "repaired": False, "message": f"CUDA jest już aktywna: {st.get('device')}", "runtime": st}
        if not self.venv_python.exists():
            raise RuntimeError('Najpierw zainstaluj DiffRhythm.')
        if not self._nvidia_present():
            raise RuntimeError('Nie wykryto karty NVIDIA przez nvidia-smi.')
        threading.Thread(target=self._repair_cuda_worker, name='SoundCoreDiffRhythmCUDARepair', daemon=True).start()
        self._install_status = {"state": "cuda_repair", "progress": 2, "message": "Przygotowanie CUDA dla DiffRhythm…"}
        return {"ok": True, "started": True, "message": self._install_status['message']}

    def _repair_cuda_worker(self) -> None:
        py = str(self.venv_python)
        try:
            self._set_install('cuda_repair', 4, 'Zatrzymuję render i zwalniam pliki PyTorch…')
            self._stop_diffrhythm_runtime_processes()

            for attempt in range(4):
                if self._torch_file_unlock_probe():
                    break
                self._set_install('cuda_repair', 5 + attempt, f'Czekam na zwolnienie torch/_C.pyd… próba {attempt + 1}/4')
                time.sleep(2.0)
            if not self._torch_file_unlock_probe():
                raise RuntimeError('Pliki PyTorch są nadal używane przez inny proces. Zamknij wszystkie procesy Python korzystające z DiffRhythm i spróbuj ponownie.')

            self._set_install('cuda_repair', 10, 'Usuwanie CPU-only PyTorch…')
            self._run_hidden([py, '-m', 'pip', 'uninstall', '-y', 'torch', 'torchaudio', 'torchvision'], cwd=str(self.repo_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

            # Remove stale partial-install folders left by failed pip operations, e.g. ~orch.
            site_packages = self.runtime_dir / 'venv' / 'Lib' / 'site-packages'
            for stale in site_packages.glob('~orch*'):
                try:
                    if stale.is_dir():
                        shutil.rmtree(stale, ignore_errors=True)
                    else:
                        stale.unlink(missing_ok=True)
                except Exception:
                    pass

            self._set_install('cuda_repair', 18, 'Pobieranie PyTorch 2.6.0 CUDA 12.4…')
            cmd = [py, '-m', 'pip', 'install', '--no-cache-dir',
                   'torch==2.6.0', 'torchvision==0.21.0', 'torchaudio==2.6.0',
                   '--index-url', 'https://download.pytorch.org/whl/cu124',
                   '--disable-pip-version-check', '--no-input', '--progress-bar', 'off']
            progress = 18
            with self.log_path.open('a', encoding='utf-8', errors='replace', buffering=1) as log:
                log.write('\n[SoundCore] Naprawa CUDA DiffRhythm\n')
                log.write('COMMAND: ' + ' '.join(cmd) + '\n')
                proc = subprocess.Popen(cmd, cwd=str(self.repo_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1, creationflags=self._hidden_creationflags())
                self._install_process = proc
                assert proc.stdout is not None
                for raw in proc.stdout:
                    line = raw.rstrip('\r\n')
                    log.write(line + '\n'); log.flush()
                    low=line.lower()
                    if line.startswith('Collecting ') or line.startswith('Downloading '): progress=min(78, progress+2)
                    elif 'installing collected packages' in low: progress=max(progress, 82)
                    elif 'successfully installed' in low: progress=94
                    self._install_status = {"state":"cuda_repair","progress":progress,"message":line[:160] if line else 'pip pracuje…'}
                rc=proc.wait()
                self._install_process=None
            if rc != 0:
                raise RuntimeError(f'Instalacja CUDA PyTorch nie powiodła się (pip exit {rc}).')
            self._set_install('cuda_repair', 96, 'Weryfikacja RTX / CUDA…')
            st=self._torch_runtime_status()
            if not st.get('cuda'):
                raise RuntimeError(f"PyTorch zainstalowany, ale CUDA nadal jest niedostępna: {st.get('error') or st.get('torch')}")
            self._set_install('completed', 100, f"CUDA READY — {st.get('device')} · torch {st.get('torch')} · CUDA {st.get('cuda_version')}")
        except Exception as exc:
            self._install_process=None
            self._set_install('error', self._install_status.get('progress',0), str(exc))

    def engine_status(self) -> dict:
        espeak = self._espeak()
        installed = self.venv_python.exists() and (self.repo_dir / "infer" / "infer.py").exists()
        return {
            "ok": True,
            "engine": "diffrhythm",
            "installed": installed,
            "runtime_dir": str(self.runtime_dir),
            "espeak": espeak,
            "install": dict(self._install_status),
            "generation": self.generation_status(),
            "torch_runtime": self._torch_runtime_status(),
            "low_vram_recommended": True,
        }

    def install_status(self) -> dict:
        data = {"ok": True, **self._install_status}
        now = time.time()
        if self._install_started_at:
            data["elapsed_seconds"] = max(0, int(now - self._install_started_at))
        if self._install_last_activity:
            data["last_activity_seconds"] = max(0, int(now - self._install_last_activity))
        if self.log_path.exists():
            try:
                data["log_tail"] = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]
            except Exception:
                data["log_tail"] = []
        else:
            data["log_tail"] = []
        data["running"] = bool(self._install_process and self._install_process.poll() is None)
        return data

    def _set_install(self, state: str, progress: int, message: str) -> None:
        self._install_status = {"state": state, "progress": int(progress), "message": message}
        self._install_last_activity = time.time()

    @staticmethod
    def _hidden_creationflags() -> int:
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0

    def _run_hidden(self, cmd: list[str], **kwargs):
        kwargs.setdefault("creationflags", self._hidden_creationflags())
        return subprocess.run(cmd, **kwargs)

    def cancel_install(self) -> dict:
        self._install_cancel.set()
        proc = self._install_process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        if self._install_status.get("state") in {"starting", "downloading", "installing"}:
            self._set_install("cancelling", self._install_status.get("progress", 0), "Przerywanie instalacji DiffRhythm…")
        return self.install_status()

    def install_engine(self) -> dict:
        if self._install_status.get("state") in {"starting", "downloading", "installing"}:
            return self.install_status()
        self._install_cancel.clear()
        self._install_started_at = time.time()
        self._install_last_activity = self._install_started_at
        threading.Thread(target=self._install_worker, name="SoundCoreDiffRhythmInstall", daemon=True).start()
        self._set_install("starting", 2, "Przygotowanie DiffRhythm…")
        return self.install_status()

    def _install_worker(self) -> None:
        with self._install_lock:
            try:
                self.runtime_dir.mkdir(parents=True, exist_ok=True)
                if not self.repo_dir.exists():
                    self._set_install("downloading", 10, "Pobieranie źródeł DiffRhythm…")
                    archive = self.runtime_dir / "diffrhythm.zip"
                    urllib.request.urlretrieve("https://github.com/ASLP-lab/DiffRhythm/archive/refs/heads/main.zip", archive)
                    tmp = self.runtime_dir / "_src"
                    if tmp.exists(): shutil.rmtree(tmp)
                    tmp.mkdir()
                    with zipfile.ZipFile(archive, "r") as zf:
                        zf.extractall(tmp)
                    extracted = next(tmp.iterdir())
                    shutil.move(str(extracted), str(self.repo_dir))
                    shutil.rmtree(tmp, ignore_errors=True)
                    archive.unlink(missing_ok=True)
                if not self.venv_python.exists():
                    self._set_install("installing", 28, "Tworzenie izolowanego środowiska Python…")
                    self._run_hidden([sys.executable, "-m", "venv", str(self.runtime_dir / "venv")], check=True)
                if self._install_cancel.is_set():
                    raise InterruptedError("Instalacja przerwana przez użytkownika.")
                py = str(self.venv_python)
                self._set_install("installing", 40, "Aktualizacja pip…")
                self._run_hidden([py, "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools", "--disable-pip-version-check", "--no-input"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if self._install_cancel.is_set():
                    raise InterruptedError("Instalacja przerwana przez użytkownika.")
                self._set_install("installing", 52, "Instalacja zależności DiffRhythm — uruchamiam pip…")
                req = self.repo_dir / "requirements.txt"
                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"
                cmd = [py, "-m", "pip", "install", "-r", str(req), "--disable-pip-version-check", "--no-input", "--progress-bar", "off"]
                progress = 52
                with self.log_path.open("w", encoding="utf-8", errors="replace", buffering=1) as log:
                    log.write("SoundCore DiffRhythm installer\n")
                    log.write("COMMAND: " + " ".join(cmd) + "\n\n")
                    self._install_process = subprocess.Popen(
                        cmd, cwd=str(self.repo_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
                        creationflags=self._hidden_creationflags(),
                    )
                    assert self._install_process.stdout is not None
                    for raw in self._install_process.stdout:
                        line = raw.rstrip("\r\n")
                        log.write(line + "\n")
                        log.flush()
                        self._install_last_activity = time.time()
                        low = line.lower()
                        if line.startswith("Collecting ") or line.startswith("Using cached ") or line.startswith("Downloading "):
                            progress = min(80, progress + 1)
                        elif "installing collected packages" in low:
                            progress = max(progress, 84)
                        elif "successfully installed" in low:
                            progress = 91
                        elif "building wheel" in low or "preparing metadata" in low:
                            progress = min(82, max(progress, 68))
                        tail = line if line else "pip pracuje…"
                        if len(tail) > 160:
                            tail = tail[:157] + "…"
                        self._install_status = {"state": "installing", "progress": progress, "message": tail}
                        if self._install_cancel.is_set():
                            try:
                                self._install_process.terminate()
                            except Exception:
                                pass
                            break
                    rc = self._install_process.wait()
                    self._install_process = None
                if self._install_cancel.is_set():
                    raise InterruptedError("Instalacja przerwana przez użytkownika.")
                if rc != 0:
                    raise RuntimeError(f"Instalacja zależności nie powiodła się (pip exit {rc}). Zobacz log w Song Studio.")
                self._set_install("installing", 93, "Sprawdzam zgodność py3langid…")
                self._ensure_py3langid_compat()
                if self._nvidia_present() and not self._torch_runtime_status().get("cuda"):
                    self._repair_cuda_worker()
                espeak = self._espeak()
                if not espeak["ok"]:
                    self._set_install("needs_espeak", 92, "DiffRhythm zainstalowany. Brakuje eSpeak NG dla Windows — zainstaluj eSpeak NG i uruchom SoundCore ponownie.")
                else:
                    self._set_install("completed", 100, "DiffRhythm gotowy. Modele pobiorą się przy pierwszym renderze.")
            except InterruptedError as exc:
                self._install_process = None
                self._set_install("cancelled", self._install_status.get("progress", 0), str(exc))
            except Exception as exc:
                self._install_process = None
                self._set_install("error", self._install_status.get("progress", 0), str(exc))

    def _project_path(self, project_id: str) -> Path:
        return self.projects_dir / project_id / "project.json"

    def list_projects(self) -> list[dict]:
        rows = []
        for p in sorted(self.projects_dir.glob("*/project.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                data["project_id"] = p.parent.name
                data["renders"] = self.list_renders(p.parent.name)
                rows.append(data)
            except Exception:
                continue
        return rows

    def new_project(self, title: str = "Nowa piosenka") -> dict:
        pid = _safe_id(title)
        folder = self.projects_dir / pid
        (folder / "renders").mkdir(parents=True, exist_ok=True)
        data = {
            "project_id": pid,
            "title": title or "Nowa piosenka",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "engine": "diffrhythm",
            "language": "pl",
            "duration_seconds": 95,
            "bpm": 100,
            "key": "C minor",
            "time_signature": "4/4",
            "style": "modern pop, emotional, wide stereo, polished production",
            "negative_style": "",
            "lyrics": DEFAULT_STRUCTURE,
            "chords": "Verse: Cm - Ab - Eb - Bb\nChorus: Ab - Eb - Bb - Cm",
            "seed": -1,
            "low_vram": True,
            "instrumental": False,
            "profile_name": "",
            "style_reference_path": "",
            "edit_mode": False,
            "edit_reference_path": "",
            "edit_segments": "[[20,40]]",
            "notes": "",
        }
        self.save_project(data)
        return data

    def save_project(self, data: dict) -> dict:
        data = dict(data or {})
        pid = data.get("project_id") or _safe_id(data.get("title", "song"))
        folder = self.projects_dir / pid
        (folder / "renders").mkdir(parents=True, exist_ok=True)
        data["project_id"] = pid
        data.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
        data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        path = folder / "project.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "project": data, "projects": self.list_projects()}

    def get_project(self, project_id: str) -> dict:
        path = self._project_path(project_id)
        if not path.exists():
            raise FileNotFoundError("Nie znaleziono projektu piosenki.")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["project_id"] = project_id
        data["renders"] = self.list_renders(project_id)
        return data

    def delete_project(self, project_id: str) -> dict:
        folder = self.projects_dir / project_id
        if folder.exists(): shutil.rmtree(folder)
        return {"ok": True, "projects": self.list_projects()}

    def lrc_preview(self, project: dict) -> dict:
        duration = int(project.get("duration_seconds", 95))
        lrc = lyrics_to_lrc(project.get("lyrics", ""), duration)
        return {"ok": True, "lrc": lrc, "duration_seconds": duration}

    def list_renders(self, project_id: str) -> list[dict]:
        folder = self.projects_dir / project_id / "renders"
        rows = []
        if not folder.exists(): return rows
        for wav in sorted(folder.glob("*.wav"), key=lambda x: x.stat().st_mtime, reverse=True):
            meta = wav.with_suffix(".json")
            item = {"name": wav.name, "path": str(wav), "created_at": datetime.fromtimestamp(wav.stat().st_mtime).isoformat(timespec="seconds")}
            if meta.exists():
                try: item.update(json.loads(meta.read_text(encoding="utf-8")))
                except Exception: pass
            rows.append(item)
        return rows

    def generation_status(self) -> dict:
        data = dict(self._generation_status)
        data["running"] = bool(self._process and self._process.poll() is None)
        if self.log_path.exists():
            try:
                data["log_tail"] = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
            except Exception:
                data["log_tail"] = []
        else:
            data["log_tail"] = []
        data["model_download"] = dict(self._model_download)
        return {"ok": True, **data}

    def _cache_size(self) -> int:
        root = self.repo_dir / "pretrained"
        total = 0
        if root.exists():
            for p in root.rglob("*"):
                try:
                    if p.is_file(): total += p.stat().st_size
                except OSError:
                    pass
        return total

    def _ensure_hf_xet(self) -> None:
        py = str(self.venv_python)
        probe = self._run_hidden([py, "-c", "import hf_xet"], cwd=str(self.repo_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if getattr(probe, "returncode", 1) == 0:
            return
        self._generation_status = {"state":"models","progress":5,"message":"Instaluję szybszy transport Hugging Face (hf_xet)…"}
        proc = self._run_hidden([py, "-m", "pip", "install", "hf_xet", "--disable-pip-version-check", "--no-input"], cwd=str(self.repo_dir), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if getattr(proc, "returncode", 1) != 0:
            raise RuntimeError("Nie udało się zainstalować hf_xet dla DiffRhythm.")

    def _prefetch_models(self, duration: int, project_id: str) -> None:
        self._ensure_hf_xet()
        helper = BASE_DIR / "music" / "hf_prefetch.py"
        if not helper.exists():
            raise RuntimeError("Brakuje helpera pobierania modeli DiffRhythm.")
        cache = self.repo_dir / "pretrained"
        cache.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        env["HF_HUB_DISABLE_XET"] = "0"
        env["PYTHONUTF8"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        cmd = [str(self.venv_python), str(helper), str(cache), str(duration)]
        before_all = self._cache_size()
        stage_start_size = before_all
        last_size = before_all
        last_time = time.time()
        current = ""
        expected = 0
        items = {}
        self._model_download = {"state":"starting","stage":"","file":"","downloaded_bytes":0,"expected_bytes":0,"speed_bps":0,"items":items}
        proc = subprocess.Popen(cmd, cwd=str(self.repo_dir), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=self._hidden_creationflags())
        self._process = proc
        assert proc.stdout is not None
        import queue
        q = queue.Queue()
        def reader():
            for line in proc.stdout:
                q.put(line.rstrip("\r\n"))
        threading.Thread(target=reader, daemon=True).start()
        with self.log_path.open("w", encoding="utf-8", errors="replace", buffering=1) as log:
            log.write("SoundCore model prefetch\n")
            while proc.poll() is None or not q.empty():
                if self._cancel.is_set():
                    self._kill_process_tree(proc)
                    raise RuntimeError("Pobieranie modeli przerwane.")
                try:
                    while True:
                        line=q.get_nowait()
                        if line.startswith("SCSTATUS "):
                            try:
                                evt=json.loads(line[9:])
                                if evt.get("event")=="stage":
                                    current=evt.get("name","")
                                    expected=int(evt.get("expected_bytes") or 0)
                                    stage_start_size=self._cache_size()
                                    items.setdefault(current,{})
                                    items[current].update({"state":"downloading","expected_bytes":expected,"downloaded_bytes":0,"file":""})
                                elif evt.get("event")=="file":
                                    if current:
                                        items[current]["file"]=evt.get("file","")
                                elif evt.get("event")=="done":
                                    nm=evt.get("name",current)
                                    items.setdefault(nm,{})["state"]="ready"
                                    items[nm]["downloaded_bytes"]=items[nm].get("expected_bytes",expected)
                                elif evt.get("event")=="all_done":
                                    self._model_download["state"]="ready"
                            except Exception:
                                pass
                        else:
                            log.write(line+"\n")
                except queue.Empty:
                    pass
                now=time.time(); size=self._cache_size(); dt=max(0.2,now-last_time); speed=max(0,int((size-last_size)/dt))
                downloaded=max(0,size-stage_start_size)
                if current:
                    items.setdefault(current,{})
                    items[current].update({"state":items[current].get("state","downloading"),"downloaded_bytes":downloaded if items[current].get("state")!="ready" else items[current].get("downloaded_bytes",downloaded),"expected_bytes":expected,"speed_bps":speed})
                total_expected=sum(int(v.get("expected_bytes") or 0) for v in items.values())
                total_downloaded=sum(min(int(v.get("downloaded_bytes") or 0), int(v.get("expected_bytes") or 0) or int(v.get("downloaded_bytes") or 0)) for v in items.values())
                pct=10 + int(45*(total_downloaded/max(1,total_expected))) if total_expected else 10
                self._model_download={"state":"downloading" if proc.poll() is None else self._model_download.get("state","downloading"),"stage":current,"file":items.get(current,{}).get("file","") if current else "","downloaded_bytes":max(0,size-before_all),"expected_bytes":total_expected,"speed_bps":speed,"items":items}
                self._generation_status={"state":"models","progress":min(55,pct),"message":f"Pobieranie modeli AI: {current or 'przygotowanie'}…","project_id":project_id}
                last_size=size; last_time=now
                time.sleep(0.5)
        if proc.returncode != 0:
            raise RuntimeError(f"Pobieranie modeli zakończyło się kodem {proc.returncode}. Sprawdź log DiffRhythm.")
        self._model_download["state"]="ready"

    def _ensure_py3langid_compat(self) -> dict:
        """Ensure DiffRhythm gets the py3langid API expected by its bundled LangSegment."""
        py = str(self.venv_python)
        if not Path(py).exists():
            return {"ok": False, "repaired": False, "message": "Brak środowiska DiffRhythm."}

        probe = (
            "from py3langid.langid import LanguageIdentifier; "
            "assert hasattr(LanguageIdentifier, 'from_pickled_model'), 'missing from_pickled_model'"
        )
        result = self._run_hidden(
            [py, "-c", probe],
            cwd=str(self.repo_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if getattr(result, "returncode", 1) == 0:
            return {"ok": True, "repaired": False, "message": "py3langid API OK"}

        self._generation_status = {
            "state": "repairing",
            "progress": 8,
            "message": "Naprawiam zgodność py3langid dla DiffRhythm…",
        }
        cmd = [
            py, "-m", "pip", "install",
            "--force-reinstall", "--no-deps",
            "py3langid==0.2.2",
            "--disable-pip-version-check", "--no-input",
        ]
        with self.log_path.open("a", encoding="utf-8", errors="replace", buffering=1) as log:
            log.write("\n[SoundCore] Naprawa py3langid -> 0.2.2\n")
            proc = subprocess.run(
                cmd,
                cwd=str(self.repo_dir),
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=self._hidden_creationflags(),
                check=False,
            )
        if proc.returncode != 0:
            raise RuntimeError("Nie udało się zainstalować zgodnego py3langid==0.2.2.")

        verify = self._run_hidden(
            [py, "-c", probe],
            cwd=str(self.repo_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if getattr(verify, "returncode", 1) != 0:
            raise RuntimeError("py3langid 0.2.2 nie udostępnia wymaganego API.")
        return {"ok": True, "repaired": True, "message": "py3langid naprawiony"}

    def start_generation(self, project: dict) -> dict:
        if self._process and self._process.poll() is None:
            raise RuntimeError("Render piosenki już trwa.")
        if not self.venv_python.exists() or not (self.repo_dir / "infer" / "infer.py").exists():
            raise RuntimeError("Najpierw zainstaluj silnik DiffRhythm w Song Studio.")
        espeak = self._espeak()
        if not espeak["ok"]:
            raise RuntimeError("Brakuje eSpeak NG. Zainstaluj eSpeak NG dla Windows i uruchom SoundCore ponownie.")
        self._ensure_py3langid_compat()
        runtime = self._torch_runtime_status()
        if self._nvidia_present() and not runtime.get("cuda"):
            raise RuntimeError("DiffRhythm ma CPU-only PyTorch. Kliknij ‘Napraw CUDA dla DiffRhythm’ i poczekaj na CUDA READY.")
        saved = self.save_project(project)["project"]
        self._cancel.clear()
        self._generation_status = {"state": "starting", "progress": 2, "message": "Przygotowanie projektu…", "project_id": saved["project_id"]}
        threading.Thread(target=self._generation_entry, args=(saved,), name="SoundCoreSongRender", daemon=True).start()
        return self.generation_status()

    def _generation_entry(self, project: dict) -> None:
        try:
            self._prefetch_models(int(project.get("duration_seconds", 95)), project.get("project_id", ""))
            if self._cancel.is_set():
                self._generation_status = {"state":"cancelled","progress":0,"message":"Render przerwany.","project_id":project.get("project_id")}
                return
            self._process = None
            self._generation_worker(project)
        except Exception as exc:
            self._process = None
            self._generation_status = {"state":"error","progress":0,"message":str(exc),"project_id":project.get("project_id")}

    def _generation_worker(self, project: dict) -> None:
        with self._generation_lock:
            try:
                pid = project["project_id"]
                project_dir = self.projects_dir / pid
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                render_dir = project_dir / "renders" / f"_tmp_{stamp}"
                render_dir.mkdir(parents=True, exist_ok=True)
                lrc_path = render_dir / "lyrics.lrc"
                duration = int(project.get("duration_seconds", 95))
                lrc = "" if project.get("instrumental") else lyrics_to_lrc(project.get("lyrics", ""), duration)
                lrc_path.write_text(lrc, encoding="utf-8")
                style = project.get("style", "")
                bpm = project.get("bpm")
                key = project.get("key")
                meter = project.get("time_signature")
                chords = project.get("chords", "")
                prompt = ", ".join(x for x in [style, f"{bpm} BPM" if bpm else "", key, f"time signature {meter}" if meter else "", f"chord mood: {chords}" if chords else ""] if x)
                infer = self.repo_dir / "infer" / "infer.py"
                cmd = [str(self.venv_python), str(infer), "--audio-length", str(duration), "--output-dir", str(render_dir)]
                style_ref = str(project.get("style_reference_path") or "").strip()
                if style_ref and Path(style_ref).is_file():
                    cmd += ["--ref-audio-path", style_ref]
                else:
                    cmd += ["--ref-prompt", prompt]
                if not project.get("instrumental"):
                    cmd += ["--lrc-path", str(lrc_path)]
                edit_ref = str(project.get("edit_reference_path") or "").strip()
                if project.get("edit_mode") and edit_ref and Path(edit_ref).is_file():
                    cmd += ["--edit", "--ref-song", edit_ref, "--edit-segments", str(project.get("edit_segments") or "[[-1,-1]]")]
                if project.get("low_vram", True):
                    cmd.append("--chunked")
                env = os.environ.copy()
                espeak = self._espeak()
                env["PHONEMIZER_ESPEAK_LIBRARY"] = espeak["dll"]
                env["PHONEMIZER_ESPEAK_PATH"] = espeak["path"]
                env["PYTHONUTF8"] = "1"
                env["PYTHONUNBUFFERED"] = "1"
                # DiffRhythm imports top-level packages such as `model`. Running
                # infer.py with cwd=infer removes the repo root from import lookup
                # on Windows, producing ModuleNotFoundError: model. Keep the repo
                # root as cwd and explicitly prepend it to PYTHONPATH.
                env["PYTHONPATH"] = str(self.repo_dir) + os.pathsep + env.get("PYTHONPATH", "")
                self._generation_status = {"state": "rendering", "progress": 60, "message": "Modele gotowe. Ładowanie do GPU i generowanie piosenki…", "project_id": pid}
                with self.log_path.open("w", encoding="utf-8", errors="replace", buffering=1) as log:
                    log.write("SoundCore DiffRhythm render\n")
                    log.write("CWD: " + str(self.repo_dir) + "\n")
                    log.write("COMMAND: " + " ".join(cmd) + "\n\n")
                    log.flush()
                    self._process = subprocess.Popen(
                        cmd, cwd=str(self.repo_dir), env=env, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=self._hidden_creationflags(),
                    )
                    while self._process.poll() is None:
                        if self._cancel.is_set():
                            self._kill_process_tree(self._process)
                            self._generation_status = {"state": "cancelled", "progress": 0, "message": "Render przerwany.", "project_id": pid}
                            return
                        time.sleep(0.5)
                if self._process.returncode != 0:
                    raise RuntimeError(f"DiffRhythm zakończył się kodem {self._process.returncode}. Sprawdź log renderu.")
                src = render_dir / "output.wav"
                if not src.exists():
                    raise RuntimeError("DiffRhythm nie utworzył output.wav.")
                safe_title = re.sub(r"[^\w-]+", "_", str(project.get("title") or "song"))[:40].strip("_") or "song"
                final = project_dir / "renders" / f"{stamp}_{safe_title}.wav"
                shutil.move(str(src), str(final))
                meta = {
                    "title": project.get("title"), "engine": "DiffRhythm", "style": style,
                    "duration_seconds": duration, "bpm": bpm, "key": key, "time_signature": meter,
                    "low_vram": bool(project.get("low_vram", True)), "instrumental": bool(project.get("instrumental", False)),
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
                final.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                shutil.rmtree(render_dir, ignore_errors=True)
                self._generation_status = {"state": "completed", "progress": 100, "message": f"Gotowe: {final.name}", "project_id": pid, "path": str(final)}
            except Exception as exc:
                self._generation_status = {"state": "error", "progress": 0, "message": str(exc), "project_id": project.get("project_id")}
            finally:
                self._process = None

    def _kill_process_tree(self, proc: Optional[subprocess.Popen]) -> None:
        if proc is None or proc.poll() is not None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=self._hidden_creationflags(), timeout=15, check=False,
                )
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
                return
            except Exception:
                pass
        try:
            proc.terminate(); proc.wait(timeout=5)
        except Exception:
            try: proc.kill()
            except Exception: pass

    def start_composer(self, brief: str, project: dict) -> dict:
        brief = (brief or "").strip()
        if not brief:
            raise ValueError("Opisz, jaką piosenkę mam wymyślić.")
        if self._composer_process and self._composer_process.poll() is None:
            raise RuntimeError("AUTO COMPOSER już pracuje.")
        if not self.venv_python.exists():
            raise RuntimeError("Najpierw zainstaluj DiffRhythm — AUTO COMPOSER używa jego izolowanego runtime.")
        self._composer_cancel.clear()
        self._composer_status = {"state":"starting","progress":5,"message":"Przygotowanie lokalnego AI Composer…"}
        threading.Thread(target=self._composer_worker, args=(brief, dict(project or {})), name="SoundCoreSongComposer", daemon=True).start()
        return self.composer_status()

    def composer_status(self) -> dict:
        data = dict(self._composer_status)
        data["running"] = bool(self._composer_process and self._composer_process.poll() is None) or data.get("state") in {"starting","loading","thinking"}
        return data

    def cancel_composer(self) -> dict:
        self._composer_cancel.set()
        self._kill_process_tree(self._composer_process)
        self._composer_process = None
        self._composer_status = {"state":"cancelled","progress":0,"message":"AUTO COMPOSER zatrzymany."}
        return self.composer_status()

    def _composer_worker(self, brief: str, project: dict) -> None:
        with self._composer_lock:
            try:
                helper = BASE_DIR / "music" / "composer_ai.py"
                if not helper.exists():
                    raise RuntimeError("Brakuje modułu AUTO COMPOSER.")
                tmp = self.runtime_dir / "composer"
                tmp.mkdir(parents=True, exist_ok=True)
                stamp = str(int(time.time()*1000))
                inp = tmp / f"input_{stamp}.json"
                out = tmp / f"output_{stamp}.json"
                inp.write_text(json.dumps({"brief":brief,"project":project}, ensure_ascii=False, indent=2), encoding="utf-8")
                cmd = [str(self.venv_python), str(helper), str(inp), str(out)]
                env = os.environ.copy()
                env["PYTHONUTF8"] = "1"
                env["PYTHONUNBUFFERED"] = "1"
                # Composer works on CPU so it never fights DiffRhythm for 6 GB VRAM.
                env["CUDA_VISIBLE_DEVICES"] = ""
                self._composer_status = {"state":"loading","progress":20,"message":"Ładowanie lokalnego Qwen2.5 Composer (pierwszy raz pobiera model)…"}
                proc = subprocess.Popen(cmd, cwd=str(BASE_DIR), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=self._hidden_creationflags())
                self._composer_process = proc
                lines=[]
                assert proc.stdout is not None
                for raw in proc.stdout:
                    line=raw.rstrip("\r\n")
                    lines.append(line)
                    if len(lines)>80: lines=lines[-80:]
                    if line.startswith("SC_COMPOSER_MODEL_READY"):
                        self._composer_status = {"state":"thinking","progress":55,"message":"AI układa strukturę, harmonię, hook i tekst…","log_tail":lines}
                    elif line:
                        self._composer_status = {**self._composer_status,"log_tail":lines}
                    if self._composer_cancel.is_set():
                        self._kill_process_tree(proc)
                        self._composer_status = {"state":"cancelled","progress":0,"message":"AUTO COMPOSER zatrzymany."}
                        return
                rc=proc.wait(); self._composer_process=None
                if rc!=0:
                    raise RuntimeError("AUTO COMPOSER zakończył się błędem. " + (lines[-1] if lines else f"kod {rc}"))
                if not out.exists():
                    raise RuntimeError("AUTO COMPOSER nie zwrócił planu utworu.")
                plan=json.loads(out.read_text(encoding="utf-8"))
                merged=dict(project)
                for key in ("title","language","duration_seconds","bpm","key","time_signature","style","lyrics","chords","composer_hook","composer_structure","composer_notes"):
                    if key in plan and plan[key] not in (None,""):
                        merged[key]=plan[key]
                saved=self.save_project(merged)["project"] if merged.get("project_id") else merged
                self._composer_status={"state":"completed","progress":100,"message":"Plan utworu gotowy. Sprawdź strukturę i kliknij Generuj piosenkę.","project":saved,"plan":plan,"log_tail":lines}
            except Exception as exc:
                self._composer_process=None
                self._composer_status={"state":"error","progress":0,"message":str(exc)}

    def cancel_generation(self) -> dict:
        self._cancel.set()
        self._generation_status = {**self._generation_status, "state":"cancelling", "message":"Zatrzymuję cały proces DiffRhythm…"}
        self._kill_process_tree(self._process)
        self._process = None
        self._generation_status = {**self._generation_status, "state":"cancelled", "progress":0, "message":"Render piosenki zatrzymany."}
        return self.generation_status()
