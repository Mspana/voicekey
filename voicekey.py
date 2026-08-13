#!/usr/bin/env python3
"""
VoiceKey - all three phases together.

  Hold SPACE (or a foot pedal)   dictate. An escape phrase inside the transcript
                                 fires an action, the way \\n works inside a
                                 string:  "ship it zulu enter"
  Hold CTRL (either one)         command only - no escape phrase needed, and the
                                 screen edge glows in colour while it listens.
                                 Never suppressed, and the capture is dropped as
                                 soon as another key follows, so Ctrl+C is still
                                 a copy.
  "zulu grid"                    mouse grid (no hotkey by default)
  Alt+Q                          stop (deactivate, keep running)
  Ctrl+Alt+G                     start again
  Esc                            abort whatever is in progress

Run `app.py` for the window; this module is the engine and also works headless.

Everything is remappable in config.json.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import actions as A
from actions import DEFAULT_ESCAPE

MISSING = []
try:
    import keyboard
except ImportError:
    MISSING.append("keyboard")
try:
    import sounddevice  # noqa: F401
except ImportError:
    MISSING.append("sounddevice")
if MISSING:
    print("Missing packages: " + ", ".join(MISSING))
    print("Install with:  pip install -r requirements.txt")
    sys.exit(1)

import mouse
from dictate import (Feedback, Recorder, TextOutput, Transcriber,
                     load_config, LOG_PATH)
from grid import MouseGrid, load_grid_config
from glow import Glow

import paths

HERE = paths.app_dir()

APP_DEFAULTS = {
    "escape_phrase": DEFAULT_ESCAPE,
    "command_key": "right ctrl",
    "grid_hotkey": None,
    "stop_hotkey": "alt+q",
    "start_hotkey": "ctrl+alt+g",
    "command_min_press_ms": 150,
    "nudge_steps": None,
}

GLOW_DEFAULTS = {
    "enabled": True,
    "animate": True,
    "thickness": 18,
    "segments": 120,
    "interval_ms": 90,
}


class ActionContext:
    """The side effects `actions.perform` needs, in one place."""

    def __init__(self, app):
        self.app = app

    def click(self, button: str, count: int = 1) -> None:
        {"left": mouse.left_click,
         "right": mouse.right_click,
         "middle": mouse.middle_click}[button](count)

    def move_to(self, x, y) -> None:
        mouse.move_to(int(x), int(y))

    def nudge(self, dx, dy, verb="move", scale=None, distance=None) -> None:
        """Relative cursor move. The verb picks the step size."""
        steps = {**A.DEFAULT_STEPS, **(self.app.app_cfg.get("nudge_steps") or {})}
        base = float(distance) if distance else float(steps.get(verb, steps["move"]))
        if distance is None and scale:
            base *= float(scale)

        x, y = mouse.position()
        vx, vy, vw, vh = mouse.virtual_screen()
        # Clamp to the desktop. Without this a few repeated bumps park the
        # cursor off-screen where it cannot be seen or recovered by voice.
        nx = min(max(x + dx * base, vx), vx + vw - 1)
        ny = min(max(y + dy * base, vy), vy + vh - 1)
        mouse.move_to(int(round(nx)), int(round(ny)))

    def hold(self, seconds) -> None:
        secs = float(seconds if seconds is not None
                     else self.app.grid_cfg.get("hold_seconds", 1.0))
        threading.Thread(target=mouse.hold_left, args=(secs,), daemon=True).start()

    def send_key(self, combo: str) -> None:
        keyboard.send(combo)

    def back(self, count: int, unit: str = "character") -> None:
        """Delete backwards by characters, words, or lines."""
        count = max(1, min(int(count), A.MAX_BACK))
        if unit == "word":
            # Ctrl+Backspace is the near-universal "delete previous word".
            for _ in range(count):
                keyboard.send("ctrl+backspace")
        elif unit == "line":
            for _ in range(count):
                keyboard.send("shift+home")     # select to line start
                keyboard.send("backspace")      # clear it
                keyboard.send("backspace")      # and eat the newline
        else:
            for _ in range(count):
                keyboard.send("backspace")

    def scroll(self, clicks: int) -> None:
        mouse.scroll(clicks)

    def app_command(self, command: str, spec: dict) -> bool:
        if command == "grid":
            self.app.open_grid(spec.get("col"), spec.get("row"))
            return True
        if command == "off":
            self.app.set_enabled(False)
            return True
        if command == "on":
            self.app.set_enabled(True)
            return True
        if command == "quit":
            self.app.quit()
            return True
        if command == "centre":
            vx, vy, vw, vh = mouse.virtual_screen()
            mouse.move_to(vx + vw // 2, vy + vh // 2)
            return True
        if command == "cursor":
            # "move mouse" with the grid open commits the current cell without
            # clicking; with it closed there is nothing to move to.
            g = self.app.grid
            if g is not None and g.visible:
                self.app._ui(g.commit, "move")
                return True
            return False
        return False


class VoiceKey:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.app_cfg = {**APP_DEFAULTS, **cfg.get("commands", {})}
        self.glow_cfg = {**GLOW_DEFAULTS, **cfg.get("glow", {})}
        self.grid_cfg = load_grid_config()

        self.escape_phrase = self.app_cfg.get("escape_phrase") or DEFAULT_ESCAPE
        self.ptt_key = cfg.get("push_to_talk_key", "space")
        self.command_key = self.app_cfg.get("command_key", "ctrl")
        self.passthrough = (cfg.get("passthrough_modifier") or "alt").lower()
        self.min_press = float(cfg.get("min_press_ms", 180)) / 1000.0
        self.command_min_press = float(self.app_cfg.get("command_min_press_ms", 150)) / 1000.0
        # Alt+Q stops it *functioning*; it no longer kills the process. The
        # window's close button is the only thing that quits.
        self.stop_hotkey = self.app_cfg.get("stop_hotkey", "alt+q")
        self.start_hotkey = self.app_cfg.get("start_hotkey", "ctrl+alt+g")

        self.feedback = Feedback(cfg)
        self.recorder = Recorder(cfg)
        self.transcriber = Transcriber(cfg)
        self.output = TextOutput(cfg)
        self.context = ActionContext(self)

        self.enabled = bool(cfg.get("start_enabled", True))
        self._mode = None          # None | "dictate" | "command"
        self._press_time = 0.0
        self._busy = threading.Lock()

        self.root = None
        self.grid = None
        self.glow = None

        # Set by a UI to mirror state. Both are optional and default to no-ops,
        # so the engine runs identically with or without a window.
        self.on_state = None          # (state: str) -> None
        self.on_activity = None       # (text: str) -> None

    # -- ui plumbing --------------------------------------------------------

    def _ui(self, fn, *args) -> None:
        """Marshal onto the Tk thread. Keyboard hooks fire on their own."""
        if self.root is not None:
            self.root.after(0, lambda: fn(*args))

    def open_grid(self, col=None, row=None) -> None:
        def run():
            if not self.grid.visible:
                self.grid.show()
            if col is not None and row is not None:
                self.grid.select_cell(int(col), int(row))
        self._ui(run)

    def _emit_state(self, state: str) -> None:
        if self.on_state:
            try:
                self.on_state(state)
            except Exception:
                pass

    def _emit_activity(self, text: str) -> None:
        if self.on_activity:
            try:
                self.on_activity(text)
            except Exception:
                pass

    def set_enabled(self, value: bool) -> None:
        if self.enabled == value:
            return
        self.enabled = value
        self._emit_state("ready" if value else "stopped")
        print(f"\n*** VoiceKey {'ENABLED' if value else 'DISABLED'} ***"
              + ("" if value else "  (all keys behave normally)"))
        self.feedback.toggled(value)
        if not value:
            self._abort_capture()

    def toggle(self) -> None:
        self.set_enabled(not self.enabled)

    def _panic_abort(self) -> None:
        """Escape: drop any capture and close the grid. Always available."""
        if self._mode is not None or (self.grid is not None and self.grid.visible):
            self._abort_capture()
            self._ui(self.grid.hide)
            self.feedback.error()

    _MODIFIERS = {"ctrl", "left ctrl", "right ctrl", "alt", "left alt",
                  "right alt", "shift", "left shift", "right shift",
                  "windows", "left windows", "right windows", "alt gr"}

    def _watch_keys(self, event) -> None:
        """Abandon a command capture the moment another key is pressed.

        This is what makes hooking Ctrl harmless. Holding Ctrl to press Ctrl+C
        starts a capture on the way down; the C cancels it. Silently - no beep,
        no transcription request, no stray text. The shortcut just works.
        """
        if self._mode != "command":
            return
        if getattr(event, "event_type", None) != "down":
            return
        name = (getattr(event, "name", "") or "").lower()
        if name in self._MODIFIERS:
            return
        self._abort_capture()

    def quit(self) -> None:
        print("\nQuitting.")
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        if self.root is not None:
            self.root.after(0, self.root.quit)

    # -- capture ------------------------------------------------------------

    def _abort_capture(self) -> None:
        if self._mode is not None:
            self._mode = None
            self.recorder.stop()
            self._ui(self.glow.hide)
            self._emit_state("ready" if self.enabled else "stopped")

    def _start(self, mode: str) -> bool:
        try:
            self.recorder.start()
        except Exception as exc:
            print(f"[error] could not open microphone: {exc}")
            self.feedback.error()
            return False
        self._mode = mode
        self._press_time = time.time()
        self._emit_state("listening_command" if mode == "command" else "listening")
        self.feedback.listening()
        # Visual reinforcement only - the earcon above is the real signal.
        # Colour for commands, grey for dictation: same shape so it reads as
        # the same state, different lightness so the two are told apart
        # without relying on hue.
        self._ui(self.glow.show, mouse.virtual_screen(), mode)
        return True

    def _finish(self):
        mode = self._mode
        self._mode = None
        held = time.time() - self._press_time
        audio = self.recorder.stop()
        self._ui(self.glow.hide)
        return mode, held, audio

    # -- dictation key ------------------------------------------------------

    def on_ptt_press(self, event) -> None:
        if not self.enabled or keyboard.is_pressed(self.passthrough):
            self._emit_literal()
            return
        if self._mode is None:
            self._start("dictate")

    def on_ptt_release(self, event) -> None:
        if self._mode != "dictate":
            return
        mode, held, audio = self._finish()
        if held < self.min_press:
            self._emit_literal()
            return
        if audio is None or len(audio) == 0:
            self.feedback.error()
            return
        self.feedback.captured()
        threading.Thread(target=self._process, args=(audio, mode, held),
                         daemon=True).start()

    def _emit_literal(self) -> None:
        if self.ptt_key in ("space", "spacebar"):
            try:
                keyboard.write(" ", delay=0)
            except Exception:
                pass

    # -- command key --------------------------------------------------------

    def _cmd_event_is_ours(self, event) -> bool:
        """A modifier held with something else is part of a real shortcut, not
        a request to listen. Alt+Ctrl+G must stay Alt+Ctrl+G."""
        for mod in ("alt", "shift", "windows"):
            try:
                if keyboard.is_pressed(mod):
                    return False
            except Exception:
                pass
        return True

    def on_cmd_press(self, event) -> None:
        if not self._cmd_event_is_ours(event):
            return
        if not self.enabled or self._mode is not None:
            return
        self._start("command")

    def on_cmd_release(self, event) -> None:
        if self._mode != "command":
            return
        mode, held, audio = self._finish()
        if held < self.command_min_press or audio is None or len(audio) == 0:
            return                       # a tap is not a command
        self.feedback.captured()
        threading.Thread(target=self._process, args=(audio, mode, held),
                         daemon=True).start()

    # -- transcription + dispatch ------------------------------------------

    def _process(self, audio, mode: str, held: float) -> None:
        with self._busy:
            self._emit_state("working")
            try:
                text = self.transcriber.transcribe(self.recorder.to_wav_bytes(audio))
            except Exception as exc:
                print(f"[error] transcription failed: {exc}")
                self._emit_activity(f"error: {exc}")
                self._emit_state("ready" if self.enabled else "stopped")
                self.feedback.error()
                return

            self._emit_state("ready" if self.enabled else "stopped")

            if not text:
                print(f"[{mode} {held:.1f}s] (empty)")
                self._emit_activity("heard nothing")
                self.feedback.error()
                return

            print(f"[{mode} {held:.1f}s] {text}")
            self._emit_activity(text)
            if self.cfg.get("log_transcripts", True):
                try:
                    with LOG_PATH.open("a", encoding="utf-8") as fh:
                        fh.write(f"{datetime.now().isoformat(timespec='seconds')}"
                                 f"\t{mode}\t{text}\n")
                except Exception:
                    pass

            # While the grid is up, a bare "four three" is a cell, not prose.
            if self.grid is not None and self.grid.visible and self._grid_voice(text):
                return

            segments = A.parse(text, self.escape_phrase,
                               command_only=(mode == "command"))
            self._dispatch(segments)

    def _grid_voice(self, text: str) -> bool:
        """Two leading numbers drive the visible grid: 'four three'."""
        tokens = A.tokenise(text)
        col, used = A.parse_number(tokens, 0)
        if col is None:
            return False
        row, used2 = A.parse_number(tokens, used)
        if row is None:
            self._ui(self.grid.choose_column, int(col))
            self.feedback.captured()
            return True
        self._ui(self.grid.select_cell, int(col), int(row))
        self.feedback.captured()
        return True

    def _dispatch(self, segments: list) -> None:
        for kind, payload in segments:
            if kind == "text":
                self.output.emit(payload)
            elif kind == "action":
                ok = A.perform(payload, self.context)
                print(f"    -> {A.describe(payload)}" + ("" if ok else "  [FAILED]"))
                if not ok:
                    self.feedback.error()
            elif kind == "unknown":
                # Heard the escape phrase, but what followed was not a command.
                # This gets its own sound on purpose: "I heard you and did
                # nothing" is a different event from "I was not listening", and
                # every tool I looked at conflates the two.
                print(f"    -> ? not a command: {payload!r}")
                self.feedback.error()

    # -- run ----------------------------------------------------------------

    # -- lifecycle for an embedding UI --------------------------------------

    def attach(self, root) -> None:
        """Wire everything onto an existing Tk root, without a mainloop.

        Split out of run() so app.py can own the window and the loop while the
        engine stays exactly the same in both entry points.
        """
        self.root = root
        self.grid = MouseGrid(cfg=self.grid_cfg)
        self.grid._root = root
        self.glow = Glow(root, self.glow_cfg)

        keyboard.on_press_key(self.ptt_key, self.on_ptt_press, suppress=True)
        keyboard.on_release_key(self.ptt_key, self.on_ptt_release, suppress=True)

        # NEVER suppressed: Ctrl has to keep working as Ctrl. Both ctrl keys
        # trigger it, which is fine - _watch_keys drops the capture as soon as
        # any other key follows, so real shortcuts are untouched.
        keyboard.on_press_key(self.command_key, self.on_cmd_press, suppress=False)
        keyboard.on_release_key(self.command_key, self.on_cmd_release, suppress=False)
        keyboard.hook(self._watch_keys, suppress=False)

        # No grid hotkey by default. The grid is a voice command ("zulu grid"),
        # and a hotkey for it kept colliding with the start/stop keys - which
        # meant starting the app dropped you straight into a grid. Set
        # commands.grid_hotkey in config.json if you want one back.
        grid_hotkey = self.app_cfg.get("grid_hotkey")
        if grid_hotkey:
            keyboard.add_hotkey(grid_hotkey, lambda: self._ui(self.grid.show),
                                suppress=False)
        keyboard.add_hotkey("esc", self._panic_abort, suppress=False)

        # Deactivate and reactivate, rather than quit. Quitting is the window's
        # close button - a hotkey that kills the process is too easy to hit by
        # accident when the process is the only way you can type.
        keyboard.add_hotkey(self.stop_hotkey, lambda: self.set_enabled(False),
                            suppress=False)
        keyboard.add_hotkey(self.start_hotkey, lambda: self.set_enabled(True),
                            suppress=False)
        keyboard.add_hotkey(self.cfg.get("master_toggle_hotkey", "ctrl+alt+d"),
                            self.toggle, suppress=False)
        self._announce()

    def detach(self) -> None:
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        try:
            if self.glow is not None:
                self.glow.hide()
        except Exception:
            pass

    def _announce(self) -> None:
        bar = "=" * 66
        print(bar)
        print("  VoiceKey")
        print(bar)
        print(f"  Dictate       : hold {self.ptt_key.upper()}")
        print(f"  Literal space : {self.passthrough.upper()}+{self.ptt_key.upper()}")
        print(f"  Command       : hold {self.command_key.upper()} (either one)")
        print(f"  Escape phrase : \"{self.escape_phrase}\"   "
              f"e.g.  \"ship it {self.escape_phrase} enter\"")
        gh = self.app_cfg.get("grid_hotkey")
        print(f"  Grid          : say \"{self.escape_phrase} grid\""
              + (f"   or {gh.upper()}" if gh else ""))
        print(f"  Stop          : {self.stop_hotkey.upper()}")
        print(f"  Start         : {self.start_hotkey.upper()}")
        print(f"  Abort         : ESC")
        print(f"  Status        : {'RUNNING' if self.enabled else 'STOPPED'}")
        print(bar + "\n")

    def run(self) -> None:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        self.attach(root)
        print("  (console mode - close this window or press Ctrl+C to quit)\n")
        try:
            root.mainloop()
        except KeyboardInterrupt:
            pass
        finally:
            self.detach()
            print("\nStopping.")


def main() -> int:
    cfg = load_config()
    try:
        app = VoiceKey(cfg)
    except Exception as exc:
        print(f"[fatal] {exc}")
        return 1
    try:
        app.run()
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
