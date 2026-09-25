from __future__ import annotations

import hashlib
import json
import os
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
REPO = os.environ.get("SOUNDCORE_REPO", "SlaVkoKRK/SoundCore")
BRANCH = os.environ.get("SOUNDCORE_BRANCH", "main")

EXCLUDE_TOP = {".git", ".venv", "venv", "voice_profiles", "output", "release_bundle", "dist"}
EXCLUDE_SUFFIXES = {".pth", ".pt", ".ckpt", ".index", ".onnx", ".tflite", ".pyc"}


def read_version() -> str:
    ns = {}
    exec((ROOT / "version.py").read_text(encoding="utf-8"), ns)
    return ns["__version__"]


def allowed(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if rel.parts and rel.parts[0] in EXCLUDE_TOP:
        return False
    if any(part == "__pycache__" for part in rel.parts):
        return False
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    if path.name.startswith(".env"):
        return False
    return True


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    version = read_version()
    tag = f"v{version}"
    DIST.mkdir(exist_ok=True)
    update_name = "soundcore_update.tar.gz"
    source_name = f"SoundCore-{version}-source.tar.gz"
    update_path = DIST / update_name
    source_path = DIST / source_name

    files = [p for p in ROOT.rglob("*") if p.is_file() and allowed(p)]
    for target in (update_path, source_path):
        with tarfile.open(target, "w:gz") as tf:
            for p in files:
                tf.add(p, arcname=p.relative_to(ROOT).as_posix(), recursive=False)

    update_hash = sha256(update_path)
    source_hash = sha256(source_path)
    (DIST / f"{update_name}.sha256").write_text(f"{update_hash}  {update_name}\n", encoding="ascii")
    (DIST / f"{source_name}.sha256").write_text(f"{source_hash}  {source_name}\n", encoding="ascii")

    release_notes_name = f"RELEASE_NOTES_{version}.md"
    release_notes = ROOT / "RELEASE_NOTES.md"
    release_notes_copy = DIST / release_notes_name
    release_notes_copy.write_text(release_notes.read_text(encoding="utf-8"), encoding="utf-8")

    channel = {
        "version": version,
        "min_version": "0.2.0",
        "sha256": update_hash,
        "package_encoding": "tar.gz",
        "package_url": f"https://github.com/{REPO}/releases/download/{tag}/{update_name}",
        "sha256_url": f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/dist/{update_name}.sha256",
        "release_notes_url": f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/dist/{release_notes_name}",
    }
    (DIST / "channel.next.json").write_text(json.dumps(channel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "app": "SoundCore",
        "version": version,
        "tag": tag,
        "repo": REPO,
        "update_package": update_name,
        "update_sha256": update_hash,
        "source_package": source_name,
        "source_sha256": source_hash,
        "release_notes": release_notes_name,
    }
    (DIST / "release.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
