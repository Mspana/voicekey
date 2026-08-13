#!/usr/bin/env python3
"""Screen capture for the grid magnifier.

The full screen is grabbed once, *before* the overlay window appears, and the
magnifier crops from that cached image. Grabbing on demand would capture the
overlay itself.
"""

from __future__ import annotations

import sys

IS_WINDOWS = sys.platform.startswith("win")

try:
    from PIL import Image, ImageGrab, ImageTk  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def available() -> bool:
    return HAVE_PIL


def grab_screen(rect):
    """Return a PIL Image of `rect` = (x, y, w, h), or None if unavailable."""
    if not HAVE_PIL:
        return None
    x, y, w, h = (int(v) for v in rect)
    try:
        if IS_WINDOWS:
            # all_screens spans the virtual desktop rather than just the primary.
            return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
        return ImageGrab.grab(bbox=(x, y, x + w, y + h))
    except Exception:
        return None


def crop_and_scale(image, box, size):
    """Crop `box` = (l, t, r, b) from `image` and scale to `size` = (w, h).

    Nearest-neighbour on purpose: at these magnifications a smoothed image
    makes small UI elements harder to identify, not easier.
    """
    if image is None:
        return None
    try:
        from PIL import Image as _Image
        l, t, r, b = (int(round(v)) for v in box)
        l = max(0, min(l, image.width - 1))
        t = max(0, min(t, image.height - 1))
        r = max(l + 1, min(r, image.width))
        b = max(t + 1, min(b, image.height))
        w, h = (max(1, int(size[0])), max(1, int(size[1])))
        return image.crop((l, t, r, b)).resize((w, h), _Image.NEAREST)
    except Exception:
        return None


def fit_box(region_w: float, region_h: float, max_w: int, max_h: int):
    """Largest (w, h) inside max_w x max_h preserving the region's aspect."""
    region_w = max(1e-6, float(region_w))
    region_h = max(1e-6, float(region_h))
    scale = min(max_w / region_w, max_h / region_h)
    return (max(1, int(round(region_w * scale))), max(1, int(round(region_h * scale))))


def zoom_factor(region_w: float, screen_w: float) -> float:
    return float(screen_w) / max(1e-6, float(region_w))


def context_box(region, root, screen_w: float, screen_h: float):
    """Work out what to show when zoomed into `region`.

    Square cells mean the region is roughly square, and a square region can't
    fill a 16:9 screen without distortion. Rather than leaving black bars, we
    show a screen-shaped area *centred on* the region - so the margins carry
    the surrounding screen content, which is also what tells you where you are.

    Returns ((vx, vy, vw, vh) in screen coordinates, scale).
    """
    rx, ry, rw, rh = (float(v) for v in region)
    ox, oy, rootw, rooth = (float(v) for v in root)
    rw, rh = max(1e-6, rw), max(1e-6, rh)

    # Blow the region up as far as it goes without spilling off the screen...
    scale = min(screen_w / rw, screen_h / rh)
    # ...but never so far out that we'd need pixels the desktop doesn't have.
    scale = max(scale, screen_w / rootw, screen_h / rooth)

    vw = min(screen_w / scale, rootw)
    vh = min(screen_h / scale, rooth)

    cx, cy = rx + rw / 2.0, ry + rh / 2.0
    vx = min(max(cx - vw / 2.0, ox), ox + rootw - vw)
    vy = min(max(cy - vh / 2.0, oy), oy + rooth - vh)
    return (vx, vy, vw, vh), scale
