# SoundCore 0.4.2

## Installer hotfix

- Fixed a PowerShell parser error in `installer/bootstrap.ps1` that prevented the bootstrap script from starting at all (`$Label:` -> `${Label}:`).
- Added installer-side `setup-bootstrap.log`, created before PowerShell starts, so bootstrap launch failures are always diagnosable.
- Installer still validates `venv\\Scripts\\python.exe`, `pythonw.exe`, and `.installed` before creating working launch shortcuts.
- Existing Fast Start, updater, profile library, media trimming, CUDA repair and training features are unchanged.
