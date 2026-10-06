#!/usr/bin/env python3
"""Parametric laser-cut desk frame for the 5.65" ACeP panel + ESP32 + LiPo.

Writes one SVG per layer (mm units, red hairline cuts, ready for LightBurn or
WeCreat MakeIt) plus preview.png. Edit the parameters below and re-run.

Stack, front to back (all 3 mm sheet):
  L1 face     window onto the active area
  L2 pocket   holds the panel; captures four M3 nuts
  L3 backer   flat support behind the glass, with a slot for the ribbon cable
  L4-L7 ring  electronics cavity (12 mm deep); USB-C notch for the charger
  L8 back     removable; four M3 screws; slots for the two feet
  foot x2     press into the back at the lean angle

Panel geometry is from Waveshare's mechanical drawing (5.65inch e-Paper F spec, p.5).
"""

import math
import pathlib

from PIL import Image, ImageDraw

OUT = pathlib.Path(__file__).resolve().parent / "svg"

# ---------------------------------------------------------------- parameters
T = 3.0          # sheet thickness; measure yours, plywood is rarely exactly 3.0
KERF = 0.12      # beam width; slots for press-fit tabs are narrowed by this
W, H = 170.0, 140.0          # outer frame size
TOP_BORDER = 24.0            # face border above the window (bottom gets the rest)
WALL = 10.0                  # cavity ring wall
LEAN = 15.0                  # degrees back from vertical
FOOT_SPAN = 22.0             # how far up the back the feet attach
FOOT_INSET = 32.0            # feet distance from the side edges
M3_HOLE = 3.4
M3_NUT_FLATS = 5.6           # 5.5 nominal + a hair
SCREW_INSET = 5.5
USB_NOTCH = (14.0, 66.0)     # (width, center y) of the charger port notch, right wall
USB_LAYERS = {5, 6, 7}       # which ring layers get the notch (9 mm tall opening)

# Panel (landscape, ribbon cable exiting the bottom edge).
PANEL_W, PANEL_H = 125.4, 99.5
AA_W, AA_H = 114.9, 85.8
AA_LEFT, AA_TOP = 5.25, 4.60     # active area offset inside the glass
WINDOW_INSET = 0.5               # hide the glass's dead border
PANEL_CLEAR = 0.3
FPC_SLOT = (32.0, 6.0)           # ribbon pass-through (covers either FPC position)

# ---------------------------------------------------------------- derived
aa_x, aa_y = (W - AA_W) / 2, TOP_BORDER
px, py = aa_x - AA_LEFT, aa_y - AA_TOP          # panel top-left
fpc_x0 = px + PANEL_W / 2 - FPC_SLOT[0] / 2 + 6  # FPC sits ~6 mm right of center
fpc_x1 = fpc_x0 + FPC_SLOT[0]
screws = [(SCREW_INSET, SCREW_INSET), (W - SCREW_INSET, SCREW_INSET),
          (SCREW_INSET, H - SCREW_INSET), (W - SCREW_INSET, H - SCREW_INSET)]


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def circle(cx, cy, d, n=48):
    r = d / 2
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def hexagon(cx, cy, flats):
    r = flats / math.sqrt(3)  # circumradius
    return [(cx + r * math.cos(math.pi / 6 + i * math.pi / 3),
             cy + r * math.sin(math.pi / 6 + i * math.pi / 3)) for i in range(6)]


def outline():
    return rect(0, 0, W, H)


def layers():
    L = {}
    L["L1-face"] = [outline(), rect(aa_x + WINDOW_INSET, aa_y + WINDOW_INSET,
                                    aa_x + AA_W - WINDOW_INSET, aa_y + AA_H - WINDOW_INSET)]

    # Pocket = panel outline + clearance, with a tongue below it for the ribbon to fold back.
    c = PANEL_CLEAR
    pb = py + PANEL_H + c
    pocket = [(px - c, py - c), (px + PANEL_W + c, py - c), (px + PANEL_W + c, pb),
              (fpc_x1, pb), (fpc_x1, pb + FPC_SLOT[1]), (fpc_x0, pb + FPC_SLOT[1]),
              (fpc_x0, pb), (px - c, pb)]
    L["L2-pocket"] = [outline(), pocket] + [hexagon(x, y, M3_NUT_FLATS) for x, y in screws]

    holes = [circle(x, y, M3_HOLE) for x, y in screws]
    slot_y0 = py + PANEL_H - 3
    L["L3-backer"] = [outline(), rect(fpc_x0, slot_y0, fpc_x1, slot_y0 + FPC_SLOT[1] + 3)] + holes

    for i in (4, 5, 6, 7):
        if i in USB_LAYERS:
            L[f"L{i}-ring"] = [ring_with_notch(*USB_NOTCH)] + holes
        else:
            L[f"L{i}-ring"] = [outline(), rect(WALL, WALL, W - WALL, H - WALL)] + holes

    # Back: screw holes + two press-fit slots for the feet near the bottom edge.
    # Slot runs along the height (feet stand perpendicular to the back).
    slots = []
    for fx in (FOOT_INSET, W - FOOT_INSET):
        slots.append(rect(fx - (T - KERF) / 2, H - FOOT_SPAN + 2, fx + (T - KERF) / 2, H - 2))
    L["L8-back"] = [outline()] + holes + slots
    return L


