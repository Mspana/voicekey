# VoiceKey

Hands-free PC control. Built in three phases:

1. **Dictation** — push-to-talk, OpenAI backend ✅
2. **Mouse grid** — column-then-row drill-down with zoom ✅
3. **Action keys** — escape phrase + Ctrl ✅
4. **Window** — status dot, Start / Stop ✅

**Double-click `VoiceKey.exe`.** One file, nothing to install. On first run it
asks for your OpenAI key, saves it in a `config.json` beside itself, and starts.

To build that exe (PyInstaller cannot cross-compile — a Windows exe has to be
built on Windows):

```bat
build.bat
```

It installs the dependencies and PyInstaller, then leaves **`dist\VoiceKey.exe`**.
Copy that one file anywhere.

Running from source instead: `run-console.bat` first, then `VoiceKey.bat`.

If nothing appears, read **`voicekey.log`** next to the scripts, or run
**`doctor.bat`** — it prints which Python it found, whether the packages are
installed, whether the API key is visible, and the tail of the log.

---

## Setup (Windows)

```bat
pip install -r requirements.txt
setx OPENAI_API_KEY "sk-..."
```

Open a **new** terminal (so `setx` takes effect), then:

```bat
VoiceKey.bat           &:: the window, no console
run-console.bat        &:: same, with a console for watching transcripts
python voicekey.py     &:: engine only, no window
python dictate.py      &:: dictation only
python grid.py         &:: grid only
```

If the `keyboard` library can't install the low-level hook, run the terminal as
Administrator once — some systems need it, most don't.

## Use

| Input | Result |
|---|---|
| **Hold Space** (or foot pedal), speak, release | Transcript typed into the focused window |
| **Hold Ctrl** (either one), speak, release | Command only. Screen edge glows in colour. |
| **Alt+Space** | Types a literal space |
| **Alt+Q** | Stop — deactivates, keeps running |
| **Ctrl+Alt+G** | Start again |
| **Esc** | Abort whatever is in progress |
| **Close the window** | Quit |

The grid has **no hotkey** — say `zulu grid`. A hotkey for it kept colliding
with start/stop, which meant launching the app dropped you into a grid. Set
`commands.grid_hotkey` if you want one back.

You'll hear a high beep when it starts listening, a lower beep when it captures,
and a long low beep on an error or an empty transcript. The sounds are the
primary feedback channel on purpose — you shouldn't have to look at anything.

## Foot pedal

Most USB pedals enumerate as an ordinary HID keyboard. Press the pedal in
Notepad to see what character it sends, then set that in `config.json`:

```json
"push_to_talk_key": "f13"
```

Pedals that ship configuration software (Elgato, VEC Infinity, RadialTech) can
usually be remapped to `F13`–`F24`, which is ideal — those keys exist in the
scancode set but no application uses them, so there's nothing to suppress and
no passthrough needed.

## config.json

| Key | Notes |
|---|---|
| `push_to_talk_key` | `keyboard`-library key name. `space`, `right ctrl`, `f13`… |
| `passthrough_modifier` | Hold this + PTT key to get the key's normal behaviour |
| `master_toggle_hotkey` | Global enable/disable |
| `min_press_ms` | Presses shorter than this are treated as a real keypress, not speech. Stops pedal bounce and stray taps from firing requests. |
| `model` / `model_fallbacks` | Tries in order, remembers what worked. OpenAI's model IDs have churned (`whisper-1` → `gpt-4o-transcribe` → `gpt-transcribe`), so this survives the next rename. |
| `vocabulary_hint` | Free-text biasing. Put game names, tool names, jargon here — e.g. `"Vulkan, DirectX, Blender, Figma, kubectl"`. Cheap accuracy win. |
| `input_device` | `null` = system default. Set to a device index if you have several mics. |
| `output_method` | `paste` (fast, unicode-safe, restores your clipboard) or `type` |
| `trailing_space` | Adds a space after each utterance so consecutive dictations don't run together |
| `log_transcripts` | Appends to `transcripts.log` — useful for spotting recurring misrecognitions to add to `vocabulary_hint` |

## Design notes

**Why push-to-talk.** Explicit start/stop boundaries are the single biggest
accuracy win available. Batch transcription models are excellent on a bounded
clip of deliberate speech and unreliable when left listening to a room deciding
for themselves what counts as speech — that's where the hallucinated text comes
from. The pedal isn't a workaround, it's the feature.

