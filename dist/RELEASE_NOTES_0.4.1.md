# SoundCore 0.4.1

## Windows installer hotfix

- Fixed the Windows launcher path used by Inno Setup (`venv\Scripts\pythonw.exe`).
- The installer now verifies `python.exe`, `pythonw.exe` and the `.installed` marker before creating shortcuts or launching SoundCore.
- A failed bootstrap can no longer fall through to a misleading `CreateProcess; code 2` error.
- Bootstrap failures now stop installation with a clear message pointing to `install.log`.
- Added detailed stdout/stderr logging for Python, pip, virtual-environment and runtime-verification steps.
- Added explicit validation immediately after venv creation and again before setup completion.
- Existing application update behavior remains unchanged.
