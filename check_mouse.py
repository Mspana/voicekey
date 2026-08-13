#!/usr/bin/env python3
"""Diagnostic for "it clicked where the cursor already was".

Run this on the Windows machine and paste the output. It isolates the three
things that cause it, without needing the rest of the app:

  1. Cursor moves being ignored entirely.
  2. DPI scaling - the overlay is drawn in one coordinate space and the cursor
     moved in another, so clicks land at a consistent offset. This is the usual
     culprit on a 4K display at 150%.
  3. Timing - the click dispatching before the move has landed.

  python check_mouse.py
"""

import sys
import time

import mouse

print("=" * 64)
print("  VoiceKey mouse diagnostic")
print("=" * 64)
print(f"  platform          : {sys.platform}")
print(f"  mouse backend     : {'Windows SendInput' if mouse.IS_WINDOWS else 'STUB (no real input!)'}")

if not mouse.IS_WINDOWS:
    print("\n  This is the stub backend - it records calls instead of moving")
    print("  the cursor. Nothing will click. Run this on Windows.")
    sys.exit(0)

import ctypes

awareness = ctypes.c_int()
try:
    ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
    levels = {0: "UNAWARE  <-- coordinates will be wrong on a scaled display",
              1: "SYSTEM   <-- wrong on a multi-monitor mixed-DPI setup",
              2: "PER-MONITOR (correct)"}
    print(f"  DPI awareness     : {levels.get(awareness.value, awareness.value)}")
except Exception as exc:
    print(f"  DPI awareness     : could not query ({exc})")

x, y, w, h = mouse.virtual_screen()
print(f"  virtual screen    : {w} x {h} at ({x}, {y})")

try:
    user32 = ctypes.WinDLL("user32")
    prim = (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    print(f"  primary monitor   : {prim[0]} x {prim[1]}")
    if prim[0] > w or prim[1] > h:
        print("    !! primary is larger than the virtual desktop - DPI mismatch")
except Exception:
    pass

print("\n  Moving the cursor to five points and reading the position back.")
print("  'got' should equal 'want' exactly.\n")

targets = [
    (x + w // 2, y + h // 2, "centre"),
    (x + 100, y + 100, "top-left area"),
    (x + w - 100, y + 100, "top-right area"),
    (x + 100, y + h - 100, "bottom-left area"),
    (x + w - 100, y + h - 100, "bottom-right area"),
]

worst = 0
for tx, ty, label in targets:
    mouse.move_to(tx, ty)
    time.sleep(0.05)
    gx, gy = mouse.position()
    dx, dy = gx - tx, gy - ty
    worst = max(worst, abs(dx), abs(dy))
    flag = "  OK" if (dx, dy) == (0, 0) else f"  OFF BY ({dx}, {dy})"
    print(f"    {label:20} want ({tx}, {ty})  got ({gx}, {gy}){flag}")

print()
if worst == 0:
    print("  Cursor movement is exact. If clicks still land in the wrong")
    print("  place, it is the overlay teardown or the settle delay - raise")
    print("  grid.settle_ms and grid.teardown_ms in config.json.")
elif worst < 5:
    print(f"  Off by up to {worst}px - rounding, harmless.")
else:
    print(f"  Off by up to {worst}px. That is a DPI scaling mismatch.")
    print("  Set Windows display scaling to 100%, or right-click python.exe ->")
    print("  Properties -> Compatibility -> Change high DPI settings ->")
    print("  Override high DPI scaling behaviour: Application.")

print("\n" + "=" * 64)
