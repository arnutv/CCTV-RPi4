// ═══════════════════════════════════════════════════════════════════════════
//  CCTV-Camera — Enclosure parts (combined preview file)
//  For single-part STL export use the individual files:
//    tray.scad           — Electronics tray  (open → F6 → Export STL)
//    solar_bracket.scad  — Solar panel arm   (open → F6 → Export STL)
//
//  This file lets you preview both parts together or pick one with PART.
//  All dimensions in mm. Print in PETG (preferred) or PLA+.
// ═══════════════════════════════════════════════════════════════════════════

// ─── PICK ONE PART TO RENDER ──────────────────────────────────────────────
PART = "all";   // "tray" | "solar_bracket" | "all"

// ─── IP65 BOX INNER DIMENSIONS ────────────────────────────────────────────
BOX_W = 134;   // inside width  (140 mm outer − 2×3 mm walls)
BOX_D =  72;   // inside depth  ( 78 mm outer − 2×3 mm walls)

// ─── ELECTRONICS (real measured sizes, mm) ────────────────────────────────
HOLDER_W = 75;  HOLDER_D = 36;
CN3791_W = 30;  CN3791_D = 20;
MT3608_W = 36;  MT3608_D = 17;
BMS_W    = 20;  BMS_D    = 10;   // 1S BMS (DW01A+FS8205A, 20×10 mm)

// ─── SOLAR BRACKET ────────────────────────────────────────────────────────
ARM_L   = 80;
ARM_W   = 25;
ARM_TH  =  4;
PLATE_H = 100;

// ─── PRINT TOLERANCES ─────────────────────────────────────────────────────
WALL = 1.6;
SLOP = 0.3;
$fn = 64;

// ═══════════════════════════════════════════════════════════════════════════
//                                 PARTS
// ═══════════════════════════════════════════════════════════════════════════

// ─── Helper: PCB clip ─────────────────────────────────────────────────────
module pcb_clip(pcb_w, pcb_d, h) {
    difference() {
        cube([pcb_w + WALL*2 + SLOP*2, pcb_d + WALL*2 + SLOP*2, h]);
        translate([WALL, WALL, 1.6])
            cube([pcb_w + SLOP*2, pcb_d + SLOP*2, h]);
        translate([(pcb_w + WALL*2)/2 - 6, -1, 3])
            cube([12, pcb_d + WALL*4 + SLOP*2 + 2, h]);
    }
}

// ─── 1. ELECTRONICS TRAY ──────────────────────────────────────────────────
module electronics_tray() {
    difference() {
        union() {
            cube([BOX_W - 4, BOX_D - 4, 2]);

            translate([4, 4, 2])
                difference() {
                    cube([HOLDER_W + SLOP*2, HOLDER_D + SLOP*2, 8]);
                    translate([WALL, WALL, 2])
                        cube([HOLDER_W + SLOP*2 - WALL*2,
                              HOLDER_D + SLOP*2 - WALL*2, 10]);
                }

            // Right column: MPPT (top) → Boost (middle) → BMS (bottom)
            translate([4 + HOLDER_W + 6, 4, 2])
                pcb_clip(CN3791_W, CN3791_D, 6);

            translate([4 + HOLDER_W + 6, 4 + CN3791_D + 5, 2])
                pcb_clip(MT3608_W, MT3608_D, 6);

            translate([4 + HOLDER_W + 6, 4 + CN3791_D + 5 + MT3608_D + 5, 2])
                pcb_clip(BMS_W, BMS_D, 6);

            for (x = [10, BOX_W - 14], y = [10, BOX_D - 14])
                translate([x, y, 2]) cylinder(d=4, h=12);
        }

        for (x = [6, BOX_W - 10], y = [6, BOX_D - 10])
            translate([x, y, -1]) cylinder(d=3.4, h=5);
    }
}

// ─── 2. SOLAR BRACKET ─────────────────────────────────────────────────────
module solar_bracket() {
    // Vertical wall plate
    difference() {
        cube([ARM_W, ARM_TH, PLATE_H]);
        for (z = [15, PLATE_H - 15]) {
            translate([ARM_W/2, -1, z])
                rotate([-90, 0, 0])
                    cylinder(d=5.5, h=ARM_TH + 2);
            translate([ARM_W/2, -0.1, z])
                rotate([-90, 0, 0])
                    cylinder(d1=10.5, d2=5.5, h=3.2);
        }
    }

    // Horizontal arm
    translate([0, ARM_TH, PLATE_H - ARM_TH])
        difference() {
            cube([ARM_W, ARM_L, ARM_TH]);
            // 4× M4 panel mounting holes near far end
            for (xp = [5, ARM_W - 5], yp = [ARM_L - 20, ARM_L - 8])
                translate([xp, yp, -1])
                    cylinder(d=4.5, h=ARM_TH + 2);
        }

    // Triangular gusset
    translate([0, ARM_TH, PLATE_H - ARM_TH])
        rotate([0, -90, 0])
            linear_extrude(ARM_W)
                polygon([[0, 0], [25, 0], [0, -25]]);
}

// ═══════════════════════════════════════════════════════════════════════════
//                            LAY OUT FOR EXPORT
// ═══════════════════════════════════════════════════════════════════════════
if      (PART == "tray")           electronics_tray();
else if (PART == "solar_bracket")  solar_bracket();
else {
    // "all" — both parts side by side for preview
    electronics_tray();
    translate([BOX_W + 30, 0, 0]) solar_bracket();
}
