# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a single double-clickable VoiceKey.exe.

    build.bat        (or:  pyinstaller voicekey.spec --noconfirm)

Notes on the non-obvious bits:

* `sounddevice` ships a PortAudio DLL as package data. PyInstaller does not
  find it by module analysis, so it is collected explicitly - without this the
  exe builds fine and then dies at startup with "PortAudio library not found".
* The font is bundled as data and read through paths.resource(), which resolves
  into the unpacked bundle at runtime.
* config.json is bundled too, but paths.config_path() copies it OUT next to the
  exe on first run, because the bundle directory is deleted on exit.
* PIL._tkinter_finder is a hidden import - PIL.ImageTk needs it and nothing
  references it by name.
"""

import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

# build.bat can point this at a temporary config that has the key baked in.
# See build.bat - it is a convenience, NOT a secret: anything inside the exe
# can be extracted.
CONFIG = os.environ.get("VOICEKEY_CONFIG", "config.json")

sd_datas, sd_binaries, sd_hidden = collect_all("sounddevice")

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=sd_binaries,
    datas=[
        ("fonts/Lora-Variable.ttf", "fonts"),
        ("fonts/OFL-Lora.txt", "fonts"),
        (CONFIG, "."),
    ] + sd_datas,
    hiddenimports=[
        "PIL._tkinter_finder",
        "openai",
        "pyperclip",
        "keyboard",
    ] + sd_hidden + collect_submodules("openai"),
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "pandas", "pytest", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VoiceKey",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,           # no console window
    disable_windowed_traceback=False,
    icon="VoiceKey.ico",
)
