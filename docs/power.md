# Battery power

The ESP32 board has no battery input or charger, but its power path is simple
(from Waveshare's schematic): USB 5 V → Schottky (D3) → **VDD5V** → two RT9193
3.3 V LDOs (one for the ESP32, one for the panel). A 1S LiPo is enough to drive
those LDOs, so the battery feeds VDD5V directly.

```
LiPo 1S ──► charger/protection ──► switch ──┬──► 1N5817 ──► VDD5V  (board)
 2000mAh    (USB-C, charges here)           │                GND ──► GND
                                            └─ 220k ─┬─ 220k ─ GND
                                                     ├─ 100nF ─ GND
                                                     └──► GPIO35 (battery sense)
```

- **Diode (1N5817 or similar Schottky):** stops the board's USB 5 V from back-feeding the battery when you plug in a cable to flash firmware. It costs ~0.3 V of headroom, which is why the firmware's critical cutoff is 3.4 V.
- **Divider:** two 220 kΩ resistors halve the battery voltage into GPIO35, an ADC1 pin that still works with Wi-Fi on. It draws ~8 µA. Then uncomment `BATTERY_ADC_PIN` in `config.h`.
- **Pads:** per the schematic, VDD5V is pin 19 and GPIO35 is pin 6 of header J3, and GND is J3 pin 14. Check with a multimeter before soldering, because Rev 3 may have moved them.

## The one board mod: kill the power LED

The red PWR LED (LED2, with resistor R2 = 2.2 kΩ, on 3.3 V) draws ~0.6 mA, all the time. That's 3–4× everything else combined while asleep. Desolder R2 (or the LED) or cut its trace.

## Battery life estimate

| | Current | Per day |
|---|---|---|
| Deep sleep: 2× RT9193 quiescent (~90 µA each) + ESP32 + divider | ~0.2 mA | ~4.8 mAh |
| Wake: Wi-Fi + TLS download, ~10 s at ~130 mA | | ~0.4 mAh |
| Refresh: ~35 s at ~45 mA (ESP32 idling while the panel works) | | ~0.4 mAh |
| **Total, LED removed** | | **~5.6 mAh/day** |
| Total, LED left on | | ~21 mAh/day |

A 2000 mAh pack with ~1700 mAh usable above the 3.4 V cutoff lasts **~9–10 months with the LED removed** and ~2.5 months with it on. These are datasheet numbers, so put a meter on it once it's built. Deep sleep is dominated by the LDOs, not the ESP32. That's the next thing to fix if it ever matters.

## What the firmware does

- **Below 3.55 V:** a small battery glyph appears in the top-right corner of the day's quote.
- **Below 3.4 V:** it skips Wi-Fi (the current spike could brown it out), draws a full-screen "charge me" battery, and sleeps with no wake timer. After charging, press **EN**.
- **Wi-Fi down:** retries back off from 30 min to every 6 h so a dead router doesn't drain the pack.

## Parts

| Part | Example | Notes |
|---|---|---|
| LiPo 1S 2000 mAh, with protection circuit, JST-PH | Adafruit 2011 (~60 × 36 × 7 mm) | Fits the 150 × 120 × 12 mm cavity with room to spare |
| USB-C LiPo charger | Adafruit 4410 (Micro-Lipo USB-C), or a protected TP4056 USB-C module | Its USB-C port lines up with the frame's side notch |
| Schottky diode | 1N5817 | |
| Resistors | 2× 220 kΩ, 1× 100 nF ceramic | |
| Slide switch (optional) | SS12D00 | In the battery line; makes flashing and storage safer |
