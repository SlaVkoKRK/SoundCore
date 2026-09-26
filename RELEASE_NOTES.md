# SoundCore 0.3.4

Windows/UI quality hotfix.

- SoundCore starts maximized using the native pywebview `maximized` mode.
- System title bar is styled to match the light SoundCore theme on supported Windows builds.
- Added a native SoundCore `.ico` for the title bar, Alt-Tab and taskbar identity.
- SoundCore automatically creates/refreshes a desktop shortcut that starts the app through `pythonw.exe` from the active venv.
- Training stop controls are shown only while a training job is actually running; start/stop buttons now track the real training state.
- CUDA repair state is reconciled with the actual PyTorch CUDA state. If CUDA is active, the stale “restart SoundCore” prompt disappears automatically.
- CUDA repair no longer lets pip upgrade NumPy/SciPy unexpectedly. PyTorch CUDA wheels are installed with `--no-deps`, then SoundCore restores `numpy==1.22.0` and `scipy==1.10.1`.
- Normal WebView2 diagnostic logging is reduced to avoid noisy Chromium console messages during shutdown.
- Requirements now explicitly pin SciPy 1.10.1 for the current NumPy/TTS stack.
