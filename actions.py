#!/usr/bin/env python3
"""
VoiceKey - Phase 3: the command grammar.

An escape phrase inside dictated text works like `\\n` inside a string literal:
everything up to it is text, the words right after it are an action.

    "send it tomorrow zulu enter"   ->  types "send it tomorrow", presses Enter
    "zulu right click"              ->  right-clicks
    "line one zulu enter line two"  ->  types, Enter, types

Parsing is pure - no keyboard, no mouse, no config files - so the whole grammar
is testable without a display or a microphone. Execution lives in `perform`.
"""

from __future__ import annotations

import re
import unicodedata

DEFAULT_ESCAPE = "zulu"

# Number words, for "hold three seconds" and for grid cells spoken aloud.
NUMBER_WORDS = {
    "zero": 0, "oh": 0, "one": 1, "won": 1, "two": 2, "to": 2, "too": 2,
    "three": 3, "four": 4, "for": 4, "fore": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "ate": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "sixty": 60,
}


def _spec(kind: str, **params) -> dict:
    return {"kind": kind, **params}


# ------------------------------------------------------------------- nudging

# Relative cursor moves: "bump top left", "nudge right a lot", "move left 120".
# These fill the gap between the grid (which gets you to roughly the right
# place in two syllables) and a click (which needs to be exact). Going back to
# the grid to correct a 10px miss is the slow path; a bump is the fast one.
# The VERB carries the distance. That is the whole point: picking a magnitude
# costs zero extra syllables, and syllables are the scarce resource when you
# are talking to a computer for eight hours. Pixel values are the defaults in
# commands.nudge_steps and are all configurable.
#
#   bump  8px   pixel-level correction, "I'm one character off"
#   skip  30px  nudge onto the neighbouring control
#   jog   80px  across a toolbar
#   move  200px across a panel
#   jump  500px across the screen
NUDGE_VERBS = {
    "bump": "bump", "nudge": "bump", "inch": "bump", "tap": "bump",
    "skip": "skip", "scoot": "skip",
    "jog": "jog", "shift": "jog", "slide": "jog",
    "move": "move", "go": "move", "drift": "move",
    "jump": "jump", "leap": "jump", "fly": "jump", "throw": "jump",
}

DEFAULT_STEPS = {"bump": 8, "skip": 30, "jog": 80, "move": 200, "jump": 500}

DIRECTIONS = {
    "up": (0, -1), "north": (0, -1), "north": (0, -1),
    "down": (0, 1), "south": (0, 1),
    "left": (-1, 0), "west": (-1, 0),
    "right": (1, 0), "east": (1, 0),

    "up left": (-1, -1), "top left": (-1, -1), "upper left": (-1, -1),
    "left up": (-1, -1), "northwest": (-1, -1), "north west": (-1, -1),

    "up right": (1, -1), "top right": (1, -1), "upper right": (1, -1),
    "right up": (1, -1), "northeast": (1, -1), "north east": (1, -1),

    "down left": (-1, 1), "bottom left": (-1, 1), "lower left": (-1, 1),
    "left down": (-1, 1), "southwest": (-1, 1), "south west": (-1, 1),

    "down right": (1, 1), "bottom right": (1, 1), "lower right": (1, 1),
    "right down": (1, 1), "southeast": (1, 1), "south east": (1, 1),
}

# Multipliers on the configured step, so you never have to say a pixel count.
SIZE_WORDS = {
    "a hair": 0.15, "a touch": 0.15, "barely": 0.15, "tiny": 0.15,
    "a little": 0.4, "a bit": 0.4, "slightly": 0.4, "small": 0.4, "gently": 0.4,
    "a lot": 3.0, "big": 3.0, "large": 3.0, "far": 4.0, "way": 4.0,
    "further": 2.0, "more": 2.0,
}
MAX_SIZE_TOKENS = max(len(p.split()) for p in SIZE_WORDS)
MAX_DIR_TOKENS = max(len(p.split()) for p in DIRECTIONS)


