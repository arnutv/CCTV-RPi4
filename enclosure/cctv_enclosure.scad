// ═══════════════════════════════════════════════════════════════════════════
//  CCTV-Camera — Enclosure parts for ESP32-CAM + solar + battery
//  Open in OpenSCAD (https://openscad.org), choose a part below, then F6 → Export STL
//  All dimensions in mm. Tested in PETG (preferred for UV/outdoor) or PLA+ (indoor).
// ═══════════════════════════════════════════════════════════════════════════

// ─── PICK ONE PART TO RENDER ──────────────────────────────────────────────
PART = "all";   // "tray" | "tray_cover" | "bezel" | "lid_seal" |
                // "solar_bracket" | "wall_mount" | "ip65_box" | "ip65_lid" | "all"

// ─── ENCLOSURE BOX (off-the-shelf IP65) ───────────────────────────────────
// INNER usable dimensions. Default for 140×78 mm outer junction box (typical thai):
//   140 - 2*3 mm walls = 134 mm inner length
//    78 - 2*3 mm walls =  72 mm inner depth
// Edit to match your box (always use INNER measurements).
BOX_W  = 134;       // inside width  (lengthwise)
BOX_D  = 72;        // inside depth  (top → bottom mounted)
BOX_H  = 50;        // inside height (front → back, lid-to-base)

// ─── ELECTRONICS (real measured sizes) ────────────────────────────────────
ESP_W  = 40.5;  ESP_D = 27;   ESP_H = 4.5;     // ESP32-CAM PCB
LENS_DIA = 8.5;                                 // ESP32-CAM lens barrel
HOLDER_W = 75;  HOLDER_D = 36; HOLDER_H = 19;   // 2× 18650 battery holder
CN3791_W = 30;  CN3791_D = 20;                  // MPPT charger PCB
MT3608_W = 36;  MT3608_D = 17;                  // Boost converter PCB
SMA_DIA  = 6.5;                                 // SMA antenna mounting hole

// ─── PRINT TOLERANCES ─────────────────────────────────────────────────────
WALL = 1.6;         // wall thickness (4 perimeters @ 0.4mm nozzle)
SLOP = 0.3;         // fit tolerance
$fn = 64;

// ─── IP65 PRINTED-BOX SPECIFIC ────────────────────────────────────────────
BOX_WALL_TH   = 3.0;  // printed wall thickness for box / lid
BOX_LID_TH    = 4.0;  // lid plate thickness
GASKET_LIP    = 2.5;  // raised rim on top edge of box (gasket alignment)
GASKET_RIM_W  = 2.0;  // width of gasket rim

// ═══════════════════════════════════════════════════════════════════════════
//                                  PARTS
// ═══════════════════════════════════════════════════════════════════════════

// ─── 1. ELECTRONICS TRAY ──────────────────────────────────────────────────
//   Sits inside the IP65 box, holds battery + boards in fixed positions
//   so they don't rattle. Has channels for wiring between modules.
module electronics_tray() {
    difference() {
        // Base plate
        union() {
            cube([BOX_W - 4, BOX_D - 4, 2]);

            // Battery holder pocket (left side, vertical)
            translate([4, 4, 2])
                difference() {
                    cube([HOLDER_W + SLOP*2, HOLDER_D + SLOP*2, 8]);
                    translate([WALL, WALL, 2])
                        cube([HOLDER_W + SLOP*2 - WALL*2,
                              HOLDER_D + SLOP*2 - WALL*2, 10]);
                }

            // MPPT module clip (right of battery)
            translate([4 + HOLDER_W + 6, 4, 2])
                pcb_clip(CN3791_W, CN3791_D, 6);

            // Boost converter clip (right of MPPT)
            translate([4 + HOLDER_W + 6, 4 + CN3791_D + 5, 2])
                pcb_clip(MT3608_W, MT3608_D, 6);

            // Cable routing posts (4 corners)
            for (x=[10, BOX_W-14], y=[10, BOX_D-14])
                translate([x, y, 2]) cylinder(d=4, h=12);
        }

        // M3 screw mount holes (to standoffs in the IP65 box)
        for (x=[6, BOX_W-10], y=[6, BOX_D-10])
            translate([x, y, -1]) cylinder(d=3.4, h=5);
    }
}

