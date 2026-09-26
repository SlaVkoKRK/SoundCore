# SoundCore 0.4.0

## Windows installer

- Added a native Windows installer project based on Inno Setup.
- GitHub Actions automatically builds `SoundCore-Setup-<version>.exe` when a GitHub Release is published.
- Per-user installation to `%LOCALAPPDATA%\Programs\SoundCore` without requiring administrator rights for SoundCore itself.
- Automatic Python 3.10 environment creation and dependency installation.
- Automatic Microsoft WebView2 Runtime bootstrap.
- NVIDIA GPU detection with PyTorch CUDA 12.4 installation and CPU fallback.
- Desktop and Start menu shortcuts with the SoundCore icon.
- Existing voice profiles and user recordings are not removed by normal application updates.
- The installer verifies the Python runtime before finishing.

## Distribution

The regular SoundCore release/update package remains unchanged. The installer is an additional GitHub Release asset intended for clean installations on new Windows systems.
