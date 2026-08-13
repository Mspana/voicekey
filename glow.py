#!/usr/bin/env python3
"""
VoiceKey - the listening indicator.

A Siri-style gradient glow around the screen edge while a command is being
listened for.

IMPORTANT: this is *reinforcement*, never the only signal. A screen-edge colour
change conveys nothing to a blind user, is invisible to anyone running a screen
magnifier (the periphery is the first thing cropped), and relying on colour
alone to indicate state fails WCAG 2.2 SC 1.4.1. The earcons in `dictate.py`
are the primary channel; this is the part sighted users happen to like.

Two other things learned the hard way from the reference implementations:

* Naive versions of this effect burn 40-60% of a CPU core, because they
  regenerate the whole gradient on a fast timer. Here the palette is
  precomputed once and animation is a cheap index rotation, the frame interval
  is configurable, and the window is destroyed - not hidden - when idle.
* `prefers-reduced-motion` has no equivalent on Windows, so `animate: false`
  gives a static border instead. Turning motion off must not remove the
  indicator.
"""

from __future__ import annotations

import math
import sys
import time

IS_WINDOWS = sys.platform.startswith("win")

# The Apple Intelligence palette, as reconstructed by the community. Used for
# command mode, where something is about to *happen*.
DEFAULT_STOPS = ["#BC82F3", "#F5B9EA", "#8D9FFF", "#AA6EEE",
                 "#FF6778", "#FFBA71", "#C686FF"]

# Dictation is the quieter, far more frequent mode, so it gets the same shape
# in neutral greys: unmistakably "listening", but not competing for attention
# eight hours a day. The two modes must also be distinguishable by *lightness*
# alone, not just hue - roughly 1 in 12 men has a colour vision deficiency.
DICTATE_STOPS = ["#6E7784", "#AEB7C4", "#8C95A3", "#C6CDD8",
                 "#7A8391", "#B6BEC9", "#949CAA"]

# Any colour that will not appear in the glow itself; on Windows this key is
# made fully transparent AND click-through, so the overlay never eats a click.
CHROMA_KEY = "#010203"

DEFAULT_BANDS = [
    ("",       0.00, 0.20),
    ("gray75", 0.14, 0.40),
    ("gray50", 0.32, 0.60),
    ("gray25", 0.52, 0.80),
    ("gray12", 0.70, 1.00),
]


def _hex_to_rgb(value: str):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def build_ramp(stops, steps: int = 180) -> list:
    """Precompute a cyclic colour ramp.

    Done once at construction: interpolating per frame is what makes these
    effects expensive.
    """
    stops = list(stops) or list(DEFAULT_STOPS)
    rgb = [_hex_to_rgb(s) for s in stops]
    rgb.append(rgb[0])                      # wrap, so the loop is seamless
    ramp = []
    span = len(rgb) - 1
    for i in range(steps):
        pos = (i / steps) * span
        lo = int(pos)
        frac = pos - lo
        a, b = rgb[lo], rgb[lo + 1]
        ramp.append(_rgb_to_hex(tuple(a[k] + (b[k] - a[k]) * frac for k in range(3))))
    return ramp


def wisp(t: float, seed: float = 0.0) -> float:
    """Smooth pseudo-random 0..1 around a loop, for an organic edge.

    Three sines at coprime-ish frequencies. Cheap, seamless at t=0/1 (so the
    band does not jump at the top-left corner), and deterministic - the shape
    is computed once at build time and only the colour animates.
    """
    v = (0.5
         + 0.26 * math.sin(2 * math.pi * (3 * t + seed))
         + 0.15 * math.sin(2 * math.pi * (7 * t + seed * 1.7))
         + 0.09 * math.sin(2 * math.pi * (13 * t + seed * 2.3)))
    return max(0.0, min(1.0, v))


