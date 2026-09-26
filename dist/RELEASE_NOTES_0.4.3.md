# SoundCore 0.4.3

## Windows installer pipeline hotfix

- Fixed the GitHub Actions validation step that prevented the Windows installer from being compiled.
- The validator no longer contains PowerShell interpolation that causes a parser error.
- The workflow now verifies `bootstrap.ps1` and `SoundCore.iss`, then continues to Inno Setup compilation.
- The generated `SoundCore-Setup-0.4.3.exe` is uploaded as a workflow artifact and attached to the GitHub Release.

Application functionality is unchanged from 0.4.2.
