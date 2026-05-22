#pragma once
#include <SD_MMC.h>
#include <FS.h>
#include <WiFiClient.h>
#include "esp_camera.h"
#include "cam_config.h"
#include <Arduino.h>

// SD card wiring (1-bit MMC — no conflict with camera or flash LED):
//   GPIO14 → CLK     GPIO15 → CMD     GPIO2 → DATA0

static bool          _sdOK     = false;
static volatile bool _recOn    = false;
static uint32_t      _recStart = 0;
static uint32_t      _lastSave = 0;
static int           _frameN   = 0;
static char          _recDir    [48] = "";   // SD path
static char          _recSession[48] = "";   // key sent to RPi server

bool initSD() {
  if (!SD_MMC.begin("/sdcard", true)) { _sdOK = false; return false; }
  if (SD_MMC.cardType() == CARD_NONE) { _sdOK = false; return false; }
  Serial.printf("SD ready (%llu MB free)\n",
    (SD_MMC.totalBytes() - SD_MMC.usedBytes()) >> 20);
  _sdOK = true;
  return true;
}

bool isSDReady()   { return _sdOK; }
bool isRecording() { return _recOn; }

// ── Upload one JPEG frame to RPi 4 server ────────────────────────────────
#if USE_SERVER
static void pushFrame(camera_fb_t* fb, int n) {
  WiFiClient c;
  if (!c.connect(SERVER_IP, SERVER_PORT)) return;
  c.print("POST /upload?cam="); c.print(CAM_ID);
  c.print("&session=");         c.print(_recSession);
  c.print("&frame=");           c.print(n);
  c.print(" HTTP/1.1\r\nHost: "); c.print(SERVER_IP);
  c.print("\r\nContent-Type: image/jpeg\r\nContent-Length: ");
  c.print((int)fb->len);
  c.print("\r\nConnection: close\r\n\r\n");
  c.write(fb->buf, fb->len);
  uint32_t t = millis();
  while (c.connected() && millis() - t < 800) { while (c.available()) c.read(); delay(1); }
  c.stop();
}
#endif

void startRecording() {
  if (_recOn) return;
  uint32_t ts = millis();
  snprintf(_recSession, sizeof(_recSession), "cam%d_%lu", CAM_ID, ts);
  snprintf(_recDir,     sizeof(_recDir),     "/rec_%lu", ts);
  if (_sdOK) SD_MMC.mkdir(_recDir);
  _recOn = true; _recStart = ts; _frameN = 0;
  Serial.printf("REC start: %s\n", _recSession);
}

void stopRecording() {
  if (!_recOn) return;
  _recOn = false;
  Serial.printf("REC stop: %d frames\n", _frameN);
}

// Called from streaming task — throttled to ~5 fps
void saveFrame(camera_fb_t* fb) {
  if (!_recOn || !fb) return;
  if (millis() - _lastSave < 200) return;
  _lastSave = millis();

#if USE_SERVER
  pushFrame(fb, _frameN);          // primary: send to RPi 4
#endif

  if (_sdOK) {                     // backup (or primary if USE_SERVER=0)
    char p[80];
    snprintf(p, sizeof(p), "%s/%05d.jpg", _recDir, _frameN);
    File f = SD_MMC.open(p, FILE_WRITE);
    if (f) { f.write(fb->buf, fb->len); f.close(); }
  }

  _frameN++;
  if (millis() - _recStart > 30000) stopRecording();  // 30-second clip limit
}

String listLocalRecs() {
  if (!_sdOK) return "[]";
  File root = SD_MMC.open("/");
  if (!root) return "[]";
  String j = "["; bool first = true;
  File e = root.openNextFile();
  while (e) {
    if (e.isDirectory() && strstr(e.name(), "rec_")) {
      if (!first) j += ',';
      j += '"'; j += e.name(); j += '"'; first = false;
    }
    e = root.openNextFile();
  }
  return j + "]";
}
