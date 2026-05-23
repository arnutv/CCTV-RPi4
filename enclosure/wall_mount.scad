// ═══════════════════════════════════════════════════════════════════════════
//  Wall Mount Plate  —  standalone part file
//  80 × 80 × 4 mm flat plate that screws to the wall (4× M5 countersunk).
//  Attach the IP65 camera box directly to the front face with
//  VHB double-sided tape or M3 screws through the box back.
//
//  Open in OpenSCAD → F6 → File → Export → STL
//  Print in PETG (preferred) or PLA+ at 0.2 mm layers, 4 perimeters,
//  25 % gyroid infill. No supports needed.
// ═══════════════════════════════════════════════════════════════════════════

PLATE_W  = 80;   // square side length (mm)
PLATE_TH =  4;   // plate thickness   (mm)

$fn = 64;

module wall_mount() {
    difference() {
        cube([PLATE_W, PLATE_W, PLATE_TH]);

        // 4× wall-screw holes (M5 clearance ⌀5.5) with countersinks on
        // the back face so the screw heads sit flush against the wall.
        for (x = [10, PLATE_W - 10], y = [10, PLATE_W - 10]) {
            translate([x, y, -1])
                cylinder(d=5.5, h=PLATE_TH + 2);
            translate([x, y, -0.1])
                cylinder(d1=10.5, d2=5.5, h=3.2);   // 90° countersink
        }
    }
}

wall_mount();
