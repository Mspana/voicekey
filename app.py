#!/usr/bin/env python3
"""
VoiceKey - the window.

A small ordinary application, the shape of a VPN client: a status dot, a line
of text, and Start / Stop. Closing it quits; Stop only deactivates.

    pythonw app.py          no console
    python  app.py          with a console, for watching transcripts

The taskbar icon is redrawn from the same state colour, so the dot is readable
without bringing the window forward.
"""

from __future__ import annotations

import datetime
import os
import sys
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

import paths

HERE = paths.app_dir()
LOG = HERE / "voicekey.log"


def log(message: str) -> None:
    """Append to voicekey.log.

    Under pythonw there is no console, so an exception at startup vanishes
    without trace. Everything interesting goes here as well as to stdout.
    """
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp}  {message}"
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    try:
        print(line)
    except Exception:
        pass


def fatal(title: str, detail: str, hint: str = "") -> None:
    """Report a startup failure in a window, since there may be no console."""
    log(f"FATAL {title}: {detail}")
    if hint:
        log(f"      hint: {hint}")
    try:
        import tkinter as _tk
        from tkinter import scrolledtext
        r = _tk.Tk()
        r.title("VoiceKey - could not start")
        r.configure(bg="#F1ECE1")
        _tk.Label(r, text=title, bg="#F1ECE1", fg="#C0392B",
                  font=(None, 13, "bold")).pack(anchor="w", padx=16, pady=(16, 4))
        if hint:
            _tk.Label(r, text=hint, bg="#F1ECE1", fg="#232120", justify="left",
                      wraplength=520).pack(anchor="w", padx=16, pady=(0, 10))
        box = scrolledtext.ScrolledText(r, width=72, height=14, bg="#FBF8F2",
                                        fg="#5D574C", relief="flat", bd=0,
                                        font=("Consolas", 9))
        box.pack(padx=16, pady=(0, 8), fill="both", expand=True)
        box.insert("1.0", detail)
        box.configure(state="disabled")
        _tk.Label(r, text=f"Also written to {LOG.name}", bg="#F1ECE1",
                  fg="#8C8578", font=(None, 8)).pack(anchor="w", padx=16, pady=(0, 12))
        r.mainloop()
    except Exception:
        pass


import icons
import paths
import textfx
from dictate import load_config
from voicekey import VoiceKey

IS_WINDOWS = sys.platform.startswith("win")

# Eggshell paper, very dark grey ink.
BG = "#F1ECE1"
CARD = "#FBF8F2"
EDGE = "#DED7C9"
TEXT = "#232120"
MUTED = "#8C8578"

# The wordmark gradient: near-black into a warm taupe.
GRAD_A = "#1E1C1A"
GRAD_B = "#8A7452"

# Dot colours, darkened from the dark-theme set so they hold up on eggshell.
# Colour, label, hint. The dot pulses in the two listening states.
STATES = {
    "stopped":           ("#A29A8C", "Stopped",    "Ctrl+Alt+G to start"),
    "ready":             ("#1F9D5B", "Ready",      "Hold Space to dictate"),
    "listening":         ("#E2542A", "Listening…", "Release to transcribe"),
    "listening_command": ("#7C4DE0", "Command…",   "Release to run"),
    "working":           ("#C98200", "Working…",   "Transcribing"),
}


def _hwnd(root):
    """The real top-level window handle behind a Tk window.

    GetAncestor(GA_ROOT) rather than GetParent: Tk's structure differs between
    a normal window and an overrideredirect one, and GetParent returns 0 for
    the latter. GA_ROOT always walks up to the actual top-level, which is the
    window the taskbar and WM_SETICON care about.
    """
    import ctypes
    u = ctypes.windll.user32
    u.GetAncestor.restype = ctypes.c_void_p
    u.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    wid = root.winfo_id()
    return u.GetAncestor(wid, 2) or wid          # GA_ROOT