# Phrase -> action. Longest phrase wins, so "right click" beats "right".
# Homophones are deliberate: transcription models pick whichever spelling they
# feel like, and a command that only fires 80% of the time is worse than none.
ACTION_TABLE: dict = {
    # -- mouse
    "click": _spec("mouse", button="left", count=1),
    "left click": _spec("mouse", button="left", count=1),
    "double click": _spec("mouse", button="left", count=2),
    "triple click": _spec("mouse", button="left", count=3),
    "right click": _spec("mouse", button="right", count=1),
    "middle click": _spec("mouse", button="middle", count=1),
    "move": _spec("app", command="cursor"),
    "move mouse": _spec("app", command="cursor"),
    "move cursor": _spec("app", command="cursor"),
    "cursor here": _spec("app", command="cursor"),
    "go there": _spec("app", command="cursor"),
    "hold": _spec("hold", seconds=None),
    "hold click": _spec("hold", seconds=None),
    "press and hold": _spec("hold", seconds=None),
    "drag": _spec("hold", seconds=None),

    # -- keys
    "enter": _spec("key", combo="enter"),
    "return": _spec("key", combo="enter"),
    "submit": _spec("key", combo="enter"),
    "new line": _spec("key", combo="enter"),
    "newline": _spec("key", combo="enter"),
    "tab": _spec("key", combo="tab"),
    "next field": _spec("key", combo="tab"),
    "back tab": _spec("key", combo="shift+tab"),
    "shift tab": _spec("key", combo="shift+tab"),
    "previous field": _spec("key", combo="shift+tab"),
    "escape": _spec("key", combo="esc"),
    "cancel": _spec("key", combo="esc"),
    "backspace": _spec("key", combo="backspace"),
    "delete": _spec("key", combo="delete"),
    "space": _spec("key", combo="space"),
    "up": _spec("key", combo="up"),
    "down": _spec("key", combo="down"),
    "left": _spec("key", combo="left"),
    "right": _spec("key", combo="right"),
    "page up": _spec("key", combo="page up"),
    "page down": _spec("key", combo="page down"),
    "home": _spec("key", combo="home"),
    "end": _spec("key", combo="end"),
    "copy": _spec("key", combo="ctrl+c"),
    "paste": _spec("key", combo="ctrl+v"),
    "cut": _spec("key", combo="ctrl+x"),
    "undo": _spec("key", combo="ctrl+z"),
    "redo": _spec("key", combo="ctrl+y"),
    "select all": _spec("key", combo="ctrl+a"),
    "save": _spec("key", combo="ctrl+s"),
    "find": _spec("key", combo="ctrl+f"),
    "close tab": _spec("key", combo="ctrl+w"),
    "switch window": _spec("key", combo="alt+tab"),

    # -- scrolling
    "scroll up": _spec("scroll", clicks=3),
    "scroll down": _spec("scroll", clicks=-3),

    # -- application
    "centre": _spec("app", command="centre"),
    "center": _spec("app", command="centre"),
    "middle": _spec("app", command="centre"),
    "grid": _spec("app", command="grid"),
    "mouse grid": _spec("app", command="grid"),
    "off": _spec("app", command="off"),
    "sleep": _spec("app", command="off"),
    "stop listening": _spec("app", command="off"),
    "on": _spec("app", command="on"),
    "wake": _spec("app", command="on"),
    "wake up": _spec("app", command="on"),
    "start listening": _spec("app", command="on"),
    "quit": _spec("app", command="quit"),
    "quit voice key": _spec("app", command="quit"),
    "quit voicekey": _spec("app", command="quit"),
    "close voice key": _spec("app", command="quit"),
    "close voicekey": _spec("app", command="quit"),
    "exit voice key": _spec("app", command="quit"),
    "shut down voice key": _spec("app", command="quit"),
    "kill voice key": _spec("app", command="quit"),
}

# Longest first, so multi-word phrases match before their prefixes.
_PHRASES = sorted(ACTION_TABLE, key=lambda p: -len(p.split()))
MAX_PHRASE_TOKENS = max(len(p.split()) for p in ACTION_TABLE)


# ------------------------------------------------------------------ normalise

_PUNCT = re.compile(r"[^\w\s']", re.UNICODE)


def normalise(text: str) -> str:
    """Lowercase, strip accents and punctuation, collapse whitespace.

    Transcripts arrive with sentence casing and trailing full stops - "Zulu,
    enter." has to match the same grammar as "zulu enter".
    """
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _PUNCT.sub(" ", text.lower())
    return " ".join(text.split())


def tokenise(text: str) -> list:
    return normalise(text).split()


_WORD = re.compile(r"[\w']+", re.UNICODE)


def tokenise_spans(text: str) -> list:
    """[(normalised_token, start, end)] against the ORIGINAL string.

    Matching has to happen on normalised tokens ("Zulu," must equal "zulu"),
    but the text handed back to the user has to be the original, with its
    capitalisation and punctuation intact. Keeping offsets lets us do both:
    match on the normalised form, emit a slice of the raw transcript.
    """
    out = []
    for m in _WORD.finditer(text or ""):
        norm = normalise(m.group(0))
        if norm:
            out.append((norm, m.start(), m.end()))
    return out


