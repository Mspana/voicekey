#!/usr/bin/env python3
"""VoiceKey's own icon: "VK" with the status dot in the top-right corner.

Two Windows details make this fiddly, and both were wrong before:

* `iconphoto()` sets the *window* icon but not reliably the taskbar one.
  Windows wants a real .ico file via `iconbitmap()`, with several sizes in it.
* Even with a correct icon, a Python script is grouped under python.exe on the
  taskbar and inherits ITS icon, unless the process declares its own
  AppUserModelID. That is why the taskbar showed the Python logo.

Icons are generated once per state colour and cached on disk.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

APP_ID = "Matthew.VoiceKey.App.1"

_CACHE_DIR = Path(tempfile.gettempdir()) / "voicekey-icons"
_cache: dict = {}

TILE = (241, 236, 225, 255)      # eggshell, matching the window
INK = (35, 33, 32, 255)          # very dark grey


def set_app_id(app_id: str = APP_ID) -> bool:
    """Stop Windows grouping us under python.exe and stealing its icon."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        return True
    except Exception:
        return False


def _font(size: int):
    """Lora SemiBold, same as the wordmark."""
    import textfx
    return textfx.font(size, "SemiBold")


def render(colour: str, size: int = 256):
    """One square icon image: dark rounded tile, "VK", dot top-right."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size

    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=TILE)

    label = "vk"
    fs = int(s * 0.52)
    for _ in range(8):
        f = _font(fs)
        box = d.textbbox((0, 0), label, font=f)
        if (box[2] - box[0]) <= s * 0.68:
            break
        fs = int(fs * 0.92)
    f = _font(fs)
    box = d.textbbox((0, 0), label, font=f)
    # Nudged left and down to leave the top-right corner clear for the dot.
    d.text(((s - (box[2] - box[0])) / 2 - box[0] - s * 0.05,
            (s - (box[3] - box[1])) / 2 - box[1] + s * 0.02),
           label, font=f, fill=INK)

    rgb = tuple(int(colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    r = s * 0.155
    cx, cy = s * 0.755, s * 0.245
    d.ellipse([cx - r * 1.45, cy - r * 1.45, cx + r * 1.45, cy + r * 1.45],
              fill=rgb + (70,))
    # A tile-coloured ring keeps the dot readable over the "K" at small sizes.
    d.ellipse([cx - r * 1.12, cy - r * 1.12, cx + r * 1.12, cy + r * 1.12],
              fill=TILE)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgb + (255,))
    return img


def ico_path(colour: str) -> str | None:
    """Path to a multi-size .ico for this state colour, generated on demand."""
    if colour in _cache:
        return _cache[colour]
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _CACHE_DIR / f"vk_{colour.lstrip('#')}.ico"
        if not path.exists():
            # Several sizes: Windows picks per context (taskbar, alt-tab,
            # title bar) and scales badly if it only finds one.
            render(colour, 256).save(
                path, format="ICO",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
        _cache[colour] = str(path)
        return _cache[colour]
    except Exception:
        _cache[colour] = None
        return None


# ---------------------------------------------------------------- Windows ---

_live_icons: list = []          # HICONs we own; freed when replaced


def apply_to_window(hwnd, path: str) -> bool:
    """Set a window's icon by sending WM_SETICON with a real HICON.

    `iconbitmap()` goes through Tk's own icon handling, which does not reliably
    reach a window whose extended style we changed by hand (which is what
    frameless-plus-taskbar needs). Loading the .ico and messaging the handle
    directly is unambiguous, and it is what the taskbar actually reads.

    Both sizes are set: the taskbar uses ICON_BIG, alt-tab and the window menu
    use ICON_SMALL, and setting only one leaves the other as python.exe's.
    """
    if not sys.platform.startswith("win") or not hwnd or not path:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        u = ctypes.windll.user32
        u.LoadImageW.restype = wintypes.HANDLE
        u.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                 wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                 wintypes.UINT]
        u.SendMessageW.restype = ctypes.c_longlong
        u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                   wintypes.WPARAM, wintypes.LPARAM]
        u.DestroyIcon.argtypes = [wintypes.HANDLE]

        IMAGE_ICON, LR_LOADFROMFILE = 1, 0x00000010
        WM_SETICON, ICON_SMALL, ICON_BIG = 0x0080, 0, 1

        ok = False
        for which, cx, cy in ((ICON_SMALL, 16, 16), (ICON_BIG, 32, 32)):
            h = u.LoadImageW(None, path, IMAGE_ICON, cx, cy, LR_LOADFROMFILE)
            if not h:
                continue
            old = u.SendMessageW(hwnd, WM_SETICON, which, h)
            _live_icons.append(h)
            if old and old in _live_icons:
                try:
                    u.DestroyIcon(old)
                    _live_icons.remove(old)
                except Exception:
                    pass
            ok = True
        return ok
    except Exception:
        return False


def apply_to_console(path: str) -> bool:
    """Give the console window the same icon.

    run-console.bat leaves a console on the taskbar next to the app, and that
    button belongs to python.exe - so without this you see the Python icon even
    when the app's own icon is correct.
    """
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        ctypes.windll.kernel32.GetConsoleWindow.restype = ctypes.c_void_p
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        return apply_to_window(hwnd, path) if hwnd else False
    except Exception:
        return False
