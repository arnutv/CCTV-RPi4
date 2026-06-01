# CCTV_NodeV2 — PCB routing guide

The schematic (`CCTV_NodeV2.kicad_sch`) and the PCB (`CCTV_NodeV2.kicad_pcb`) are both checked in. The PCB has all 9 components placed on a 100 × 80 mm 2-layer board with **every net assigned to its correct pad**. What's missing are the **copper traces** — the colored airwires you see in pcbnew.

KiCad 10 ships **without a built-in autorouter**. You have two routes from "ratsnest" to "fully routed board":

| Path | Time | Quality | Effort |
|---|---|---|---|
| **A. Interactive routing in pcbnew** | 15–30 min | excellent | manual, learn the X tool |
| **B. Freerouting (external)** | 2–5 min | good, sometimes messy | one-time download |

---

## A. Interactive routing (recommended for small boards)

1. Open `KiCad/CCTV_NodeV2.kicad_pcb` in KiCad → pcbnew opens.
2. Press **`B`** to refresh the ratsnest — colored thin lines now connect pads that share a net.
3. Press **`X`** to start the **interactive router**.
4. Click a pad (or hover over a ratsnest line and click), drag, and click again to lay each segment. Press **`V`** to drop a via to the other copper layer when you need to cross a trace.
5. Press **`Esc`** to finish a route, then click the next net.
6. When all airwires are gone you're done. **Run DRC** (`Inspect → Design Rules Checker`) to catch any clearance issues.

Order I'd recommend:
- **Power first** (`+5V`, `+3V3`, `BATT+`, `GND`, `SOLAR+/-`, `BATT-`, `PROT-` — wait, this PCB consolidates to `GND`)
- **Camera control** next (`SIOC`, `SIOD`, `VSYNC`, `HREF`, `PCLK`, `XCLK`)
- **Camera data bus last** (`CAM_D0..D7`) — these are the 8 lines that run from U4 right side to U5 right side; expect to use a couple of vias to drop through the board

---

## B. Freerouting (one-click autorouter)

### One-time setup

1. **Install Java 17 or later** if you don't have it. Test with `java -version` in a terminal — should print something with `17.x` or higher.
   - Windows: download the LTS JDK from https://adoptium.net/
2. **Download Freerouting**:
   - Go to https://github.com/freerouting/freerouting/releases
   - Grab the latest `freerouting-X.Y.Z.jar`
   - Save it somewhere stable, e.g. `C:\Tools\freerouting.jar`

### Each time you want to autoroute

1. In pcbnew with `CCTV_NodeV2.kicad_pcb` open:
   - **File → Export → Specctra DSN…**
   - Save as `CCTV_NodeV2.dsn` next to your PCB file.
2. Open a terminal in the same folder and run:
   ```powershell
   java -jar C:\Tools\freerouting.jar -de CCTV_NodeV2.dsn -do CCTV_NodeV2.ses
   ```
   - `-de` = design (input)
   - `-do` = output session
   - Freerouting will route in headless mode for a few minutes; you'll see progress in the terminal. For interactive mode (GUI), drop the `-do` flag.
3. Back in pcbnew:
   - **File → Import → Specctra Session…**
   - Pick `CCTV_NodeV2.ses`. KiCad lays down all the traces.
4. Press **`B`** to refresh ratsnest — there should be no airwires left.
5. **Run DRC** to verify clearance.

### If Freerouting struggles

- Add **net classes** before exporting: `File → Board Setup → Net Classes`. Make a "Power" class with wider traces (e.g. 0.5 mm) for `+5V`, `+3V3`, `BATT+`, `GND`, and keep default (~0.25 mm) for signals.
- Increase board size: `Edit → Properties` of the Edge.Cuts rectangle, expand to 110 × 90 if needed.
- Re-run with the `-mp <passes>` flag for more optimization, e.g. `-mp 100`.

---

## Current component placement

The PCB ships with this layout. Move things in pcbnew (`M` key) if you don't like it — the routing happens after placement so you can always re-route.

