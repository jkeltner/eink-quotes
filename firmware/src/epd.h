// Minimal driver for the Waveshare 5.65" (F) 7-color ACeP panel (AC057TC1, UC8159-class).
// Command sequence follows Waveshare's epd5in65f reference driver; the difference is
// that pixel data is streamed in (begin/write/end) so we never hold a 134 KB frame in RAM.
#pragma once
#include <Arduino.h>

namespace epd {

constexpr int WIDTH = 600;
constexpr int HEIGHT = 448;
constexpr size_t FRAME_BYTES = WIDTH * HEIGHT / 2;  // 4 bits per pixel

enum Color : uint8_t { BLACK, WHITE, GREEN, BLUE, RED, YELLOW, ORANGE };

// Waveshare ESP32 driver board pins.
constexpr int PIN_SCK = 13, PIN_MOSI = 14, PIN_CS = 15, PIN_DC = 27, PIN_RST = 26, PIN_BUSY = 25;

bool init();                               // reset + configure; false if the panel never answers
void beginFrame();                         // start sending pixel data
void write(const uint8_t *data, size_t n); // packed bytes, high nibble = left pixel
bool refresh();                            // show what was sent (~30 s, the panel flashes)
void sleep();                              // deep sleep; ALWAYS call this after a refresh

}  // namespace epd
