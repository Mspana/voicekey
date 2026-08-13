#!/usr/bin/env python3
"""Offline tests for the grid geometry and state machine.

The pure logic (subdivision, digit entry, drill-down, commit) is separated from
tkinter, so all of it is testable without a display.

Run:  python3 test_grid.py
"""
import sys, types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mouse
from grid import subdivide, centre, GridState, MouseGrid, load_grid_config

PASS, FAIL = 0, 0
def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  PASS  {label}")
    else:
        FAIL += 1; print(f"  FAIL  {label}  {detail}")


print("\n[1] subdivision geometry (6x4 over 3840x2160)")
SCREEN = (0, 0, 3840, 2160)
check("cell 1 is top-left", subdivide(SCREEN, 1, 6, 4) == (0, 0, 640, 540))
check("cell 6 is top-right", subdivide(SCREEN, 6, 6, 4) == (3200, 0, 640, 540))
check("cell 7 wraps to row 2", subdivide(SCREEN, 7, 6, 4) == (0, 540, 640, 540))
check("cell 24 is bottom-right", subdivide(SCREEN, 24, 6, 4) == (3200, 1620, 640, 540))

covered = [subdivide(SCREEN, i, 6, 4) for i in range(1, 25)]
area = sum(w * h for _, _, w, h in covered)
check("24 cells tile the screen exactly", abs(area - 3840 * 2160) < 1e-6, area)
check("no duplicate origins", len({(x, y) for x, y, _, _ in covered}) == 24)

for bad in (0, 25, -1):
    try:
        subdivide(SCREEN, bad, 6, 4); check(f"cell {bad} rejected", False)
    except ValueError:
        check(f"cell {bad} rejected", True)


print("\n[2] offset screens (negative origin, second monitor left of primary)")
OFF = (-1920, -200, 5760, 2160)
r = subdivide(OFF, 1, 6, 4)
check("respects negative origin", r == (-1920.0, -200.0, 960.0, 540.0), r)
check("centre lands inside the cell", centre(r) == (-1440, 70), centre(r))


print("\n[3] centre rounding")
check("even rect", centre((0, 0, 640, 540)) == (320, 270))
check("odd rect rounds", centre((0, 0, 3, 3)) == (2, 2), centre((0, 0, 3, 3)))
check("fractional rect", centre((10.5, 20.25, 5.0, 4.0)) == (13, 22), centre((10.5, 20.25, 5.0, 4.0)))


print("\n[4] self-similar subdivision (cells share the screen's shape)")
for label, (W, H) in (("1080p", (1920, 1080)), ("4K", (3840, 2160)),
                      ("triple 1080p", (5760, 1080)), ("portrait", (1080, 1920)),
                      ("ultrawide", (3440, 1440)), ("4:3", (1280, 1024))):
    st_ = GridState((0, 0, float(W), float(H)), 5, 5, max_depth=6)
    root_aspect = W / H
    ok = True
    for _ in range(5):
        st_.select(13)
        cw_, ch_ = st_.rect[2], st_.rect[3]
        if abs((cw_ / ch_) - root_aspect) > 1e-9:
            ok = False
    check(f"{label}: region stays screen-shaped at every depth", ok, st_.rect)

st_ = GridState((0, 0, 1920.0, 1080.0), 5, 5)
cw_, ch_ = st_.cell_size
check("a cell is exactly 1/5 x 1/5 of the region", (cw_, ch_) == (384.0, 216.0),
      (cw_, ch_))
check("a cell has the screen's aspect, not 1:1",
      abs(cw_ / ch_ - 1920 / 1080) < 1e-9, cw_ / ch_)
check("25 cells", st_.cells == 25)
check("both axes single-digit", st_.cols <= 9 and st_.rows <= 9)