def ring_with_notch(nw, ncy):
    """Ring layer whose right wall is cut through for the USB-C plug: one closed path."""
    y0, y1 = ncy - nw / 2, ncy + nw / 2
    return [(0, 0), (W, 0), (W, y0), (W - WALL, y0), (W - WALL, WALL), (WALL, WALL),
            (WALL, H - WALL), (W - WALL, H - WALL), (W - WALL, y1), (W, y1), (W, H), (0, H)]


def foot_polygon():
    """Side profile of one foot, laid flat. x = distance out from the back, y = distance
    down from the top of the attachment (so y = FOOT_SPAN is the frame's bottom edge).
    The long edge sits on the desk when the frame leans LEAN degrees back; the tab on
    the x = 0 edge presses into the back panel."""
    S = FOOT_SPAN
    tan_a = math.tan(math.radians(LEAN))
    reach = S / tan_a - 10  # trim the 15-degree tip so it isn't fragile
    return [(0, 0), (reach, 0), (reach, S - reach * tan_a), (0, S),
            (0, S - 2), (-T, S - 2), (-T, 2), (0, 2)]


def svg(paths, w, h, x0=0.0, y0=0.0):
    body = "\n".join(
        f'  <polygon points="{" ".join(f"{x - x0:.3f},{y - y0:.3f}" for x, y in p)}" />' for p in paths)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.3f}mm" height="{h:.3f}mm" '
            f'viewBox="0 0 {w:.3f} {h:.3f}">\n'
            f'<g fill="none" stroke="#ff0000" stroke-width="0.1">\n{body}\n</g>\n</svg>\n')


def main():
    OUT.mkdir(exist_ok=True)
    L = layers()
    for name, paths in L.items():
        (OUT / f"{name}.svg").write_text(svg(paths, W, H))
    f = foot_polygon()
    xs, ys = [p[0] for p in f], [p[1] for p in f]
    fw, fh = max(xs) - min(xs), max(ys) - min(ys)
    # Two feet side by side in one file.
    f2 = [(x + fw + 4, y) for x, y in f]
    (OUT / "foot-x2.svg").write_text(svg([f, f2], 2 * fw + 4, fh, min(xs), min(ys)))
    preview(L, f)
    print(f"wrote {len(L) + 1} SVGs to {OUT}")
    print(f"window {AA_W - 2 * WINDOW_INSET:.1f} x {AA_H - 2 * WINDOW_INSET:.1f} mm at "
          f"({aa_x + WINDOW_INSET:.1f}, {aa_y + WINDOW_INSET:.1f}); stack depth {8 * T:.0f} mm; "
          f"foot reach {max(x for x, _ in f):.0f} mm")


def preview(L, f):
    s = 3  # px per mm
    names = list(L)
    cols = 4
    tile_w, tile_h = int(W * s) + 20, int(H * s) + 40
    rows = (len(names) + 1 + cols - 1) // cols
    img = Image.new("RGB", (cols * tile_w, rows * tile_h), "white")
    d = ImageDraw.Draw(img)
    for i, name in enumerate(names + ["foot"]):
        ox, oy = (i % cols) * tile_w + 10, (i // cols) * tile_h + 30
        d.text((ox, oy - 22), name, fill="black")
        paths = L.get(name, [[(x + 10, y + 10) for x, y in f]])
        for p in paths:
            d.polygon([(ox + x * s, oy + y * s) for x, y in p], outline=(200, 0, 0))
        if name == "L1-face":  # show where the glass and active area sit
            d.rectangle([ox + px * s, oy + py * s, ox + (px + PANEL_W) * s, oy + (py + PANEL_H) * s],
                        outline=(120, 120, 255))
    img.save(OUT.parent / "preview.png")


if __name__ == "__main__":
    main()
