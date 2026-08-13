@echo off
rem Build a single VoiceKey.exe. Run this on the machine you want it for.
rem PyInstaller cannot cross-compile: a Windows exe must be built on Windows.
setlocal

set "PY=python"
if exist "%~dp0venv\Scripts\python.exe"  set "PY=%~dp0venv\Scripts\python.exe"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%~dp0env\Scripts\python.exe"   set "PY=%~dp0env\Scripts\python.exe"

echo Using %PY%
echo.

set "VOICEKEY_CONFIG=config.json"
echo Bake your OpenAI key into the exe?
echo   This is CONVENIENCE, NOT SECURITY - a one-file exe is an archive and the
echo   key can be extracted from it. Only do this for someone you would hand the
echo   key to anyway, and use a scoped, budget-capped key.
echo.
set /p EMBED="Embed a key? (y/N): "
if /i not "%EMBED%"=="y" goto :build

set /p KEY="Paste the key: "
"%PY%" "%~dp0embed_key.py" %KEY% || goto :fail
set "VOICEKEY_CONFIG=build-config.json"
echo.

:build
echo [1/3] dependencies
"%PY%" -m pip install -q -r "%~dp0requirements.txt" || goto :fail
"%PY%" -m pip install -q pyinstaller || goto :fail

echo [2/3] building (this takes a minute)
pushd "%~dp0"
"%PY%" -m PyInstaller voicekey.spec --noconfirm --clean || goto :fail
popd

if exist "%~dp0build-config.json" del "%~dp0build-config.json"

echo [3/3] done
echo.
echo   dist\VoiceKey.exe
echo.
echo Copy that one file anywhere and double-click it.
if /i "%EMBED%"=="y" (
  echo The key is baked in - it will start straight away.
) else (
  echo On first run it asks for the OpenAI key and saves it beside itself.
)
echo.
pause
exit /b 0

:fail
if exist "%~dp0build-config.json" del "%~dp0build-config.json"
echo.
echo BUILD FAILED - see the messages above.
pause
exit /b 1
