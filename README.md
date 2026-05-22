# CCTV-RPi4

A complete, self-hosted DIY CCTV system using **6 ESP32-CAM modules** and a **Raspberry Pi 4 or 5** as a local WiFi hub, recorder and dashboard. No cloud, no subscriptions, no router required.

[![Build Firmware](https://github.com/arnutv/CCTV-RPi4/actions/workflows/build-firmware.yml/badge.svg)](https://github.com/arnutv/CCTV-RPi4/actions/workflows/build-firmware.yml)
![Platform](https://img.shields.io/badge/platform-ESP32--CAM%20%2B%20RPi%204%2F5-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What it does

- **6 wireless cameras** stream MJPEG to a local Raspberry Pi
- **Motion detection** on each ESP32-CAM triggers recording (saves to RPi storage **and** each camera's local SD card simultaneously)
- **Web dashboard** accessible from any phone or laptop — 3×2 live grid, click any camera to enlarge
- **HDMI monitor** mode — Pi shows a fullscreen 3×2 grid directly on a TV (Chromium kiosk on RPi ≥ 2 GB, native pygame on RPi 1 GB)
- **Solar-powered cameras** — each camera runs on a 6V/10W panel + 2× 18650 batteries (~$27 hardware)
- **3D-printed enclosure** — parametric OpenSCAD & FreeCAD designs included
- **Adaptive install** — one script auto-detects RAM and configures the system optimally (LITE / MID / FULL modes)
- **Optional internet bridge** — `connect_router.sh` lets the RPi share your home WiFi or ethernet with the cameras

---

## Architecture

```
   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
   │ ESP32-CAM #1 │   │ ESP32-CAM #2 │   │ ESP32-CAM #N │
   │  + SD card   │   │  + SD card   │   │  + SD card   │
   │  + solar/bat │   │  + solar/bat │   │  + solar/bat │
   └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
          │ MJPEG @ port 81  │                  │
          │ + frame uploads  │                  │
          └─────────┬────────┴──────────────────┘
                    │  WiFi 192.168.4.0/24 (WPA2)
                    ▼
         ┌──────────────────────────┐
         │   Raspberry Pi 4 or 5    │
         │   wlan0 = AP (.4.1)      │
         │   Flask server :8080     │
         │   ├─ /         dashboard │
         │   ├─ /display  HDMI grid │
         │   ├─ /upload   from cams │
         │   └─ /api/cameras …      │
         └──┬──────────────────┬────┘
            │ HDMI             │ optional eth0 / wlan1
            ▼                  ▼
        ┌──────┐          ┌──────────────┐
        │  TV  │          │  Home router │
        └──────┘          │  → Internet  │
                          └──────────────┘
```

---

## Hardware

### Per camera (6× total)

| Item | Spec | ~Cost |
|---|---|---|
| AI-Thinker ESP32-CAM | OV2640 sensor, ESP32-S | $8 |
| MicroSD card | 16-32 GB Class 10 | $8 |
| 6 V 10 W solar panel | 250×200 mm | $9 |
| CN3791 MPPT charger | 1S Li-ion output | $3 |
| 2× 18650 Li-ion | Samsung 30Q or similar (3000 mAh) | $8 |
| MT3608 boost converter | 5 V output | $1 |
| IP65 junction box | 158×90×65 mm | $6 |
| Misc (PG7 gland, lens disc, screws) | | ~$3 |
| **Subtotal per camera** | | **~$46** |

### Hub

| Item | Spec | ~Cost |
|---|---|---|
| Raspberry Pi 4 (1 GB+) or RPi 5 (2 GB+) | | $35-50 |
| Power supply | 5V/3A USB-C (Pi 4) or 5V/5A (Pi 5) | $8-13 |
| MicroSD (or USB SSD) | 32 GB+ for OS + recordings | $8 |
| Active cooler | RPi 5 only | $5 |
| micro-HDMI cable | optional, for TV display | $5 |

**Total system cost: ~$330 for 6 cameras + hub.**

---

## Quick start

### 1. Raspberry Pi setup (15 min)

Flash **Raspberry Pi OS 64-bit (Bookworm)** to your SD card with Raspberry Pi Imager. Set hostname, enable SSH, configure your wifi for first-time access.

SSH in and run:

```bash
git clone https://github.com/arnutv/CCTV-RPi4.git
cd CCTV-RPi4/rpi4
sudo bash install.sh
sudo reboot
```

The installer **auto-detects** your board and RAM, then chooses:

| Mode | Trigger | What runs |
|---|---|---|
| **LITE** | RAM < 1.5 GB | Headless, native pygame HDMI display, `gpu_mem=32` |
| **MID** | RAM 1.5-3 GB | Chromium kiosk (trimmed), `gpu_mem=64` |
| **FULL** | RAM ≥ 4 GB | Full Chromium kiosk, `gpu_mem=128` |

After reboot:
- WiFi network **`CCTV_Network`** (pass: `cctv1234!!`) — cameras join this
- Dashboard at **`http://192.168.4.1:8080/`** from phone or laptop
- HDMI shows the 3×2 grid automatically (if connected)

### 2. Flash the cameras (5 min each)

For each ESP32-CAM, edit `CCTV-Camera/cam_config.h` to set its ID and name:

```cpp
#define CAM_ID   1                  // 1-6, unique per camera
#define CAM_NAME "Front Door"       // shown in dashboard
```

Open `CCTV-Camera/CCTV-Camera.ino` in Arduino IDE:
- Board: **AI Thinker ESP32-CAM**
- ESP32 core: **1.0.6** (pinned for stability)
- Partition: **Huge APP (3MB No OTA / 1MB SPIFFS)**

Flash with a USB-to-serial adapter (GPIO0 to GND while pressing reset).

> **Tip:** the included [GitHub Actions workflow](.github/workflows/build-firmware.yml) builds the firmware in the cloud — no Arduino IDE needed. Just go to the Actions tab → "Build ESP32-CAM Firmware" → Run workflow, fill in the cam ID/name, and download the `.bin` from the artifacts.

### 3. Power & mount the cameras

Connect each camera to its solar panel + 18650 battery rig (see `enclosure/wiring.txt`). Power on — the camera auto-connects to `CCTV_Network`, gets its static IP (`192.168.4.10X` based on `CAM_ID`), and appears live on the dashboard.

---

## Web dashboard

Browse to `http://192.168.4.1:8080/` from any device on the CCTV WiFi:

- **3×2 live grid** of all cameras with status pills (LIVE / MOTION / OFFLINE)
- **Click any camera** to enlarge to a large modal with live feed, battery %, and snapshot/page buttons
- **Recordings browser** with per-camera tabs, frame-by-frame playback, save individual frames
- **Storage chips** show RPi disk free + estimated days of retention left + auto-cleanup setting
- **One-click cleanup** button to flush recordings older than the retention period (default 30 days)
- **System health** in the header: CPU temp, uptime, internet IP (if connected), disk bar

---

## HDMI display

Plug an HDMI monitor or TV into the RPi (micro-HDMI to HDMI cable for RPi 4/5).

| Mode | Renderer | RAM cost | Notes |
|---|---|---|---|
| **LITE** | `display.py` — pygame on KMSDRM | ~80 MB | Auto-installed by `install.sh` on 1 GB boards; no X server, no browser |
| **MID/FULL** | Chromium kiosk → `/display` | ~500 MB | Same look as the web dashboard, GPU-accelerated |

Exit display: `Esc` or `Q` on a keyboard, or `sudo systemctl stop cctv-display`.

---

## Optional: internet bridge

By default the RPi is an island — cameras can talk to it but not to the internet. To bridge:

```bash
# Via ethernet (cleanest)
sudo bash rpi4/connect_router.sh eth

# Via USB WiFi dongle
sudo bash rpi4/connect_router.sh wifi "HomeWiFi" "yourpassword"

# Undo
sudo bash rpi4/connect_router.sh --remove
```

Now the dashboard is also reachable from your home network (look for the IP in the dashboard header), and you can SSH in from anywhere on your LAN.

---

## Enclosure & 3D printing

Two formats provided in `enclosure/`:

- **`cctv_enclosure.scad`** — OpenSCAD parametric source (5 parts)
- **`cctv_enclosure.FCMacro`** — FreeCAD Python macro (same 5 parts)

Designed to drop inside a **140 × 78 mm outer IP65 junction box** (typical thai weatherproof box). The lens hole and ESP32-CAM mount are drilled directly through the box's own lid.

Parts (3D-printed):

| Part | Print time | Filament | Purpose |
|---|---|---|---|
| Electronics tray | 90 min | 28 g | Organises battery + MPPT + boost inside the IP65 box |
| Wall mount | 45 min | 18 g | Wall plate + ball stalk for camera box mounting |
| Box socket | 30 min | 12 g | Snaps onto wall mount's ball, sticks to back of box (VHB tape or M3) |
| Solar bracket | 60 min | 22 g | Wall L-arm + ball stalk for solar panel mounting |
| Panel socket | 30 min | 14 g | Snaps onto solar bracket's ball, bolts to solar panel frame |

Each ball-joint pair (wall_mount + box_socket, solar_bracket + panel_socket) gives **free aiming in any direction**, locked with a single M3 clamp screw.

**Print in PETG** (or ASA) at 0.2 mm, 4 perimeters, 25 % gyroid infill. No supports needed.

See `enclosure/wiring.txt` for the full assembly + waterproofing checklist.

---

## File layout

```
CCTV-RPi4/
├── CCTV-Camera/                 # Arduino sketch (flash this to each ESP32-CAM)
│   ├── CCTV-Camera.ino
│   ├── cam_config.h            # ← Edit CAM_ID and CAM_NAME per unit
│   ├── camera_pins.h
│   ├── motion.h
│   ├── power.h
│   ├── recorder.h
│   └── webui.h
├── rpi4/                        # Raspberry Pi server side
│   ├── install.sh              # One-shot setup (auto-adaptive LITE/MID/FULL)
│   ├── cctv_server.py          # Flask dashboard + upload endpoint
│   ├── display.py              # Native pygame HDMI display (LITE mode)
│   └── connect_router.sh       # Optional internet bridge
├── preview/                     # Browser preview of the dashboard (Windows PC)
│   ├── index.html              # Static mock dashboard
│   └── serve.ps1               # Tiny PowerShell HTTP server
├── enclosure/                   # 3D-printable parts
│   ├── cctv_enclosure.scad     # OpenSCAD parametric source
│   ├── cctv_enclosure.FCMacro  # FreeCAD Python macro
│   └── wiring.txt              # ASCII wiring + waterproofing notes
├── .github/workflows/
│   └── build-firmware.yml      # Cloud-builds ESP32 firmware, exports .bin
├── .gitignore
└── README.md
```

---

## Configuration cheatsheet

| What | Where | Default |
|---|---|---|
| WiFi SSID + password | `CCTV-Camera/cam_config.h` + `rpi4/install.sh` | `CCTV_Network` / `cctv1234!!` |
| Camera ID + name | `CCTV-Camera/cam_config.h` per unit | `CAM_ID 1`, `"Front Door"` |
| RPi static IP for AP | `rpi4/install.sh` | `192.168.4.1` |
| Recording retention | `rpi4/cctv_server.py` → `RETENTION_DAYS` | `30` days |
| Frame resolution | inside `CCTV-Camera.ino`: `s->set_framesize()` | `FRAMESIZE_VGA` |
| GPU memory | auto via install.sh | 32/64/128 MB |
| Server port | `rpi4/cctv_server.py` | `8080` |
| Cameras list (for dashboard) | `rpi4/cctv_server.py` → `CAMERAS` | 6 entries, edit to add/remove |

---

## Performance

Measured with **6 cameras at VGA 5 FPS, motion-triggered recording**:

| Board | Boot | CPU idle | CPU peak | RAM used | Smoothness |
|---|---|---|---|---|---|
| RPi 4 1 GB | ~25 s | 4 % | 35-45 % | ~600 MB | Adequate |
| RPi 4 2/4/8 GB | ~22 s | 3 % | 25-35 % | ~600 MB | Smooth |
| RPi 5 (2/4/8 GB) | ~12 s | 1-2 % | 12-18 % | ~700 MB | Snappy |

Cameras can scale up to **~12 units** before grid cells become too small to read on a 32" TV.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Camera shows OFFLINE in dashboard | Bad wifi / wrong CAM_ID | Re-flash with correct config; check serial output |
| Dashboard slow / laggy | Too many concurrent viewers | Max 2-3 phones streaming full grid; close extras |
| Recordings folder filling disk | Retention too long | Lower `RETENTION_DAYS` and run "Clean now" |
| HDMI black on RPi 5 1 GB | Chromium ran out of memory | Confirm install picked LITE mode; check `systemctl status cctv-display` |
| Solar camera dies overnight | Cloudy days drained battery | Upsize to 12 V 20 W panel + LiFePO4 (see `wiring.txt` "Robust tier") |
| Lens fogged from inside | Trapped condensation | Add a PTFE breathable vent on the bottom of the IP65 box |

---

## Contributing

PRs welcome. Run the cloud build (Actions tab) before opening a PR to confirm the firmware still compiles.

---

## License

MIT — see [LICENSE](LICENSE) if present, otherwise consider this MIT-licensed.

---

## Credits

Built with `esp32-arduino`, `esp_camera`, `Flask`, `pygame`, `hostapd`, `dnsmasq` and a Raspberry Pi.