**Why the minimum-press guard.** A destructive false accept (garbage text
injected into a form) is much worse than a false reject (say it again). The
guard is deliberately biased toward rejecting.

**Why the master toggle exists.** Space-as-PTT means space isn't space. That's
correct for a workday and catastrophic mid-game. One hotkey, loud audio
confirmation, and the state is always announced.

**Empty transcripts get their own sound.** "I heard you and produced nothing" is
a different event from "I wasn't listening." No shipping voice tool distinguishes
these; it's a small thing that removes a lot of confusion.

---

# Phase 2 — mouse grid

```bat
python grid.py
```

A numbered grid covers the screen. Selection is **two digits**: the first picks
a column, the second picks a row. On the second digit it zooms straight into
that cell and shows a fresh grid, the way macOS Voice Control does. No Enter,
no multi-digit numbers, never more than 5 numbers on screen at once.

| Input | Result |
|---|---|
| **Ctrl+Alt+G** | Show / hide the grid |
| **1–5** | Column. The column highlights and row numbers appear inside it |
| **1–5** | Row. Zooms immediately — no terminator |
| **Backspace** | Un-arm the column, or if none is armed, go up a level |
| **Space** / **Enter** | Left click at the centre |
| **R / D / M** | Right click / double click / middle click |
| **H** | Hold the left button (`grid.hold_seconds`) |
| **V** | Move the cursor without clicking |
| **Escape** | Cancel |

### Why 5×5

Each cell is 1/5 the width and 1/5 the height of the region, so **a cell is the
same shape as the screen**. That makes the subdivision self-similar: the region
stays screen-shaped at every depth, which means zooming a cell to fill the
display is always an exact fit — no letterboxing, no distortion, no wasted
screen, on any monitor or multi-monitor span. There's a test asserting the
aspect ratio is preserved to within a float epsilon across six display layouts
and five levels deep.

5 is also what keeps both axes single-digit, which is what makes selection two
keystrokes with no terminator. It's hardcoded in `config.json` as `cols`/`rows`
if you want to experiment, but anything above 9 breaks the two-keystroke
property.

| Level | Zoom | 1920×1080 | 3840×2160 |
|---|---|---|---|
| 1 | 1× | 384 × 216 px | 768 × 432 px |
| 2 | 5× | 77 × 43 px | 154 × 86 px |
| 3 | 25× | 15 × 8.6 px | 31 × 17 px |
| 4 | 125× | 3 × 1.7 px | 6 × 3.5 px |

Two levels — four keystrokes — covers almost every real click target. Three gets
to individual characters.

### How the zoom works

The screen is captured **once, when the grid opens**, before the overlay window
exists — grabbing on demand would just photograph the overlay. Each drill-down
crops that image and scales it up with **nearest-neighbour** interpolation;
smoothing makes small UI elements harder to identify, not easier.

The overlay is translucent at level 1 so you can see the real screen through it,
and **opaque once zoomed** — blending a magnified image with the actual screen
underneath would show two different things at once.

### What's on screen

The **full 5×5 grid is always drawn in grey**, at both stages — you need to see
the exact cell you're aiming for, not just the band it sits in. The axis you're
currently choosing is repainted on top in cyan:

- **Picking a column** — grey grid everywhere, column dividers in cyan, one
  large number centred in each column.
- **Column armed** — grey grid still everywhere, the chosen column outlined in
  amber with its row dividers in cyan and numbers 1–5 inside it, and the rest of
  the region knocked back with a 50% stipple (tkinter has no per-item alpha).
  The dim is painted *under* the grey grid, so the reference grid stays fully
  visible — the point is to de-emphasise the content, not hide the grid you're
  navigating by.

Every grid line gets a dark underlay, the same trick as the number halos.
Without it the grey grid disappears against dimmed content of similar luminance,
and cyan washes out over white application backgrounds. The status readout gets
a solid plate rather than a halo, because at 13px an outline is one pixel wide
and vanishes over white.

### Known limits

- **Exclusive-fullscreen games won't show the overlay.** DirectX exclusive mode
  doesn't composite other windows. Borderless windowed works fine, and most
  modern titles default to it. This is also fine in practice — voice is far too
  slow for in-game aiming; the grid is for desktop and application work.