def parse_number(tokens: list, i: int):
    """Read a number at tokens[i]. Returns (value, tokens_consumed)."""
    if i >= len(tokens):
        return (None, 0)
    tok = tokens[i]
    if tok.isdigit():
        return (int(tok), 1)
    if tok in NUMBER_WORDS:
        value = NUMBER_WORDS[tok]
        # "twenty one" -> 21
        if (value in (20, 30, 60) and i + 1 < len(tokens)
                and tokens[i + 1] in NUMBER_WORDS
                and 1 <= NUMBER_WORDS[tokens[i + 1]] <= 9):
            return (value + NUMBER_WORDS[tokens[i + 1]], 2)
        return (value, 1)
    return (None, 0)


def _match_size(tokens: list, j: int):
    for n in range(min(MAX_SIZE_TOKENS, len(tokens) - j), 0, -1):
        phrase = " ".join(tokens[j:j + n])
        if phrase in SIZE_WORDS:
            return (SIZE_WORDS[phrase], n)
    return (None, 0)


def _match_direction(tokens: list, j: int):
    for n in range(min(MAX_DIR_TOKENS, len(tokens) - j), 0, -1):
        phrase = " ".join(tokens[j:j + n])
        if phrase in DIRECTIONS:
            return (DIRECTIONS[phrase], n)
    return (None, 0)


def match_nudge(tokens: list, i: int):
    """VERB [size] DIRECTION [size | number [pixels]]

    "bump left", "jump top right", "skip up a lot", "jog right 120".
    Returns (spec, tokens_consumed) or (None, 0) so the caller can fall through
    to the phrase table - that is what keeps a bare "move" working as the grid
    cursor command while "move left" becomes a nudge.
    """
    if i >= len(tokens):
        return (None, 0)
    verb = NUDGE_VERBS.get(tokens[i])
    if verb is None:
        return (None, 0)

    j = i + 1
    scale, used = _match_size(tokens, j)        # "bump a little left"
    j += used

    vec, used = _match_direction(tokens, j)
    if vec is None:
        return (None, 0)                        # no direction -> not a nudge
    j += used

    distance = None
    value, used_n = parse_number(tokens, j)
    if value is not None and value > 0:
        k = j + used_n
        # "three times" is a repeat, not a pixel count.
        if not (k < len(tokens) and tokens[k] in ("times", "time")):
            distance = float(value)
            j = k
            if j < len(tokens) and tokens[j] in ("pixels", "pixel", "px"):
                j += 1
    if distance is None:
        trailing, used_s = _match_size(tokens, j)   # "bump left a lot"
        if trailing is not None:
            scale = trailing
            j += used_s

    return (_spec("nudge", dx=vec[0], dy=vec[1], verb=verb,
                  scale=scale, distance=distance), j - i)


BACK_UNITS = {
    "character": "character", "characters": "character",
    "char": "character", "chars": "character",
    "letter": "character", "letters": "character",
    "word": "word", "words": "word",
    "line": "line", "lines": "line",
}

# A misheard count here is destructive - "back a hundred words" eats a
# paragraph. Deleting is the one place in this grammar where the failure is not
# recoverable by just saying it again.
MAX_BACK = 100

# Wheel notches. Recoverable if misheard, but a stray "scroll down a thousand"
# still throws away your place in a long document.
MAX_SCROLL = 100
SCROLL_UNITS = {"click", "clicks", "notch", "notches", "line", "lines",
                "tick", "ticks", "step", "steps"}


def match_back(tokens: list, i: int):
    """back [count] [characters | words | lines]

    Requires a count or a unit to follow, so "back tab" still resolves to
    shift+tab from the phrase table rather than being eaten as a deletion.
    """
    if i >= len(tokens) or tokens[i] != "back":
        return (None, 0)

    j = i + 1
    count = None
    if j < len(tokens) and tokens[j] in ("a", "an", "one"):
        count, j = 1, j + 1
    else:
        value, used = parse_number(tokens, j)
        if value is not None:
            count, j = int(value), j + used

    unit = None
    if j < len(tokens) and tokens[j] in BACK_UNITS:
        unit = BACK_UNITS[tokens[j]]
        j += 1

    if count is None and unit is None:
        return (None, 0)                    # bare "back" - not for us

    return (_spec("back", count=min(max(1, count or 1), MAX_BACK),
                  unit=unit or "character"), j - i)


