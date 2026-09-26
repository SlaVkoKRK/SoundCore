@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0repair_update.ps1" -AppDir "%~dp0"
endlocal
