#!/usr/bin/env python3
"""True per-pixel-alpha glow rendering.

Stipple dithering is not translucency - it is holes, and it reads as a screen
door. Real alpha needs a Windows *layered window*, which composites an RGBA
bitmap onto the desktop with 8 bits of alpha per pixel. This module builds that
bitmap; `layered.py` puts it on screen.

Everything here is pure numpy, so the look can be checked by compositing onto a
screenshot offline - no Windows, no display.

The expensive parts are precomputed once at construction:

  * `alpha`  - the falloff, which never changes
  * `param`  - each pixel's position around the perimeter, i.e. which colour it
               takes, which also never changes

Per frame all that happens is a gather from a small colour lookup table into
the ~15% of pixels that are not fully transparent. That is a few milliseconds,
versus recomputing a 2-megapixel gradient every tick.
"""

from __future__ import annotations

import numpy as np

from glow import build_ramp, DEFAULT_STOPS, DICTATE_STOPS


def smoothstep(t):
    """Hermite ease. Cubic falloff reads as light; linear reads as a ramp."""
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def wisp_np(t, seed: float = 0.0):
    """Vector form of glow.wisp. np.vectorize on 2M pixels takes seconds."""
    tau = 2.0 * np.pi
    return np.clip(0.5
                   + 0.26 * np.sin(tau * (3.0 * t + seed))
                   + 0.15 * np.sin(tau * (7.0 * t + seed * 1.7))
                   + 0.09 * np.sin(tau * (13.0 * t + seed * 2.3)),
                   0.0, 1.0)


def edge_fields(w: int, h: int, softness: float = 30.0):
    """Per-pixel distance to the nearest screen edge, and position around the
    perimeter (0..1, clockwise from the top-left).

    A hard `min()` over the four edges creases along the corner diagonals: two
    edges meet at exactly equal distance, and everything downstream - the
    thickness modulation, the colour - steps across that line. It shows up as a
    visible seam running out of each corner.

    So the four edges are blended with a softmin instead, and the perimeter
    position is a *circular* weighted mean using the same weights. Corners come
    out rounded and seamless, which is also closer to the look we're after.
    """
    x = np.arange(w, dtype=np.float32)[None, :]
    y = np.arange(h, dtype=np.float32)[:, None]

    d = np.stack([
        np.broadcast_to(y, (h, w)),                 # top
        np.broadcast_to((w - 1) - x, (h, w)),       # right
        np.broadcast_to((h - 1) - y, (h, w)),       # bottom
        np.broadcast_to(x, (h, w)),                 # left
    ]).astype(np.float32)

    k = max(1e-3, float(softness))
    weights = np.exp(-d / k)
    wsum = weights.sum(axis=0) + 1e-12
    weights /= wsum
    dist = (-k * np.log(wsum)).astype(np.float32)

    total = 2.0 * (w + h)
    xx = np.broadcast_to(x, (h, w))
    yy = np.broadcast_to(y, (h, w))
    edge_param = np.stack([
        xx,
        w + yy,
        w + h + ((w - 1) - xx),
        2 * w + h + ((h - 1) - yy),
    ]).astype(np.float32) / total

    # Circular mean: the parameter wraps at 1.0, so averaging it directly would
    # smear the whole ramp backwards near the top-left corner.
    ang = edge_param * 2.0 * np.pi
    sx = (weights * np.cos(ang)).sum(axis=0)
    sy = (weights * np.sin(ang)).sum(axis=0)
    param = (np.arctan2(sy, sx) / (2.0 * np.pi)) % 1.0

    return dist, param.astype(np.float32)


def build_alpha(w: int, h: int, thickness: float, peak: float = 0.92,
                wispiness: float = 0.45, gamma: float = 1.7,
                rim: float = 0.35, softness: float = None):
    """The falloff: opaque at the very edge, smoothly to zero inward.

    `wispiness` varies the local thickness around the perimeter so the inner
    boundary breathes instead of running perfectly parallel to the screen edge.
    `rim` adds a brighter hairline right at the edge, which is what stops a
    soft gradient from looking like fog.
    """
    dist, param = edge_fields(w, h, softness if softness is not None
                              else max(8.0, thickness * 0.35))

    local_t = thickness * (1.0 - wispiness + 2.0 * wispiness
                           * wisp_np(param).astype(np.float32))
    local_t = np.maximum(local_t, 1.0)

    a = smoothstep(1.0 - dist / local_t) ** gamma
    if rim > 0:
        a = a + rim * smoothstep(1.0 - dist / max(1.0, thickness * 0.10))
    return np.clip(a * peak, 0.0, 1.0).astype(np.float32), param