// PCB clip — two L-shaped fingers that grip a small PCB by its edges
module pcb_clip(pcb_w, pcb_d, h) {
    difference() {
        cube([pcb_w + WALL*2 + SLOP*2, pcb_d + WALL*2 + SLOP*2, h]);
        translate([WALL, WALL, 1.6])
            cube([pcb_w + SLOP*2, pcb_d + SLOP*2, h]);
        // Cut a window in the middle so we can lift the PCB out
        translate([(pcb_w + WALL*2)/2 - 6, -1, 3])
            cube([12, pcb_d + WALL*4 + SLOP*2 + 2, h]);
    }
}

// ─── 2. CAMERA BEZEL (lens window + ESP32-CAM mount) ──────────────────────
//   Replaces the front face of the box. Has a sealed window for the lens
//   and screw bosses for the ESP32-CAM PCB.
module camera_bezel() {
    bezel_w = 60;
    bezel_d = 50;
    bezel_h = 8;
    lens_offset_x = bezel_w/2;
    lens_offset_y = bezel_d/2 - 4;   // lens is offset from PCB centre

    difference() {
        union() {
            // Front plate (sits flush against IP65 lid)
            cube([bezel_w, bezel_d, 2]);
            // Lens shroud (sticks out 6mm, creates a sun-hood)
            translate([lens_offset_x, lens_offset_y, 2])
                cylinder(d1=22, d2=18, h=6);
            // ESP32-CAM mounting bosses (rear)
            for (x=[3, ESP_W-3], y=[3, ESP_D-3])
                translate([bezel_w/2 - ESP_W/2 + x,
                           bezel_d/2 - ESP_D/2 + y, -bezel_h])
                    cylinder(d=5, h=bezel_h + 2);
            // O-ring seal channel around lens (for waterproofing)
            translate([lens_offset_x, lens_offset_y, 1.5])
                difference() {
                    cylinder(d=20, h=1);
                    cylinder(d=17, h=2);
                }
        }
        // Lens hole (through everything)
        translate([lens_offset_x, lens_offset_y, -bezel_h-1])
            cylinder(d=LENS_DIA + SLOP, h=bezel_h + 12);
        // ESP32-CAM mount screw holes (M2.5)
        for (x=[3, ESP_W-3], y=[3, ESP_D-3])
            translate([bezel_w/2 - ESP_W/2 + x,
                       bezel_d/2 - ESP_D/2 + y, -bezel_h-1])
                cylinder(d=2.6, h=bezel_h + 3);
        // Status LED window (small hole below lens)
        translate([lens_offset_x - 12, lens_offset_y, -1])
            cylinder(d=3, h=4);
    }
}

// ─── 3. LID GASKET PRESS (TPU print, optional) ────────────────────────────
//   A thin TPU ring that compresses against the IP65 box lid gasket
//   when the bezel is screwed on. Belts-and-braces sealing.
module lid_seal() {
    bezel_w = 60; bezel_d = 50;
    difference() {
        cube([bezel_w, bezel_d, 1.5]);
        translate([2, 2, -1]) cube([bezel_w-4, bezel_d-4, 3]);
    }
}

// ─── 4. SOLAR PANEL L-BRACKET (adjustable tilt) ───────────────────────────
//   Mounts the 6V/10W panel above the camera box at an adjustable angle.
//   Panel attaches with 4× M4 bolts, bracket attaches to wall with 2× M5.
module solar_bracket() {
    arm_l  = 80;     // bracket arm length
    arm_w  = 25;
    arm_th = 4;

    // Vertical wall plate
    difference() {
        cube([arm_w, arm_th, 100]);
        // Wall mount holes (M5)
        for (z=[15, 85])
            translate([arm_w/2, -1, z])
                rotate([-90, 0, 0]) cylinder(d=5.5, h=6);
    }
    // Horizontal arm (panel side)
    translate([0, arm_th, 100 - arm_th])
        difference() {
            cube([arm_w, arm_l, arm_th]);
            // Tilt pivot hole (M5 — panel angle adjusts here)
            translate([arm_w/2, arm_l - 10, -1])
                cylinder(d=5.5, h=arm_th + 2);
            // Tilt-lock arc of holes (15°, 30°, 45°, 60°)
            for (a = [15, 30, 45, 60])
                translate([arm_w/2 + 25*sin(a), arm_l - 10 - 25*cos(a), -1])
                    cylinder(d=4.5, h=arm_th + 2);
        }
    // Gusset between vertical and horizontal (strength)
    translate([0, arm_th, 100 - arm_th])
        rotate([0, -90, 0])
            linear_extrude(arm_w)
                polygon([[0,0], [25,0], [0,-25]]);
}

