@echo off
rem Same app, with a console. Use this first, and any time it misbehaves -
rem errors print here AND go to voicekey.log.
setlocal

set "PY=python"
if exist "%~dp0venv\Scripts\python.exe"  set "PY=%~dp0venv\Scripts\python.exe"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%~dp0env\Scripts\python.exe"   set "PY=%~dp0env\Scripts\python.exe"

echo Using: %PY%
echo.
"%PY%" "%~dp0app.py"
echo.
echo ---- exited. Press any key to close. ----
pause >nul