class GlowRenderer:
    """Builds premultiplied BGRA frames for a layered window."""

    def __init__(self, w: int, h: int, thickness: float = 45.0,
                 stops=None, dictate_stops=None, ramp_steps: int = 360,
                 **falloff):
        self.w, self.h = int(w), int(h)
        alpha, param = build_alpha(self.w, self.h, float(thickness), **falloff)

        # Only pixels with visible alpha are ever touched. On 1920x1080 with a
        # 90px band that is ~18% of the screen, so a frame is a gather over
        # 400k values rather than 2M.
        self.mask = alpha > (1.0 / 255.0)
        self.alpha = alpha[self.mask]
        self.param = param[self.mask]

        self.ramps = {
            "command": np.array([_hex(c) for c in build_ramp(stops or DEFAULT_STOPS,
                                                             ramp_steps)],
                                dtype=np.float32),
            "dictate": np.array([_hex(c) for c in build_ramp(dictate_stops or DICTATE_STOPS,
                                                             ramp_steps)],
                                dtype=np.float32),
        }
        self.steps = ramp_steps
        self._base_index = (self.param * ramp_steps).astype(np.int32)
        self._buffer = np.zeros((self.h, self.w, 4), dtype=np.uint8)
        self._a8 = (self.alpha * 255.0).astype(np.uint8)
        # Flat indices of the visible pixels. Assigning through one fancy index
        # into a reshaped view is several times faster than four separate
        # boolean-mask assignments, and the fade needs every millisecond it can
        # get to look smooth on a 4K desktop.
        self._flat = np.flatnonzero(self.mask.reshape(-1))
        self._scratch = np.empty((self._flat.size, 4), dtype=np.uint8)

    @property
    def coverage(self) -> float:
        return float(self.mask.sum()) / float(self.w * self.h)

    def render_into(self, out, phase: int = 0, mode: str = "command",
                    opacity: float = 1.0) -> None:
        """Write premultiplied BGRA straight into `out` (an (h, w, 4) uint8
        view). Writing into the layered window's own DIB memory avoids copying
        8MB per frame at 1080p, or 33MB at 4K.

        `opacity` scales the whole thing - that is the entire fade mechanism,
        one extra multiply rather than rebuilding anything.
        """
        ramp = self.ramps.get(mode, self.ramps["command"])
        idx = (self._base_index + int(phase)) % self.steps
        rgb = ramp[idx]                                   # (n, 3) float 0..255

        o = max(0.0, min(1.0, float(opacity)))
        a = self.alpha * o
        premul = rgb * a[:, None]

        sc = self._scratch
        sc[:, 0] = premul[:, 2]                           # B
        sc[:, 1] = premul[:, 1]                           # G
        sc[:, 2] = premul[:, 0]                           # R
        sc[:, 3] = a * 255.0
        flat = out.reshape(-1, 4)
        flat[self._flat] = sc

    def frame(self, phase: int = 0, mode: str = "command",
              opacity: float = 1.0) -> np.ndarray:
        """Premultiplied BGRA in the renderer's own buffer."""
        self.render_into(self._buffer, phase, mode, opacity)
        return self._buffer

    def rgba(self, phase: int = 0, mode: str = "command") -> np.ndarray:
        """Straight (non-premultiplied) RGBA, for previews and tests."""
        ramp = self.ramps.get(mode, self.ramps["command"])
        idx = (self._base_index + int(phase)) % self.steps
        rgb = ramp[idx].astype(np.uint8)
        out = np.zeros((self.h, self.w, 4), dtype=np.uint8)
        out[..., 0][self.mask] = rgb[:, 0]
        out[..., 1][self.mask] = rgb[:, 1]
        out[..., 2][self.mask] = rgb[:, 2]
        out[..., 3][self.mask] = self._a8
        return out


def _hex(value: str):
    value = value.lstrip("#")
    return [int(value[i:i + 2], 16) for i in (0, 2, 4)]
