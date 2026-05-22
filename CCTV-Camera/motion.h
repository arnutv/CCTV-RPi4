#pragma once
#include "esp_camera.h"
#include <Arduino.h>

// Frame-differencing motion detection.
// Samples 500 byte positions across consecutive JPEG buffers.
// No format switching or frame decoding required.

static volatile bool _motOn   = true;
static volatile int  _motThr  = 15;   // % of samples that must differ
static volatile bool _motSeen = false;
static uint32_t      _motTime = 0;
static uint8_t*      _prev    = nullptr;
static size_t        _prevLen = 0;
static uint32_t      _prevUpd = 0;

bool checkMotion(camera_fb_t* fb) {
  if (!_motOn || !fb) return false;
  bool motion = false;

  if (_prev && _prevLen > 0) {
    size_t len  = min(fb->len, _prevLen);
    int    step = max(1, (int)(len / 500));
    int    diff = 0, total = 0;
    for (size_t i = 0; i < len; i += step) {
      if (abs((int)fb->buf[i] - (int)_prev[i]) > 15) diff++;
      total++;
    }
    motion = total > 0 && (diff * 100 / total) > _motThr;
  }

  if (millis() - _prevUpd > 500) {
    _prevUpd = millis();
    if (_prevLen != fb->len) { free(_prev); _prev = (uint8_t*)malloc(fb->len); _prevLen = _prev ? fb->len : 0; }
    if (_prev) memcpy(_prev, fb->buf, _prevLen);
  }

  if (motion)                             { _motSeen = true;  _motTime = millis(); }
  else if (millis() - _motTime > 5000)    { _motSeen = false; }
  return motion;
}

bool isMotionSeen()       { return _motSeen; }
void setMotionOn(bool en) { _motOn  = en; }
void setMotionThr(int t)  { _motThr = constrain(t, 5, 50); }
bool getMotionOn()        { return _motOn; }
int  getMotionThr()       { return _motThr; }