def perimeter_points(x: float, y: float, w: float, h: float, count: int) -> list:
    """`count` points around the rectangle, clockwise from the top-left.

    Points are allocated per edge rather than by walking one distance around
    the whole perimeter, so each corner is hit exactly. Walking the perimeter
    lets a segment straddle a corner, which visibly chamfers it.
    """
    count = max(4, int(count))
    w, h = max(1e-6, float(w)), max(1e-6, float(h))
    total = 2.0 * (w + h)

    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    lengths = [w, h, w, h]

    # Round each edge's share, then give the remainder to the longest edge so
    # the total is exactly `count`.
    shares = [max(1, int(round(count * L / total))) for L in lengths]
    drift = count - sum(shares)
    shares[lengths.index(max(lengths))] += drift
    if min(shares) < 1:                       # pathological count vs aspect
        shares = [max(1, s) for s in shares]

    points = []
    for i in range(4):
        p0 = corners[i]
        p1 = corners[(i + 1) % 4]
        n = shares[i]
        for k in range(n):
            t = k / n
            points.append((p0[0] + (p1[0] - p0[0]) * t,
                           p0[1] + (p1[1] - p0[1]) * t))
    return points


class Glow:
    """Edge glow overlay. Needs an existing Tk root to attach to."""

    def __init__(self, root, cfg: dict | None = None):
        self.root = root
        cfg = cfg or {}
        self.stops = cfg.get("command_stops") or cfg.get("stops") or DEFAULT_STOPS
        self.dictate_stops = cfg.get("dictate_stops") or DICTATE_STOPS
        # Thick enough to hold a visible falloff. Solid at the screen edge,
        # dithering out to nothing inward - see _build_segments.
        self.thickness = int(cfg.get("thickness", 44))
        self.segments = int(cfg.get("segments", 120))
        # (stipple, start, end) as fractions of the thickness, outermost first.
        # "" is solid; the grays are tkinter's built-in dither bitmaps at
        # roughly 75/50/25/12% coverage. Ranges OVERLAP so the steps blend, and
        # they widen going inward so the falloff is gradual rather than linear.
        self.bands = list(cfg.get("bands") or DEFAULT_BANDS)
        self.interval_ms = int(cfg.get("interval_ms", 90))
        self.phase_step = int(cfg.get("phase_step", 4))
        # True per-pixel alpha via a Windows layered window; falls back to the
        # tkinter stipple version automatically if anything goes wrong.
        self.use_layered = bool(cfg.get("soft", True))
        self.soft_thickness = float(cfg.get("soft_thickness", 45))
        # A hard cut on and off reads as a glitch. 100ms is short enough to
        # feel instant but long enough for the eye to register a transition.
        self.fade_ms = int(cfg.get("fade_ms", 120))
        # How often to try to repaint during a fade. Frames that cannot be made
        # in time are simply skipped - the fade still finishes on schedule.
        self.fade_interval_ms = max(1, int(cfg.get("fade_interval_ms", 8)))
        self.animate = bool(cfg.get("animate", True))
        self.enabled = bool(cfg.get("enabled", True))

        # Both ramps precomputed at construction - switching modes must not
        # cost an interpolation pass at the moment the user presses a key.
        self.ramps = {
            "command": build_ramp(self.stops),
            "dictate": build_ramp(self.dictate_stops),
        }
        self.ramp = self.ramps["command"]
        self.mode = "command"
        self._win = None
        self._canvas = None
        self._items: list = []
        self._phase = 0
        self._timer = None
        self._layer = None
        self._renderer = None
        self._opacity = 0.0
        self._fade_to = 0.0
        self._fade_from = 0.0
        self._fade_start = 0.0
        self._fade_timer = None
        self._pending_rect = None
        self.visible = False

    # -- lifecycle ----------------------------------------------------------

    # -- true per-pixel alpha (Windows) --------------------------------------

    def _try_layered(self, rect, mode: str) -> bool:
        """Real soft glow via a layered window. Returns False to fall back."""
        if not self.use_layered:
            return False
        try:
            import layered
            import glowfx
        except Exception:
            return False
        if not layered.available():
            return False
        try:
            x, y, w, h = (int(v) for v in rect)
            if (self._renderer is None or self._renderer.w != w
                    or self._renderer.h != h):
                # ~1.5s on a 4K desktop, so it is built once and reused for the
                # lifetime of the process, not per press.
                self._renderer = glowfx.GlowRenderer(
                    w, h, thickness=float(self.soft_thickness),
                    stops=self.stops, dictate_stops=self.dictate_stops)
            self._layer = layered.LayeredGlow((x, y, w, h))
            # Opacity 0 for the very first blit. Painting the new window at
            # full and *then* starting the fade is what made it snap to full
            # and fade from there.
            self._opacity = 0.0
            self._blit()
            return True
        except Exception as exc:
            print(f"[glow] layered window unavailable ({exc}); using fallback")
            self.use_layered = False
            try:
                if self._layer is not None:
                    self._layer.destroy()
            except Exception:
                pass
            self._layer = None
            return False

    def show(self, rect, mode: str = "command") -> None:
        """rect = (x, y, w, h) of the virtual screen.

        mode "command" = the colour palette, "dictate" = neutral greys.
        """
        if not self.enabled or self.visible:
            return

        self.mode = mode if mode in self.ramps else "command"
        self.ramp = self.ramps[self.mode]

        # A press that lands mid fade-out reuses the window still on screen -
        # cheaper than tearing down and rebuilding, and it fades back up from
        # wherever it got to rather than snapping to zero.
        if self._layer is not None and self._renderer is not None:
            self.visible = True
            self._start_fade(1.0)
            if self.animate:
                self._tick()
            return

        if self._try_layered(rect, self.mode):
            self.visible = True
            self._opacity = 0.0
            self._start_fade(1.0)
            if self.animate:
                self._tick()
            return

        import tkinter as tk

        self.mode = mode if mode in self.ramps else "command"
        self.ramp = self.ramps[self.mode]

        x, y, w, h = (int(v) for v in rect)
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.configure(bg=CHROMA_KEY)
        try:
            # Windows only: the key colour becomes transparent *and*
            # click-through, so the overlay cannot swallow a click.
            win.attributes("-transparentcolor", CHROMA_KEY)
        except Exception:
            # Elsewhere, fall back to a translucent window. Not click-through,
            # so it is only shown while we are already capturing input.
            try:
                win.attributes("-alpha", 0.55)
            except Exception:
                pass

        try:
            win.attributes("-alpha", 0.0)     # invisible before it is mapped
        except Exception:
            pass

        canvas = tk.Canvas(win, width=w, height=h, highlightthickness=0,
                           bg=CHROMA_KEY)
        canvas.pack(fill="both", expand=True)

        self._win, self._canvas = win, canvas
        self._items = []
        self._build_segments(w, h)
        self.visible = True
        self._opacity = 0.0
        self._start_fade(1.0)
        if self.animate:
            self._tick()

    def hide(self) -> None:
        """Fade out, then dispose.

        The window has to survive until the fade finishes, so teardown happens
        in the fade callback rather than here. `visible` flips immediately so a
        second show() during the fade re-enters cleanly.
        """
        if not self.visible and self._opacity <= 0.0:
            return
        self.visible = False
        if self._timer is not None:
            try:
                self.root.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None

        if self.root is None:                 # headless / tests
            self._opacity = 0.0
            self._teardown()
            return
        self._start_fade(0.0)

    # -- drawing ------------------------------------------------------------

    def _build_segments(self, w: int, h: int) -> None:
        """Create the canvas items once; animation only recolours them.

        The band is built as concentric rings from the screen edge inward, each
        drawn with a sparser stipple than the last. tkinter has no per-item
        alpha, but a stipple leaves the chroma key showing through in the gaps -
        and the chroma key is transparent - so a dither pattern IS partial
        transparency. Four densities plus solid gives a five-step fade from the
        edge inward instead of a hard line.

        Each segment's width is also modulated by `wisp`, so the inner boundary
        is irregular rather than a clean parallel line.
        """
        bands = list(self.bands)
        T = float(self.thickness)
        n_bands = max(1, len(bands))

        for bi, (stipple, start, end) in enumerate(bands):
            # Bands overlap on purpose. Butted up against each other they read
            # as concentric rings; overlapping, the transitions blur together.
            inset = T * (start + end) / 2.0
            base = T * (end - start)
            pts = perimeter_points(inset, inset,
                                   max(1.0, w - 2 * inset),
                                   max(1.0, h - 2 * inset),
                                   self.segments)
            n = len(pts)
            for k in range(n):
                x0, y0 = pts[k]
                x1, y1 = pts[(k + 1) % n]
                # Outer rings stay near full width; inner ones vary a lot, so
                # the inner boundary is ragged instead of a clean parallel line.
                spread = 0.10 + 0.75 * (bi / max(1, n_bands - 1))
                mult = (1.0 - spread) + spread * 2.0 * wisp(k / n, seed=bi * 0.37)
                item = self._canvas.create_line(
                    x0, y0, x1, y1,
                    width=max(1.0, base * 1.5 * mult),
                    capstyle="round",
                    stipple=stipple,
                    fill=self.ramp[0])
                self._items.append((item, k, n))

    def _blit(self) -> None:
        """Render into the layered window's own DIB memory, then blit."""
        try:
            if self._layer.array is not None:
                self._renderer.render_into(self._layer.array, self._phase,
                                           self.mode, self._opacity)
                self._layer.commit()
            else:
                self._layer.update(self._renderer.frame(self._phase, self.mode,
                                                        self._opacity))
        except Exception:
            pass

    def _start_fade(self, target: float) -> None:
        """Fade to `target` over fade_ms of WALL CLOCK time.

        Stepping by a fixed fraction per tick assumes every frame costs the
        same. A 4K frame takes ~20ms to render, so the fixed-step version
        overran badly and the fade read as a stutter. Driving it from elapsed
        time means a slow machine drops frames instead of stretching the fade.
        """
        self._fade_to = float(target)
        self._fade_from = float(self._opacity)
        self._fade_start = time.monotonic()
        if self._fade_timer is not None:
            try:
                self.root.after_cancel(self._fade_timer)
            except Exception:
                pass
            self._fade_timer = None
        self._fade_step()

    def _fade_step(self) -> None:
        self._fade_timer = None
        span = max(1.0, float(self.fade_ms)) / 1000.0
        t = (time.monotonic() - self._fade_start) / span
        if t >= 1.0:
            self._opacity = self._fade_to
        else:
            # Ease in-out. A linear ramp is visibly mechanical over 100ms.
            eased = t * t * (3.0 - 2.0 * t)
            self._opacity = self._fade_from + (self._fade_to - self._fade_from) * eased

        self._paint()

        if abs(self._opacity - self._fade_to) > 1e-6:
            self._fade_timer = self.root.after(self.fade_interval_ms,
                                               self._fade_step)
        elif self._fade_to <= 0.0:
            self._teardown()

    def _teardown(self) -> None:
        """Actually dispose of the window, once faded out."""
        if self._layer is not None:
            try:
                self._layer.destroy()
            except Exception:
                pass
            self._layer = None
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
        self._win = None
        self._canvas = None
        self._items = []

    def _paint(self) -> None:
        if self._layer is not None and self._renderer is not None:
            self._blit()
            return
        if self._win is not None:
            # Fallback path: whole-window opacity is all tkinter offers, but it
            # is enough for a fade.
            try:
                self._win.attributes("-alpha", self._opacity)
            except Exception:
                pass
        if self._canvas is None:
            return
        size = len(self.ramp)
        for item, k, n in self._items:
            idx = int((k / n) * size + self._phase) % size
            try:
                self._canvas.itemconfigure(item, fill=self.ramp[idx])
            except Exception:
                return

    def _tick(self) -> None:
        if not self.visible or (self._canvas is None and self._layer is None):
            return
        self._phase = (self._phase + self.phase_step) % (
            self._renderer.steps if self._renderer is not None else len(self.ramp))
        self._paint()
        self._timer = self.root.after(self.interval_ms, self._tick)