def claim_taskbar(root) -> None:
    """Put a frameless window back on the taskbar.

    overrideredirect(True) removes the native title bar, and Windows then also
    drops the taskbar button - the window becomes a tool window. Clearing
    WS_EX_TOOLWINDOW and setting WS_EX_APPWINDOW puts it back.
    """
    if not IS_WINDOWS:
        return
    try:
        import ctypes
        GWL_EXSTYLE, WS_EX_APPWINDOW, WS_EX_TOOLWINDOW = -20, 0x00040000, 0x00000080
        u = ctypes.windll.user32
        get = getattr(u, "GetWindowLongPtrW", u.GetWindowLongW)
        setl = getattr(u, "SetWindowLongPtrW", u.SetWindowLongW)
        get.restype, get.argtypes = ctypes.c_longlong, [ctypes.c_void_p, ctypes.c_int]
        setl.restype = ctypes.c_longlong
        setl.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong]

        h = _hwnd(root)
        style = get(h, GWL_EXSTYLE)
        setl(h, GWL_EXSTYLE, (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW)
        # The style only takes effect on re-show.
        root.withdraw()
        root.after(10, root.deiconify)
    except Exception:
        pass


def minimize(root) -> None:
    """Minimise a frameless window. iconify() does not work once
    overrideredirect is set, so go through ShowWindow directly."""
    if IS_WINDOWS:
        try:
            import ctypes
            u = ctypes.windll.user32
            u.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
            u.ShowWindow(_hwnd(root), 6)          # SW_MINIMIZE
            return
        except Exception:
            pass
    try:
        root.iconify()
    except Exception:
        pass


class Dot(tk.Canvas):
    """The status dot. Also the source of the taskbar icon."""

    def __init__(self, master, size=30, **kw):
        super().__init__(master, width=size, height=size, bg=CARD,
                         highlightthickness=0, **kw)
        self.size = size
        self.colour = STATES["stopped"][0]
        self.pulsing = False
        self._phase = 0.0
        self._item = None
        self._halo = None
        self._draw(1.0)

    def _draw(self, scale: float) -> None:
        self.delete("all")
        s = self.size
        # 0.20 leaves room for the halo (1.9x) at full pulse (1.28x) without
        # the oval clipping to a square against the canvas edge.
        r = (s * 0.20) * scale
        cx = cy = s / 2
        # A dim halo makes the dot legible on the dark card without needing a
        # second colour for "active".
        self._halo = self.create_oval(cx - r * 1.9, cy - r * 1.9,
                                      cx + r * 1.9, cy + r * 1.9,
                                      outline="", fill=self._mix(self.colour, CARD, 0.72))
        self._item = self.create_oval(cx - r, cy - r, cx + r, cy + r,
                                      outline="", fill=self.colour)

    @staticmethod
    def _mix(a: str, b: str, t: float) -> str:
        ar, ag, ab = (int(a[i:i + 2], 16) for i in (1, 3, 5))
        br, bg_, bb = (int(b[i:i + 2], 16) for i in (1, 3, 5))
        return "#%02X%02X%02X" % (int(ar + (br - ar) * t),
                                  int(ag + (bg_ - ag) * t),
                                  int(ab + (bb - ab) * t))

    def set_state(self, colour: str, pulsing: bool) -> None:
        self.colour = colour
        self.pulsing = pulsing
        if not pulsing:
            self._phase = 0.0
            self._draw(1.0)

    def tick(self) -> None:
        if self.pulsing:
            import math
            self._phase += 0.22
            self._draw(1.0 + 0.28 * math.sin(self._phase))


class App:
    def __init__(self):
        # Must happen before any window exists, or Windows groups us under
        # python.exe on the taskbar and shows ITS icon.
        log(f"app id set: {icons.set_app_id()}")
        self.root = tk.Tk()
        self.root.title("VoiceKey")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.overrideredirect(True)   # no native title bar
        self._drag = None

        self.state = "stopped"
        self._icon_cache = {}
        self._icon_image = None
        self._icon_logged = False

        self._build()

        cfg = load_config()
        self.engine = VoiceKey(cfg)
        self.engine.on_state = lambda s: self.root.after(0, self.set_state, s)
        self.engine.attach(self.root)

        claim_taskbar(self.root)           # frameless windows lose it otherwise
        self.set_state("ready" if self.engine.enabled else "stopped")
        # The taskbar button is created by that re-show, so the icon has to be
        # set again once it exists.
        self.root.after(150, lambda: self._set_taskbar_dot(STATES[self.state][0]))
        self._pulse()

    # -- layout -------------------------------------------------------------

    def _image(self, pil_image):
        """PIL image -> PhotoImage, kept alive by the caller."""
        try:
            from PIL import ImageTk
            return ImageTk.PhotoImage(pil_image)
        except Exception:
            return None

    def _build(self) -> None:
        textfx.register_bundled()
        fam = textfx.tk_family(self.root)
        self.f_title = (fam, 15, "bold")
        self.f_hint = (fam, 10)
        self.f_bar = (fam, 10, "bold")
        self.f_btn = (fam, 11, "bold")

        outer = tk.Frame(self.root, bg=BG, highlightbackground=EDGE,
                         highlightthickness=1)
        outer.pack(fill="both", expand=True)

        # ---- our own title bar ----
        bar = tk.Frame(outer, bg=BG, height=30)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        self.lbl_brand = tk.Label(bar, bg=BG, bd=0)
        self._brand_img = self._image(
            textfx.gradient_text("voicekey", 17, GRAD_A, GRAD_B, BG))
        if self._brand_img:
            self.lbl_brand.configure(image=self._brand_img)
        else:
            self.lbl_brand.configure(text="voicekey", fg=TEXT, font=self.f_bar)
        self.lbl_brand.pack(side="left", padx=12)

        self.btn_close = self._chrome_button(bar, "✕", self.quit, "#D8453F", "#FFFFFF")
        self.btn_close.pack(side="right")
        self.btn_min = self._chrome_button(bar, "–", self.minimise, "#E3DCCC", TEXT)
        self.btn_min.pack(side="right")

        # Dragging the bar moves the window, since there is no native one.
        for w in (bar,) + tuple(bar.winfo_children()):
            if w in (self.btn_close, self.btn_min):
                continue
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        pad = tk.Frame(outer, bg=BG)
        pad.pack(fill="both", expand=True, padx=14, pady=(2, 14))

        card = tk.Frame(pad, bg=CARD, highlightbackground=EDGE,
                        highlightthickness=1)
        card.pack(fill="x")

        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x", padx=16, pady=(16, 12))

        self.dot = Dot(row, size=30)
        self.dot.pack(side="left", padx=(0, 12))

        labels = tk.Frame(row, bg=CARD)
        labels.pack(side="left", fill="x", expand=True)
        self.lbl_state = tk.Label(labels, bg=CARD, fg=TEXT, anchor="w",
                                  font=self.f_title)
        self.lbl_state.pack(fill="x")
        self._state_img = None
        self.lbl_hint = tk.Label(labels, text="", bg=CARD, fg=MUTED,
                                 font=self.f_hint, anchor="w")
        self.lbl_hint.pack(fill="x")

        buttons = tk.Frame(card, bg=CARD)
        buttons.pack(fill="x", padx=16, pady=(0, 16))
        self.btn_start = self._button(buttons, "Start", self.start, TEXT)
        self.btn_start.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.btn_stop = self._button(buttons, "Stop", self.stop, CARD)
        self.btn_stop.pack(side="left", expand=True, fill="x", padx=(5, 0))

        self.root.update_idletasks()
        self.root.geometry(f"330x{self.root.winfo_reqheight()}")

    def _chrome_button(self, parent, text, command, hover, hover_fg):
        b = tk.Label(parent, text=text, bg=BG, fg=MUTED, font=(None, 11),
                     width=4, cursor="hand2")
        b.bind("<Button-1>", lambda _e: command())
        b.bind("<Enter>", lambda _e: b.configure(bg=hover, fg=hover_fg))
        b.bind("<Leave>", lambda _e: b.configure(bg=BG, fg=MUTED))
        b.pack_propagate(False)
        return b

    def _drag_start(self, event) -> None:
        self._drag = (event.x_root - self.root.winfo_x(),
                      event.y_root - self.root.winfo_y())

    def _drag_move(self, event) -> None:
        if not getattr(self, "_drag", None):
            return
        self.root.geometry(f"+{event.x_root - self._drag[0]}"
                           f"+{event.y_root - self._drag[1]}")

    def minimise(self) -> None:
        minimize(self.root)

    def _button(self, parent, text, command, colour):
        primary = colour == TEXT
        return tk.Button(parent, text=text, command=command, font=self.f_btn,
                         bg=colour, fg=BG if primary else TEXT,
                         activebackground=colour,
                         activeforeground=BG if primary else TEXT,
                         relief="flat", bd=0,
                         highlightthickness=0 if primary else 1,
                         highlightbackground=EDGE, highlightcolor=EDGE,
                         cursor="hand2", pady=7)

    # -- state --------------------------------------------------------------

    def set_state(self, state: str) -> None:
        if state not in STATES:
            return
        self.state = state
        colour, label, hint = STATES[state]
        img = self._image(textfx.solid_text(label, 21, TEXT, CARD))
        if img:
            self._state_img = img          # PhotoImages are not owned by tk
            self.lbl_state.configure(image=img, text="")
        else:
            self.lbl_state.configure(text=label, fg=TEXT)
        self.lbl_hint.configure(text=hint)
        self.dot.set_state(colour, pulsing=state.startswith("listening"))

        running = state != "stopped"
        self.btn_start.configure(state="disabled" if running else "normal",
                                 bg="#E6E0D3" if running else TEXT,
                                 fg="#B0A897" if running else BG)
        self.btn_stop.configure(state="normal" if running else "disabled",
                                bg=CARD, fg=TEXT if running else "#BDB5A5")
        self._set_taskbar_dot(colour)

    def _set_taskbar_dot(self, colour: str) -> None:
        """Recolour the window and taskbar icon to match the state.

        Windows needs a real .ico via iconbitmap for the taskbar; iconphoto
        alone leaves it showing whatever python.exe uses.
        """
        path = icons.ico_path(colour)
        if not path:
            return
        # Tk first (harmless, and it is what non-Windows uses)...
        try:
            self.root.iconbitmap(default=path)
        except Exception:
            try:
                self.root.iconbitmap(path)
            except Exception:
                pass
        # ...then the authoritative route: WM_SETICON straight to the handle.
        # Tk's own icon handling does not reliably reach a window whose
        # extended style we rewrote to get the taskbar button back.
        try:
            ok = icons.apply_to_window(_hwnd(self.root), path)
            if not self._icon_logged:
                self._icon_logged = True
                log(f"icon: {path}  WM_SETICON={'ok' if ok else 'failed'}")
        except Exception as exc:
            log(f"icon: failed to apply ({exc})")
        icons.apply_to_console(path)

    def _pulse(self) -> None:
        self.dot.tick()
        self.root.after(60, self._pulse)

    # -- actions ------------------------------------------------------------

    def start(self) -> None:
        self.engine.set_enabled(True)
        self.set_state("ready")

    def stop(self) -> None:
        self.engine.set_enabled(False)
        self.set_state("stopped")

    def quit(self) -> None:
        try:
            self.engine.detach()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self) -> None:
        self.root.mainloop()


