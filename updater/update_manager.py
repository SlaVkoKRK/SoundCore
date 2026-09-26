from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import urllib.parse
import time
import zipfile
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHANNEL_URL = "https://raw.githubusercontent.com/SlaVkoKRK/SoundCore/main/dist/channel.json"
PROTECTED_TOP_LEVEL = {"voice_profiles", "output", ".venv", "venv", ".git"}


def _version_tuple(v: str) -> tuple[int, ...]:
    parts = []
    for p in str(v).strip().lstrip("v").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            num = "".join(ch for ch in p if ch.isdigit())
            parts.append(int(num or 0))
    return tuple(parts)


def check_for_update(current_version: str, channel_url: str = DEFAULT_CHANNEL_URL) -> dict:
    # raw.githubusercontent.com/CDN may briefly cache channel.json after a release.
    # Always request a unique URL and explicitly disable intermediary/client caches.
    separator = "&" if "?" in channel_url else "?"
    fresh_url = f"{channel_url}{separator}_soundcore_ts={int(time.time() * 1000)}"
    req = urllib.request.Request(
        fresh_url,
        headers={
            "User-Agent": "SoundCore-Updater",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        channel = json.loads(r.read().decode("utf-8"))
    latest = str(channel.get("version", "0.0.0"))
    return {
        "ok": True,
        "current_version": current_version,
        "latest_version": latest,
        "update_available": _version_tuple(latest) > _version_tuple(current_version),
        "channel": channel,
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def _safe_extract_zip(zip_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        dest_abs = dest.resolve()
        for name in zf.namelist():
            target = (dest / name).resolve()
            if not str(target).startswith(str(dest_abs)):
                raise RuntimeError(f"Niebezpieczna ścieżka w paczce: {name}")
        zf.extractall(dest)


def download_update(channel: dict) -> dict:
    url = channel.get("package_url")
    expected = str(channel.get("sha256", "")).lower()
    if not url or not expected:
        raise RuntimeError("Kanał aktualizacji nie zawiera package_url/sha256.")
    temp_dir = Path(tempfile.mkdtemp(prefix="soundcore-update-"))
    package = temp_dir / "soundcore_update.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "SoundCore-Updater"})
    with urllib.request.urlopen(req, timeout=60) as r, package.open("wb") as f:
        shutil.copyfileobj(r, f)
    actual = _sha256(package)
    if actual != expected:
        raise RuntimeError(f"SHA256 nie zgadza się. Oczekiwano {expected}, otrzymano {actual}.")
    extract_dir = temp_dir / "payload"
    extract_dir.mkdir()
    _safe_extract_zip(package, extract_dir)
    return {"temp_dir": str(temp_dir), "package": str(package), "payload": str(extract_dir), "sha256": actual}


def create_apply_helper(payload_dir: str, app_root: str | None = None) -> str:
    app = Path(app_root or APP_ROOT)
    temp_dir = Path(payload_dir).parent
    helper = temp_dir / "apply_update.py"
    helper.write_text(
        '''from __future__ import annotations
import os, shutil, subprocess, sys, time
from pathlib import Path

payload = Path(sys.argv[1]).resolve()
app = Path(sys.argv[2]).resolve()
pid = int(sys.argv[3])
protected = {"voice_profiles", "output", ".venv", "venv", ".git"}

for _ in range(120):
    try:
        if os.name == "nt":
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                time.sleep(0.25)
                continue
        else:
            os.kill(pid, 0)
            time.sleep(0.25)
            continue
    except Exception:
        break

for child in payload.iterdir():
    if child.name in protected:
        continue
    dest = app / child.name
    if child.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(child, dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(child, dest)

requirements = app / "requirements.txt"
if requirements.exists():
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements)], cwd=str(app), check=False)

subprocess.Popen([sys.executable, str(app / "main.py")], cwd=str(app), creationflags=(0x00000008 if os.name == "nt" else 0))
''',
        encoding="utf-8",
    )
    return str(helper)


def launch_apply(payload_dir: str, app_root: str | None = None) -> None:
    app = str(Path(app_root or APP_ROOT).resolve())
    helper = create_apply_helper(payload_dir, app)
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    subprocess.Popen([sys.executable, helper, payload_dir, app, str(os.getpid())], creationflags=flags, close_fds=(os.name != "nt"))
