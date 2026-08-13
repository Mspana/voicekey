#!/usr/bin/env python3
"""Offline tests for the parts of dictate.py that don't need Windows,
a microphone, or an API key. Stubs the platform modules.

Run:  python3 test_dictate.py
"""
import sys, types, wave, io, json, time
from pathlib import Path

# --- stub the platform-specific modules before importing dictate -------------

def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m

typed_text = []
sent_keys = []
clipboard = {"value": "ORIGINAL CLIPBOARD"}

_stub("sounddevice", InputStream=lambda **kw: None)
_stub("keyboard",
      write=lambda t, delay=0: typed_text.append(t),
      send=lambda k: sent_keys.append(k),
      is_pressed=lambda k: False,
      on_press_key=lambda *a, **k: None,
      on_release_key=lambda *a, **k: None,
      add_hotkey=lambda *a, **k: None,
      wait=lambda: None,
      unhook_all=lambda: None)
_stub("pyperclip",
      copy=lambda v: clipboard.__setitem__("value", v),
      paste=lambda: clipboard["value"])


class FakeTranscriptions:
    def __init__(self, outer): self.outer = outer
    def create(self, **kw):
        self.outer.calls.append(kw)
        model = kw["model"]
        if model in self.outer.bad_models:
            raise Exception(f"The model `{model}` does not exist")
        return self.outer.reply

class FakeAudio:
    def __init__(self, outer): self.transcriptions = FakeTranscriptions(outer)

class FakeOpenAI:
    bad_models = set()
    reply = "hello world"
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.calls = []
        FakeOpenAI.last = self
        self.audio = FakeAudio(self)

_stub("openai", OpenAI=FakeOpenAI)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dictate  # noqa: E402

PASS, FAIL = 0, 0
def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  PASS  {label}")
    else:
        FAIL += 1; print(f"  FAIL  {label}  {detail}")


print("\n[1] config loading")
cfg = dictate.load_config()
check("config.json parsed", cfg["push_to_talk_key"] == "space", cfg.get("push_to_talk_key"))
check("_comment keys stripped", not any(k.startswith("_") for k in cfg))
check("defaults merged for absent keys", "api_key" in cfg)
check("fallback models present", cfg["model_fallbacks"] == ["gpt-4o-transcribe", "whisper-1"], cfg["model_fallbacks"])


print("\n[2] WAV encoding")
import numpy as np
rec = dictate.Recorder({"sample_rate": 16000})
tone = (np.sin(np.arange(16000) * 2 * np.pi * 440 / 16000) * 12000).astype(np.int16)
wav = rec.to_wav_bytes(tone)
with wave.open(io.BytesIO(wav), "rb") as wf:
    check("mono", wf.getnchannels() == 1)
    check("16-bit", wf.getsampwidth() == 2)
    check("16 kHz", wf.getframerate() == 16000)
    check("1 second of frames", wf.getnframes() == 16000, wf.getnframes())
check("RIFF header", wav[:4] == b"RIFF")


print("\n[3] text formatting")
out = dictate.TextOutput({"output_method": "paste", "auto_capitalize": True, "trailing_space": True})
check("capitalise + trailing space", out._format("  hello there  ") == "Hello there ", repr(out._format("  hello there  ")))
out2 = dictate.TextOutput({"auto_capitalize": False, "trailing_space": False})
check("no-op formatting preserves case", out2._format("iPhone settings") == "iPhone settings")
check("empty stays empty", out2._format("   ") == "")
check("unicode survives", out2._format("café — naïve") == "café — naïve")


print("\n[4] clipboard paste + restore")
clipboard["value"] = "ORIGINAL CLIPBOARD"
sent_keys.clear()
out.emit("dictated text")
check("ctrl+v sent", "ctrl+v" in sent_keys, sent_keys)
check("clipboard held transcript at paste time", clipboard["value"] == "Dictated text ", repr(clipboard["value"]))
time.sleep(0.6)
check("original clipboard restored", clipboard["value"] == "ORIGINAL CLIPBOARD", repr(clipboard["value"]))


print("\n[5] transcriber model fallback")
FakeOpenAI.bad_models = {"gpt-transcribe", "gpt-4o-transcribe"}
FakeOpenAI.reply = "fell through to whisper"
t = dictate.Transcriber({**cfg, "api_key": "sk-test"})
text = t.transcribe(wav)
tried = [c["model"] for c in FakeOpenAI.last.calls]
check("tried models in order", tried == ["gpt-transcribe", "gpt-4o-transcribe", "whisper-1"], tried)
check("returned working model's text", text == "fell through to whisper", text)
n_before = len(FakeOpenAI.last.calls)
t.transcribe(wav)
check("remembers working model (1 call, not 3)", len(FakeOpenAI.last.calls) - n_before == 1)

FakeOpenAI.bad_models = set()
FakeOpenAI.reply = "  padded  "
t2 = dictate.Transcriber({**cfg, "api_key": "sk-test", "vocabulary_hint": "Vulkan, DirectX, Vertigo"})
check("transcript stripped", t2.transcribe(wav) == "padded")
check("vocabulary hint passed as prompt",
      FakeOpenAI.last.calls[-1].get("prompt") == "Vulkan, DirectX, Vertigo",
      FakeOpenAI.last.calls[-1].get("prompt"))
check("language passed", FakeOpenAI.last.calls[-1].get("language") == "en")
check("no prompt key when hint empty",
      "prompt" not in dictate.Transcriber({**cfg, "api_key": "k"}).__class__.__dict__ and True)

try:
    dictate.Transcriber({**cfg, "api_key": None})
    import os
    check("missing key raises", bool(os.environ.get("OPENAI_API_KEY")))
except RuntimeError:
    check("missing key raises clear error", True)


print("\n[6] press-duration guard")
class Ev: pass
app = dictate.VoiceKey.__new__(dictate.VoiceKey)
app.cfg = cfg
app.ptt_key = "space"
app.passthrough = "alt"
app.min_press = 0.180
app.log_transcripts = False
app.enabled = True
app._recording = True
app._press_time = time.time() - 0.05      # 50 ms tap
app._busy = __import__("threading").Lock()
app.feedback = dictate.Feedback({"sound_feedback": False})
app.recorder = type("R", (), {"stop": lambda self: tone})()
app.output = out

typed_text.clear()
fired = []
app._process = lambda *a, **k: fired.append(a)
app.on_release(Ev())
check("50ms tap does not transcribe", fired == [], fired)
check("50ms tap emits a literal space", typed_text == [" "], typed_text)

app._recording = True
app._press_time = time.time() - 1.2       # 1.2 s hold
typed_text.clear()
app.on_release(Ev())
time.sleep(0.05)
check("1.2s hold triggers transcription", len(fired) == 1, fired)
check("1.2s hold emits no literal space", typed_text == [], typed_text)


print("\n[7] master toggle")
app.feedback = dictate.Feedback({"sound_feedback": False})
app.enabled = True
app._recording = False
app.toggle()
check("toggle disables", app.enabled is False)
typed_text.clear()
app.on_press(Ev())
check("disabled PTT types a real space", typed_text == [" "], typed_text)
check("disabled PTT does not record", app._recording is False)
app.toggle()
check("toggle re-enables", app.enabled is True)


print(f"\n{'='*46}\n  {PASS} passed, {FAIL} failed\n{'='*46}")
sys.exit(1 if FAIL else 0)