def ask_for_key() -> bool:
    """First-run key entry, and save it into config.json beside the exe.

    A single downloaded .exe has no terminal to `setx` in, so telling the user
    to set an environment variable is a dead end. This asks, writes it next to
    the exe, and carries on.
    """
    import json
    result = {"ok": False}
    r = tk.Tk()
    r.title("VoiceKey - setup")
    r.configure(bg=BG)
    r.resizable(False, False)

    tk.Label(r, text="One thing first", bg=BG, fg=TEXT,
             font=(textfx.tk_family(r), 15, "bold")).pack(
        anchor="w", padx=20, pady=(20, 4))
    tk.Label(r, text="VoiceKey needs an OpenAI API key to transcribe speech.\n"
                     "Paste it here and it will be saved next to the app.",
             bg=BG, fg=MUTED, justify="left",
             font=(textfx.tk_family(r), 10)).pack(anchor="w", padx=20)

    entry = tk.Entry(r, width=46, show="•", relief="flat", bg=CARD, fg=TEXT,
                     insertbackground=TEXT, font=("Consolas", 11))
    entry.pack(padx=20, pady=(14, 6), ipady=6, fill="x")
    entry.focus_set()

    err = tk.Label(r, text="", bg=BG, fg="#C0392B",
                   font=(textfx.tk_family(r), 9))
    err.pack(anchor="w", padx=20)

    def save(_event=None):
        key = entry.get().strip()
        if not key.startswith("sk-") or len(key) < 20:
            err.configure(text="That does not look like a key (they start sk-).")
            return
        try:
            path = paths.config_path()
            cfg = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            cfg["api_key"] = key
            path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            err.configure(text=f"Could not save: {exc}")
            return
        log(f"api key saved to {paths.config_path()}")
        result["ok"] = True
        r.destroy()

    entry.bind("<Return>", save)
    row = tk.Frame(r, bg=BG)
    row.pack(fill="x", padx=20, pady=(10, 18))
    tk.Button(row, text="Save and start", command=save, relief="flat", bd=0,
              bg=TEXT, fg=BG, activebackground=TEXT, activeforeground=BG,
              font=(textfx.tk_family(r), 11, "bold"), cursor="hand2",
              pady=7).pack(side="left", expand=True, fill="x")
    tk.Button(row, text="Quit", command=r.destroy, relief="flat", bd=0,
              bg=CARD, fg=TEXT, highlightthickness=1, highlightbackground=EDGE,
              font=(textfx.tk_family(r), 11), cursor="hand2",
              pady=7).pack(side="left", padx=(8, 0))

    r.mainloop()
    return result["ok"]


