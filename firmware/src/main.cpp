// E-ink quote board.
//
// Each wake: join Wi-Fi, set the clock, download <date>.bin and stream it straight
// to the panel, refresh, then deep-sleep until WAKE_HOUR tomorrow. All layout work
// happens in render/render.py; this side just moves bytes.
//
// Press EN (reset) to force a refresh right now.
//
// On battery (see docs/power.md): a small red battery glyph appears in the corner
// when it's time to charge, and below the critical level the board draws a
// "charge me" screen without touching Wi-Fi and sleeps until reset.

#include <Arduino.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <time.h>

#include "epd.h"

#ifdef BRINGUP

// Seven color bands, no network. If this works, wiring + switch are right.
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("bringup: init");
  if (!epd::init()) {
    Serial.println("bringup: panel never released BUSY. Check the FPC seating and that the "
                   "Display Config switch is on B.");
    return;
  }
  epd::beginFrame();
  uint8_t row[epd::WIDTH / 2];
  for (int y = 0; y < epd::HEIGHT; y++) {
    uint8_t c = y * 7 / epd::HEIGHT;
    memset(row, (c << 4) | c, sizeof row);
    epd::write(row, sizeof row);
  }
  Serial.println("bringup: refreshing (~30 s, it will flash)");
  Serial.println(epd::refresh() ? "bringup: done" : "bringup: refresh timed out");
  epd::sleep();
}
void loop() {}

#else

#include "config.h"

// RTC memory survives deep sleep, not power loss.
RTC_DATA_ATTR char lastEtag[64] = "";
RTC_DATA_ATTR uint8_t failures = 0;

// ---------------------------------------------------------------- battery

#ifdef BATTERY_ADC_PIN
static int batteryMv() {
  analogReadMilliVolts(BATTERY_ADC_PIN);  // first read after wake is noisy
  uint32_t sum = 0;
  for (int i = 0; i < 16; i++) sum += analogReadMilliVolts(BATTERY_ADC_PIN);
  return sum / 16 * BATTERY_DIVIDER;
}
#else
static int batteryMv() { return 0; }  // no divider fitted: battery features off
#endif

// Low-battery glyph: a small battery outline with a red sliver, drawn into the
// panel's top-right corner by patching bytes as they stream past.
constexpr int GLYPH_X = 560, GLYPH_Y = 14, GLYPH_W = 24, GLYPH_H = 12;

static int glyphPixel(int x, int y) {
  int gx = x - GLYPH_X, gy = y - GLYPH_Y;
  if (gx < 0 || gy < 0 || gx >= GLYPH_W + 3 || gy >= GLYPH_H) return -1;
  if (gx >= GLYPH_W) return (gy >= 3 && gy < GLYPH_H - 3) ? epd::BLACK : -1;  // nub
  bool edge = gx < 2 || gy < 2 || gx >= GLYPH_W - 2 || gy >= GLYPH_H - 2;
  if (edge) return epd::BLACK;
  return (gx >= 4 && gx < 8 && gy >= 4 && gy < GLYPH_H - 4) ? epd::RED : epd::WHITE;
}

// Patch a chunk of the streamed frame. `offset` is the byte index of buf[0].
static void overlayGlyph(uint8_t *buf, size_t n, size_t offset) {
  for (size_t i = 0; i < n; i++) {
    size_t px = (offset + i) * 2;
    int y = px / epd::WIDTH, x = px % epd::WIDTH;
    if (y < GLYPH_Y || y >= GLYPH_Y + GLYPH_H) continue;
    int hi = glyphPixel(x, y), lo = glyphPixel(x + 1, y);
    if (hi >= 0) buf[i] = (buf[i] & 0x0F) | (hi << 4);
    if (lo >= 0) buf[i] = (buf[i] & 0xF0) | lo;
  }
}

// Battery critical: big outlined battery in the middle of a white screen, then
// sleep with no timer. Pressing EN (or plugging in USB) starts over.
static void drawChargeMeAndHalt() {
  Serial.println("battery critical: drawing charge screen, halting");
  if (epd::init()) {
    epd::beginFrame();
    const int bw = 160, bh = 80, bx = (epd::WIDTH - bw) / 2, by = (epd::HEIGHT - bh) / 2;
    uint8_t row[epd::WIDTH / 2];
    for (int y = 0; y < epd::HEIGHT; y++) {
      for (int x = 0; x < epd::WIDTH; x += 2) {
        uint8_t c[2];
        for (int k = 0; k < 2; k++) {
          int gx = x + k - bx, gy = y - by;
          bool body = gx >= 0 && gx < bw && gy >= 0 && gy < bh;
          bool nub = gx >= bw && gx < bw + 12 && gy >= bh / 4 && gy < bh * 3 / 4;
          bool wall = body && (gx < 8 || gy < 8 || gx >= bw - 8 || gy >= bh - 8);
          bool fill = body && gx >= 16 && gx < 36 && gy >= 16 && gy < bh - 16;
          c[k] = (wall || nub) ? epd::BLACK : fill ? epd::RED : epd::WHITE;
        }
        row[x / 2] = (c[0] << 4) | c[1];
      }
      epd::write(row, sizeof row);
    }
    epd::refresh();
    epd::sleep();
  }
  esp_deep_sleep_start();  // no wake source: stays off until reset
}

// ---------------------------------------------------------------- network

