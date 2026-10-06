#!/usr/bin/env python3
"""Render the day's quote for the Waveshare 5.65" 7-color ACeP panel.

Outputs (in --out, default ./out), one set per day for --days N:
  YYYY-MM-DD.bin  134,400 bytes, the panel's native format: 600x448, 4 bits/pixel,
                  two pixels per byte (left pixel in the high nibble). The ESP32
                  streams this straight to the panel without decoding anything.
  YYYY-MM-DD.png  Preview using the panel's real (muted) colors.
  today.bin/.png  Copies of the first day.
  manifest.json   Which quote lands on which day.
  index.html      Gallery of the upcoming days.

  --sheet     Also renders every quote to sheet.png for design review.
"""

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import textwrap
from zoneinfo import ZoneInfo

import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent
FONTS = ROOT / "fonts"
W, H = 600, 448

# Panel color indices (from Waveshare's epd5in65f.h).
BLACK, WHITE, GREEN, BLUE, RED, YELLOW, ORANGE = range(7)
INDEX = {"black": BLACK, "white": WHITE, "green": GREEN, "blue": BLUE,
         "red": RED, "yellow": YELLOW, "orange": ORANGE}

# What the pigments actually look like on this panel (measured palette used by
# Pimoroni for the same AC057TC1 glass). Only used for previews.
PREVIEW_RGB = [(57, 48, 57), (255, 255, 255), (58, 91, 70), (61, 59, 94),
               (156, 72, 75), (208, 190, 71), (177, 106, 73)]

KIND_ACCENT = {"quote": RED, "poem": BLUE, "word": GREEN}


def font(name, size, **axes):
    """Load a variable font at a given size, setting axes by name (wght, opsz...)."""
    f = ImageFont.truetype(str(FONTS / name), size)
    tags = {b"Weight": "wght", b"Optical Size": "opsz", b"Optical size": "opsz",
            b"Softness": "SOFT", b"Wonky": "WONK"}
    vals = []
    for ax in f.get_variation_axes():
        tag = tags.get(ax["name"])
        want = axes.get(tag, size if tag == "opsz" else ax["default"])
        vals.append(max(ax["minimum"], min(ax["maximum"], want)))
    f.set_variation_by_axes(vals)
    return f


class Canvas:
    """A palette-indexed canvas. Text is drawn anti-aliased, then thresholded,
    because the panel has no grays: dithered edges look fuzzy, hard edges look printed."""

    def __init__(self, w, h):
        self.img = Image.new("P", (w, h), WHITE)
        self.w, self.h = w, h

    def text(self, xy, s, f, color, anchor="la", tracking=0):
        mask = Image.new("L", (self.w, self.h), 0)
        d = ImageDraw.Draw(mask)
        if tracking:
            x, y = xy
            if anchor[0] in "mr":
                width = text_width(s, f, tracking)
                x -= width / 2 if anchor[0] == "m" else width
            for ch in s:
                d.text((x, y), ch, font=f, fill=255, anchor="l" + anchor[1])
                x += f.getlength(ch) + tracking
        else:
            d.text(xy, s, font=f, fill=255, anchor=anchor)
        self.img.paste(color, mask=mask.point(lambda v: 255 if v >= 110 else 0))

    def rect(self, box, color):
        ImageDraw.Draw(self.img).rectangle(box, fill=color)


def text_width(s, f, tracking=0):
    return f.getlength(s) + tracking * max(len(s) - 1, 0)


def wrap(s, f, max_w):
    """Greedy word wrap by measured width. Keeps explicit newlines."""
    lines = []
    for para in s.split("\n"):
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if line and f.getlength(trial) > max_w:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


def fit(s, name, box_w, box_h, sizes, leading, keep_lines=False, **axes):
    """Largest font size where the wrapped text fits the box. keep_lines=True
    (poems) also requires that no line gets broken."""
    for size in sizes:
        f = font(name, size, **axes)
        lines = wrap(s, f, box_w)
        if keep_lines and len(lines) > s.count("\n") + 1:
            continue
        if len(lines) * size * leading <= box_h and all(f.getlength(l) <= box_w for l in lines):
            return f, lines, size
    return f, lines, size