- Absolute cursor positioning can be ignored by games using raw mouse input.
- Multi-monitor is handled: the overlay spans the virtual desktop, including
  monitors at negative coordinates (a second screen to the left of the primary).

---

# Phase 3 — action keys

```bat
python voicekey.py
```

The escape phrase works like `\n` inside a string literal: everything before it
is text, the words right after it are an action.

```
"ship it zulu enter"              types "ship it", presses Enter
"line one zulu enter line two"    types, Enter, types
"zulu right click"                right-clicks
"zulu grid four three"            opens the grid at column 4, row 3
"zulu hold three seconds"         press-and-hold the left button
"zulu off"                        stop listening
```

Or hold **Right Ctrl** and just say the command — no escape phrase needed, and
the screen edge glows while it listens. **Left Ctrl is untouched**; only the
right one is hooked.

| Category | Phrases |
|---|---|
| Mouse | click, left/right/middle click, double click, triple click, hold, drag |
| Nudge | bump / skip / jog / move / jump + a direction |
| Keys | enter, return, submit, new line, tab, back tab, escape, backspace, delete, space, arrows, page up/down, home, end |
| Delete | `back` *n* `characters` / `words` / `lines` |
| Combos | copy, paste, cut, undo, redo, select all, save, find, close tab, switch window |
| Scroll | scroll up / down, optionally *n* (`scroll up 5`, `scroll down 12 clicks`) |
| App | grid, grid *col row*, centre, off / sleep, on / wake, quit / close voice key |

Counts work too: `zulu tab twice`, `zulu click three times`, `zulu hold for 5
seconds`.

### Nudging the cursor

The grid gets you close in two syllables; a nudge closes the last few pixels.
Going back into the grid to fix a 10px miss is the slow path.

**The verb carries the distance**, so choosing a magnitude costs no extra
syllables — and syllables are the scarce resource when you're talking to a
computer all day.

| Verb | Step | For |
|---|---|---|
| `bump` | 8 px | "I'm one character off" |
| `skip` | 30 px | onto the neighbouring control |
| `jog` | 80 px | across a toolbar |
| `move` | 200 px | across a panel |
| `jump` | 500 px | across the screen |

Aliases: `nudge`/`inch`/`tap` = bump, `scoot` = skip, `shift`/`slide` = jog,
`go`/`drift` = move, `leap`/`fly` = jump.

Eight directions, with plenty of ways to say each:

```
"zulu bump left"              8px left
"zulu jump top right"         500px diagonally
"zulu skip up a lot"          90px up  (size words multiply)
"zulu bump a hair right"      1px
"zulu jog right 120"          exactly 120px
"zulu bump left twice"        two bumps
"zulu centre"                 straight to the middle of the screen
```

`up left`, `top left`, `upper left`, `northwest` all work. So do `north`,
`south`, `east`, `west`.

The cursor is **clamped to the desktop** — without that, a few repeated bumps
park it off-screen where you can't see it or get it back by voice.

A bare `move` is still the grid's cursor command; `move left` is a nudge.
Longest-match handles it, and there's a test pinning both.

### Deleting

```
"zulu back 3 characters"
"zulu back 4 words"
"zulu back 2 lines"
"zulu back three"          three characters — the default unit
"zulu back a word"
```

`character`/`char`/`letter`, `word`, `line`, singular or plural. Words use
Ctrl+Backspace, which is the near-universal "delete previous word".

Two deliberate limits. **The count is clamped to 100** — a misheard "back a
hundred words" eats a paragraph, and deleting is the one action in this grammar
that saying it again can't undo. And **bare `back` does nothing**: it needs a
count or a unit, so `back tab` still resolves to Shift+Tab from the phrase table
rather than being swallowed as a deletion.