static void sleepFor(uint64_t seconds) {
  Serial.printf("sleeping %llu s\n", seconds);
  Serial.flush();
  esp_sleep_enable_timer_wakeup(seconds * 1000000ULL);
  esp_deep_sleep_start();
}

static bool connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(500);
  Serial.printf("wifi: %s\n", WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString().c_str() : "failed");
  return WiFi.status() == WL_CONNECTED;
}

static bool syncClock() {
  configTzTime(TZ_INFO, "pool.ntp.org", "time.google.com");
  struct tm now;
  return getLocalTime(&now, 15000);
}

// Seconds from now until the next WAKE_HOUR:WAKE_MINUTE local time.
static uint64_t secondsUntilWake() {
  time_t now = time(nullptr);
  struct tm t;
  localtime_r(&now, &t);
  t.tm_hour = WAKE_HOUR;
  t.tm_min = WAKE_MINUTE;
  t.tm_sec = 0;
  time_t next = mktime(&t);
  if (next <= now + 60) {
    t.tm_mday += 1;
    t.tm_isdst = -1;  // let mktime work out DST for tomorrow
    next = mktime(&t);
  }
  return next - now;
}

enum class Result { Updated, Unchanged, Failed };

static Result fetchAndDraw(bool force, bool lowBattery) {
  WiFiClientSecure tls;
  tls.setInsecure();  // public, non-sensitive content; skips managing a CA bundle
  // Images are rendered a week ahead, so a late GitHub cron run never matters.
  char url[200];
  time_t now = time(nullptr);
  struct tm t;
  localtime_r(&now, &t);
  snprintf(url, sizeof url, "%s/%04d-%02d-%02d.bin", IMAGE_BASE_URL, t.tm_year + 1900, t.tm_mon + 1, t.tm_mday);
  Serial.printf("http: GET %s\n", url);
  HTTPClient http;
  http.begin(tls, url);
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  const char *keep[] = {"ETag"};
  http.collectHeaders(keep, 1);
  if (!force && lastEtag[0]) http.addHeader("If-None-Match", lastEtag);

  int code = http.GET();
  Serial.printf("http: %d\n", code);
  if (code == HTTP_CODE_NOT_MODIFIED) return Result::Unchanged;
  if (code != HTTP_CODE_OK || http.getSize() != (int)epd::FRAME_BYTES) {
    Serial.printf("http: bad response (size %d)\n", http.getSize());
    return Result::Failed;
  }

  String etag = http.header("ETag");
  if (!epd::init()) return Result::Failed;
  // Stream network -> panel RAM. If the download dies halfway we just skip the
  // refresh: the old image stays on screen and the half frame is never shown.
  epd::beginFrame();
  WiFiClient *stream = http.getStreamPtr();
  uint8_t buf[1024];
  size_t got = 0;
  uint32_t lastData = millis();
  while (got < epd::FRAME_BYTES && millis() - lastData < 10000) {
    size_t n = stream->readBytes(buf, min(sizeof buf, epd::FRAME_BYTES - got));
    if (n) {
      if (lowBattery) overlayGlyph(buf, n, got);
      epd::write(buf, n);
      got += n;
      lastData = millis();
    }
  }
  http.end();
  if (got != epd::FRAME_BYTES) {
    Serial.printf("http: short read %u/%u\n", got, epd::FRAME_BYTES);
    epd::sleep();
    return Result::Failed;
  }

  Serial.println("epd: refreshing");
  bool ok = epd::refresh();
  epd::sleep();  // never leave the panel powered: high voltage damages ACeP glass
  // A low-battery frame shouldn't count as "already showing this image".
  strlcpy(lastEtag, lowBattery ? "" : etag.c_str(), sizeof lastEtag);
  return ok ? Result::Updated : Result::Failed;
}

// Retry backoff after failures: 30 min, 1 h, 2 h, 4 h, then every 6 h.
// Keeps a dead router from draining the battery.
static uint64_t retryDelay() {
  static const uint16_t minutes[] = {30, 60, 120, 240, 360};
  uint8_t i = failures < 5 ? failures : 4;
  failures = failures < 255 ? failures + 1 : failures;
  return minutes[i] * 60ULL;
}

void setup() {
  Serial.begin(115200);
  delay(200);
  // Timer wake = scheduled refresh. Anything else (power-on, EN button) = force.
  bool force = esp_sleep_get_wakeup_cause() != ESP_SLEEP_WAKEUP_TIMER;

  int mv = batteryMv();
  Serial.printf("battery: %d mV\n", mv);
#ifdef BATTERY_ADC_PIN
  if (mv < BATTERY_CRITICAL_MV) drawChargeMeAndHalt();
#endif
  bool low = mv && mv < BATTERY_LOW_MV;

  if (!connectWifi()) sleepFor(retryDelay());
  if (!syncClock()) sleepFor(retryDelay());

  Result r = fetchAndDraw(force, low);
  Serial.printf("result: %s\n", r == Result::Updated ? "updated" : r == Result::Unchanged ? "unchanged" : "failed");
  WiFi.disconnect(true);

  // The deep-sleep timer runs off an RC oscillator and can drift a few percent,
  // so every wake re-syncs NTP and re-aims at tomorrow's slot.
  if (r == Result::Failed) sleepFor(retryDelay());
  failures = 0;
  sleepFor(secondsUntilWake());
}

void loop() {}

#endif
