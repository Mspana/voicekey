# VoiceKey

Hold **Space** and talk to type; hold **Ctrl** and talk to run a command. Inside
dictation, the word **zulu** works like a keyboard key — everything before it is
text, the words right after it are an action. That's the whole idea.

---

## Hotkeys

| | |
|---|---|
| **Hold Space** | Dictate. Release to type it. |
| **Alt+Space** | A literal space |
| **Hold Ctrl** | Command only, no `zulu` needed |
| **Alt+Q** | Stop listening (stays running) |
| **Ctrl+Alt+G** | Start again |
| **Esc** | Cancel whatever's happening |
| **Close the window** | Quit |

## Saying commands

```
"ship it zulu enter"            types "ship it", presses Enter
"line one zulu enter line two"  types, Enter, types
"zulu right click"
```

**Keys** — enter · tab · back tab · escape · backspace · delete · space ·
up / down / left / right · page up / page down · home · end

**Shortcuts** — copy · paste · cut · undo · redo · select all · save · find ·
close tab · switch window

**Mouse** — click · right click · double click · middle click · hold · drag ·
`hold three seconds`

**Scroll** — `scroll up` · `scroll down 12`

**Delete** — `back 3 characters` · `back 4 words` · `back 2 lines`

**Move the cursor** — a direction after any of these, e.g. `bump left`,
`jump top right`, `skip up a lot`:

| | |
|---|---|
| `bump` | 8 px |
| `skip` | 30 px |
| `jog` | 80 px |
| `move` | 200 px |
| `jump` | 500 px |

Directions: up · down · left · right · top left · top right · bottom left ·
bottom right. Also `centre`.

**App** — `zulu grid` · `zulu off` · `zulu wake up` · `zulu close voice key`

**Repeats** — `zulu tab twice` · `zulu click three times`

## The grid

Say **`zulu grid`**. Type a **column** number, then a **row** number — it zooms
into that cell and shows a fresh grid. Repeat until you're on target.

| | |
|---|---|
| **1–5** | column, then row |
| **Space** | click |
| **R / D / M** | right / double / middle click |
| **H** | hold the button down |
| **V** | move there without clicking |
| **Backspace** | back one step |
| **Esc** | cancel |

Two levels gets you within about 50 pixels; three gets you to a single
character.

## Settings

`config.json`, next to the app. Worth changing:

- `commands.escape_phrase` — `zulu` if it clashes with how you talk
- `push_to_talk_key` — `f13` for a foot pedal
- `vocabulary_hint` — game and app names, jargon; improves accuracy
- `glow.soft_thickness` — how big the screen-edge glow is

Not working? Read **`voicekey.log`**, or run **`doctor.bat`**.
