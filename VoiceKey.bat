@echo off
rem VoiceKey - no console window.
rem If nothing appears, read voicekey.log next to this file, or use
rem run-console.bat which keeps the window open and shows everything.
setlocal

rem Prefer a virtualenv sitting next to this script. A bare `pythonw` picks up
rem the SYSTEM Python, which will not have the packages installed in the venv -
rem that alone makes the app die instantly with no window and no message.
set "PYW=pythonw"
if exist "%~dp0venv\Scripts\pythonw.exe"  set "PYW=%~dp0venv\Scripts\pythonw.exe"
if exist "%~dp0.venv\Scripts\pythonw.exe" set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if exist "%~dp0env\Scripts\pythonw.exe"   set "PYW=%~dp0env\Scripts\pythonw.exe"

start "" "%PYW%" "%~dp0app.py"
