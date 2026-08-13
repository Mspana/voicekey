#!/usr/bin/env python3
"""Cursor movement and clicks.

Windows uses SendInput via ctypes - no extra dependency, and SendInput is the
only method that reliably reaches applications using raw input. On other
platforms this degrades to a recording stub so the rest of the code (and the
tests) still run.
"""

from __future__ import annotations

import sys
import time

IS_WINDOWS = sys.platform.startswith("win")

# Recorded actions, used by the test suite on non-Windows platforms.
RECORDED: list = []


if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    # Per-monitor DPI awareness, so coordinates match physical pixels on
    # scaled displays. Must run before any window is created.
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass

    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79

    INPUT_MOUSE = 0
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_VIRTUALDESK = 0x4000

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]

    class _INPUTunion(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", _INPUTunion)]

    def _send(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> None:
        mi = MOUSEINPUT(dx, dy, data, flags, 0, None)
        inp = INPUT(INPUT_MOUSE, _INPUTunion(mi))
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def virtual_screen() -> tuple:
        """(x, y, width, height) spanning every monitor."""
        return (user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
                user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
                user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
                user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))

    def move_to(x: int, y: int) -> None:
        user32.SetCursorPos(int(x), int(y))

    def position() -> tuple:
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)

    def _click(down: int, up: int, count: int = 1) -> None:
        for i in range(count):
            _send(down)
            _send(up)
            if i + 1 < count:
                time.sleep(0.04)

    def left_click(count: int = 1):   _click(MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, count)
    def right_click(count: int = 1):  _click(MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, count)
    def middle_click(count: int = 1): _click(MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP, count)

    def left_down():  _send(MOUSEEVENTF_LEFTDOWN)
    def left_up():    _send(MOUSEEVENTF_LEFTUP)

    def scroll(clicks: int) -> None:
        _send(MOUSEEVENTF_WHEEL, data=int(clicks) * 120)

    def hold_left(seconds: float) -> None:
        left_down()
        time.sleep(max(0.0, float(seconds)))
        left_up()

else:  # ---------------------------------------------------------- stub
    _pos = [0, 0]

    def virtual_screen() -> tuple:
        return (0, 0, 1920, 1080)

    def move_to(x: int, y: int) -> None:
        _pos[0], _pos[1] = int(x), int(y)
        RECORDED.append(("move", int(x), int(y)))

    def position() -> tuple:
        return (_pos[0], _pos[1])

    def left_click(count: int = 1):   RECORDED.append(("left_click", count))
    def right_click(count: int = 1):  RECORDED.append(("right_click", count))
    def middle_click(count: int = 1): RECORDED.append(("middle_click", count))
    def left_down():                  RECORDED.append(("left_down",))
    def left_up():                    RECORDED.append(("left_up",))
    def scroll(clicks: int):          RECORDED.append(("scroll", int(clicks)))

    def hold_left(seconds: float):    RECORDED.append(("hold_left", float(seconds)))
