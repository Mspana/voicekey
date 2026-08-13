#!/usr/bin/env python3
"""
VoiceKey - Phase 1: push-to-talk dictation.

Hold the push-to-talk key (default: spacebar, or a foot pedal), speak, release.
The transcript is typed into whatever window has focus.

  Alt+Space          -> types a real space (passthrough)
  Ctrl+Alt+D         -> master enable/disable (turn OFF before gaming)
  Ctrl+C in console  -> quit

Requires OPENAI_API_KEY in the environment, or "api_key" in config.json.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
import wave
import threading
import traceback
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------- dependencies

MISSING = []
try:
    import numpy as np
except ImportError:
    MISSING.append("numpy")
try:
    import sounddevice as sd
except ImportError:
    MISSING.append("sounddevice")
try:
    import keyboard
except ImportError:
    MISSING.append("keyboard")
try:
    import pyperclip
except ImportError:
    MISSING.append("pyperclip")
try:
    from openai import OpenAI
except ImportError:
    MISSING.append("openai")

if MISSING:
    print("Missing packages: " + ", ".join(MISSING))
    print("Install with:  pip install -r requirements.txt")
    sys.exit(1)

IS_WINDOWS = sys.platform.startswith("win")
if IS_WINDOWS:
    import winsound


import paths

HERE = paths.app_dir()
CONFIG_PATH = paths.config_path()
LOG_PATH = HERE / "transcripts.log"


DEFAULTS = {
    "push_to_talk_key": "space",
    "passthrough_modifier": "alt",
    "master_toggle_hotkey": "ctrl+alt+d",
    "min_press_ms": 180,
    "max_record_seconds": 120,
    "model": "gpt-transcribe",
    "model_fallbacks": ["gpt-4o-transcribe", "whisper-1"],
    "language": "en",
    "vocabulary_hint": "",
    "sample_rate": 16000,
    "input_device": None,
    "output_method": "paste",
    "auto_capitalize": False,
    "trailing_space": True,
    "sound_feedback": True,
    "start_beep_hz": 880,
    "stop_beep_hz": 620,
    "error_beep_hz": 300,
    "start_enabled": True,
    "log_transcripts": True,
    "api_key": None,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in user.items() if not k.startswith("_")})
        except Exception as exc:
            print(f"[warn] could not parse config.json ({exc}); using defaults")
    return cfg


# --------------------------------------------------------------------- feedback

class Feedback:
    """Audio cues. Deliberately non-visual - the user may not be looking at a
    tray icon, and for accessibility the sound IS the primary channel."""

    def __init__(self, cfg: dict):
        self.enabled = bool(cfg.get("sound_feedback", True))
        self.start_hz = int(cfg.get("start_beep_hz", 880))
        self.stop_hz = int(cfg.get("stop_beep_hz", 620))
        self.error_hz = int(cfg.get("error_beep_hz", 300))

    def _beep(self, hz: int, ms: int) -> None:
        if not self.enabled:
            return
        try:
            if IS_WINDOWS:
                winsound.Beep(hz, ms)
            else:
                # Terminal bell is the portable fallback; pitch is ignored.
                sys.stdout.write("\a")
                sys.stdout.flush()
        except Exception:
            pass

    # Distinct *timbres* would be better than distinct pitches for users with
    # hearing loss; these are placeholders until we ship real earcon samples.
    def listening(self):   threading.Thread(target=self._beep, args=(self.start_hz, 60), daemon=True).start()
    def captured(self):    threading.Thread(target=self._beep, args=(self.stop_hz, 60), daemon=True).start()
    def error(self):       threading.Thread(target=self._beep, args=(self.error_hz, 220), daemon=True).start()

    def toggled(self, on: bool):
        def run():
            self._beep(700 if on else 500, 70)
            time.sleep(0.03)
            self._beep(900 if on else 350, 70)
        threading.Thread(target=run, daemon=True).start()


# --------------------------------------------------------------------- recorder

class Recorder:
    """Captures mono int16 audio while the PTT key is held."""

    def __init__(self, cfg: dict):
        self.sample_rate = int(cfg.get("sample_rate", 16000))
        self.device = cfg.get("input_device")
        self.max_frames = int(self.sample_rate * float(cfg.get("max_record_seconds", 120)))
        self._stream = None
        self._chunks: list = []
        self._lock = threading.Lock()
        self._frames = 0

    def _callback(self, indata, frames, time_info, status):
        if status:
            pass  # over/underruns are non-fatal; keep the stream alive
        with self._lock:
            if self._frames < self.max_frames:
                self._chunks.append(indata.copy())
                self._frames += frames

    def start(self) -> None:
        with self._lock:
            self._chunks = []
            self._frames = 0
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            device=self.device,
            blocksize=0,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> "np.ndarray | None":
        if self._stream is None:
            return None
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        self._stream = None
        with self._lock:
            if not self._chunks:
                return None
            return np.concatenate(self._chunks, axis=0).reshape(-1)

    def to_wav_bytes(self, audio: "np.ndarray") -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio.tobytes())
        buf.seek(0)
        return buf.read()


# ------------------------------------------------------------------ transcriber

class Transcriber:
    """OpenAI transcription with automatic fallback across model names.

    Model IDs have churned (whisper-1 -> gpt-4o-transcribe -> gpt-transcribe),
    so rather than hard-coding one, we try in order and remember what worked.
    """

    def __init__(self, cfg: dict):
        key = cfg.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "No OpenAI API key. Set OPENAI_API_KEY in your environment, "
                'or add "api_key": "sk-..." to config.json'
            )
        self.client = OpenAI(api_key=key)
        self.candidates = [cfg.get("model", "gpt-transcribe")] + list(
            cfg.get("model_fallbacks", [])
        )
        self.language = cfg.get("language") or None
        self.hint = (cfg.get("vocabulary_hint") or "").strip()
        self._working_model = None

    def transcribe(self, wav_bytes: bytes) -> str:
        models = [self._working_model] if self._working_model else self.candidates
        last_error = None

        for model in models:
            if not model:
                continue
            try:
                fh = io.BytesIO(wav_bytes)
                fh.name = "audio.wav"  # the SDK infers format from the filename
                kwargs = {"model": model, "file": fh, "response_format": "text"}
                if self.language:
                    kwargs["language"] = self.language
                if self.hint:
                    # Context biasing: nudges the model toward domain vocabulary.
                    kwargs["prompt"] = self.hint

                result = self.client.audio.transcriptions.create(**kwargs)
                text = result if isinstance(result, str) else getattr(result, "text", "")
                self._working_model = model
                return (text or "").strip()

            except Exception as exc:
                last_error = exc
                msg = str(exc).lower()
                # Only fall through on "this model doesn't exist" style errors.
                if any(s in msg for s in ("model", "not found", "does not exist", "invalid")):
                    print(f"[info] model '{model}' unavailable, trying next")
                    continue
                raise

        raise RuntimeError(f"All transcription models failed. Last error: {last_error}")


# ---------------------------------------------------------------------- output

class TextOutput:
    """Injects text into the focused window."""

    def __init__(self, cfg: dict):
        self.method = cfg.get("output_method", "paste")
        self.auto_capitalize = bool(cfg.get("auto_capitalize", False))
        self.trailing_space = bool(cfg.get("trailing_space", True))

    def _format(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if self.auto_capitalize:
            text = text[0].upper() + text[1:]
        if self.trailing_space:
            text += " "
        return text

    def emit(self, text: str) -> None:
        text = self._format(text)
        if not text:
            return

        if self.method == "paste":
            try:
                # Pasting is far faster than synthesising keystrokes and is
                # safe for unicode. We restore the old clipboard afterwards.
                previous = None
                try:
                    previous = pyperclip.paste()
                except Exception:
                    pass

                pyperclip.copy(text)
                time.sleep(0.02)
                keyboard.send("ctrl+v")

                if previous is not None:
                    def restore():
                        time.sleep(0.4)
                        try:
                            pyperclip.copy(previous)
                        except Exception:
                            pass
                    threading.Thread(target=restore, daemon=True).start()
                return
            except Exception as exc:
                print(f"[warn] paste failed ({exc}); falling back to typing")

        keyboard.write(text, delay=0)


# ------------------------------------------------------------------------ app

class VoiceKey:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ptt_key = cfg.get("push_to_talk_key", "space")
        self.passthrough = (cfg.get("passthrough_modifier") or "alt").lower()
        self.min_press = float(cfg.get("min_press_ms", 180)) / 1000.0
        self.log_transcripts = bool(cfg.get("log_transcripts", True))

        self.feedback = Feedback(cfg)
        self.recorder = Recorder(cfg)
        self.transcriber = Transcriber(cfg)
        self.output = TextOutput(cfg)

        self.enabled = bool(cfg.get("start_enabled", True))
        self._recording = False
        self._press_time = 0.0
        self._busy = threading.Lock()

    # -- key handling -------------------------------------------------------

    def _passthrough_held(self) -> bool:
        try:
            return keyboard.is_pressed(self.passthrough)
        except Exception:
            return False

    def on_press(self, event) -> None:
        if not self.enabled:
            self._emit_literal_key()
            return

        # Alt+Space (or whatever the modifier is) types a real space.
        if self._passthrough_held():
            self._emit_literal_key()
            return

        if self._recording:
            return

        try:
            self.recorder.start()
        except Exception as exc:
            print(f"[error] could not open microphone: {exc}")
            self.feedback.error()
            return

        self._recording = True
        self._press_time = time.time()
        self.feedback.listening()

    def on_release(self, event) -> None:
        if not self._recording:
            return

        self._recording = False
        held = time.time() - self._press_time
        audio = self.recorder.stop()

        # Guard against accidental taps. A pedal bounce or a stray keypress
        # should never fire a transcription request.
        if held < self.min_press:
            self._emit_literal_key()
            return

        if audio is None or len(audio) == 0:
            self.feedback.error()
            return

        self.feedback.captured()
        threading.Thread(target=self._process, args=(audio, held), daemon=True).start()

    def _emit_literal_key(self) -> None:
        """Produce the key's normal character, since we suppressed it."""
        if self.ptt_key in ("space", "spacebar"):
            try:
                keyboard.write(" ", delay=0)
            except Exception:
                pass

    # -- transcription ------------------------------------------------------

    def _process(self, audio, held: float) -> None:
        with self._busy:
            started = time.time()
            try:
                wav = self.recorder.to_wav_bytes(audio)
                text = self.transcriber.transcribe(wav)
            except Exception as exc:
                print(f"[error] transcription failed: {exc}")
                self.feedback.error()
                return

            elapsed = time.time() - started

            if not text:
                # Heard nothing usable. This gets its own signal - "I heard you
                # but produced nothing" is different from "I wasn't listening",
                # and no shipping voice tool distinguishes them.
                print(f"[{held:.1f}s audio] (empty)")
                self.feedback.error()
                return

            print(f"[{held:.1f}s audio / {elapsed:.1f}s stt] {text}")

            if self.log_transcripts:
                try:
                    with LOG_PATH.open("a", encoding="utf-8") as fh:
                        fh.write(f"{datetime.now().isoformat(timespec='seconds')}\t{text}\n")
                except Exception:
                    pass

            self.output.emit(text)

    # -- master toggle ------------------------------------------------------

    def toggle(self) -> None:
        self.enabled = not self.enabled
        state = "ENABLED" if self.enabled else "DISABLED"
        print(f"\n*** VoiceKey {state} ***"
              + ("" if self.enabled else "  (spacebar behaves normally)"))
        self.feedback.toggled(self.enabled)
        if not self.enabled and self._recording:
            self._recording = False
            self.recorder.stop()

    # -- run ----------------------------------------------------------------

    def run(self) -> None:
        toggle_hotkey = self.cfg.get("master_toggle_hotkey", "ctrl+alt+d")

        keyboard.on_press_key(self.ptt_key, self.on_press, suppress=True)
        keyboard.on_release_key(self.ptt_key, self.on_release, suppress=True)
        keyboard.add_hotkey(toggle_hotkey, self.toggle, suppress=False)

        print("=" * 62)
        print("  VoiceKey - push-to-talk dictation")
        print("=" * 62)
        print(f"  Hold          : {self.ptt_key.upper()}")
        print(f"  Literal space : {self.passthrough.upper()}+{self.ptt_key.upper()}")
        print(f"  Master toggle : {toggle_hotkey.upper()}   <- turn OFF before gaming")
        print(f"  Model         : {self.cfg.get('model')} "
              f"(fallbacks: {', '.join(self.cfg.get('model_fallbacks', [])) or 'none'})")
        print(f"  Status        : {'ENABLED' if self.enabled else 'DISABLED'}")
        print("=" * 62)
        print("  Ctrl+C to quit.\n")

        try:
            keyboard.wait()
        except KeyboardInterrupt:
            pass
        finally:
            print("\nStopping.")
            try:
                keyboard.unhook_all()
            except Exception:
                pass


def main() -> int:
    cfg = load_config()
    try:
        app = VoiceKey(cfg)
    except Exception as exc:
        print(f"[fatal] {exc}")
        return 1

    if IS_WINDOWS is False:
        print("[note] Global key hooks need root on Linux and Accessibility "
              "permission on macOS. This is built for Windows.\n")

    try:
        app.run()
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
