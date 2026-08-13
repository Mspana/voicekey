@echo off
rem Prints everything needed to diagnose "it does not start".
setlocal

set "PY=python"
if exist "%~dp0venv\Scripts\python.exe"  set "PY=%~dp0venv\Scripts\python.exe"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%~dp0env\Scripts\python.exe"   set "PY=%~dp0env\Scripts\python.exe"

echo ================ VoiceKey doctor ================
echo Script folder : %~dp0
echo Python        : %PY%
"%PY%" -c "import sys; print('Version       :', sys.version.split()[0]); print('Executable    :', sys.executable)"
echo.
echo -- OPENAI_API_KEY --
if defined OPENAI_API_KEY (echo present in this shell) else (echo NOT SET in this shell)
"%PY%" -c "import json,os,pathlib; c=json.load(open(pathlib.Path(r'%~dp0')/'config.json')); print('config.json api_key:', 'set' if c.get('api_key') else 'not set')"
echo.
echo -- packages --
"%PY%" -c "import importlib;[print(f'{m:14}', 'OK' if importlib.util.find_spec(m) else 'MISSING') for m in ('numpy','sounddevice','keyboard','pyperclip','openai','PIL','tkinter')]"
echo.
echo -- last 20 log lines --
if exist "%~dp0voicekey.log" (powershell -NoProfile -Command "Get-Content '%~dp0voicekey.log' -Tail 20") else (echo no voicekey.log yet)
echo.
pause
