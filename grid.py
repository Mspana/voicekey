#!/usr/bin/env python3
"""
VoiceKey - Phase 2: mouse grid.

A numbered grid is drawn over the screen. Choosing a cell zooms that cell to
fill the screen and lays a fresh grid over it, the way macOS Voice Control
does. Cells are the same SHAPE as the screen, so the zoom is always an exact
fit. Three steps on 3840x2160 gets to about 31x17 px.

Selection is always two digits: the first picks a COLUMN, the second picks a
ROW inside it. The grid is 5x5, so both axes are single-digit - nothing is
ambiguous and there is no Enter to press.

Standalone:   python grid.py
  Ctrl+Alt+G    show / hide the grid
  1-5           column, then row - zooms immediately on the second digit
  Backspace     un-arm the column, or go up one level
  Space/Enter   click at the current centre
  R             right click      D  double click     M  middle click
  H             hold left button (see grid.hold_seconds in config)
  V             move the cursor without clicking
  Escape        cancel

Importable: MouseGrid exposes show/hide/select/back/commit so phase 3 can
drive the same state machine by voice.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import mouse
import capture

import paths

HERE = paths.app_dir()
CONFIG_PATH = paths.config_path()

GRID_DEFAULTS = {
    # Fixed 5 x 5. Each cell is 1/5 the width and 1/5 the height of the region,
    # so a cell has the SAME SHAPE as the screen and the subdivision is
    # self-similar all the way down. 5 keeps both axes single-digit, which is
    # what makes selection two keystrokes with no terminator.
    "cols": 5,
    "rows": 5,
    "max_depth": 4,
    "hotkey": "ctrl+alt+g",
    "alpha": 0.45,
    "line_color": "#00E5FF",
    "grid_color": "#8A93A6",
    "line_width": 2,
    "label_color": "#FFFFFF",
    "label_outline": "#000000",
    "highlight_color": "#FFB300",
    "background": "#101018",
    "font_family": "Segoe UI",
    "font_scale": 0.34,
    "min_font": 9,
    "max_font": 34,
    "hold_seconds": 1.0,
    "monitor": "all",
    "close_after_action": True,
    # Every drill-down zooms the chosen region to fill the screen, so labels
    # stay full size at any depth. Needs a screen capture; without Pillow the
    # grid falls back to drawing in place.
    "zoom_on_drill": True,
    "zoom_alpha": 1.0,
    "context_brightness": 0.4,
}


def load_grid_config() -> dict:
    cfg = dict(GRID_DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            user = data.get("grid", {})
            cfg.update({k: v for k, v in user.items() if not k.startswith("_")})
        except Exception:
            pass
    return cfg


# ------------------------------------------------------------ geometry (pure)

def subdivide(rect, index: int, cols: int, rows: int):
    """Return the sub-rectangle for 1-indexed, row-major cell `index`.

    Kept as a free function with no UI dependency so it can be tested directly.
    """
    if not (1 <= index <= cols * rows):
        raise ValueError(f"cell {index} out of range 1..{cols * rows}")
    x, y, w, h = rect
    r, c = divmod(index - 1, cols)
    cw = w / cols
    ch = h / rows
    return (x + c * cw, y + r * ch, cw, ch)


def centre(rect):
    x, y, w, h = rect
    return (int(round(x + w / 2.0)), int(round(y + h / 2.0)))


class GridState:
    """The drill-down state machine. No UI, no side effects.

    The grid is a fixed COLS x ROWS, so every cell has the same aspect ratio as
    the region containing it, and therefore the same aspect ratio as the screen.
    That makes the subdivision self-similar: the region is screen-shaped at
    every depth, so zooming a cell to fill the display is always an exact fit -
    no letterboxing, no distortion, and the numbers land in the same places.
    """

    def __init__(self, rect, cols: int, rows: int, max_depth: int = 4):
        self.root_rect = tuple(rect)
        self._cols = int(cols)
        self._rows = int(rows)
        self.max_depth = int(max_depth)
        self.history: list = []
        self.rect = tuple(rect)

    @property
    def shape(self):
        return (self._cols, self._rows)

    @property
    def cols(self) -> int:
        return self._cols

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def cell_size(self):
        cols, rows = self.shape
        return (self.rect[2] / cols, self.rect[3] / rows)

    @property
    def cells(self) -> int:
        cols, rows = self.shape
        return cols * rows

    @property
    def depth(self) -> int:
        return len(self.history)

    @property
    def exhausted(self) -> bool:
        """True once we're as deep as allowed, or the cell is sub-pixel."""
        if self.depth >= self.max_depth:
            return True
        cw, ch = self.cell_size
        return cw < 1.0 or ch < 1.0

    def select(self, index: int) -> bool:
        if self.exhausted:
            return False
        cols, rows = self.shape
        self.history.append(self.rect)
        self.rect = subdivide(self.rect, index, cols, rows)
        return True

    def back(self) -> bool:
        if not self.history:
            return False
        self.rect = self.history.pop()
        return True

    def reset(self) -> None:
        self.history.clear()
        self.rect = self.root_rect

    def point(self):
        return centre(self.rect)


