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
from dataclasses import dataclass
from packaging.version import Version

from version import __version__

DEFAULT_CHANNEL_URL = "https://raw.githubusercontent.com/SlaVkoKRK/SoundCore/main/dist/channel.json"

@dataclass
class UpdateInfo:
    version: str
    package_url: str
    sha256: str
    release_notes_url: str = ""

    @property
    def newer(self) -> bool:
        return Version(self.version) > Version(__version__)


def _get_bytes(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"SoundCore/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def check_for_update(channel_url: str = DEFAULT_CHANNEL_URL) -> UpdateInfo:
    data = json.loads(_get_bytes(channel_url).decode("utf-8"))
    return UpdateInfo(
        version=str(data["version"]),
        package_url=str(data["package_url"]),
        sha256=str(data["sha256"]).lower(),
        release_notes_url=str(data.get("release_notes_url", "")),
    )


def read_release_notes(info: UpdateInfo) -> str:
    if not info.release_notes_url:
        return ""
    return _get_bytes(info.release_notes_url).decode("utf-8", errors="replace")


def download_and_stage(info: UpdateInfo, progress=None) -> str:
    temp_root = tempfile.mkdtemp(prefix="soundcore-update-")
    package = os.path.join(temp_root, "soundcore_update.tar.gz")
    req = urllib.request.Request(info.package_url, headers={"User-Agent": f"SoundCore/{__version__}"})
    with urllib.request.urlopen(req, timeout=60) as response, open(package, "wb") as f:
        total = int(response.headers.get("Content-Length", "0") or 0)
        done = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done / total)
    digest = hashlib.sha256()
    with open(package, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest().lower()
    if actual != info.sha256:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise RuntimeError(f"Błąd integralności aktualizacji. SHA256: {actual} != {info.sha256}")
    extracted = os.path.join(temp_root, "payload")
    os.makedirs(extracted, exist_ok=True)
    with tarfile.open(package, "r:gz") as tf:
        root = os.path.realpath(extracted)
        for member in tf.getmembers():
            target = os.path.realpath(os.path.join(extracted, member.name))
            if not (target == root or target.startswith(root + os.sep)):
                raise RuntimeError("Niebezpieczna ścieżka w paczce aktualizacji.")
        tf.extractall(extracted)
    return extracted


def launch_apply_update(staged_dir: str, app_root: str) -> None:
    script = os.path.join(app_root, "updater", "apply_update.py")
    args = [sys.executable, script, "--source", staged_dir, "--target", app_root, "--pid", str(os.getpid()), "--restart", os.path.join(app_root, "main.py")]
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(args, cwd=app_root, **kwargs)