print("\n[5] drill-down state machine")
st = GridState(SCREEN, 6, 4, max_depth=4)
check("starts at depth 0", st.depth == 0)
check("24 cells", st.cells == 24)
st.select(1)
check("level 1 cell size", st.rect == (0, 0, 640, 540), st.rect)
st.select(1)
check("level 2 narrows 6x", st.rect == (0, 0, 640/6, 540/4), st.rect)
check("depth tracks", st.depth == 2)
st.back()
check("back restores level 1", st.rect == (0, 0, 640, 540), st.rect)
check("depth decremented", st.depth == 1)
st.reset()
check("reset returns to full screen", st.rect == SCREEN and st.depth == 0)
check("back at root is a no-op", st.back() is False)

st2 = GridState(SCREEN, 6, 4, max_depth=3)
for _ in range(3):
    st2.select(1)
check("max_depth reached", st2.exhausted is True)
check("select past max_depth refused", st2.select(1) is False)
check("depth did not grow", st2.depth == 3)

st3 = GridState((0, 0, 20, 20), 6, 4, max_depth=99)
st3.select(1)
check("sub-pixel cells stop the drill-down", st3.exhausted is True, st3.rect)

print("\n  precision per level (6x4 on 3840x2160):")
w, h = 3840.0, 2160.0
for d in range(1, 5):
    w, h = w / 6, h / 4
    print(f"    level {d}: {w:7.1f} x {h:6.1f} px")
check("3 levels reach sub-20px width", 3840 / 6**3 < 20, 3840 / 6**3)


print("\n[6] MouseGrid without a display (headless)")
mouse.RECORDED.clear()
g = MouseGrid(cfg={**load_grid_config(), "cols": 6, "rows": 4, "max_depth": 4})
g._draw = lambda: None            # skip rendering
g._build_window = lambda: None
g.show()
check("visible after show", g.visible is True)
check("state built from virtual screen", g.state.root_rect == (0.0, 0.0, 1920.0, 1080.0), g.state.root_rect)

ROOT_HD = (0.0, 0.0, 1920.0, 1080.0)

# First digit arms a column and must NOT drill.
g.type_digit("3")
check("first digit arms a column", g.pending_col == 3 and g.state.depth == 0,
      (g.pending_col, g.state.depth))
# Second digit drills immediately - no Enter.
g.type_digit("2")
check("second digit drills with no terminator",
      g.pending_col is None and g.state.depth == 1, (g.pending_col, g.state.depth))
check("landed on (col 3, row 2)",
      g.state.rect == subdivide(ROOT_HD, (2 - 1) * 6 + 3, 6, 4), g.state.rect)

g.state.reset(); g.pending_col = None
check("column beyond the grid is refused", g.type_digit("7") is False)
check("nothing armed after a refused column", g.pending_col is None)
check("zero is never a valid digit", g.type_digit("0") is False)
check("non-digits are ignored", g.type_digit("x") is False)

g.type_digit("6")
check("last column arms", g.pending_col == 6)
check("row beyond the grid is refused", g.type_digit("5") is False)
check("column stays armed after a refused row", g.pending_col == 6)
check("valid row still lands", g.type_digit("4") is True and g.state.depth == 1)
check("landed on (col 6, row 4)",
      g.state.rect == subdivide(ROOT_HD, (4 - 1) * 6 + 6, 6, 4), g.state.rect)

g.state.reset(); g.pending_col = None
g.type_digit("2")
check("backspace un-arms the column before climbing a level",
      g.back() is True and g.pending_col is None and g.state.depth == 0)

g.state.reset(); g.pending_col = None
check("select_cell maps (col,row) to the right rect",
      g.select_cell(4, 3) and g.state.rect == subdivide(ROOT_HD, (3 - 1) * 6 + 4, 6, 4),
      g.state.rect)
check("select_cell rejects an out-of-range column", g.select_cell(99, 1) is False)
check("select_cell rejects an out-of-range row", g.select_cell(1, 99) is False)

g.state.reset(); g.pending_col = None
check("out-of-range select refused", g.select(99) is False)
check("zero select refused", g.select(0) is False)