def smart_quotes(s):
    out, open_ = [], True
    for i, ch in enumerate(s):
        if ch == '"':
            out.append("“" if open_ else "”")
            open_ = not open_
        elif ch == "'":
            prev = s[i - 1] if i else " "
            out.append("‘" if prev.isspace() or prev in "(“" else "’")
        else:
            out.append(ch)
    return "".join(out).replace("--", "—")


# ---------------------------------------------------------------- layouts

M = 40  # outer margin


def footer(c, q, accent, date, show_date):
    """Accent rule + attribution bottom-left, small date bottom-right."""
    y = c.h - M
    by = q.get("by")
    if by:
        name = font("Inter.ttf", 15, wght=650)
        c.rect((M, y - 30, M + 28, y - 27), accent)
        c.text((M, y), by.upper(), name, BLACK, anchor="ls", tracking=1.6)
        if q.get("source"):
            x = M + text_width(by.upper(), name, 1.6) + 10
            c.text((x, y), smart_quotes(q["source"]), font("SourceSerif4-Italic.ttf", 16, wght=500),
                   BLACK, anchor="ls")
    if show_date:
        c.text((c.w - M, y), date.strftime("%a %b %-d").upper(),
               font("Inter.ttf", 12, wght=600), BLACK, anchor="rs", tracking=1.4)


def layout_quote(c, q, accent, date, show_date):
    text = smart_quotes(q["text"].strip())
    # Big hanging quote mark in the accent color.
    c.text((M - 6, M - 28), "“", font("Fraunces.ttf", 150, wght=700, opsz=144, SOFT=50), accent)
    top, bottom = M + 62, c.h - M - 54
    f, lines, size = fit(text, "SourceSerif4.ttf", c.w - 2 * M, bottom - top,
                         range(64, 17, -2), 1.22, wght=560)
    lead = size * 1.22
    # Vertically center the block in the space between the mark and the footer.
    y = top + (bottom - top - len(lines) * lead) / 2 + size * 0.85
    for line in lines:
        c.text((M, y), line, f, BLACK, anchor="ls")
        y += lead
    footer(c, q, accent, date, show_date)


def layout_poem(c, q, accent, date, show_date):
    text = smart_quotes(q["text"].strip("\n"))
    top, bottom = M + 10, c.h - M - 54
    f, lines, size = fit(text, "SourceSerif4-Italic.ttf", c.w - 2 * M - 20, bottom - top,
                         range(40, 15, -1), 1.4, keep_lines=True, wght=500)
    lead = size * 1.4
    block_top = top + (bottom - top - len(lines) * lead) / 2
    y = block_top + size * 0.85
    for line in lines:
        c.text((M + 20, y), line, f, BLACK, anchor="ls")
        y += lead
    c.rect((M, block_top, M + 3, block_top + len(lines) * lead), accent)
    footer(c, q, accent, date, show_date)


def layout_word(c, q, accent, date, show_date):
    word = q["text"].strip()
    f, _, size = fit(word, "Fraunces.ttf", c.w - 2 * M, 140, range(110, 39, -4), 1.0,
                     wght=600, opsz=144, SOFT=30)
    y = M + 30 + size * 0.8
    c.text((M, y), word, f, BLACK, anchor="ls")
    y += size * 0.25 + 30  # clear the descenders
    if q.get("source"):
        c.text((M, y), q["source"], font("SourceSerif4-Italic.ttf", 22, wght=500), accent, anchor="ls")
        y += 22
    meaning = smart_quotes(q.get("meaning", "").strip())
    if meaning:
        mf, lines, msize = fit(meaning, "SourceSerif4.ttf", c.w - 2 * M, c.h - M - 40 - y,
                               range(30, 15, -1), 1.3, wght=450)
        y += msize * 1.3
        for line in lines:
            c.text((M, y), line, mf, BLACK, anchor="ls")
            y += msize * 1.3
    if show_date:
        c.text((c.w - M, c.h - M), date.strftime("%a %b %-d").upper(),
               font("Inter.ttf", 12, wght=600), BLACK, anchor="rs", tracking=1.4)
    c.rect((M, c.h - M - 3, M + 28, c.h - M), accent)


