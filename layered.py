#!/usr/bin/env python3
"""A Windows layered window: a borderless, click-through, always-on-top surface
that composites an RGBA bitmap onto the desktop with real per-pixel alpha.

This is the only way to get a genuinely soft glow. tkinter offers whole-window
opacity and a chroma key, neither of which is a gradient, and stipple dithering
is holes rather than translucency.

WS_EX_TRANSPARENT makes it invisible to hit-testing, so it can never eat a
click. WS_EX_NOACTIVATE keeps it from stealing focus, which matters a lot here:
the whole point is to show it *while the user is typing into something else*.

EVERY function below declares argtypes and restype. On 64-bit Python, ctypes
defaults an undeclared return value to C `int` - 32 bits - so window and DC
handles get silently truncated, and an undeclared argument gets converted to
c_int, so a real 64-bit LPARAM raises "int too long to convert". Both failures
look like nonsense at the call site far away from the missing declaration.
"""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # LRESULT / LONG_PTR are pointer-sized, so they must follow the build.
    LRESULT = ctypes.c_int64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
    HCURSOR = wintypes.HANDLE
    HBRUSH = wintypes.HANDLE
    HGDIOBJ = wintypes.HANDLE

    WS_POPUP = 0x80000000
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOPMOST = 0x00000008
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_NOACTIVATE = 0x08000000

    ULW_ALPHA = 0x00000002
    AC_SRC_OVER = 0x00
    AC_SRC_ALPHA = 0x01
    BI_RGB = 0
    DIB_RGB_COLORS = 0
    SW_SHOWNOACTIVATE = 4
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_NOACTIVATE = 0x0010

    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSEX(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT),
                    ("style", wintypes.UINT),
                    ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON),
                    ("hCursor", HCURSOR),
                    ("hbrBackground", HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR),
                    ("hIconSm", wintypes.HICON)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD),
                    ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long),
                    ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD),
                    ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                    ("bmiColors", wintypes.DWORD * 3)]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte),
                    ("BlendFlags", ctypes.c_ubyte),
                    ("SourceConstantAlpha", ctypes.c_ubyte),
                    ("AlphaFormat", ctypes.c_ubyte)]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class SIZE(ctypes.Structure):
        _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

    # ---- signatures. Not optional on 64-bit; see the module docstring. ----
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

    user32.DefWindowProcW.restype = LRESULT
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM]

    user32.RegisterClassExW.restype = wintypes.ATOM
    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEX)]

    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]

    user32.DestroyWindow.restype = wintypes.BOOL
    user32.DestroyWindow.argtypes = [wintypes.HWND]

    user32.ShowWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

    user32.SetWindowPos.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    wintypes.UINT]

    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

    user32.UpdateLayeredWindow.restype = wintypes.BOOL
    user32.UpdateLayeredWindow.argtypes = [
        wintypes.HWND, wintypes.HDC, ctypes.POINTER(POINT),
        ctypes.POINTER(SIZE), wintypes.HDC, ctypes.POINTER(POINT),
        wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]

    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.SelectObject.restype = HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteObject.argtypes = [HGDIOBJ]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]

    def _wndproc(hwnd, msg, wparam, lparam):
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    _WNDPROC_REF = WNDPROC(_wndproc)      # must outlive every window
    _CLASS_NAME = "VoiceKeyGlowLayer"
    _registered = [False]


def available() -> bool:
    return IS_WINDOWS


class LayeredGlow:
    """Click-through per-pixel-alpha overlay covering `rect`."""

    def __init__(self, rect):
        if not IS_WINDOWS:
            raise RuntimeError("layered windows are Windows-only")

        self.hwnd = None
        self.screen_dc = None
        self.mem_dc = None
        self.hbitmap = None
        self.old_bitmap = None

        self.x, self.y, self.w, self.h = (int(v) for v in rect)
        hinst = kernel32.GetModuleHandleW(None)

        if not _registered[0]:
            wc = WNDCLASSEX()
            wc.cbSize = ctypes.sizeof(WNDCLASSEX)
            wc.style = 0
            wc.lpfnWndProc = _WNDPROC_REF
            wc.hInstance = hinst
            wc.lpszClassName = _CLASS_NAME
            if not user32.RegisterClassExW(ctypes.byref(wc)):
                err = ctypes.get_last_error()
                if err not in (0, 1410):          # 1410 = already registered
                    raise ctypes.WinError(err)
            _registered[0] = True

        self.hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
            | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            _CLASS_NAME, None, WS_POPUP,
            self.x, self.y, self.w, self.h,
            None, None, hinst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())

        self.screen_dc = user32.GetDC(None)
        self.mem_dc = gdi32.CreateCompatibleDC(self.screen_dc)

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = self.w
        bmi.bmiHeader.biHeight = -self.h          # negative = top-down rows
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB

        self.bits = ctypes.c_void_p()
        self.hbitmap = gdi32.CreateDIBSection(
            self.mem_dc, ctypes.byref(bmi), DIB_RGB_COLORS,
            ctypes.byref(self.bits), None, 0)
        if not self.hbitmap:
            err = ctypes.get_last_error()
            self.destroy()
            raise ctypes.WinError(err)
        self.old_bitmap = gdi32.SelectObject(self.mem_dc, self.hbitmap)
        self.nbytes = self.w * self.h * 4

        # A numpy view straight onto the DIB's pixels. Callers render into this
        # and then call commit(), so a frame costs zero copies - as opposed to
        # 8MB per frame at 1080p, or 33MB at 4K, if we serialised to bytes.
        self.array = None
        try:
            import numpy as np
            block = (ctypes.c_ubyte * self.nbytes).from_address(self.bits.value)
            self.array = np.frombuffer(block, dtype=np.uint8).reshape(
                self.h, self.w, 4)
            self.array[:] = 0
        except Exception:
            self.array = None

        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)

    def update(self, bgra) -> None:
        """Copy premultiplied BGRA in, then blit. Prefer `array` + `commit()`."""
        if not self.hwnd:
            return
        buf = bgra.tobytes() if hasattr(bgra, "tobytes") else bytes(bgra)
        if len(buf) != self.nbytes:
            raise ValueError(f"expected {self.nbytes} bytes, got {len(buf)}")
        ctypes.memmove(self.bits, buf, self.nbytes)
        self.commit()

    def commit(self) -> None:
        """Blit whatever is currently in the bitmap to the screen."""
        if not self.hwnd:
            return
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        src = POINT(0, 0)
        dst = POINT(self.x, self.y)
        size = SIZE(self.w, self.h)
        ok = user32.UpdateLayeredWindow(
            self.hwnd, self.screen_dc, ctypes.byref(dst), ctypes.byref(size),
            self.mem_dc, ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA)
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())

    def raise_(self) -> None:
        if self.hwnd:
            user32.SetWindowPos(self.hwnd, wintypes.HWND(-1), 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def destroy(self) -> None:
        try:
            if self.hbitmap:
                if self.old_bitmap:
                    gdi32.SelectObject(self.mem_dc, self.old_bitmap)
                gdi32.DeleteObject(self.hbitmap)
                self.hbitmap = None
            if self.mem_dc:
                gdi32.DeleteDC(self.mem_dc)
                self.mem_dc = None
            if self.screen_dc:
                user32.ReleaseDC(None, self.screen_dc)
                self.screen_dc = None
            if self.hwnd:
                user32.DestroyWindow(self.hwnd)
                self.hwnd = None
        except Exception:
            pass
