@echo off
setlocal
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe publish_release.py %*
) else (
    python publish_release.py %*
)

pause
