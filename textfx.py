#!/usr/bin/env python3
"""Lora text, rendered with PIL so it can be semibold and gradient-filled.

Two reasons not to use a plain tk Label:

* tkinter only understands "normal" and "bold". Lora is a variable font and
  SemiBold (weight 600) sits between them, so the weight has to be set on the
  font object, which only PIL can do.
* tkinter cannot fill text with a gradient at all.

Lora is bundled in fonts/ under the OFL, so this looks the same on a machine
where it is not installed. If the bundled file is missing we fall back through
the serif fonts Windows ships with.
"""

from __future__ import annotations

from pathlib import Path

import paths

BUNDLED = paths.resource("fonts", "Lora-Variable.ttf")

# Ordered fallbacks. Georgia and Constantia are on every Windows install and
# are the closest in feel to Lora.
FALLBACKS = [
    r"C:\Windows\Fonts\georgiab.ttf",
    r"C:\Windows\Fonts\constanb.ttf",
    r"C:\Windows\Fonts\cambriab.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
]

# tk family names to try for the labels we do NOT render ourselves.
TK_FAMILIES = ["Lora", "Georgia", "Constantia", "Cambria", "DejaVu Serif",
               "Times New Roman"]

_font_cache: dict = {}


def font(size: int, weight: str = "SemiBold"):
    """A PIL font at `size`, at the named variation weight where available."""
    key = (size, weight)
    if key in _font_cache:
        return _font_cache[key]

    from PIL import ImageFont
    f = None
    if BUNDLED.exists():
        try:
            f = ImageFont.truetype(str(BUNDLED), size)
            try:
                f.set_variation_by_name(weight)
            except Exception:
                pass                       # static build; the default is fine
        except Exception:
            f = None
    if f is None:
        for path in FALLBACKS:
            try:
                f = ImageFont.truetype(path, size)
                break
            except Exception:
                continue
    if f is None:
        f = ImageFont.load_default()
    _font_cache[key] = f
    return f


def tk_family(root) -> str:
    """First of our preferred families that tk can actually see."""
    try:
        from tkinter import font as tkfont
        have = {name.lower() for name in tkfont.families(root)}
        for name in TK_FAMILIES:
            if name.lower() in have:
                return name
    except Exception:
        pass
    return "Georgia"


def register_bundled() -> bool:
    """Make the bundled Lora visible to tk as a family name.

    Windows will not use a font file that is not installed, so it is added as a
    *private* process font - visible to us, not written into the system.
    """
    if not BUNDLED.exists():
        return False
    import sys
    if not sys.platform.startswith("win"):
        return True                        # fontconfig already knows about it
    try:
        import ctypes
        FR_PRIVATE = 0x10
        add = ctypes.windll.gdi32.AddFontResourceExW
        add.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        return bool(add(str(BUNDLED), FR_PRIVATE, None))
    except Exception:
        return False


def gradient_text(text: str, size: int, start: str, end: str,
                  bg: str, pad: int = 2, weight: str = "SemiBold",
                  angle: str = "horizontal"):
    """Render `text` filled with a gradient, composited onto `bg`.

    Returned as a PIL image; the caller wraps it in a PhotoImage. Compositing
    onto the known background rather than keeping alpha avoids halos, since tk
    Labels do not blend transparent images against their parent.
    """
    from PIL import Image, ImageDraw

    f = font(size, weight)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    box = probe.textbbox((0, 0), text, font=f)
    w = (box[2] - box[0]) + pad * 2
    h = (box[3] - box[1]) + pad * 2

    a = tuple(int(start.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    b = tuple(int(end.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    grad = Image.new("RGB", (w, h))
    gd = ImageDraw.Draw(grad)
    span = w if angle == "horizontal" else h
    for i in range(max(1, span)):
        t = i / max(1, span - 1)
        colour = tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))
        if angle == "horizontal":
            gd.line([(i, 0), (i, h)], fill=colour)
        else:
            gd.line([(0, i), (w, i)], fill=colour)

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((pad - box[0], pad - box[1]), text, font=f, fill=255)

    out = Image.new("RGB", (w, h),
                    tuple(int(bg.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)))
    out.paste(grad, (0, 0), mask)
    return out


def solid_text(text: str, size: int, colour: str, bg: str, pad: int = 2,
               weight: str = "SemiBold"):
    """Same renderer, one colour - for labels that need the semibold weight."""
    return gradient_text(text, size, colour, colour, bg, pad, weight)