# Every (col, row) pair must be reachable in exactly two keystrokes.
missing = []
for col in range(1, 7):
    for row in range(1, 5):
        g.state.reset(); g.pending_col = None
        if not (g.type_digit(str(col)) and g.type_digit(str(row))):
            missing.append((col, row))
        elif g.state.rect != subdivide(ROOT_HD, (row - 1) * 6 + col, 6, 4):
            missing.append((col, row, "wrong cell"))
check("all 24 cells reachable in exactly 2 keystrokes", not missing, missing[:3])


print("\n[7] commit performs the right action, after tearing the overlay down")
g.state.reset(); g.pending_col = None
g.select(1); g.select(1)
expected = centre(g.state.rect)
mouse.RECORDED.clear()
point = g.commit("left_click")
check("returns the centre point", point == expected, (point, expected))
check("overlay hidden before clicking", g.visible is False)
check("moved then clicked, in that order",
      mouse.RECORDED == [("move", point[0], point[1]), ("left_click", 1)], mouse.RECORDED)

for action, expect in (("right_click", ("right_click", 1)),
                       ("double_click", ("left_click", 2)),
                       ("middle_click", ("middle_click", 1))):
    g.show(); g.select(3)
    mouse.RECORDED.clear()
    g.commit(action)
    check(f"{action} dispatches correctly", mouse.RECORDED[1] == expect, mouse.RECORDED)

g.show(); g.select(3)
mouse.RECORDED.clear()
g.commit("move")
check("move does not click", mouse.RECORDED == [("move", *centre(g.state.rect))], mouse.RECORDED)

g.show(); g.select(5)
mouse.RECORDED.clear()
g.commit("hold")
import time; time.sleep(0.05)
check("hold uses press-and-release", any(a[0] == "hold_left" for a in mouse.RECORDED), mouse.RECORDED)


print("\n[8] zoom geometry")
import capture
SCREEN_HD = (0, 0, 1920, 1080)

# Square grids preserve aspect at every depth, so the zoomed view fills the
# screen exactly. Non-square grids drift and letterbox a bit more each level.
st_sq = GridState(SCREEN_HD, 5, 5, max_depth=4)
root_aspect = 1920 / 1080
ok = True
for _ in range(3):
    st_sq.select(13)
    _, _, w, h = st_sq.rect
    if abs((w / h) - root_aspect) > 1e-9:
        ok = False
check("5x5 preserves aspect at every level", ok, st_sq.rect)

st_rect = GridState(SCREEN_HD, 6, 4, max_depth=4)
st_rect.select(1)
_, _, w, h = st_rect.rect
check("6x4 does NOT preserve aspect (why the default is square)",
      abs((w / h) - root_aspect) > 0.1, w / h)

st_sq.reset()
st_sq.select(13)
_, _, w, h = st_sq.rect
fw, fh = capture.fit_box(w, h, 1920, 1080)
check("square grid zoom fills the screen exactly", (fw, fh) == (1920, 1080), (fw, fh))
check("zoom factor is 5x at level 1", round(capture.zoom_factor(w, 1920)) == 5,
      capture.zoom_factor(w, 1920))
st_sq.select(13)
_, _, w, h = st_sq.rect
check("zoom factor is 25x at level 2", round(capture.zoom_factor(w, 1920)) == 25,
      capture.zoom_factor(w, 1920))

fw, fh = capture.fit_box(320, 270, 1920, 1080)
check("non-square region letterboxes rather than stretching",
      abs(fw / fh - 320 / 270) < 1e-6 and fw <= 1920 and fh <= 1080, (fw, fh))
check("fit_box never exceeds the box", capture.fit_box(4000, 100, 1920, 1080)[0] <= 1920)

print("\n  5x5 precision on 3840x2160:")
w, h = 3840.0, 2160.0
for d in range(1, 5):
    w, h = w / 5, h / 5
    print(f"    level {d}: {w:7.1f} x {h:6.1f} px   ({5**d}x zoom)")
check("3 levels reach sub-35px on 4K", 3840 / 5**3 < 35, 3840 / 5**3)


