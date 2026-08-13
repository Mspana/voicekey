#!/usr/bin/env python3
"""Renders the listening glow and screenshots it. Dev tool, not part of the app.

Run:  xvfb-run -s "-screen 0 1920x1080x24" python3.12 render_glow.py
"""
import sys, subprocess, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tkinter as tk
import glow as G

W, H = 1920, 1080


def render(name, phase=0, thickness=44, segments=120):
    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry(f"{W}x{H}+0+0")
    # Stand-in for the desktop showing through the transparent interior.
    root.configure(bg="#243044")
    canvas = tk.Canvas(root, width=W, height=H, highlightthickness=0, bg="#243044")
    canvas.pack(fill="both", expand=True)
    canvas.create_text(W // 2, H // 2, text="listening…", fill="#93A1B5",
                       font=("DejaVu Sans", 40, "bold"))

    g = G.Glow(root, {"thickness": thickness, "segments": segments})
    g._canvas = canvas
    g._items = []
    g._build_segments(W, H)
    g._phase = phase
    g._paint()
    root.update()
    root.update_idletasks()
    time.sleep(0.25)

    png = Path(f"{name}.png")
    subprocess.run(["import", "-window", "root", str(png)], check=True)
    root.destroy()
    print(f"  wrote {png}")


render("glow_frame_a", phase=0)
render("glow_frame_b", phase=60)
print("done")
