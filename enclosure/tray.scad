// ═══════════════════════════════════════════════════════════════════════════
//  Electronics Tray  —  standalone part file
//  Sits inside the IP65 junction box and holds battery + MPPT + boost
//  converter + BMS in fixed positions (no rattling).
//
//  Circuit flow:
//    Solar → CN3791 (MPPT charge) → 18650 × 2 → BMS (discharge protect)
//    → MT3608 (boost 5 V) → ESP32-CAM
//
//  Open in OpenSCAD → F6 → File → Export → STL
//  Print in PETG (preferred) or PLA+ at 0.2 mm layers, 4 perimeters,
//  25 % gyroid infill. No supports needed.
// ═══════════════════════════════════════════════════════════════════════════

// ─── IP65 BOX INNER DIMENSIONS ────────────────────────────────────────────
// Default for 140 × 78 mm outer junction box (typical thai weatherproof box):
//   140 - 2×3 mm walls = 134 mm inner length
//    78 - 2×3 mm walls =  72 mm inner depth
// Edit to match your box (always use INNER measurements).
BOX_W = 134;   // inside width  (lengthwise)
BOX_D =  72;   // inside depth  (top → bottom mounted)

// ─── ELECTRONICS (real measured sizes, mm) ────────────────────────────────
HOLDER_W = 75;  HOLDER_D = 36;   // 2× 18650 battery holder footprint
CN3791_W = 30;  CN3791_D = 20;   // CN3791 MPPT charger PCB
MT3608_W = 36;  MT3608_D = 17;   // MT3608 boost converter PCB
BMS_W    = 20;  BMS_D    = 10;   // 1S BMS module (DW01A+FS8205A, 20×10 mm)

// ─── PRINT TOLERANCES ─────────────────────────────────────────────────────
WALL = 1.6;   // wall thickness (4 perimeters @ 0.4 mm nozzle)
SLOP = 0.3;   // fit clearance
$fn = 64;

// Column X offset shared by MPPT, Boost, BMS clips
COL_X = 4 + HOLDER_W + 6;   // = 85 mm from tray left edge

// ═══════════════════════════════════════════════════════════════════════════

// PCB clip — two L-shaped fingers that grip a small PCB by its edges.
// A centre window lets you lift the PCB out without tools.
module pcb_clip(pcb_w, pcb_d, h) {
    difference() {
        cube([pcb_w + WALL*2 + SLOP*2, pcb_d + WALL*2 + SLOP*2, h]);
        translate([WALL, WALL, 1.6])
            cube([pcb_w + SLOP*2, pcb_d + SLOP*2, h]);
        translate([(pcb_w + WALL*2)/2 - 6, -1, 3])
            cube([12, pcb_d + WALL*4 + SLOP*2 + 2, h]);
    }
}

// Main tray
module electronics_tray() {
    difference() {
        union() {
            // Base plate
            cube([BOX_W - 4, BOX_D - 4, 2]);

            // Battery holder pocket (open box around holder, left side)
            translate([4, 4, 2])
                difference() {
                    cube([HOLDER_W + SLOP*2, HOLDER_D + SLOP*2, 8]);
                    translate([WALL, WALL, 2])
                        cube([HOLDER_W + SLOP*2 - WALL*2,
                              HOLDER_D + SLOP*2 - WALL*2, 10]);
                }

            // MPPT charger clip (right column, top)
            translate([COL_X, 4, 2])
                pcb_clip(CN3791_W, CN3791_D, 6);

            // Boost converter clip (right column, middle)
            translate([COL_X, 4 + CN3791_D + 5, 2])
                pcb_clip(MT3608_W, MT3608_D, 6);

            // BMS clip (right column, bottom — under boost)
            translate([COL_X, 4 + CN3791_D + 5 + MT3608_D + 5, 2])
                pcb_clip(BMS_W, BMS_D, 6);

            // Cable routing posts at 4 corners
            for (x = [10, BOX_W - 14], y = [10, BOX_D - 14])
                translate([x, y, 2]) cylinder(d=4, h=12);
        }

        // M3 screw holes (align with standoffs inside the IP65 box)
        for (x = [6, BOX_W - 10], y = [6, BOX_D - 10])
            translate([x, y, -1]) cylinder(d=3.4, h=5);
    }
}

electronics_tray();