# ---------------------------------------------------------------- the overlay

class MouseGrid:
    """Grid overlay plus the key handling that drives it."""

    _HALO_CACHE: dict = {}

    def __init__(self, cfg: dict | None = None, on_close=None):
        self.cfg = cfg or load_grid_config()
        self.on_close = on_close
        self.state = None
        self.pending_col = None    # column chosen, waiting on a row
        self._root = None
        self._win = None
        self._canvas = None
        self._screenshot = None    # grabbed before the overlay appears
        self._photo = None         # kept alive; tkinter does not own PhotoImages
        self.visible = False

    # -- lifecycle ----------------------------------------------------------

    def _screen_rect(self):
        x, y, w, h = mouse.virtual_screen()
        return (float(x), float(y), float(w), float(h))

    def show(self) -> None:
        if self.visible:
            return
        rect = self._screen_rect()
        # Grab BEFORE the overlay exists, or the magnifier shows the overlay.
        self._screenshot = capture.grab_screen(rect)
        self.state = GridState(rect, self.cfg["cols"], self.cfg["rows"],
                               self.cfg["max_depth"])
        self.pending_col = None
        self.visible = True
        self._build_window()
        self._draw()

    def hide(self) -> None:
        self.visible = False
        self.pending_col = None
        self._screenshot = None
        self._photo = None
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None
            self._canvas = None
        if self.on_close:
            try:
                self.on_close()
            except Exception:
                pass

    # -- state transitions (also the phase 3 voice API) ---------------------

    def select(self, index: int) -> bool:
        """Drill into a cell by row-major index. Returns False if invalid."""
        if not self.visible or self.state is None:
            return False
        if not (1 <= index <= self.state.cells):
            return False
        ok = self.state.select(index)
        self.pending_col = None
        self._draw()
        return ok

    def select_cell(self, col: int, row: int) -> bool:
        """Drill into the cell at 1-indexed (col, row)."""
        if not self.visible or self.state is None:
            return False
        cols, rows = self.state.shape
        if not (1 <= col <= cols and 1 <= row <= rows):
            return False
        return self.select((row - 1) * cols + col)

    def choose_column(self, col: int) -> bool:
        """First half of a selection: arm a column and wait for a row."""
        if not self.visible or self.state is None:
            return False
        if not (1 <= col <= self.state.shape[0]):
            return False
        self.pending_col = int(col)
        self._draw()
        return True

    def back(self) -> bool:
        if not self.visible or self.state is None:
            return False
        # Un-arm the column before climbing a level, so a mis-typed column
        # costs one keystroke to undo rather than losing the zoom.
        if self.pending_col is not None:
            self.pending_col = None
            self._draw()
            return True
        ok = self.state.back()
        self._draw()
        return ok

    def _run_action(self, point, action: str, count: int) -> None:
        mouse.move_to(*point)

        # SetCursorPos and SendInput go through different paths into the input
        # queue. Clicking in the same breath can dispatch the button at the old
        # position - the classic "it clicked where the cursor already was".
        settle = float(self.cfg.get("settle_ms", 40)) / 1000.0
        if settle > 0:
            time.sleep(settle)

        if action == "move":
            return
        if action == "left_click":
            mouse.left_click(count)
        elif action == "right_click":
            mouse.right_click(count)
        elif action == "middle_click":
            mouse.middle_click(count)
        elif action == "double_click":
            mouse.left_click(2)
        elif action == "hold":
            threading.Thread(target=mouse.hold_left,
                             args=(float(self.cfg.get("hold_seconds", 1.0)),),
                             daemon=True).start()

    def commit(self, action: str = "left_click", count: int = 1) -> tuple:
        """Move the cursor to the current centre and perform `action`.

        The overlay has to be *gone* before the click, not merely asked to go.
        `hide()` calls Toplevel.destroy(), but Tk only processes that when
        control returns to the event loop - and commit() is normally called
        from inside a key handler, i.e. still inside the loop. Clicking there
        and then lands the click on the overlay window instead of the app
        underneath, which reads exactly like the cursor never moved.

        So: tear down, flush the event queue, and only then move and click.
        """
        if self.state is None:
            return (0, 0)
        point = self.state.point()
        close = self.cfg.get("close_after_action", True) or action != "move"
        if close:
            self.hide()

        if self._root is not None and close:
            try:
                self._root.update()          # actually destroy the window
            except Exception:
                pass
            # One more trip through the loop, so Windows has repainted whatever
            # was underneath before it receives the click.
            self._root.after(int(self.cfg.get("teardown_ms", 30)),
                             lambda: self._run_action(point, action, count))
        else:
            self._run_action(point, action, count)
        return point

    # -- digit entry --------------------------------------------------------

    def type_digit(self, ch: str) -> bool:
        """Column first, then row. Exactly two keystrokes, no terminator.

        Both axes are capped at 9 cells (see grid_shape), so a digit is never
        ambiguous and there is nothing to wait for or confirm.
        """
        if not self.visible or self.state is None:
            return False
        if not ch.isdigit():
            return False
        d = int(ch)
        if d == 0:
            return False

        if self.pending_col is None:
            return self.choose_column(d)

        cols, rows = self.state.shape
        if not (1 <= d <= rows):
            return False                # impossible row, ignore the keystroke
        return self.select_cell(self.pending_col, d)

    # -- rendering ----------------------------------------------------------

    def _build_window(self) -> None:
        import tkinter as tk

        if self._root is None:
            self._root = tk.Tk()
            self._root.withdraw()

        x, y, w, h = (int(v) for v in self.state.root_rect)
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", float(self.cfg.get("alpha", 0.45)))
        except Exception:
            pass
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.configure(bg=self.cfg.get("background", "#101018"))

        canvas = tk.Canvas(win, width=w, height=h, highlightthickness=0,
                           bg=self.cfg.get("background", "#101018"))
        canvas.pack(fill="both", expand=True)

        win.bind("<Key>", self._on_key)
        win.focus_force()

        self._win = win
        self._canvas = canvas

    def _on_key(self, event) -> None:
        key = event.keysym
        if key == "Escape":
            self.hide()
        elif key == "BackSpace":
            self.back()
        elif key in ("Return", "KP_Enter"):
            self.commit("left_click")
        elif key == "space":
            self.commit("left_click")
        elif key.lower() == "r":
            self.commit("right_click")
        elif key.lower() == "d":
            self.commit("double_click")
        elif key.lower() == "m":
            self.commit("middle_click")
        elif key.lower() == "h":
            self.commit("hold")
        elif key.lower() == "v":
            self.commit("move")
        elif len(key) == 1 and key.isdigit():
            self.type_digit(key)

    @staticmethod
    def _halo_offsets(radius: int):
        """Filled disc of offsets - a solid outline rather than 8 thin points.

        Cached per radius; without this the magnifier redraws ~700 canvas items
        of trigonometry on every keystroke.
        """
        cached = MouseGrid._HALO_CACHE.get(radius)
        if cached is None:
            cached = [(dx, dy)
                      for dx in range(-radius, radius + 1)
                      for dy in range(-radius, radius + 1)
                      if (dx or dy) and dx * dx + dy * dy <= radius * radius]
            MouseGrid._HALO_CACHE[radius] = cached
        return cached

    def _text_halo(self, c, x, y, text, font, anchor="center") -> None:
        """Draw text with a dark outline so it stays legible over any content.

        Contrast cannot depend on the wallpaper or the application underneath -
        the magnified panel shows real screen pixels, which are often white.
        The outline scales with the font, or big labels wash out.
        """
        outline = self.cfg.get("label_outline", "#000000")
        size = font[1] if len(font) > 1 else 12
        radius = max(1, min(3, int(size / 7)))
        for dx, dy in self._halo_offsets(radius):
            c.create_text(x + dx, y + dy, text=text, font=font,
                          fill=outline, anchor=anchor)
        c.create_text(x, y, text=text, font=font,
                      fill=self.cfg.get("label_color", "#FFFFFF"), anchor=anchor)

    def _line(self, c, x0, y0, x1, y1, fill, width) -> None:
        """A line with a dark underlay, so it reads on any content.

        Without this the grey reference grid disappears against dimmed screen
        content of similar luminance, and cyan washes out over white.
        """
        c.create_line(x0, y0, x1, y1,
                      fill=self.cfg.get("label_outline", "#000000"),
                      width=width + 2)
        c.create_line(x0, y0, x1, y1, fill=fill, width=width)

    def _rect(self, c, x0, y0, x1, y1, outline, width) -> None:
        c.create_rectangle(x0, y0, x1, y1,
                           outline=self.cfg.get("label_outline", "#000000"),
                           width=width + 2)
        c.create_rectangle(x0, y0, x1, y1, outline=outline, width=width)

    def _font(self, target_px: float):
        size = max(int(self.cfg.get("min_font", 9)),
                   min(int(self.cfg.get("max_font", 34)), int(target_px)))
        return (self.cfg.get("font_family", "Segoe UI"), size, "bold")

    def _draw_cells(self, c, px, py, pw, ph) -> None:
        """Draw whichever half of the selection we're on.

        The full cell grid is always drawn in grey, so you can see the exact
        cell you're aiming for rather than just the band it sits in. The axis
        being chosen is then repainted on top in the active colour:

        Nothing armed  -> column dividers highlighted, one big number per column.
        Column armed   -> that column outlined, split into numbered rows, and
                          the rest of the region dimmed back.

        Only one axis is ever labelled, so the numbers can be far larger than a
        full cell grid allows and there is never more than 9 of them on screen.
        """
        cols, rows = self.state.shape
        cw = pw / cols
        line = self.cfg.get("line_color", "#00E5FF")
        lw = int(self.cfg.get("line_width", 2))

        ch = ph / rows
        grey = self.cfg.get("grid_color", "#8A93A6")
        dim = self.cfg.get("background", "#101018")

        # The dim goes down first so the reference grid stays fully visible on
        # top of it - the point of dimming is to de-emphasise the *content*,
        # not to hide the grid you are navigating by.
        if self.pending_col is not None:
            ci = self.pending_col - 1
            colx = px + ci * cw
            # Stipple rather than a solid fill: tkinter has no per-item alpha,
            # and a 50% dither still lets the content read through underneath.
            if ci > 0:
                c.create_rectangle(px, py, colx, py + ph,
                                   fill=dim, outline="", stipple="gray50")
            if ci < cols - 1:
                c.create_rectangle(colx + cw, py, px + pw, py + ph,
                                   fill=dim, outline="", stipple="gray50")

        # Whole grid in grey, always. You need to see the cell you're aiming
        # for, not just the band it sits in.
        for i in range(1, cols):
            self._line(c, px + i * cw, py, px + i * cw, py + ph, grey, lw)
        for j in range(1, rows):
            self._line(c, px, py + j * ch, px + pw, py + j * ch, grey, lw)
        self._rect(c, px, py, px + pw, py + ph, grey, lw)

        if self.pending_col is None:
            # Column dividers repainted in the active colour, over the grey.
            self._rect(c, px, py, px + pw, py + ph, line, lw + 2)
            for i in range(1, cols):
                self._line(c, px + i * cw, py, px + i * cw, py + ph, line, lw + 1)
            font = self._font(min(cw * 0.55, ph * 0.30))
            for i in range(cols):
                self._text_halo(c, px + i * cw + cw / 2, py + ph / 2,
                                str(i + 1), font)
            return

        ci = self.pending_col - 1
        colx = px + ci * cw
        hi = self.cfg.get("highlight_color", "#FFB300")
        self._rect(c, colx, py, colx + cw, py + ph, hi, lw + 2)
        for j in range(1, rows):
            self._line(c, colx, py + j * ch, colx + cw, py + j * ch, line, lw + 1)

        font = self._font(min(cw, ch) * 0.55)
        for j in range(rows):
            self._text_halo(c, colx + cw / 2, py + j * ch + ch / 2, str(j + 1), font)

    def _set_alpha(self, value: float) -> None:
        if self._win is None:
            return
        try:
            self._win.attributes("-alpha", float(value))
        except Exception:
            pass

    def _draw(self) -> None:
        if self._canvas is None or self.state is None:
            return
        c = self._canvas
        c.delete("all")
        self._photo = None

        ox, oy = self.state.root_rect[0], self.state.root_rect[1]
        _, _, sw, sh = self.state.root_rect
        rx, ry, rw, rh = self.state.rect

        want_zoom = (self.state.depth > 0
                     and bool(self.cfg.get("zoom_on_drill", True))
                     and capture.available()
                     and self._screenshot is not None)

        zoomed = self._draw_zoomed(c, ox, oy, sw, sh) if want_zoom else False

        if not zoomed:
            # Level 0, or no capture available: draw over the live screen and
            # let the window's translucency show it through.
            self._set_alpha(self.cfg.get("alpha", 0.45))
            self._draw_cells(c, rx - ox, ry - oy, rw, rh)

        status = f"level {self.state.depth + 1}"
        if zoomed:
            zoom_factor = sw / rw if rw else 1.0
            status += f"   {zoom_factor:.0f}x"
        status += (f"   column {self.pending_col} - row?"
                   if self.pending_col is not None else "   column?")
        if self.state.exhausted:
            status += "   (deepest - space to click)"

        # A solid plate, not a halo: at 13px the outline is one pixel wide and
        # vanishes over white application content.
        font = (self.cfg.get("font_family", "Segoe UI"), 13, "bold")
        item = c.create_text(14, 12, text=status, font=font, anchor="nw",
                             fill=self.cfg.get("label_color", "#FFFFFF"))
        x0, y0, x1, y1 = c.bbox(item)
        plate = c.create_rectangle(x0 - 8, y0 - 5, x1 + 8, y1 + 5,
                                   fill=self.cfg.get("background", "#101018"),
                                   outline=self.cfg.get("line_color", "#00E5FF"))
        c.tag_lower(plate, item)

    def _draw_zoomed(self, c, ox, oy, sw, sh) -> bool:
        """Blow the current region up, then grid it.

        The region is roughly square (square cells), so it can't fill a 16:9
        screen without distortion. Instead of black bars we show a screen-shaped
        area centred on the region and dim everything outside it - the margins
        then carry the surrounding screen content, which is what orients you
        once you're 25x in.

        Returns False if the capture failed, so the caller can fall back to
        drawing the grid in place over the live screen.
        """
        rx, ry, rw, rh = self.state.rect
        (vx, vy, vw, vh), scale = capture.context_box(
            self.state.rect, self.state.root_rect, sw, sh)

        img = capture.crop_and_scale(
            self._screenshot,
            (vx - ox, vy - oy, vx - ox + vw, vy - oy + vh),
            (int(sw), int(sh)),
        )
        if img is None:
            return False

        # Where the region lands inside the displayed area.
        dx = (rx - vx) * (sw / vw)
        dy = (ry - vy) * (sh / vh)
        dw = rw * (sw / vw)
        dh = rh * (sh / vh)

        try:
            from PIL import ImageEnhance, ImageTk
            dim = float(self.cfg.get("context_brightness", 0.4))
            if dim < 1.0:
                l, t = int(round(dx)), int(round(dy))
                r, b = int(round(dx + dw)), int(round(dy + dh))
                inner = img.crop((max(0, l), max(0, t),
                                  min(img.width, r), min(img.height, b)))
                img = ImageEnhance.Brightness(img.convert("RGB")).enhance(dim)
                img.paste(inner, (max(0, l), max(0, t)))
            self._photo = ImageTk.PhotoImage(img)
        except Exception:
            return False

        # Opaque while zoomed: blending the magnified image with the real
        # screen underneath would show two different things at once.
        self._set_alpha(self.cfg.get("zoom_alpha", 1.0))

        c.create_image(0, 0, image=self._photo, anchor="nw")
        self._draw_cells(c, dx, dy, dw, dh)
        return True

    # -- standalone ---------------------------------------------------------

    def run_standalone(self) -> None:
        import tkinter as tk
        import keyboard

        self._root = tk.Tk()
        self._root.withdraw()

        hotkey = self.cfg.get("hotkey", "ctrl+alt+g")

        def toggle():
            # Tk is not thread-safe; marshal onto its event loop.
            self._root.after(0, lambda: self.hide() if self.visible else self.show())

        keyboard.add_hotkey(hotkey, toggle)

        print("=" * 62)
        print("  VoiceKey - mouse grid")
        print("=" * 62)
        print(f"  Toggle : {hotkey.upper()}")
        print(f"  Grid   : {self.cfg['cols']}x{self.cfg['rows']} "
              f"({self.cfg['cols'] * self.cfg['rows']} cells), "
              f"max depth {self.cfg['max_depth']}")
        x, y, w, h = mouse.virtual_screen()
        print(f"  Screen : {w}x{h} at ({x},{y})")
        step = (w / self.cfg['cols'], h / self.cfg['rows'])
        for d in range(1, self.cfg['max_depth'] + 1):
            print(f"    level {d}: {step[0]:.0f}x{step[1]:.0f} px per cell")
            step = (step[0] / self.cfg['cols'], step[1] / self.cfg['rows'])
        print("=" * 62)
        print("  digits pick a cell | space=click r=right d=double h=hold")
        print("  backspace=up  escape=cancel  |  Ctrl+C here to quit\n")

        try:
            self._root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            try:
                keyboard.unhook_all()
            except Exception:
                pass


def main() -> int:
    MouseGrid().run_standalone()
    return 0


if __name__ == "__main__":
    sys.exit(main())