// ─── 5. WALL MOUNT (sits behind the IP65 box, articulating) ───────────────
//   2-piece pivoting wall bracket so the camera can be aimed.
module wall_mount() {
    // Wall plate (4× screw holes)
    difference() {
        cube([80, 80, 4]);
        for (x=[10, 70], y=[10, 70])
            translate([x, y, -1]) cylinder(d=5, h=6);    // M4 wall screws
        translate([40, 40, -1]) cylinder(d=8, h=6);       // pivot hole
    }
    // Ball-joint stalk (snaps into matching socket on box back)
    translate([40, 40, 4]) {
        cylinder(d=10, h=15);
        translate([0, 0, 15]) sphere(d=20);
    }
}

// ─── 6. IP65 BOX (full printable body) ────────────────────────────────────
//   Print with opening UP for clean vertical walls.
//   Use M3 brass heat-set inserts in the 4 corner bosses for the lid screws.
module ip65_box() {
    OW = BOX_W + 2 * BOX_WALL_TH;     // 154
    OD = BOX_D + 2 * BOX_WALL_TH;     // 86
    OH = BOX_H + BOX_WALL_TH;          // 58

    difference() {
        union() {
            // Outer shell (hollow box, open top)
            difference() {
                cube([OW, OD, OH]);
                translate([BOX_WALL_TH, BOX_WALL_TH, BOX_WALL_TH])
                    cube([BOX_W, BOX_D, BOX_H + 1]);
            }
            // Gasket alignment rim on top edge
            translate([BOX_WALL_TH, BOX_WALL_TH, OH])
                difference() {
                    cube([BOX_W, BOX_D, GASKET_LIP]);
                    translate([GASKET_RIM_W, GASKET_RIM_W, -0.5])
                        cube([BOX_W - 2*GASKET_RIM_W,
                              BOX_D - 2*GASKET_RIM_W,
                              GASKET_LIP + 1]);
                }
            // 4× corner screw bosses
            for (x = [BOX_WALL_TH + 5, OW - BOX_WALL_TH - 5],
                 y = [BOX_WALL_TH + 5, OD - BOX_WALL_TH - 5])
                translate([x, y, BOX_WALL_TH])
                    cylinder(d=8, h=BOX_H);
            // 4× tray floor standoffs
            for (x = [BOX_WALL_TH + 6, BOX_WALL_TH + BOX_W - 10],
                 y = [BOX_WALL_TH + 6, BOX_WALL_TH + BOX_D - 10])
                translate([x, y, BOX_WALL_TH])
                    cylinder(d=6, h=4);
        }
        // M3 brass insert pockets (corner bosses)
        for (x = [BOX_WALL_TH + 5, OW - BOX_WALL_TH - 5],
             y = [BOX_WALL_TH + 5, OD - BOX_WALL_TH - 5])
            translate([x, y, BOX_H - 8 + BOX_WALL_TH])
                cylinder(d=4, h=10);
        // Tray standoff M3 self-tap holes
        for (x = [BOX_WALL_TH + 6, BOX_WALL_TH + BOX_W - 10],
             y = [BOX_WALL_TH + 6, BOX_WALL_TH + BOX_D - 10])
            translate([x, y, BOX_WALL_TH])
                cylinder(d=2.8, h=6);
        // PG7 cable gland (top wall)
        translate([OW/2, OD + 1, OH - 15])
            rotate([90, 0, 0])
                cylinder(d=12, h=BOX_WALL_TH + 3);
        // SMA antenna hole (right wall)
        translate([OW + 1, OD/2, OH/2])
            rotate([0, -90, 0])
                cylinder(d=6.5, h=BOX_WALL_TH + 3);
        // Drain hole (bottom wall)
        translate([OW/2, -1, 8])
            rotate([-90, 0, 0])
                cylinder(d=3, h=BOX_WALL_TH + 3);
        // Wall mount holes (through back, with countersink)
        for (x = [12, OW - 12], y = [12, OD - 12]) {
            translate([x, y, -1]) cylinder(d=5, h=BOX_WALL_TH + 2);
            translate([x, y, -0.1]) cylinder(d1=10, d2=5, h=2.5);
        }
    }
}

// ─── 7. IP65 LID (full printable, with integrated camera bezel) ───────────
//   Drops over the box's gasket rim. M3 countersunk screws into box bosses.
module ip65_lid() {
    OW = BOX_W + 2 * BOX_WALL_TH;
    OD = BOX_D + 2 * BOX_WALL_TH;

    lens_x = OW / 2;
    lens_y = OD / 2 - 4;