def preflight() -> str:
    """Return a human explanation of anything that will stop us starting."""
    cfg = load_config()
    if not (cfg.get("api_key") or os.environ.get("OPENAI_API_KEY")):
        return ("No OpenAI API key.\n\n"
                "Either set it once for your account:\n"
                '    setx OPENAI_API_KEY "sk-..."\n'
                "then open a NEW terminal, or put it straight into config.json:\n"
                '    "api_key": "sk-..."\n\n'
                "A key set with `set` in one terminal is not visible to a "
                "double-clicked shortcut, which is the usual cause.")
    return ""


def main() -> int:
    log("=" * 60)
    log(f"starting  python={sys.version.split()[0]}  exe={sys.executable}")
    log(f"cwd={os.getcwd()}")

    if preflight():
        log("no api key - asking")
        if not ask_for_key():
            log("setup cancelled")
            return 1

    try:
        app = App()
    except Exception as exc:
        fatal(f"{type(exc).__name__}: {exc}", traceback.format_exc(),
              "This happened while starting up, before the window appeared.")
        return 1

    log("window up, engine attached")
    try:
        app.run()
    except Exception as exc:
        fatal(f"{type(exc).__name__}: {exc}", traceback.format_exc(),
              "This happened while running.")
        return 1
    log("clean exit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
