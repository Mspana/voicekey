@echo off
rem Sets the console + a test window icon and reports what happened.
rem Run this if the taskbar still shows the Python logo.
setlocal
set "PY=python"
if exist "%~dp0venv\Scripts\python.exe"  set "PY=%~dp0venv\Scripts\python.exe"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%~dp0env\Scripts\python.exe"   set "PY=%~dp0env\Scripts\python.exe"
"%PY%" "%~dp0icon_test.py"
pause