| Ref | Component | Position (mm) | Rotation | Notes |
|---|---|---|---|---|
| J1 | Solar input (2-pin header) | (10, 12) | 90° | top-left, wires up to solar panel |
| U1 | CN3791 MPPT | (35, 12) | 0° | next to J1 |
| U2 | 1S BMS DW01A+FS8205A | (62, 12) | 0° | top-right of power chain |
| J2 | Battery pack connector (2-pin) | (10, 28) | 90° | left side, wires to 18650 pack |
| U3 | MT3608 boost | (62, 28) | 0° | below U2, +5V output goes south to U4 |
| R1 | 4.7 kΩ SIOD pull-up | (40, 38) | 90° | between MT3608 and U4 |
| R2 | 4.7 kΩ SIOC pull-up | (50, 38) | 90° | next to R1 |
| U4 | ESP32-S3-DevKitC-1 | (30, 55) | 0° | bottom-center, USB-C marker pointing up |
| U5 | OV7670 camera module | (70, 55) | 0° | bottom-right, lens marker at center |

Board outline: 0,0 to 100,80 mm rectangle on Edge.Cuts.

---

## What's already routed

The PCB ships with **18 power traces at 1 mm width on F.Cu** already laid down. You only need to finish the signal nets and a couple of leftover power connections.

| Net | Status | Notes |
|---|---|---|
| `SOLAR+` | ✅ done | J1.1 → U1.1, diagonal |
| `SOLAR-` | ✅ done | J1.2 → U1.2, 2-segment L |
| `BATT+` | ✅ done (4 of 5 pads) | Top rail at y=5 connecting U1.3, U2.1, U2.3, U3.1. **J2.1 still needs to connect** — easiest route is `J2.1 → (4, 28) → (4, 5) → rail`. |
| `BATT-` | ✅ done (2 of 3 pads) | U1.4 → U2.2. **J2.2 still needs to connect** — route on B.Cu or via the left edge. |
| `+5V` | ✅ done | U3.3 → U4.1 via right side and underbelly at y=40 |
| `+3V3` | ⚠ partial | R1.1 → R2.1 → U5.1 done. **U4.3 → R1.1 still needs to connect** — U4's right pad column blocks a direct path; easiest is U4.3 → exit right above U4 body → R1.1. |
| `GND` | ⚠ tiny stub | U3.2 ↔ U3.4 only. **The other 4 GND pads need connection** (U2.4, U4.2, U5.2, U5.4). This is the most complex net — recommend either Freerouting handles it, or you draw a small ground fill on B.Cu in pcbnew (`Place → Filled Zone → B.Cu → GND`). |
| Camera bus (`SIOC`, `SIOD`, `VSYNC`, `HREF`, `PCLK`, `XCLK`) | ❌ unrouted | 6 short nets between U4 left side and U5 left side |
| Camera data (`CAM_D0..D7`) | ❌ unrouted | 8 nets, U4 right side to U5 right side — will likely need vias and B.Cu |

For the unrouted nets, either:
- Open in pcbnew, press `B` to refresh ratsnest, press `X` to route interactively (~10 min for what's left)
- Or follow the Freerouting steps below — it will route around the existing 1 mm power traces and lay down the rest

## Net summary (21 nets + GND)

Power: `SOLAR+`, `SOLAR-`, `BATT+`, `BATT-`, `GND`, `+5V`, `+3V3`
Camera I²C/control: `SIOD`, `SIOC`, `VSYNC`, `HREF`, `PCLK`, `XCLK`
Camera data: `CAM_D0`, `CAM_D1`, …, `CAM_D7`

> Note: the PCB consolidates the schematic's `PROT-` net into `GND` (they're electrically the same node — BMS P- and chip grounds tied together). If you re-run `Update PCB from Schematic` (F8), KiCad will flag this; either accept the merge or update the schematic to use `GND` everywhere downstream of the BMS.

---

## Manufacturing checklist (when ready)

- [ ] DRC passes (zero errors)
- [ ] Run `File → Plot…` → Gerbers + drill files
- [ ] Upload zip to JLCPCB / PCBWay / OSHPark
- [ ] Order 2-layer, 1.6 mm thickness, HASL or ENIG finish, standard FR-4
- [ ] Order matching stencil if you're doing reflow (not needed — all through-hole on this board)
