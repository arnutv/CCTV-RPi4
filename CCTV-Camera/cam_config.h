#pragma once
#include <IPAddress.h>

// ═══════════════════════════════════════════════════════════════════════════
//  CCTV-Camera — per-camera configuration
//  Only edit CAM_ID and CAM_NAME before flashing each unit.
//  Everything else stays the same across all cameras.
// ═══════════════════════════════════════════════════════════════════════════

#define CAM_ID   1              // 1–6, unique per camera
#define CAM_NAME "Front Door"   // shown in dashboard and recordings

// WiFi — must match AP settings in rpi4/install.sh
#define WIFI_SSID     "CCTV_Network"
#define WIFI_PASSWORD "cctv1234!!"

// Raspberry Pi 4 / 5 server
#define SERVER_IP   "192.168.4.1"
#define SERVER_PORT 8080
#define USE_SERVER  1   // 1 = send frames to RPi (+ SD backup if card present)
                        // 0 = SD card only (no RPi upload)

// ── Frame size — pick based on your RPi's RAM ────────────────────────────
// VGA  (640×480) ≈ 25 KB/frame  → default, sharp. Use on RPi ≥ 2 GB.
// CIF  (352×288) ≈ 15 KB/frame  → ~40% less RAM, still clear.
// QVGA (320×240) ≈ 10 KB/frame  → recommended for RPi 5 / RPi 4 with 1 GB.
// Edit FRAMESIZE_* inside CCTV-Camera.ino — search for `s->set_framesize`.

// ── Static IP (auto-derived from CAM_ID, no router config needed) ─────────
//   CAM 1 → 192.168.4.101    CAM 4 → 192.168.4.104
//   CAM 2 → 192.168.4.102    CAM 5 → 192.168.4.105
//   CAM 3 → 192.168.4.103    CAM 6 → 192.168.4.106
static const IPAddress CAM_STATIC_IP(192, 168, 4, 100 + CAM_ID);
static const IPAddress CAM_GATEWAY  (192, 168, 4, 1);
static const IPAddress CAM_SUBNET   (255, 255, 255, 0);
static const IPAddress CAM_DNS      (192, 168, 4, 1);