def _match_repeat(tokens: list, j: int):
    """Trailing 'twice' / 'three times'. Returns (repeat, consumed)."""
    if j < len(tokens) and tokens[j] == "twice":
        return (2, 1)
    if j < len(tokens) and tokens[j] == "thrice":
        return (3, 1)
    value, used = parse_number(tokens, j)
    if (value is not None and 2 <= value <= 20
            and j + used < len(tokens) and tokens[j + used] in ("times", "time")):
        return (int(value), used + 1)
    return (None, 0)


def match_action(tokens: list, i: int):
    """Longest-match an action phrase at tokens[i].

    Returns (spec, tokens_consumed) or (None, 0).
    """
    # Deletions and nudges are checked before the phrase table, because both
    # start with words the table also owns ("back tab", "move").
    spec, consumed = match_back(tokens, i)
    if spec is not None:
        return (spec, consumed)

    spec, consumed = match_nudge(tokens, i)
    if spec is not None:
        repeat, used = _match_repeat(tokens, i + consumed)
        if repeat:
            spec["repeat"] = repeat
            consumed += used
        return (spec, consumed)

    for n in range(min(MAX_PHRASE_TOKENS, len(tokens) - i), 0, -1):
        phrase = " ".join(tokens[i:i + n])
        spec = ACTION_TABLE.get(phrase)
        if spec is None:
            continue
        spec = dict(spec)
        consumed = n

        if spec["kind"] == "hold":
            # "hold three seconds", "hold for 3 seconds", or bare "hold".
            j = i + n
            if j < len(tokens) and tokens[j] == "for":
                j += 1
            value, used = parse_number(tokens, j)
            if value is not None:
                j += used
                if j < len(tokens) and tokens[j] in ("second", "seconds", "sec", "secs"):
                    j += 1
                spec["seconds"] = float(value)
                consumed = j - i

        elif spec["kind"] == "app" and spec.get("command") == "grid":
            # "grid four three" jumps straight to a cell.
            j = i + n
            col, used_c = parse_number(tokens, j)
            if col is not None:
                row, used_r = parse_number(tokens, j + used_c)
                if row is not None:
                    spec["col"], spec["row"] = col, row
                    consumed = (j + used_c + used_r) - i

        elif spec["kind"] == "scroll":
            # "scroll up 5" - an explicit amount, in wheel notches.
            j = i + n
            value, used_n = parse_number(tokens, j)
            if value is not None and value > 0:
                k = j + used_n
                # "scroll up three times" is a repeat, not an amount.
                if not (k < len(tokens) and tokens[k] in ("times", "time")):
                    sign = 1 if spec["clicks"] > 0 else -1
                    spec["clicks"] = sign * min(int(value), MAX_SCROLL)
                    j = k
                    if j < len(tokens) and tokens[j] in SCROLL_UNITS:
                        j += 1
                    consumed = j - i
            repeat, used = _match_repeat(tokens, i + consumed)
            if repeat:
                spec["repeat"] = repeat
                consumed += used

        elif spec["kind"] in ("mouse", "key"):
            # "click three times", "tab twice"
            repeat, used = _match_repeat(tokens, i + n)
            if repeat:
                spec["repeat"] = repeat
                consumed = n + used

        return (spec, consumed)
    return (None, 0)


# --------------------------------------------------------------------- parse

