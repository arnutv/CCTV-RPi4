#pragma once
#include <Arduino.h>

// Battery monitor wiring:
//   Battery+ → 100kΩ → GPIO33 → 100kΩ → GND
//   GPIO33 = ADC1_CH5 — reads correctly while WiFi is active
//   Vbat = Vadc × 2  (18650 range: 3.0 V empty → 4.2 V full)

#define BATT_PIN 33

static float    _battV   = 3.7f;
static int      _battPct = 50;
static uint32_t _battT   = 0;

void initPower() {
  analogSetAttenuation(ADC_11db);
  analogSetPinAttenuation(BATT_PIN, ADC_11db);
}

void updatePower() {
  if (millis() - _battT < 30000) return;
  _battT = millis();
  uint32_t s = 0;
  for (int i = 0; i < 16; i++) s += analogRead(BATT_PIN);
  _battV   = (s / 16.0f / 4095.0f * 3.3f) * 2.0f;
  _battPct = constrain((int)((_battV - 3.0f) / 1.2f * 100.0f), 0, 100);
}

float getBattV()   { return _battV;   }
int   getBattPct() { return _battPct; }
