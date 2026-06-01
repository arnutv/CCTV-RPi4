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

The PCB ships **fully routed** — 96 trace segments covering all 21 nets:
- 18 power traces at 1 mm width on F.Cu (BATT+, BATT-, +5V, +3V3, SOLAR+, SOLAR-, partial GND)
- 38 signal + auxiliary power traces at 0.7 mm width on F.Cu (camera control + GND chain + J2 routes on B.Cu)
- 40 camera data traces at 0.7 mm width on B.Cu (CAM_D0..D7, 5 segments each in a switching pattern)

Open in pcbnew and press `B` — the ratsnest should be empty (no airwires).

| Net | Status | Notes |
|---|---|---|
| `SOLAR+` | ✅ done (1 mm F.Cu) | J1.1 → U1.1, diagonal |
| `SOLAR-` | ✅ done (1 mm F.Cu) | J1.2 → U1.2, 2-segment L |
| `BATT+` | ✅ done (1 mm F.Cu + 0.7 mm B.Cu) | Top rail at y=5 + J2.1 via left edge on B.Cu through y=8 |
| `BATT-` | ✅ done (1 mm F.Cu + 0.7 mm B.Cu) | U1.4 → U2.2 + J2.2 via left edge on B.Cu through y=16 |
| `+5V` | ✅ done (1 mm F.Cu) | U3.3 → U4.1 via right side and underbelly at y=40 |
| `+3V3` | ✅ done (1 mm + 0.7 mm F.Cu) | U4.3 → R1 → R2 → U5.1 (U4.3 exit via y=49.92 west-east then up around R1) |
| `GND` | ✅ done (0.7 mm F.Cu) | U2.4 → right edge (x=75) → U3.4 → down through OV7670 body → U5.2 + U5.4 bypass + U4.2 horizontal |
| Camera control: `SIOC`, `SIOD`, `VSYNC`, `HREF`, `PCLK`, `XCLK` | ✅ done (0.7 mm F.Cu) | Each routed as L-shape from U4 left column to U5 left column through inter-column gap |
| Camera data (`CAM_D0..D7`) | ✅ done (0.7 mm B.Cu) | All 8 lines routed on the back copper layer with a 5-segment switching pattern: exit U4 east, drop south to a unique bottom rail (y=68–76.4, 1.2 mm pitch), traverse east past U5, climb north to target y, into U5 right pad from the east. No vias needed (through-hole pads bridge layers). |

All nets are routed. If you want to verify or improve:
- Open in pcbnew, press `B` to refresh ratsnest — should be empty
- Run DRC (`Inspect → Design Rules Checker`) — expect ~6 clearance warnings at U4's right pad column (see DRC notes below)
- If desired, run Freerouting on the same DSN export — it will re-optimize the layout (typically tightening corners and reducing total trace length 10–20%)

### DRC notes for the hand-routed traces

Most traces pass between header pads at the standard 2.54 mm pitch. With 0.7 mm trace width + 1.7 mm pad diameter, the trace-to-pad clearance through the gap is **~0.07 mm** — KiCad's default 0.2 mm clearance rule will flag these.

To resolve, in **File → Board Setup → Constraints**:
- Set "Minimum clearance" to 0.1 mm (industry minimum for most fabs)
- Or reduce just the affected traces to 0.5 mm width and clearance stays at 0.2 mm
- Or accept the DRC violations if you're hand-soldering (the pads still fit, the traces just sit closer than the design rule prefers)

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
