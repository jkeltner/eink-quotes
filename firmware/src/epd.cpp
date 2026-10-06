#include "epd.h"

#include <SPI.h>

namespace epd {

static SPIClass spi(HSPI);
static const SPISettings kSpi(4000000, MSBFIRST, SPI_MODE0);

static void command(uint8_t c) {
  digitalWrite(PIN_DC, LOW);
  digitalWrite(PIN_CS, LOW);
  spi.beginTransaction(kSpi);
  spi.transfer(c);
  spi.endTransaction();
  digitalWrite(PIN_CS, HIGH);
}

static void data(const uint8_t *d, size_t n) {
  digitalWrite(PIN_DC, HIGH);
  digitalWrite(PIN_CS, LOW);
  spi.beginTransaction(kSpi);
  spi.writeBytes(d, n);
  spi.endTransaction();
  digitalWrite(PIN_CS, HIGH);
}

static void cmd(uint8_t c, std::initializer_list<uint8_t> args = {}) {
  command(c);
  if (args.size()) data(args.begin(), args.size());
}

// BUSY is active-low on this panel. Wait for it to reach `level`, with a timeout
// so a disconnected panel can't hang us awake forever.
static bool waitBusy(int level, uint32_t timeoutMs = 60000) {
  uint32_t start = millis();
  while (digitalRead(PIN_BUSY) != level) {
    if (millis() - start > timeoutMs) {
      Serial.printf("epd: BUSY stuck (wanted %d) after %lu ms\n", level, timeoutMs);
      return false;
    }
    delay(10);
  }
  return true;
}

bool init() {
  pinMode(PIN_CS, OUTPUT);
  pinMode(PIN_DC, OUTPUT);
  pinMode(PIN_RST, OUTPUT);
  pinMode(PIN_BUSY, INPUT);
  digitalWrite(PIN_CS, HIGH);
  spi.begin(PIN_SCK, -1, PIN_MOSI, PIN_CS);

  digitalWrite(PIN_RST, LOW);
  delay(1);
  digitalWrite(PIN_RST, HIGH);
  delay(200);
  if (!waitBusy(HIGH, 5000)) return false;

  cmd(0x00, {0xEF, 0x08});              // panel setting
  cmd(0x01, {0x37, 0x00, 0x23, 0x23});  // power setting
  cmd(0x03, {0x00});                    // power off sequence
  cmd(0x06, {0xC7, 0xC7, 0x1D});        // booster soft start
  cmd(0x30, {0x3C});                    // PLL
  cmd(0x41, {0x00});                    // temperature sensor
  cmd(0x50, {0x37});                    // VCOM / data interval
  cmd(0x60, {0x22});                    // TCON
  cmd(0x61, {0x02, 0x58, 0x01, 0xC0});  // resolution 600x448
  cmd(0xE3, {0xAA});
  delay(100);
  cmd(0x50, {0x37});
  return true;
}

void beginFrame() {
  cmd(0x61, {0x02, 0x58, 0x01, 0xC0});
  command(0x10);  // data start transmission
}

void write(const uint8_t *d, size_t n) { data(d, n); }

bool refresh() {
  cmd(0x04);  // power on
  bool ok = waitBusy(HIGH);
  cmd(0x12);  // display refresh
  ok = waitBusy(HIGH) && ok;
  cmd(0x02);  // power off
  waitBusy(LOW, 5000);  // Waveshare waits for BUSY to drop here; don't fail on it

  delay(200);
  return ok;
}

void sleep() {
  delay(100);
  cmd(0x07, {0xA5});
  delay(100);
  digitalWrite(PIN_RST, LOW);
}

}  // namespace epd