    difference() {
        union() {
            // Lid plate
            cube([OW, OD, BOX_LID_TH]);
            // Sun shroud (cone above lens)
            translate([lens_x, lens_y, BOX_LID_TH])
                cylinder(d1=22, d2=18, h=7);
            // ESP32-CAM mounting bosses (rear / inside face)
            for (x = [3, ESP_W - 3], y = [3, ESP_D - 3])
                translate([OW/2 - ESP_W/2 + x,
                           OD/2 - ESP_D/2 + y, -5])
                    cylinder(d=5, h=5);
        }
        // Recess to fit over the box gasket rim
        translate([BOX_WALL_TH + 0.2, BOX_WALL_TH + 0.2, -0.5])
            cube([BOX_W - 0.4, BOX_D - 0.4, GASKET_LIP]);
        // 4× corner countersunk M3 through holes
        for (x = [BOX_WALL_TH + 5, OW - BOX_WALL_TH - 5],
             y = [BOX_WALL_TH + 5, OD - BOX_WALL_TH - 5]) {
            translate([x, y, -1]) cylinder(d=3.4, h=BOX_LID_TH + 2);
            translate([x, y, BOX_LID_TH - 1.8]) cylinder(d1=3.4, d2=7, h=1.8);
        }
        // ESP32-CAM mount M2.5 holes
        for (x = [3, ESP_W - 3], y = [3, ESP_D - 3])
            translate([OW/2 - ESP_W/2 + x, OD/2 - ESP_D/2 + y, -6])
                cylinder(d=2.6, h=BOX_LID_TH + 8);
        // Lens through hole
        translate([lens_x, lens_y, -1])
            cylinder(d=LENS_DIA + SLOP, h=BOX_LID_TH + 15);
        // Status LED window
        translate([lens_x - 12, lens_y, -1])
            cylinder(d=3, h=BOX_LID_TH + 2);
    }
}

// ─── 8. TRAY COVER (snap-on, holds batteries + organises cables) ──────────
//   Snaps over the 4 cable routing posts on the electronics tray.
//   Has ventilation grid, LED viewing window, and cable routing slot.
module tray_cover() {
    cover_w  = BOX_W - 4;
    cover_d  = BOX_D - 4;
    cover_th = 2.5;

    difference() {
        union() {
            cube([cover_w, cover_d, cover_th]);
            // Lift tab on front edge
            translate([cover_w/2 - 7.5, -3, 0])
                cube([15, 4, cover_th]);
        }
        // 4× snap holes (over tray posts)
        for (x = [10, cover_w - 14], y = [10, cover_d - 14])
            translate([x, y, -1]) cylinder(d=4.4, h=cover_th + 2);
        // Vent grid (6×3 holes, 3 mm dia, 8 mm pitch)
        for (vc = [0:5], vr = [0:2]) {
            vx = cover_w - 60 + vc * 8;
            vy = cover_d - 30 + vr * 8;
            if (vx > 4 && vx < cover_w - 4 && vy > 4 && vy < cover_d - 4)
                translate([vx, vy, -1]) cylinder(d=3, h=cover_th + 2);
        }
        // LED viewing window (over MPPT module)
        translate([90, 6, -1]) cube([22, 10, cover_th + 2]);
        // Cable routing slot (rear edge)
        translate([cover_w/2 - 20, cover_d - 8, -1])
            cube([40, 4, cover_th + 2]);
    }
}

// ═══════════════════════════════════════════════════════════════════════════
//                              LAY OUT FOR EXPORT
// ═══════════════════════════════════════════════════════════════════════════
if (PART == "tray")               electronics_tray();
else if (PART == "tray_cover")    tray_cover();
else if (PART == "bezel")         camera_bezel();
else if (PART == "lid_seal")      lid_seal();
else if (PART == "solar_bracket") solar_bracket();
else if (PART == "wall_mount")    wall_mount();
else if (PART == "ip65_box")      ip65_box();
else if (PART == "ip65_lid")      ip65_lid();
else {
    // "all" → show every part spread out for preview
    electronics_tray();
    translate([0, -BOX_D - 20, 0]) tray_cover();
    translate([0, BOX_D + 20, 0]) camera_bezel();
    translate([70, BOX_D + 20, 0]) lid_seal();
    translate([BOX_W + 20, 0, 0]) solar_bracket();
    translate([BOX_W + 70, 0, 0]) wall_mount();
    translate([BOX_W + 250, 0, 0]) ip65_box();
    translate([BOX_W + 250, BOX_D + 40, 0]) ip65_lid();
}