def parse(text: str, escape_phrase: str = DEFAULT_ESCAPE,
          command_only: bool = False) -> list:
    """Split a transcript into text and action segments.

    Returns a list of ("text", str) / ("action", spec) / ("unknown", str).

    `command_only` treats the whole utterance as a command with no escape
    phrase required - that's what the Right Ctrl key gives you.

    "unknown" exists so the caller can tell "I heard the escape phrase but the
    words after it were not a command" apart from "I heard nothing". Silently
    swallowing the difference is the single most confusing behaviour in every
    shipping voice tool I looked at.
    """
    raw = text or ""
    spans = tokenise_spans(raw)
    tokens = [t for t, _, _ in spans]
    esc = tokenise(escape_phrase) or tokenise(DEFAULT_ESCAPE)
    esc_len = len(esc)

    segments: list = []
    run_start = None            # index of the first token in the current text run

    def flush(next_token_index):
        """Emit the pending text run as a slice of the ORIGINAL transcript.

        The slice runs to the start of whatever interrupted it, so punctuation
        sitting between the last word and the escape phrase is kept:
        "Ship it. Zulu, enter." -> "Ship it."
        """
        nonlocal run_start
        if run_start is None:
            return
        start = spans[run_start][1]
        end = spans[next_token_index][1] if next_token_index < len(spans) else len(raw)
        chunk = raw[start:end].strip()
        if chunk:
            segments.append(("text", chunk))
        run_start = None

    if command_only:
        i = 0
        matched_any = False
        while i < len(tokens):
            spec, used = match_action(tokens, i)
            if spec is not None:
                flush(i)
                segments.append(("action", spec))
                matched_any = True
                i += used
            else:
                if run_start is None:
                    run_start = i
                i += 1
        if not matched_any and run_start is not None:
            return [("unknown", raw[spans[run_start][1]:].strip())]
        flush(len(spans))
        return segments

    i = 0
    while i < len(tokens):
        if tokens[i:i + esc_len] == esc:
            flush(i)
            spec, used = match_action(tokens, i + esc_len)
            if spec is not None:
                segments.append(("action", spec))
                i += esc_len + used
            else:
                # Escape phrase with nothing usable after it. Emit an
                # "unknown" signal so the caller can play the rejection earcon,
                # but let the following words carry on as text: dropping them
                # would silently destroy dictation, and a false accept is the
                # expensive failure here, not a false reject. Worst case the
                # user gets a stray word they can delete, plus a sound telling
                # them the command did not take.
                preview = " ".join(tokens[i + esc_len:i + esc_len + 3])
                segments.append(("unknown", preview))
                i += esc_len
            continue
        if run_start is None:
            run_start = i
        i += 1

    flush(len(spans))
    return segments


def describe(spec: dict) -> str:
    """Short human-readable label, for the console and the log."""
    kind = spec.get("kind")
    rep = spec.get("repeat", 1)
    suffix = f" x{rep}" if rep and rep > 1 else ""
    if kind == "mouse":
        return f"{spec['button']} click" + (f" x{spec['count']}" if spec["count"] > 1 else "") + suffix
    if kind == "hold":
        return f"hold {spec.get('seconds') or 'default'}s"
    if kind == "back":
        n = spec.get("count", 1)
        unit = spec.get("unit", "character")
        return f"back {n} {unit}" + ("s" if n != 1 else "")
    if kind == "nudge":
        names = {(0, -1): "up", (0, 1): "down", (-1, 0): "left", (1, 0): "right",
                 (-1, -1): "up-left", (1, -1): "up-right",
                 (-1, 1): "down-left", (1, 1): "down-right"}
        where = names.get((spec.get("dx"), spec.get("dy")), "?")
        how = (f"{spec['distance']:.0f}px" if spec.get("distance")
               else spec.get("verb", "move"))
        if spec.get("scale"):
            how += f" x{spec['scale']}"
        return f"{how} {where}" + suffix
    if kind == "key":
        return f"key {spec['combo']}" + suffix
    if kind == "scroll":
        n = abs(int(spec.get("clicks", 0)))
        return f"scroll {'up' if spec['clicks'] > 0 else 'down'} {n}" + suffix
    if kind == "app":
        cmd = spec.get("command")
        if cmd == "grid" and "col" in spec:
            return f"grid {spec['col']},{spec['row']}"
        return str(cmd)
    return str(spec)


# ------------------------------------------------------------------- execute

def perform(spec: dict, ctx) -> bool:
    """Run one action.

    `ctx` supplies the side effects (mouse, keys, app control) so this module
    stays importable and testable without any of them.
    """
    kind = spec.get("kind")
    repeat = int(spec.get("repeat", 1) or 1)

    try:
        if kind == "mouse":
            for _ in range(repeat):
                ctx.click(spec["button"], int(spec.get("count", 1)))
            return True
        if kind == "back":
            ctx.back(int(spec.get("count", 1)), spec.get("unit", "character"))
            return True
        if kind == "nudge":
            for _ in range(repeat):
                ctx.nudge(spec["dx"], spec["dy"], spec.get("verb", "move"),
                          spec.get("scale"), spec.get("distance"))
            return True
        if kind == "hold":
            ctx.hold(spec.get("seconds"))
            return True
        if kind == "key":
            for _ in range(repeat):
                ctx.send_key(spec["combo"])
            return True
        if kind == "scroll":
            for _ in range(repeat):
                ctx.scroll(int(spec["clicks"]))
            return True
        if kind == "app":
            return bool(ctx.app_command(spec.get("command"), spec))
    except Exception:
        return False
    return False
