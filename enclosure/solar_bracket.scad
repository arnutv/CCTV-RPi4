// ═══════════════════════════════════════════════════════════════════════════
//  Solar Bracket  —  standalone part file
//  L-shaped wall arm for mounting a 6V/10W solar panel.
//
//  Geometry:
//    Vertical wall plate  25 × 4 × 100 mm   — screws to wall (2× M5)
//    Horizontal arm       25 × 80 × 4 mm    — panel rests on top
//    Triangular gusset                       — prevents arm from drooping
//    Panel mounting holes  4× M4 at arm end — bolts through panel frame
//
//  Open in OpenSCAD → F6 → File → Export → STL
//  Print in PETG (preferred for UV/outdoor) at 0.2 mm layers,
//  4 perimeters, 40 % gyroid infill. No supports needed.
// ═══════════════════════════════════════════════════════════════════════════

ARM_L   = 80;    // horizontal arm length (mm)
ARM_W   = 25;    // arm + plate width     (mm)
ARM_TH  =  4;    // arm + plate thickness (mm)
PLATE_H = 100;   // vertical plate height (mm)

$fn = 64;

module solar_bracket() {
    // ── Vertical wall plate ──────────────────────────────────────────────
    difference() {
        cube([ARM_W, ARM_TH, PLATE_H]);
        // 2× M5 wall-screw holes (⌀5.5), countersunk on the back face
        for (z = [15, PLATE_H - 15]) {
            translate([ARM_W/2, -1, z])
                rotate([-90, 0, 0])
                    cylinder(d=5.5, h=ARM_TH + 2);
            translate([ARM_W/2, -0.1, z])
                rotate([-90, 0, 0])
                    cylinder(d1=10.5, d2=5.5, h=3.2);   // 90° countersink
        }
    }

    // ── Horizontal arm (extends outward from top of plate) ───────────────
    translate([0, ARM_TH, PLATE_H - ARM_TH])
        difference() {
            cube([ARM_W, ARM_L, ARM_TH]);
            // 4× M4 panel mounting holes (⌀4.5) near the far end of arm
            for (xp = [5, ARM_W - 5], yp = [ARM_L - 20, ARM_L - 8])
                translate([xp, yp, -1])
                    cylinder(d=4.5, h=ARM_TH + 2);
        }

    // ── Triangular gusset (joins underside of arm to plate) ─────────────
    translate([0, ARM_TH, PLATE_H - ARM_TH])
        rotate([0, -90, 0])
            linear_extrude(ARM_W)
                polygon([[0, 0], [25, 0], [0, -25]]);
}

solar_bracket();