Character-level deletion is the fallback, not the main path — at roughly a
second per utterance, spelling out backspaces is unusable. Every established
tool (Dragon's "Scratch That", macOS's "Undo that", Voice Access's "Delete last
three words") works at the utterance or word level for exactly that reason.

### Choosing an escape phrase

The default is **`zulu`**. Three properties matter, and they pull against each
other:

- **It must be a real word.** Invented words get mangled by transcription — the
  model will render them differently each time and the command misfires. This
  rules out most "distinctive" made-up triggers.
- **It must be rare in ordinary speech**, or you'll fire commands by accident
  mid-sentence.
- **It should be short.** Voice strain is the single most reported problem among
  full-time voice-control users, and a prefix is paid on *every* command
  forever. Two syllables is the ceiling.

**Don't use "computer".** It's a shipping Alexa wake word, and Northeastern's
125-hour smart-speaker study found that wake-word set false-triggering on
"pickle", "cotton", and "exclamation", 1.5–19 times per day. It's also three
syllables.

`zulu` has a rare Z onset, is in every transcription model's vocabulary via the
NATO alphabet, and essentially never appears in normal dictation. Change it in
`config.json` → `commands.escape_phrase`.

### Nothing you say is ever lost

If the escape phrase is heard but the words after it aren't a command, you get
the rejection earcon **and the words are still typed as text**. Dropping them
would silently destroy dictation. A stray word you can delete is a much cheaper
failure than a sentence that vanished — the same reasoning as the minimum-press
guard in phase 1.

### The listening glow

Right Ctrl brings up a Siri-style gradient band around the screen edge. It's
**reinforcement, not the signal.** An edge glow conveys nothing to a blind user,
is the first thing cropped by a screen magnifier, and colour-alone state
indication fails WCAG 2.2 SC 1.4.1. The earcons are the primary channel.

The band is drawn with **true per-pixel alpha** — a smooth gradient falloff
from the screen edge inward, with rounded corners.

Getting there took two attempts. tkinter offers whole-window opacity and a
chroma key, neither of which is a gradient, and stipple dithering — the obvious
workaround — is *holes*, not translucency; it reads as a screen door. So the
glow is rendered as an RGBA bitmap with numpy and composited by a Windows
**layered window** (`WS_EX_LAYERED`), which blends 8 bits of alpha per pixel
onto the desktop. `WS_EX_TRANSPARENT` makes it invisible to hit-testing so it
can never eat a click, and `WS_EX_NOACTIVATE` stops it stealing focus — which
matters, since the entire point is to show it while you're typing into
something else.

Two details that took a second pass:

- **Corner seams.** A hard `min()` over the four edge distances creases along
  the corner diagonals: two edges meet at exactly equal distance and everything
  downstream steps across that line. Replaced with a softmin, and the perimeter
  position with a *circular* weighted mean using the same weights. Corners come
  out rounded and seamless.
- **Cost.** The alpha field and each pixel's position around the perimeter never
  change, so both are precomputed once (~1.5s on a 4K desktop, at startup). A
  frame is then just a gather from a 360-entry colour table into the ~25% of
  pixels that aren't fully transparent — about 16ms, and only while listening.

It **fades in and out over 120ms** (`glow.fade_ms`), eased rather than linear.
Three things this needed:

- The new window's first blit is at **opacity zero**. Painting it at full and
  then starting the fade is what made it snap to full and fade *from* there.
- The fade is driven by **wall clock**, not a fixed number of equal steps. A 4K
  frame costs ~20ms to render, so fixed stepping overran and stuttered; on the
  clock, a slow machine drops frames and the fade still finishes on time.
- Frames render **straight into the layered window's own DIB memory** through a
  numpy view, so a frame costs zero copies rather than 8MB at 1080p or 33MB at
  4K. That alone took a 1080p frame from 16ms to under 10.

The window is not disposed until the fade finishes, and a press landing mid
fade-out reuses the window still on screen and fades back up from where it got
to.

If the layered window fails for any reason it falls back automatically to the
tkinter version and says so on the console.

> Every ctypes function in `layered.py` declares `argtypes` and `restype`. This
> is not optional on 64-bit Python: an undeclared return value defaults to C
> `int`, so window and device-context handles get silently truncated to 32 bits,
> and an undeclared argument is converted to `c_int`, so a real 64-bit `LPARAM`
> raises *"int too long to convert"*. Both failures surface far from the missing
> declaration and look like nonsense.

`glow.animate: false` gives a static border for anyone sensitive to peripheral
motion — Windows has no `prefers-reduced-motion` equivalent, and turning motion
off must not remove the indicator.

Reference implementations of this effect burn 40–60% of a CPU core because they
rebuild the gradient every frame. Here the colour ramp is computed once, the
canvas segments are created once, animation is an index rotation, and the window
is **destroyed rather than hidden** when idle.

---

## Tests

```bat
python test_dictate.py     &::  32 tests
python test_grid.py        &::  89 tests
python test_actions.py     &:: 245 tests
```

366 offline tests. Config parsing, WAV encoding, text formatting, clipboard
save/restore, model fallback order, press-duration guard, master toggle, grid
subdivision geometry, tiling completeness, negative-origin screens, self-similar
aspect preservation across six display layouts, column-then-row entry including
every rejection path, drill-down and depth limits, context-box framing and edge
clamping, action dispatch ordering, a sweep proving all 625 two-level targets
resolve to on-screen points, the full command grammar including every phrase in
the table, ASR homophones, custom escape phrases, and the glow's colour ramp and
corner-exact perimeter. The audio,
keyboard, and mouse layers are stubbed, so everything runs without a mic, an API
key, or Windows.

There's also `render_check.py`, a dev tool that renders the overlay under Xvfb
and screenshots it, for checking the visuals without a Windows box.

---

## About the API key

**You cannot hide a key inside the exe.** A PyInstaller one-file build is an
archive; anyone with the file can unpack it and read the key, and encrypting it
does not help because the app has to decrypt it at runtime to use it. Treat
anything shipped inside the exe as public.

What actually contains the risk is scoping the key, not hiding it. On
platform.openai.com:

1. **A separate project** for this, so nothing else shares its keys.
2. **Model usage** limited to the transcription models — the project then
   cannot call anything else, whatever the key is used for.
3. **A monthly budget** with a hard cap, so the worst case is a bounded bill.
4. **A restricted key** rather than a full-access one.

Then a leak means someone can transcribe audio on your account up to the cap,
and you revoke that one key without touching anything else.

`build.bat` offers to bake a key into the exe. That is convenience for handing
it to one person you would give the key to anyway — it is labelled as such, and
it is not security.

## What ends up next to the exe

`config.json`, `voicekey.log` and `transcripts.log` are written **beside the
executable**, not inside it. PyInstaller's one-file mode unpacks the bundle to
a temp directory and deletes it on exit, so anything the user edits or that we
want to keep has to live outside — `paths.py` draws that line, with
`app_dir()` for writable state and `bundle_dir()` for shipped resources like
the font.

The bundled `config.json` is copied out on first run, so the exe arrives with
working defaults and leaves an editable file behind.

## Troubleshooting

**The taskbar shows the Python icon.** Three separate things all have to be
right on Windows, and any one of them being wrong gives you python.exe's icon:

1. **AppUserModelID.** Without `SetCurrentProcessExplicitAppUserModelID`,
   Windows groups the process under python.exe and uses its icon regardless of
   what the window says. Set before any window is created.
2. **A real multi-size `.ico`.** `iconphoto()` with a PhotoImage is not enough
   for the taskbar; it wants an icon file, and it wants several sizes in it.
3. **`WM_SETICON` on the real handle.** `iconbitmap()` goes through Tk's own
   icon handling, which does not reliably reach a window whose extended style
   we rewrote by hand — and rewriting it is exactly what a frameless window
   needs to get a taskbar button at all. So the `.ico` is also loaded with
   `LoadImageW` and sent to the handle directly, both ICON_SMALL and ICON_BIG,
   and re-sent after the window is re-shown (which is when the taskbar button
   is actually created).

Run **`icon-test.bat`** if it is still wrong; it reports which step failed.

If you use `run-console.bat`, the **console** gets its own taskbar button
belonging to python.exe — that one is given the same icon too, but a second
button next to the app is expected. `VoiceKey.bat` has no console at all.

**"Trust this publisher" / SmartScreen when running the .bat** is unrelated to
any of this. It is the mark-of-the-web on files extracted from a downloaded
zip. Right-click the zip → Properties → Unblock *before* extracting, and it
goes away for everything inside.

**Nothing happens when I double-click the .bat.** Two usual causes, both now
diagnosed for you rather than failing silently:

- **The API key isn't visible to a double-clicked shortcut.** A key set with
  `set` applies only to that one terminal. Use `setx OPENAI_API_KEY "sk-..."`
  and open a new terminal, or put `"api_key": "sk-..."` in `config.json`.
  Startup now checks for this first and shows a window explaining it.
- **The venv.** A bare `pythonw` runs the *system* Python, which won't have the
  packages installed in your virtualenv, so it dies instantly with no window and
  no message. The launchers now look for `venv\`, `.venv\` or `env\` next to
  the script and prefer that interpreter.

Everything is logged to **`voicekey.log`**, including startup, and any crash
also pops a window with the traceback — `pythonw` has no console, so without
that an exception vanishes completely. `doctor.bat` dumps the whole picture.


**Clicks land where the cursor already was.** `hide()` asks Tk to destroy the
overlay, but Tk only does it when control returns to the event loop — and
`commit()` runs *inside* a key handler, still in the loop. So the click landed
on the overlay window instead of the app underneath. Fixed by flushing the event
queue and deferring the click (`grid.teardown_ms`), plus a pause between
`SetCursorPos` and the click (`grid.settle_ms`) because those go through
different paths into the input queue.

If it persists, run `python check_mouse.py` — it reports DPI awareness, moves
the cursor to five points and reads the position back. Consistent offsets mean
display scaling; exact readings mean it's timing and the two delays want raising.

**Ctrl and command mode.** Both Ctrl keys trigger it. That's harmless because
the hook never suppresses, ignores a press made while Alt/Shift/Win is held, and
**drops the capture as soon as any other key follows** — so holding Ctrl to
press Ctrl+C starts a capture on the way down and the C silently cancels it. No
beep, no API call, no stray text. Ctrl keeps working as Ctrl everywhere.

## The window

A small ordinary application, the shape of a VPN client — it sits on the taskbar
and stays out of the way.

| | |
|---|---|
| **Status dot** | grey stopped · green ready · **pulsing red-orange while listening** · purple for command mode · amber while transcribing |
| **Title bar** | ours, not Windows' — drag anywhere on it to move, – to minimise, ✕ to quit |
| **Type** | Lora SemiBold, lowercase, very dark grey on eggshell. The wordmark is gradient-filled. |
| **Start / Stop** | Stop deactivates every hotkey but leaves it running. Start re-arms it. |
| **Activity line** | the last transcript, or what went wrong |
| **Taskbar icon** | a real multi-size `.ico` — "VK" with the state dot in the corner, regenerated per colour |

**Closing the window is the only thing that quits.** Alt+Q stops it
*functioning* — a hotkey that kills the process is too easy to hit by accident
when the process is the only way you can type.

The engine is the same either way: `app.py` owns the window and the event loop
and calls `VoiceKey.attach(root)`, while `voicekey.py` still runs headless on
its own. Settings live in `config.json` for now; a settings pane is the obvious
next addition.

**Lora is bundled** in `fonts/` under the OFL, so it looks the same on a
machine where it isn't installed. On Windows it's added as a *private* process
font (`AddFontResourceExW` with `FR_PRIVATE`) rather than installed system-wide.

The wordmark and the state label are rendered by PIL rather than being tk
Labels, for two reasons: tkinter only understands "normal" and "bold", and Lora
SemiBold is weight 600 on a variable axis, which only PIL can set; and tkinter
cannot fill text with a gradient at all. Everything else uses the tk family with
a fallback chain through Georgia and Constantia.

Two Windows details the frameless window needed. `overrideredirect(True)`
removes the title bar *and* the taskbar button, so the window has to clear
`WS_EX_TOOLWINDOW` and set `WS_EX_APPWINDOW` to get the button back. And
`iconify()` stops working once the title bar is gone, so minimise goes through
`ShowWindow(SW_MINIMIZE)` directly.

### Getting out

| Key | Does |
|---|---|
| **Alt+Q** | Stop — deactivates everything, keeps running |
| **Ctrl+Alt+G** | Start again |
| **Esc** | Abort the current capture, close the grid |
| **Close the window** | Quit |
| **"zulu close voice key"** | Quit, by voice |

Also `zulu quit`, `zulu close voicekey`, `zulu shut down voice key`. If your
hands are the thing that stopped working, the exit has to be sayable.

## Not yet built

- **Local pop/click detection.** A pop is a broadband transient — detectable in
  ~40 lines of numpy off the raw mic stream, which is already open. It cannot
  come from the OpenAI API: transcription models emit text tokens for speech and
  will either drop a pop or hallucinate it into a word. Worth doing, because a
  non-speech trigger costs zero syllables and still works when your voice is
  tired.
- **Earcon samples.** The current cues are `winsound.Beep` tones. Distinct
  *timbres* survive hearing loss better than distinct pitches.
- **Haptics and screen-reader announcements** on state change.
