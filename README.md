# E-ink Quote Board

A 5.65" 7-color e-ink display that shows a new quote every morning.

```
quotes.yaml ──push──▶ GitHub Action ──▶ GitHub Pages ◀──6am daily── ESP32 ──▶ panel
 (edit here)          render/render.py   YYYY-MM-DD.bin    (Wi-Fi)    deep sleep
                      renders 7 days     + previews
```

**Why it's split this way:** the layout code is all Python on the Mac/CI side, where fonts, previews and iteration are easy. The ESP32 just downloads 134,400 bytes and streams them to the panel. Design changes never need a reflash. Rendering a week ahead means a late or skipped GitHub cron run doesn't matter.

## Adding quotes

Edit `quotes.yaml` (the GitHub web editor works from a phone), commit, done. See the comment at the top of the file for fields: `kind: poem | word`, `date: "MM-DD"` pins an entry to a day each year, `accent` overrides the color.

## Designing

```sh
python3 -m venv .venv && .venv/bin/pip install -r render/requirements.txt
.venv/bin/python render/render.py --days 7 --sheet   # out/sheet.png shows every quote
```

Previews use the panel's real muted pigment colors, so they're a fair guess at the look. Verify on the glass before trusting them.

## Firmware

```sh
.venv/bin/pip install platformio
cd firmware
cp include/config.example.h include/config.h   # Wi-Fi + Pages URL
../.venv/bin/pio run -e bringup -t upload -t monitor   # color bars first
../.venv/bin/pio run -e quotes  -t upload -t monitor
```

Press **EN** on the board to force a refresh. Hardware notes and gotchas (especially the **A/B switch → B**) are in [docs/hardware.md](docs/hardware.md).

## Publishing

Repo: <https://github.com/jkeltner/eink-quotes>. GitHub Pages serves it at
<https://jeffkeltner.com/eink-quotes/> (inherited from the custom domain on
jkeltner.github.io), which shows the upcoming week. The `render` workflow runs
on every push to `quotes.yaml` or `render/`, nightly, and on demand from the
Actions tab.

## Layout

```
quotes.yaml            the content
render/render.py       quote → panel image (+ previews, gallery)
render/fonts/          Source Serif 4, Inter, Fraunces (OFL)
firmware/              PlatformIO project for the ESP32 driver board
docs/hardware.md       part IDs, hookup, bring-up
docs/power.md          battery wiring, board mod, battery life
docs/enclosure.md      laser-cut desk frame: design + assembly
enclosure/frame.py     parametric frame generator → enclosure/svg/
docs/img/              photos of the hardware
```
