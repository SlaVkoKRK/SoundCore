from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

_ICON_HANDLES: list[int] = []



def prepare_windows_process() -> None:
    """Give the process a stable Windows application identity before the window exists."""
    if os.name != 'nt':
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SoundCore.AIVoiceStudio')
    except Exception:
        pass


def _rgb_to_colorref(hex_color: str) -> int:
    value = hex_color.lstrip('#')
    r, g, b = (int(value[i:i+2], 16) for i in (0, 2, 4))
    return r | (g << 8) | (b << 16)


def _find_soundcore_window(timeout: float = 12.0) -> int:
    if os.name != 'nt':
        return 0
    user32 = ctypes.windll.user32
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = user32.FindWindowW(None, 'SoundCore')
        if hwnd:
            return int(hwnd)
        time.sleep(0.15)
    return 0


def apply_windows_chrome(icon_path: str | Path, caption_color: str = '#F6F8FC') -> None:
    """Apply Windows shell polish without touching pywebview native/COM objects."""
    if os.name != 'nt':
        return
    hwnd = _find_soundcore_window()
    if not hwnd:
        return
    user32 = ctypes.windll.user32

    # Ensure maximized even if a backend ignores create_window(maximized=True).
    SW_MAXIMIZE = 3
    user32.ShowWindow(hwnd, SW_MAXIMIZE)

    # Set app icon in title bar/task switcher.
    icon_path = str(Path(icon_path).resolve())
    if Path(icon_path).exists():
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        WM_SETICON = 0x0080
        ICON_SMALL, ICON_BIG = 0, 1
        for size, which in ((32, ICON_SMALL), (256, ICON_BIG)):
            handle = user32.LoadImageW(None, icon_path, IMAGE_ICON, size, size, LR_LOADFROMFILE)
            if handle:
                _ICON_HANDLES.append(int(handle))
                user32.SendMessageW(hwnd, WM_SETICON, which, handle)

    # Windows 11 title bar/border colors. Calls simply fail on older builds.
    try:
        dwmapi = ctypes.windll.dwmapi
        color = ctypes.c_int(_rgb_to_colorref(caption_color))
        text = ctypes.c_int(_rgb_to_colorref('#18233D'))
        border = ctypes.c_int(_rgb_to_colorref('#E7EDF6'))
        for attr, val in ((35, color), (36, text), (34, border)):
            dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


def ensure_desktop_shortcut(base_dir: str | Path, icon_path: str | Path) -> bool:
    """Create/refresh a SoundCore desktop shortcut for the current venv."""
    if os.name != 'nt':
        return False
    base_dir = Path(base_dir).resolve()
    icon_path = Path(icon_path).resolve()
    python_exe = Path(sys.executable).resolve()
    pythonw = python_exe.with_name('pythonw.exe')
    if not pythonw.exists():
        pythonw = python_exe
    main_py = base_dir / 'main.py'

    # WScript.Shell resolves OneDrive/redirected Desktop correctly.
    ps = f'''$ws = New-Object -ComObject WScript.Shell;
$desktop = $ws.SpecialFolders("Desktop");
$link = $ws.CreateShortcut((Join-Path $desktop "SoundCore.lnk"));
$link.TargetPath = "{str(pythonw).replace('"','`"')}";
$link.Arguments = '"{str(main_py).replace("'", "''")}"';
$link.WorkingDirectory = "{str(base_dir).replace('"','`"')}";
$link.IconLocation = "{str(icon_path).replace('"','`"')},0";
$link.Description = "SoundCore AI Voice Studio";
$link.Save();'''
    try:
        subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', ps],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return True
    except Exception:
        return False


def setup_windows_shell_async(base_dir: str | Path, icon_path: str | Path) -> None:
    if os.name != 'nt':
        return

    def worker() -> None:
        ensure_desktop_shortcut(base_dir, icon_path)
        apply_windows_chrome(icon_path)

    threading.Thread(target=worker, name='SoundCoreWindowsShell', daemon=True).start()
