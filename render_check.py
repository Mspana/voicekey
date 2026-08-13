#!/usr/bin/env python3
"""Renders the grid overlay and screenshots it, so the visual output can be
checked without a Windows box. Dev tool, not part of the app.

Run:  xvfb-run -s "-screen 0 1920x1080x24" python3.12 render_check.py
"""
import sys, subprocess, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tkinter as tk
from PIL import Image, ImageDraw
import grid as G

W, H = 1920, 1080
CFG = G.load_grid_config()


def fake_desktop():
    """Stand-in for a real screen grab. Deliberately dense with small targets,
    so the zoom levels are visually obvious in the rendered output."""
    img = Image.new("RGB", (W, H), (236, 238, 242))
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, 40], fill=(24, 27, 34))
    for i in range(22):
        x = 14 + i * 46
        d.rectangle([x, 10, x + 30, 30],
                    fill=(70, 130, 220) if i % 3 else (220, 90, 70))
        d.text((x + 11, 15), f"{i:02d}", fill=(255, 255, 255))

    d.rectangle([0, 40, 260, H], fill=(248, 249, 251), outline=(214, 218, 226))
    for i in range(24):
        y = 60 + i * 40
        d.rectangle([12, y, 32, y + 20], fill=(120, 170, 240))
        d.text((44, y + 5), f"sidebar item {i:02d}", fill=(50, 56, 66))

    d.rectangle([280, 70, 1880, 1040], fill=(255, 255, 255), outline=(206, 210, 218))
    for c_i, cx in enumerate((300, 700, 1100, 1500)):
        d.text((cx, 86), ["name", "status", "owner", "updated"][c_i], fill=(90, 96, 108))
    for r in range(23):
        y = 116 + r * 39
        d.line([292, y + 30, 1868, y + 30], fill=(234, 236, 240))
        d.text((300, y + 8), f"record-{r:03d}-alpha", fill=(34, 38, 46))
        d.text((700, y + 8), "active" if r % 3 else "blocked",
               fill=(30, 130, 70) if r % 3 else (190, 60, 50))
        d.text((1100, y + 8), f"user{r % 7}@example.com", fill=(34, 38, 46))
        d.text((1500, y + 8), f"2026-08-{(r % 28) + 1:02d}", fill=(34, 38, 46))
        for k, lbl in enumerate(("edit", "del")):
            bx = 1740 + k * 62
            d.rectangle([bx, y + 4, bx + 54, y + 26],
                        fill=(240, 242, 246), outline=(198, 204, 214))
            d.text((bx + 14, y + 9), lbl, fill=(60, 66, 78))
    return img


def render(name: str, col=None, path=(), note=""):
    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry(f"{W}x{H}+0+0")
    root.configure(bg=CFG["background"])
    canvas = tk.Canvas(root, width=W, height=H, highlightthickness=0,
                       bg=CFG["background"])
    canvas.pack(fill="both", expand=True)

    g = G.MouseGrid(cfg=CFG)
    g._build_window = lambda: None
    g._set_alpha = lambda v: None       # no compositor under Xvfb
    g.show()
    g._screenshot = fake_desktop()      # stand in for the real grab
    g._canvas = canvas
    for c_, r_ in path:
        g.type_digit(str(c_)); g.type_digit(str(r_))
    if col is not None:
        g.type_digit(str(col))
    g._draw()
    root.update()
    root.update_idletasks()
    time.sleep(0.3)

    png = Path(f"{name}.png")
    subprocess.run(["import", "-window", "root", str(png)], check=True)
    cw = g.state.rect[2] / g.state.cols
    ch = g.state.rect[3] / g.state.rows
    zoom = W / g.state.rect[2]
    root.destroy()
    print(f"  {png}  depth={len(path)}  cell={cw:.1f}x{ch:.1f}px  zoom={zoom:.0f}x  {note}")


# Two keystrokes per level: column, then row.
render("grid_1_columns", note="pick a column")
render("grid_2_column_armed", col=5, note="column 5 armed, pick a row")
render("grid_3_zoomed", path=((5, 3),), note="after 5 then 3")
render("grid_4_armed_zoomed", path=((5, 3),), col=4, note="zoomed, column 4 armed")
render("grid_5_deep", path=((5, 3), (4, 2)), note="two levels in")
print("done")
