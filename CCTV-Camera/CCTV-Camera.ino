/*
 * CCTV-Camera — ESP32-CAM Node Firmware
 * ═══════════════════════════════════════════════════════════════════════════
 * Board  : AI-Thinker ESP32-CAM
 * Core   : esp32 by Espressif ≤ 1.0.6
 *
 * Before flashing each camera:
 *   → Open cam_config.h
 *   → Set CAM_ID (1–5) and CAM_NAME
 *   → Everything else (WiFi, server IP) stays the same
 *
 * Hardware wiring
 * ───────────────
 * SD card (1-bit MMC, no conflict with camera or flash LED)
 *   GPIO14 → CLK     GPIO15 → CMD     GPIO2 → DATA0
 *
 * Battery monitor (18650 via TP4056 solar charger)
 *   Batt+ → 100kΩ → GPIO33 → 100kΩ → GND
 *   GPIO33 = ADC1_CH5, works while WiFi active
 *
 * Network ports (per camera)
 * ──────────────────────────
 *   http://192.168.4.10x/        Per-camera debug UI
 *   http://192.168.4.10x:81/     MJPEG stream (consumed by RPi dashboard)
 *   http://192.168.4.10x/status  JSON status (polled by RPi dashboard)
 * ═══════════════════════════════════════════════════════════════════════════
 */

#include "cam_config.h"
#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>
#include "camera_pins.h"
#include "power.h"
#include "motion.h"
#include "recorder.h"
#include "webui.h"

WebServer  apiServer(80);
WiFiServer streamServer(81);

static void streamTask(void*) {
  for (;;) {
    WiFiClient c = streamServer.available();
    if (c) handleStreamClient(c);
    delay(10);
  }
}

void setup() {
  Serial.begin(115200);
  Serial.printf("\nCCTV-Camera %d (%s) starting...\n", CAM_ID, CAM_NAME);

  // Camera
  camera_config_t cfg = getCameraConfig();
  if (esp_camera_init(&cfg) != ESP_OK) {
    Serial.println("ERROR: camera init failed — check board selection");
    while (1) delay(1000);
  }

  // SD card (optional backup)
  if (!initSD()) Serial.println("No SD card — RPi-only recording");

  // Battery ADC
  initPower();

  // Connect to Raspberry Pi Access Point
  WiFi.mode(WIFI_STA);
  WiFi.config(CAM_STATIC_IP, CAM_GATEWAY, CAM_SUBNET, CAM_DNS);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.printf("Connecting to %s as 192.168.4.%d", WIFI_SSID, 100 + CAM_ID);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - t0 > 20000) { Serial.println("\nTimeout — restarting"); ESP.restart(); }
    Serial.print('.'); delay(500);
  }
  Serial.printf("\nOnline: http://%s\n", WiFi.localIP().toString().c_str());

  // Start servers
  setupWebServer(apiServer);
  apiServer.begin();
  streamServer.begin();

  // MJPEG stream runs on Core 0 (alongside WiFi stack)
  // API server + motion detection handle on Core 1 (loop)
  xTaskCreatePinnedToCore(streamTask, "stream", 8192, nullptr, 5, nullptr, 0);

  Serial.println("Ready.");
}

void loop() {
  apiServer.handleClient();
  updatePower();
  delay(5);
}