print("\n[9] fixed shape")
st9 = GridState(SCREEN_HD, 5, 5, max_depth=4)
shapes = []
for _ in range(4):
    shapes.append(st9.shape)
    st9.select(13)
check("shape never changes with depth", set(shapes) == {(5, 5)}, shapes)

print("\n  precision on 3840x2160:")
w9, h9 = 3840.0, 2160.0
for d in range(1, 5):
    w9, h9 = w9 / 5, h9 / 5
    print(f"    level {d}: {w9:7.1f} x {h9:6.1f} px   ({5**d}x zoom)")
check("3 levels reach sub-35px width", 3840 / 5**3 < 35, 3840 / 5**3)


print("\n[10] zoom context box")
ROOT = (0.0, 0.0, 1920.0, 1080.0)

region = (800.0, 400.0, 274.0, 270.0)          # a level-1 square-ish cell
(vx, vy, vw, vh), scale = capture.context_box(region, ROOT, 1920, 1080)
check("context box keeps the screen's aspect", abs((vw / vh) - (1920 / 1080)) < 1e-6,
      (vw, vh))
check("region fits inside the context box",
      vx <= region[0] and vy <= region[1]
      and region[0] + region[2] <= vx + vw and region[1] + region[3] <= vy + vh)
check("context box stays on the desktop",
      vx >= 0 and vy >= 0 and vx + vw <= 1920.001 and vy + vh <= 1080.001, (vx, vy, vw, vh))
check("region fills the screen height when zoomed",
      abs(region[3] * scale - 1080) < 1.0, region[3] * scale)
check("region does not overflow the width", region[2] * scale <= 1920.001)

# Corners: the box has to slide inwards rather than run off the desktop.
for corner in ((0.0, 0.0, 20.0, 20.0), (1900.0, 1060.0, 20.0, 20.0),
               (0.0, 1060.0, 20.0, 20.0), (1900.0, 0.0, 20.0, 20.0)):
    (vx, vy, vw, vh), _ = capture.context_box(corner, ROOT, 1920, 1080)
    ok = (vx >= -1e-6 and vy >= -1e-6
          and vx + vw <= 1920.001 and vy + vh <= 1080.001
          and vx <= corner[0] and vy <= corner[1])
    check(f"corner region {corner[:2]} stays in bounds", ok, (vx, vy, vw, vh))

# Negative-origin desktops (second monitor to the left).
NEG = (-1920.0, 0.0, 3840.0, 1080.0)
(vx, vy, vw, vh), _ = capture.context_box((-1900.0, 10.0, 30.0, 30.0), NEG, 1920, 1080)
check("negative-origin desktop handled", vx >= -1920.001 and vx + vw <= 1920.001,
      (vx, vw))

(vx, vy, vw, vh), scale = capture.context_box(ROOT, ROOT, 1920, 1080)
check("whole-screen region needs no context", (vw, vh) == (1920.0, 1080.0) and scale == 1.0,
      (vw, vh, scale))


print("\n[11] every cell resolves to a point on screen")
g2 = MouseGrid(cfg=load_grid_config())
g2._draw = lambda: None; g2._build_window = lambda: None
sx, sy, sw, sh = 0, 0, 1920, 1080
bad = []
combos = 0
g2.show()
level1 = g2.state.cells
g2.hide()
for a in range(1, level1 + 1):
    g2.show()
    g2.select(a)
    level2 = g2.state.cells
    g2.hide()
    for b in range(1, level2 + 1):
        g2.show(); g2.select(a); g2.select(b)
        px, py = g2.state.point()
        if not (sx <= px < sx + sw and sy <= py < sy + sh):
            bad.append((a, b, px, py))
        combos += 1
        g2.hide()
check(f"all {combos} two-level targets land on screen", not bad, bad[:3])


print(f"\n{'='*46}\n  {PASS} passed, {FAIL} failed\n{'='*46}")
sys.exit(1 if FAIL else 0)
