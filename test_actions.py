#!/usr/bin/env python3
"""Offline tests for the command grammar and the glow maths.

Both are pure, so this needs no display, microphone, or API key.

Run:  python3 test_actions.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import actions as A
import glow as G

PASS, FAIL = 0, 0
def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  PASS  {label}")
    else:
        FAIL += 1; print(f"  FAIL  {label}  {detail}")


def kinds(segs):
    return [k for k, _ in segs]

def texts(segs):
    return [v for k, v in segs if k == "text"]

def acts(segs):
    return [v for k, v in segs if k == "action"]


class FakeCtx:
    def __init__(self): self.log = []
    def click(self, b, c=1): self.log.append(("click", b, c))
    def hold(self, s): self.log.append(("hold", s))
    def send_key(self, k): self.log.append(("key", k))
    def scroll(self, n): self.log.append(("scroll", n))
    def nudge(self, dx, dy, verb="move", scale=None, distance=None):
        self.log.append(("nudge", dx, dy, verb, scale, distance))
    def back(self, count, unit="character"): self.log.append(("back", count, unit))
    def app_command(self, c, spec): self.log.append(("app", c)); return True


print("\n[1] normalisation")
check("lowercases", A.normalise("Zulu ENTER") == "zulu enter")
check("strips trailing punctuation", A.normalise("Zulu, enter.") == "zulu enter")
check("collapses whitespace", A.normalise("  a   b  ") == "a b")
check("keeps apostrophes", A.normalise("don't") == "don't")
check("strips accents", A.normalise("café") == "cafe")
check("empty input is safe", A.normalise(None) == "")


print("\n[2] the escape sequence (the \\n analogy)")
segs = A.parse("ship it zulu enter")
check("text then action", kinds(segs) == ["text", "action"], kinds(segs))
check("text is everything before the phrase", texts(segs) == ["ship it"], texts(segs))
check("action is Enter", acts(segs)[0]["combo"] == "enter", acts(segs)[0])

segs = A.parse("line one zulu enter line two zulu enter")
check("interleaves text and actions",
      kinds(segs) == ["text", "action", "text", "action"], kinds(segs))
check("both text runs survive", texts(segs) == ["line one", "line two"], texts(segs))

segs = A.parse("zulu right click")
check("leading escape needs no text", kinds(segs) == ["action"], kinds(segs))
check("right click parsed", acts(segs)[0] == {"kind": "mouse", "button": "right", "count": 1},
      acts(segs)[0])

segs = A.parse("just some ordinary dictation")
check("no escape phrase means pure text", kinds(segs) == ["text"], kinds(segs))
check("text passes through unchanged",
      texts(segs) == ["just some ordinary dictation"], texts(segs))

segs = A.parse("Ship it. Zulu, enter.")
check("real transcript punctuation and casing still parse",
      kinds(segs) == ["text", "action"] and acts(segs)[0]["combo"] == "enter", segs)


print("\n[3] longest-match wins")
check("'right click' beats 'right'",
      acts(A.parse("zulu right click"))[0]["kind"] == "mouse")
check("bare 'right' is the arrow key",
      acts(A.parse("zulu right"))[0] == {"kind": "key", "combo": "right"},
      acts(A.parse("zulu right")))
check("'double click' beats 'click'",
      acts(A.parse("zulu double click"))[0]["count"] == 2)
check("'select all' is one action",
      acts(A.parse("zulu select all"))[0]["combo"] == "ctrl+a")
check("'back tab' beats 'tab'",
      acts(A.parse("zulu back tab"))[0]["combo"] == "shift+tab")


print("\n[4] unknown commands are signalled, and no words are lost")
# Design choice: a mis-heard command must never destroy dictation. The
# "unknown" segment is a *signal* for the rejection earcon; the words
# themselves continue on as text.
segs = A.parse("zulu flibbertigibbet")
check("escape + nonsense signals unknown", kinds(segs) == ["unknown", "text"], segs)
check("unknown carries a preview of what was heard",
      segs[0][1].startswith("flibberti"), segs)
check("the words are still typed rather than dropped",
      texts(segs) == ["flibbertigibbet"], texts(segs))

segs = A.parse("hello zulu wibble")
check("text before an unknown is still emitted",
      kinds(segs) == ["text", "unknown", "text"], kinds(segs))
check("nothing the user said is lost", texts(segs) == ["hello", "wibble"], texts(segs))

segs = A.parse("hello zulu wibble zulu enter")
check("a later valid command still fires after an unknown",
      kinds(segs) == ["text", "unknown", "text", "action"], kinds(segs))
check("and it is the right action", acts(segs)[0]["combo"] == "enter")

segs = A.parse("", command_only=True)
check("empty utterance yields nothing", segs == [], segs)


print("\n[5] command-only mode (right ctrl)")
segs = A.parse("enter", command_only=True)
check("no escape phrase needed", kinds(segs) == ["action"], segs)
check("it is Enter", acts(segs)[0]["combo"] == "enter")

segs = A.parse("right click", command_only=True)
check("multi-word command", acts(segs)[0]["button"] == "right")

segs = A.parse("uh could you maybe click", command_only=True)
check("filler words around a command still work",
      "action" in kinds(segs) and acts(segs)[0]["kind"] == "mouse", segs)

segs = A.parse("what is the weather", command_only=True)
check("a non-command utterance is reported unknown, not typed",
      kinds(segs) == ["unknown"], segs)


print("\n[6] numbers")
for word, value in (("three", 3), ("3", 3), ("twenty", 20), ("twenty one", 21),
                    ("nine", 9), ("eight", 8)):
    toks = A.tokenise(word)
    got, used = A.parse_number(toks, 0)
    check(f"'{word}' -> {value}", got == value and used == len(toks), (got, used))
check("non-numbers return None", A.parse_number(["banana"], 0) == (None, 0))
check("past the end returns None", A.parse_number([], 0) == (None, 0))

# ASR homophones: "to"/"too"/"two" and "for"/"four" are chronically confused.
check("'to' is accepted as 2", A.parse_number(["to"], 0)[0] == 2)
check("'for' is accepted as 4", A.parse_number(["for"], 0)[0] == 4)
check("'ate' is accepted as 8", A.parse_number(["ate"], 0)[0] == 8)


print("\n[7] hold with a duration")
spec = acts(A.parse("zulu hold three seconds"))[0]
check("hold three seconds", spec == {"kind": "hold", "seconds": 3.0}, spec)
check("hold for 5 seconds", acts(A.parse("zulu hold for 5 seconds"))[0]["seconds"] == 5.0)
check("bare hold defers to config", acts(A.parse("zulu hold"))[0]["seconds"] is None)
check("'drag' is a hold", acts(A.parse("zulu drag"))[0]["kind"] == "hold")

segs = A.parse("zulu hold three seconds then more text")
check("words after a hold return to text",
      texts(segs) == ["then more text"], texts(segs))


print("\n[8] repeats")
check("tab twice", acts(A.parse("zulu tab twice"))[0].get("repeat") == 2)
check("click three times", acts(A.parse("zulu click three times"))[0].get("repeat") == 3)
check("no repeat by default", "repeat" not in acts(A.parse("zulu tab"))[0])
check("a bare number after a key is not a repeat",
      "repeat" not in acts(A.parse("zulu tab seven"))[0],
      acts(A.parse("zulu tab seven")))
segs = A.parse("zulu tab seven")
check("that number falls back to text", texts(segs) == ["seven"], texts(segs))


print("\n[8b] scrolling with an amount")
def scroll(phrase):
    got = acts(A.parse(f"zulu {phrase}"))
    return got[0] if got else None

check("bare scroll up keeps the default", scroll("scroll up")["clicks"] == 3,
      scroll("scroll up"))
check("bare scroll down is negative", scroll("scroll down")["clicks"] == -3)
check("scroll up 5", scroll("scroll up 5")["clicks"] == 5, scroll("scroll up 5"))
check("scroll down 10 keeps the sign", scroll("scroll down 10")["clicks"] == -10,
      scroll("scroll down 10"))
check("spoken amount", scroll("scroll up three")["clicks"] == 3)
for unit in ("clicks", "click", "notches", "lines", "ticks", "steps"):
    check(f"amount with unit '{unit}'",
          scroll(f"scroll down 12 {unit}")["clicks"] == -12,
          scroll(f"scroll down 12 {unit}"))

check("'three times' is still a repeat, not an amount",
      scroll("scroll up three times").get("repeat") == 3
      and scroll("scroll up three times")["clicks"] == 3,
      scroll("scroll up three times"))
check("an amount and a repeat can combine",
      scroll("scroll down 5 twice")["clicks"] == -5
      and scroll("scroll down 5 twice").get("repeat") == 2,
      scroll("scroll down 5 twice"))
check("an absurd amount is clamped",
      abs(scroll("scroll down 500")["clicks"]) == A.MAX_SCROLL,
      scroll("scroll down 500"))

segs = A.parse("zulu scroll up 5 and then some words")
check("words after an amount return to text",
      texts(segs) == ["and then some words"], texts(segs))

ctx = FakeCtx()
A.perform(scroll("scroll down 7"), ctx)
check("perform passes the amount through", ctx.log == [("scroll", -7)], ctx.log)


print("\n[9] grid commands")
spec = acts(A.parse("zulu grid"))[0]
check("bare grid opens it", spec == {"kind": "app", "command": "grid"}, spec)
spec = acts(A.parse("zulu grid four three"))[0]
check("grid with a cell", (spec.get("col"), spec.get("row")) == (4, 3), spec)
check("off", acts(A.parse("zulu off"))[0]["command"] == "off")
check("wake up", acts(A.parse("zulu wake up"))[0]["command"] == "on")
check("stop listening", acts(A.parse("zulu stop listening"))[0]["command"] == "off")


print("\n[10] custom escape phrases")
check("single word", acts(A.parse("hi onyx enter", "onyx"))[0]["combo"] == "enter")
check("two words", acts(A.parse("hi blue moon enter", "blue moon"))[0]["combo"] == "enter")
check("the old phrase stops working after remapping",
      kinds(A.parse("hi zulu enter", "onyx")) == ["text"],
      A.parse("hi zulu enter", "onyx"))
check("empty phrase falls back to the default",
      acts(A.parse("hi zulu enter", ""))[0]["combo"] == "enter")
check("phrase matching is case-insensitive",
      acts(A.parse("hi ONYX enter", "Onyx"))[0]["combo"] == "enter")


print("\n[11] the whole action table is reachable")
unreachable = []
for phrase in A.ACTION_TABLE:
    got = acts(A.parse(f"zulu {phrase}"))
    if not got:
        unreachable.append(phrase)
check(f"all {len(A.ACTION_TABLE)} phrases parse", not unreachable, unreachable[:5])

undescribed = [p for p in A.ACTION_TABLE
               if not A.describe(A.ACTION_TABLE[p]).strip()]
check("every action has a description", not undescribed, undescribed[:3])


print("\n[12] perform() dispatches to the context")
ctx = FakeCtx()
check("enter sends a key",
      A.perform({"kind": "key", "combo": "enter"}, ctx) and ctx.log == [("key", "enter")],
      ctx.log)

ctx = FakeCtx()
A.perform({"kind": "mouse", "button": "right", "count": 1}, ctx)
check("right click dispatches", ctx.log == [("click", "right", 1)], ctx.log)

ctx = FakeCtx()
A.perform({"kind": "key", "combo": "tab", "repeat": 3}, ctx)
check("repeat sends three times", ctx.log == [("key", "tab")] * 3, ctx.log)

ctx = FakeCtx()
A.perform({"kind": "app", "command": "off"}, ctx)
check("app command dispatches", ctx.log == [("app", "off")], ctx.log)

ctx = FakeCtx()
A.perform(acts(A.parse("zulu bump top left"))[0], ctx)
check("nudge dispatches with the direction and verb",
      ctx.log == [("nudge", -1, -1, "bump", None, None)], ctx.log)

ctx = FakeCtx()
A.perform(acts(A.parse("zulu bump left twice"))[0], ctx)
check("a repeated nudge fires twice", len(ctx.log) == 2, ctx.log)

class BoomCtx(FakeCtx):
    def send_key(self, k): raise RuntimeError("no keyboard")
check("a failing action returns False rather than raising",
      A.perform({"kind": "key", "combo": "enter"}, BoomCtx()) is False)
check("an unknown kind returns False",
      A.perform({"kind": "nonsense"}, FakeCtx()) is False)


print("\n[13] end-to-end: a realistic form fill")
segs = A.parse("matthew at example dot com zulu tab hunter two zulu enter")
check("three text runs and two actions",
      kinds(segs) == ["text", "action", "text", "action"], kinds(segs))
ctx = FakeCtx()
typed = []
for kind, payload in segs:
    if kind == "text":
        typed.append(payload)
    else:
        A.perform(payload, ctx)
check("typed the right things",
      typed == ["matthew at example dot com", "hunter two"], typed)
check("pressed tab then enter", ctx.log == [("key", "tab"), ("key", "enter")], ctx.log)


print("\n[13b] relative cursor nudges")
def nudge(phrase):
    got = acts(A.parse(f"zulu {phrase}"))
    return got[0] if got else None

check("bump left", nudge("bump left") ==
      {"kind": "nudge", "dx": -1, "dy": 0, "verb": "bump", "scale": None, "distance": None},
      nudge("bump left"))
check("the verb sets the magnitude, not the direction",
      nudge("jump left")["verb"] == "jump" and nudge("bump left")["verb"] == "bump")

for verb, level in (("bump", "bump"), ("nudge", "bump"), ("inch", "bump"),
                    ("skip", "skip"), ("scoot", "skip"),
                    ("jog", "jog"), ("shift", "jog"), ("slide", "jog"),
                    ("move", "move"), ("go", "move"),
                    ("jump", "jump"), ("leap", "jump"), ("fly", "jump")):
    check(f"'{verb}' is the {level} step", nudge(f"{verb} left")["verb"] == level,
          nudge(f"{verb} left"))

check("the ladder is strictly increasing",
      [A.DEFAULT_STEPS[k] for k in ("bump", "skip", "jog", "move", "jump")]
      == sorted(A.DEFAULT_STEPS.values()), A.DEFAULT_STEPS)

for phrase, vec in (("up", (0, -1)), ("down", (0, 1)), ("left", (-1, 0)),
                    ("right", (1, 0)), ("top left", (-1, -1)),
                    ("up left", (-1, -1)), ("upper left", (-1, -1)),
                    ("northwest", (-1, -1)), ("top right", (1, -1)),
                    ("bottom left", (-1, 1)), ("bottom right", (1, 1)),
                    ("down right", (1, 1)), ("southeast", (1, 1)),
                    ("east", (1, 0)), ("north", (0, -1))):
    spec = nudge(f"bump {phrase}")
    check(f"direction '{phrase}'", spec and (spec["dx"], spec["dy"]) == vec, spec)

check("diagonals move on both axes", nudge("bump top left")["dx"] != 0
      and nudge("bump top left")["dy"] != 0)

check("leading size word", nudge("bump a little left")["scale"] == 0.4,
      nudge("bump a little left"))
check("trailing size word", nudge("skip left a lot")["scale"] == 3.0,
      nudge("skip left a lot"))
check("a hair is smaller than a little",
      A.SIZE_WORDS["a hair"] < A.SIZE_WORDS["a little"] < 1.0 < A.SIZE_WORDS["a lot"])
check("explicit pixels", nudge("jog right 120")["distance"] == 120.0,
      nudge("jog right 120"))
check("explicit pixels with the unit spoken",
      nudge("jog right 120 pixels")["distance"] == 120.0)
check("spoken number as pixels", nudge("bump left twelve")["distance"] == 12.0,
      nudge("bump left twelve"))

check("repeat still works on a nudge", nudge("bump left twice")["repeat"] == 2,
      nudge("bump left twice"))
check("'three times' is a repeat, not a pixel count",
      nudge("bump left three times").get("repeat") == 3
      and nudge("bump left three times").get("distance") is None,
      nudge("bump left three times"))

# The bare grid commands must survive having nudge verbs in front of them.
check("bare 'move' is still the grid cursor command",
      acts(A.parse("zulu move"))[0] == {"kind": "app", "command": "cursor"},
      acts(A.parse("zulu move")))
check("'move mouse' is still the grid cursor command",
      acts(A.parse("zulu move mouse"))[0]["command"] == "cursor")
check("'go there' is still the grid cursor command",
      acts(A.parse("zulu go there"))[0]["command"] == "cursor")
check("a verb with no direction is not a nudge",
      A.match_nudge(A.tokenise("bump"), 0) == (None, 0))
check("a non-verb is not a nudge",
      A.match_nudge(A.tokenise("banana left"), 0) == (None, 0))

check("centre", acts(A.parse("zulu centre"))[0]["command"] == "centre")

# Quitting by voice, so the app is never something you have to force-quit.
for phrase in ("close voice key", "close voicekey", "quit voice key",
               "quit voicekey", "exit voice key", "shut down voice key",
               "kill voice key", "quit"):
    got = acts(A.parse(f"zulu {phrase}"))
    check(f"'{phrase}' quits", got and got[0]["command"] == "quit", got)
check("quitting is reachable in command-only mode too",
      acts(A.parse("close voice key", command_only=True))[0]["command"] == "quit")
check("american spelling", acts(A.parse("zulu center"))[0]["command"] == "centre")

segs = A.parse("zulu bump left then keep typing")
check("words after a nudge return to text",
      texts(segs) == ["then keep typing"], texts(segs))

print("\n[13c] back N characters / words / lines")
def back(phrase):
    got = acts(A.parse(f"zulu {phrase}"))
    return got[0] if got else None

check("back 3 characters",
      back("back 3 characters") == {"kind": "back", "count": 3, "unit": "character"},
      back("back 3 characters"))
check("back 4 words",
      back("back 4 words") == {"kind": "back", "count": 4, "unit": "word"},
      back("back 4 words"))
check("back 2 lines", back("back 2 lines")["unit"] == "line")

check("spoken numbers", back("back three characters")["count"] == 3)
check("bare count defaults to characters",
      back("back three") == {"kind": "back", "count": 3, "unit": "character"},
      back("back three"))
check("bare unit defaults to one", back("back word")["count"] == 1)
check("'a word' is one word", back("back a word") == {"kind": "back", "count": 1, "unit": "word"})
check("'one character'", back("back one character")["count"] == 1)

for word, unit in (("character", "character"), ("characters", "character"),
                   ("char", "character"), ("chars", "character"),
                   ("letter", "character"), ("letters", "character"),
                   ("word", "word"), ("words", "word"),
                   ("line", "line"), ("lines", "line")):
    check(f"unit '{word}'", back(f"back 2 {word}")["unit"] == unit,
          back(f"back 2 {word}"))

# "back tab" is shift+tab and must not be eaten as a deletion.
check("'back tab' is still shift+tab",
      acts(A.parse("zulu back tab"))[0] == {"kind": "key", "combo": "shift+tab"},
      acts(A.parse("zulu back tab")))
check("bare 'back' is not a deletion", A.match_back(A.tokenise("back"), 0) == (None, 0))
check("bare 'back' reports unknown rather than deleting",
      kinds(A.parse("zulu back")) == ["unknown", "text"], A.parse("zulu back"))

# Deleting is the one action a re-say cannot undo, so the count is clamped.
check("an absurd count is clamped", back("back 500 words")["count"] == A.MAX_BACK,
      back("back 500 words"))
check("the clamp is a sane size", 20 <= A.MAX_BACK <= 200, A.MAX_BACK)
check("zero is floored to one", back("back 0 words")["count"] == 1,
      back("back 0 words"))

segs = A.parse("zulu back 3 words and carry on")
check("words after a deletion return to text",
      texts(segs) == ["and carry on"], texts(segs))

ctx = FakeCtx()
A.perform(back("back 4 words"), ctx)
check("perform dispatches to ctx.back", ctx.log == [("back", 4, "word")], ctx.log)


print("\n[14] dictated text keeps its punctuation and casing")
# Regression: parse() used to emit the *normalised* tokens as text, which
# stripped every capital and full stop out of ordinary dictation.
segs = A.parse("Hello there. How are you?")
check("plain dictation is passed through verbatim",
      texts(segs) == ["Hello there. How are you?"], texts(segs))

segs = A.parse("Ship it. Zulu, enter.")
check("punctuation before the escape phrase is kept",
      texts(segs) == ["Ship it."], texts(segs))
check("and the action still fires", acts(segs)[0]["combo"] == "enter")

segs = A.parse("Dear Bob, thanks for the update. zulu enter Best, Matthew.")
check("commas and capitals survive on both sides",
      texts(segs) == ["Dear Bob, thanks for the update.", "Best, Matthew."],
      texts(segs))

segs = A.parse("It's 42% done -- see e.g. the README.")
check("apostrophes, symbols and dashes all survive",
      texts(segs) == ["It's 42% done -- see e.g. the README."], texts(segs))

segs = A.parse("naïve café résumé")
check("accents are not stripped from output",
      texts(segs) == ["naïve café résumé"], texts(segs))

segs = A.parse("ZULU ENTER")
check("an all-caps escape phrase still matches",
      kinds(segs) == ["action"], segs)

segs = A.parse("hello", command_only=True)
check("command-only unknown keeps the original text",
      segs == [("unknown", "hello")], segs)

check("normalise is still used for matching, not for output",
      A.tokenise("Zulu, Enter.") == ["zulu", "enter"])

spans = A.tokenise_spans("Ship it. Zulu, enter.")
check("spans point back into the original string",
      [t for t, _, _ in spans] == ["ship", "it", "zulu", "enter"], spans)
check("span offsets are correct",
      "Ship it. Zulu, enter."[spans[0][1]:spans[1][2]] == "Ship it", spans[:2])


print("\n[15] glow modes")
g = G.Glow(root=None, cfg={})
check("both ramps precomputed", set(g.ramps) == {"command", "dictate"}, list(g.ramps))
check("command and dictate differ", g.ramps["command"] != g.ramps["dictate"])

def _lum(hexcolour):
    r, gr, b = G._hex_to_rgb(hexcolour)
    return 0.2126 * r + 0.7152 * gr + 0.0722 * b

def _sat(hexcolour):
    r, gr, b = G._hex_to_rgb(hexcolour)
    return max(r, gr, b) - min(r, gr, b)

check("dictate palette is desaturated (readable without colour vision)",
      max(_sat(c) for c in g.ramps["dictate"]) < 40,
      max(_sat(c) for c in g.ramps["dictate"]))
check("command palette is saturated",
      max(_sat(c) for c in g.ramps["command"]) > 80,
      max(_sat(c) for c in g.ramps["command"]))
check("both are visible against a dark desktop",
      min(_lum(c) for c in g.ramps["dictate"]) > 90
      and min(_lum(c) for c in g.ramps["command"]) > 90,
      (min(_lum(c) for c in g.ramps["dictate"]),
       min(_lum(c) for c in g.ramps["command"])))


print("\n[15b] soft glow rendering (true per-pixel alpha)")
try:
    import numpy as _np
    import glowfx as FX

    R = FX.GlowRenderer(320, 200, thickness=40)
    check("some pixels are fully transparent", (R.rgba()[..., 3] == 0).any())
    check("some pixels are strongly opaque", (R.rgba()[..., 3] > 200).any())
    check("intermediate alphas exist - a real gradient, not a mask",
          ((R.rgba()[..., 3] > 20) & (R.rgba()[..., 3] < 200)).sum() > 2000,
          int(((R.rgba()[..., 3] > 20) & (R.rgba()[..., 3] < 200)).sum()))
    check("the band does not cover the whole screen", 0.05 < R.coverage < 0.75,
          R.coverage)

    a = R.rgba()[..., 3]
    check("edges are the most opaque part", a[0, 160] > a[100, 160], (a[0,160], a[100,160]))
    # int() matters: these are uint8, so "0 - 2" wraps to 254.
    check("alpha decays monotonically inward",
          all(int(a[i, 160]) >= int(a[i + 1, 160]) - 2 for i in range(0, 60)),
          [int(v) for v in a[0:60:10, 160]])
    check("the centre is fully clear", a[100, 160] == 0, int(a[100, 160]))

    # The corner seam bug: a hard min() over the four edges creases along the
    # diagonal. Softmin removes it. Sample across where the crease used to be.
    diag = [int(a[i, i]) for i in range(4, 40)]
    jumps = [abs(diag[i + 1] - diag[i]) for i in range(len(diag) - 1)]
    check("no hard seam across the corner diagonal", max(jumps) < 40, max(jumps))

    check("premultiplied frame is BGRA and the right size",
          R.frame().shape == (200, 320, 4) and R.frame().dtype == _np.uint8,
          R.frame().shape)
    _f = R.frame().astype(_np.int32)
    check("premultiplied colour never exceeds alpha",
          bool((_f[..., :3].max(axis=2) <= _f[..., 3] + 1).all()))
    check("command and dictate frames differ",
          not _np.array_equal(R.rgba(0, "command"), R.rgba(0, "dictate")))
    check("advancing the phase changes the colours",
          not _np.array_equal(R.rgba(0), R.rgba(90)))
    check("but not the alpha - only hue animates",
          _np.array_equal(R.rgba(0)[..., 3], R.rgba(90)[..., 3]))
    check("smoothstep is clamped",
          FX.smoothstep(-1.0) == 0.0 and FX.smoothstep(2.0) == 1.0)
    check("wisp_np matches the scalar version",
          abs(float(FX.wisp_np(_np.array([0.37]))[0]) - G.wisp(0.37)) < 1e-6)
except ImportError as exc:
    check(f"numpy available for the soft glow ({exc})", False)


print("\n[15c] fade in / out")
import time as _time

class FakeRoot:
    """Runs callbacks immediately but advances a fake clock, so a whole fade
    can be exercised without sleeping."""
    def __init__(self): self.q, self.n = [], 0
    def after(self, ms, fn):
        self.n += 1; self.q.append((self.n, ms, fn)); return self.n
    def after_cancel(self, tid): self.q = [e for e in self.q if e[0] != tid]
    def run(self, clock, limit=500):
        steps = 0
        while self.q and steps < limit:
            _, ms, fn = self.q.pop(0)
            clock.advance(ms / 1000.0)
            fn(); steps += 1
        return steps

class Clock:
    def __init__(self): self.t = 1000.0
    def advance(self, dt): self.t += dt
    def __call__(self): return self.t

def fading_glow(**cfg):
    root, clock = FakeRoot(), Clock()
    G.time.monotonic = clock
    g = G.Glow(root, {"soft": False, "fade_ms": 100, **cfg})
    g._try_layered = lambda rect, mode: False
    g._build_window = lambda: None
    seen = []
    g._paint = lambda: seen.append(round(g._opacity, 3))
    return root, g, seen, clock

_real_monotonic = G.time.monotonic
try:
    root, g, seen, clock = fading_glow()
    g.visible = True
    g._start_fade(1.0); root.run(clock)
    check("fade in starts at zero, not at full",
          seen[0] < 0.35, seen[:3])
    check("fade in ends fully opaque", g._opacity == 1.0 and seen[-1] == 1.0, seen[-3:])
    check("fade in is monotonic", all(b >= a for a, b in zip(seen, seen[1:])), seen)
    check("more than a couple of frames", len(seen) >= 5, len(seen))
    check("eased, not linear - the middle is past halfway",
          seen[len(seen) // 2] > 0.4, seen)

    seen.clear()
    g.hide(); root.run(clock)
    check("fade out reaches zero", g._opacity == 0.0 and seen[-1] == 0.0, seen[-3:])
    check("fade out is monotonic", all(b <= a for a, b in zip(seen, seen[1:])), seen)
    check("torn down only once the fade completes", g._win is None and g._layer is None)
    check("not visible afterwards", g.visible is False)

    # A slow machine must drop frames, not stretch the fade.
    root, g, seen, clock = fading_glow(fade_ms=100, fade_interval_ms=45)
    g.visible = True
    g._start_fade(1.0); root.run(clock)
    check("a slow frame rate still finishes on schedule", g._opacity == 1.0, seen)
    check("and it does so in few frames", len(seen) <= 5, len(seen))

    # Interrupting a fade-out resumes from where it got to.
    root, g, seen, clock = fading_glow()
    g.visible = True; g._opacity = 1.0
    g.hide()
    if root.q:
        _, ms, fn = root.q.pop(0); clock.advance(ms / 1000.0); fn()
    mid = g._opacity
    g.visible = True
    g._start_fade(1.0); root.run(clock)
    check("interrupted fade-out recovers to fully opaque", g._opacity == 1.0, g._opacity)
    check("and resumed from where it was, not from zero", 0.0 < mid < 1.0, mid)

    check("hide() on an already-hidden glow is a no-op",
          G.Glow(FakeRoot(), {"soft": False}).hide() is None)
finally:
    G.time.monotonic = _real_monotonic


print("\n[16] glow maths")
ramp = G.build_ramp(G.DEFAULT_STOPS, steps=180)
check("ramp has the requested length", len(ramp) == 180)
check("every entry is a hex colour",
      all(len(c) == 7 and c[0] == "#" for c in ramp), ramp[:2])
check("ramp is cyclic (start and end are close)",
      abs(int(ramp[0][1:3], 16) - int(ramp[-1][1:3], 16)) < 24, (ramp[0], ramp[-1]))
check("interpolates rather than repeating stops", len(set(ramp)) > 100, len(set(ramp)))
check("a single stop degenerates safely", len(set(G.build_ramp(["#FF0000"], 10))) == 1)
check("empty stops fall back to the default palette",
      len(G.build_ramp([], 20)) == 20)

pts = G.perimeter_points(0, 0, 1920, 1080, 120)
check("perimeter returns the requested count", len(pts) == 120, len(pts))
check("starts at the origin", pts[0] == (0, 0), pts[0])
check("all points are on an edge",
      all(abs(x) < 1e-6 or abs(x - 1920) < 1e-6 or abs(y) < 1e-6 or abs(y - 1080) < 1e-6
          for x, y in pts), [p for p in pts if 0 < p[0] < 1920 and 0 < p[1] < 1080][:2])
check("travels clockwise from the top-left", pts[1][0] > pts[0][0], pts[:2])
covered = {("top" if abs(y) < 1e-6 else "bottom" if abs(y - 1080) < 1e-6 else
            "left" if abs(x) < 1e-6 else "right") for x, y in pts}
check("visits all four edges", covered == {"top", "right", "bottom", "left"}, covered)

# Every corner must be an actual point, or a segment straddles it and the
# corner comes out visibly chamfered.
for corner in ((0, 0), (1920, 0), (1920, 1080), (0, 1080)):
    check(f"corner {corner} is hit exactly",
          any(abs(px - corner[0]) < 1e-6 and abs(py - corner[1]) < 1e-6
              for px, py in pts), corner)

for w, h, n in ((1920, 1080, 120), (3840, 2160, 96), (5760, 1080, 120),
                (1080, 1920, 64), (2, 2, 8), (100, 100, 4)):
    got = G.perimeter_points(0, 0, w, h, n)
    check(f"{w}x{h} with {n} segments -> exactly {n}", len(got) == n, len(got))

check("clamps a silly segment count", len(G.perimeter_points(0, 0, 100, 100, 1)) >= 4)
check("degenerate size does not crash", len(G.perimeter_points(0, 0, 0, 0, 8)) == 8)


print(f"\n{'='*46}\n  {PASS} passed, {FAIL} failed\n{'='*46}")
sys.exit(1 if FAIL else 0)
