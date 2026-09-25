from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
import time

PRESERVE_TOP_LEVEL = {"voice_profiles", "output", "venv", ".venv", ".git"}


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, 0, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def copy_payload(source: str, target: str):
    for name in os.listdir(source):
        if name in PRESERVE_TOP_LEVEL:
            continue
        src = os.path.join(source, name)
        dst = os.path.join(target, name)
        if os.path.isdir(src):
            os.makedirs(dst, exist_ok=True)
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--pid", required=True, type=int)
    p.add_argument("--restart", required=True)
    args = p.parse_args()
    deadline = time.time() + 30
    while pid_exists(args.pid) and time.time() < deadline:
        time.sleep(0.25)
    if pid_exists(args.pid):
        raise RuntimeError("SoundCore nie zamknął się w wymaganym czasie.")
    copy_payload(args.source, args.target)
    subprocess.Popen([sys.executable, args.restart], cwd=args.target)
    shutil.rmtree(os.path.dirname(args.source), ignore_errors=True)

if __name__ == "__main__":
    main()
