// Copy to config.h and fill in. config.h is gitignored.
#pragma once

#define WIFI_SSID "your-network"
#define WIFI_PASS "your-password"

// Where the rendered images live. The board fetches <base>/YYYY-MM-DD.bin
// (600x448, 4bpp packed, 134,400 bytes). No trailing slash.
#define IMAGE_BASE_URL "https://jeffkeltner.com/eink-quotes"

// POSIX TZ string. Pacific: "PST8PDT,M3.2.0,M11.1.0"
#define TZ_INFO "PST8PDT,M3.2.0,M11.1.0"

// Local time to wake and refresh each day.
#define WAKE_HOUR 6
#define WAKE_MINUTE 0

// Battery monitoring (optional). Needs a 2x 220k divider from battery+ to GPIO35,
// with 100nF from GPIO35 to GND (docs/power.md). Leave commented out on USB power:
// an unconnected pin reads garbage and would trigger the "charge me" screen.
// #define BATTERY_ADC_PIN 35
#define BATTERY_DIVIDER 2
#define BATTERY_LOW_MV 3550       // show the corner glyph
#define BATTERY_CRITICAL_MV 3400  // stop using Wi-Fi, show "charge me", halt
