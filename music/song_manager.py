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
        self._espeak_install_status = {"state": "resolving", "progress": 5, "message": "Szukam oficjalnego instalatora eSpeak NG x64…"}
        threading.Thread(target=self._install_espeak_worker, name="SoundCoreEspeakInstall", daemon=True).start()
        return self.espeak_install_status()

    def _install_espeak_worker(self) -> None:
        try:
            api_url = "https://api.github.com/repos/espeak-ng/espeak-ng/releases/latest"
            req = urllib.request.Request(api_url, headers={"User-Agent": "SoundCore/0.7.4", "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                release = json.loads(resp.read().decode("utf-8"))
            assets = release.get("assets") or []
            asset = next((a for a in assets if str(a.get("name", "")).lower().endswith("x64.msi")), None)
            if not asset:
                raise RuntimeError("Nie znaleziono oficjalnego instalatora eSpeak NG x64 w najnowszym wydaniu GitHub.")
            url = asset.get("browser_download_url")
            if not url:
                raise RuntimeError("GitHub nie zwrócił adresu instalatora eSpeak NG.")
            target = self.runtime_dir / str(asset.get("name") or "espeak-ng-x64.msi")
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
        return {"ok": True, **data}

    def start_generation(self, project: dict) -> dict:
        if self._process and self._process.poll() is None:
            raise RuntimeError("Render piosenki już trwa.")
        if not self.venv_python.exists() or not (self.repo_dir / "infer" / "infer.py").exists():
            raise RuntimeError("Najpierw zainstaluj silnik DiffRhythm w Song Studio.")
        espeak = self._espeak()
        if not espeak["ok"]:
            raise RuntimeError("Brakuje eSpeak NG. Zainstaluj eSpeak NG dla Windows i uruchom SoundCore ponownie.")
        saved = self.save_project(project)["project"]
        self._cancel.clear()
        self._generation_status = {"state": "starting", "progress": 2, "message": "Przygotowanie projektu…", "project_id": saved["project_id"]}
        threading.Thread(target=self._generation_worker, args=(saved,), name="SoundCoreSongRender", daemon=True).start()
        return self.generation_status()

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
                self._generation_status = {"state": "rendering", "progress": 15, "message": "DiffRhythm generuje piosenkę. Pierwszy render pobiera również modele…", "project_id": pid}
                with self.log_path.open("w", encoding="utf-8", errors="replace") as log:
                    self._process = subprocess.Popen(cmd, cwd=str(self.repo_dir / "infer"), env=env, stdout=log, stderr=subprocess.STDOUT)
                    while self._process.poll() is None:
                        if self._cancel.is_set():
                            self._process.terminate()
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

    def cancel_generation(self) -> dict:
        self._cancel.set()
        if self._process and self._process.poll() is None:
            try: self._process.terminate()
            except Exception: pass
        return self.generation_status()