LAYOUTS = {"quote": layout_quote, "poem": layout_poem, "word": layout_word}


# ---------------------------------------------------------------- pipeline

def render(q, date, settings):
    rotate = int(settings.get("rotate", 0)) % 360
    w, h = (H, W) if rotate in (90, 270) else (W, H)
    c = Canvas(w, h)
    kind = q.get("kind", "quote")
    accent = INDEX.get(q.get("accent", ""), KIND_ACCENT.get(kind, ORANGE))
    LAYOUTS[kind](c, q, accent, date, settings.get("show_date", True))
    img = c.img
    if rotate:
        img = img.transpose({90: Image.ROTATE_90, 180: Image.ROTATE_180, 270: Image.ROTATE_270}[rotate])
    return img


def pack(img):
    """P-mode 600x448 -> panel bytes (high nibble = left pixel)."""
    px = img.tobytes()
    assert len(px) == W * H and max(px) <= 6
    return bytes((px[i] << 4) | px[i + 1] for i in range(0, len(px), 2))


def preview(img):
    pal = [v for rgb in PREVIEW_RGB for v in rgb]
    p = img.copy()
    p.putpalette(pal + [0] * (768 - len(pal)))
    return p.convert("RGB")


def pick(quotes, date):
    """Dated entries win on their day. Otherwise cycle through the rest in a fixed
    order (sorted by a hash of the text) so every quote shows before any repeats."""
    mmdd = date.strftime("%m-%d")
    for q in quotes:
        if str(q.get("date", "")) == mmdd:
            return q
    pool = sorted((q for q in quotes if not q.get("date")),
                  key=lambda q: hashlib.sha1(q["text"].encode()).hexdigest())
    return pool[date.toordinal() % len(pool)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quotes", default=str(ROOT.parent / "quotes.yaml"))
    ap.add_argument("--out", default=str(ROOT.parent / "out"))
    ap.add_argument("--date", help="first day, YYYY-MM-DD (default: today in --tz)")
    ap.add_argument("--days", type=int, default=1, help="render this many days ahead")
    ap.add_argument("--tz", default="America/Los_Angeles")
    ap.add_argument("--sheet", action="store_true", help="also render every quote to sheet.png")
    args = ap.parse_args()

    data = yaml.safe_load(open(args.quotes))
    settings, quotes = data.get("settings", {}), data["quotes"]
    first = (dt.date.fromisoformat(args.date) if args.date
             else dt.datetime.now(ZoneInfo(args.tz)).date())
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    manifest = []
    for i in range(args.days):
        date = first + dt.timedelta(days=i)
        q = pick(quotes, date)
        img = render(q, date, settings)
        for stem in [date.isoformat()] + (["today"] if i == 0 else []):
            (out / f"{stem}.bin").write_bytes(pack(img))
            preview(img).save(out / f"{stem}.png")
        manifest.append({"date": date.isoformat(), "quote": q})
        print(f"{date}: {textwrap.shorten(q['text'], 60)} — {q.get('by', '')}")
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (out / "index.html").write_text(gallery(manifest))

    if args.sheet:
        tiles = [preview(render(q, first, settings)) for q in quotes]
        tw, th = tiles[0].size
        cols = 2
        rows = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * tw + (cols + 1) * 16, rows * th + (rows + 1) * 16), (40, 40, 40))
        for i, t in enumerate(tiles):
            sheet.paste(t, (16 + (i % cols) * (tw + 16), 16 + (i // cols) * (th + 16)))
        sheet.save(out / "sheet.png")
        print(f"sheet: {len(tiles)} quotes -> {out / 'sheet.png'}")


def gallery(manifest):
    """A plain page showing what's coming up, so you can check from your phone."""
    cards = "\n".join(
        f'<figure><img src="{m["date"]}.png" alt=""><figcaption>{m["date"]}</figcaption></figure>'
        for m in manifest)
    return f"""<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Quote Board</title>
<style>
body{{margin:0;padding:16px;background:#222;color:#ccc;font:14px system-ui}}
main{{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(300px,1fr))}}
img{{width:100%;display:block;border-radius:4px}} figure{{margin:0}}
</style>
<main>{cards}</main>
"""


if __name__ == "__main__":
    main()
