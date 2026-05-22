// ═══════════════════════════════════════════════════════════════════════════
//  CCTV-Camera — Enclosure parts for ESP32-CAM + solar + battery
//  Open in OpenSCAD (https://openscad.org), choose a part below, then F6 → Export STL
//  All dimensions in mm. Tested in PETG (preferred for UV/outdoor) or PLA+ (indoor).
// ═══════════════════════════════════════════════════════════════════════════

// ─── PICK ONE PART TO RENDER ──────────────────────────────────────────────
PART = "all";   // "tray" | "wall_mount" | "box_socket" |
                // "solar_bracket" | "panel_socket" | "all"

// ─── Ball joint geometry (shared between mounts and sockets) ──────────────
BALL_DIA  = 20;
STALK_DIA = 10;
STALK_H   = 15;

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

// ─── Helper: clamping socket on an adapter plate (ball joint receptacle) ──
module _socket(plate_w, plate_d, plate_th=3) {
    socket_od = BALL_DIA + 8;
    socket_h  = BALL_DIA/2 + 6;
    slit_w    = 1.6;
    ball_r    = BALL_DIA/2 + 0.15;
    cup_x = plate_w/2; cup_y = plate_d/2;
    ball_z = plate_th + BALL_DIA/2 + 1;

    difference() {
        union() {
            // Adapter plate
            cube([plate_w, plate_d, plate_th]);
            // Socket cup
            translate([cup_x, cup_y, plate_th])
                cylinder(d=socket_od, h=socket_h);
            // Clamp boss
            translate([cup_x + socket_od/2 - 3, cup_y - 4, plate_th + 2])
                cube([18, 8, socket_h - 4]);
        }
        // Ball cavity
        translate([cup_x, cup_y, ball_z]) sphere(r=ball_r);
        // Cone opening at top
        translate([cup_x, cup_y, ball_z])
            cylinder(d1=ball_r*2 - 3, d2=STALK_DIA + 2, h=socket_h);
        // Slit (flex line)
        translate([cup_x, cup_y - slit_w/2, plate_th + 2])
            cube([socket_od/2 + 2, slit_w, socket_h + 1]);
        // M3 clamp screw hole (horizontal through boss)
        translate([cup_x + socket_od/2 + 18, cup_y, plate_th + 2 + (socket_h - 4)/2])
            rotate([0, -90, 0])
                cylinder(d=3.4, h=socket_od + 24);
        // Hex nut pocket
        translate([cup_x + socket_od/2 + 14, cup_y - 3.1, plate_th + 2 + (socket_h - 4)/2 - 1.25])
            cube([3, 6.2, 2.5]);
    }
}

// ─── 2. WALL MOUNT (wall plate + ball stalk) ──────────────────────────────
//   Pairs with box_socket to give a freely-aimable ball joint at the box.
module wall_mount() {
    plate_w = 80;
    plate_th = 4;
    difference() {
        cube([plate_w, plate_w, plate_th]);
        for (x = [10, plate_w - 10], y = [10, plate_w - 10]) {
            translate([x, y, -1]) cylinder(d=5, h=plate_th + 2);
            // Countersink
            translate([x, y, -0.1]) cylinder(d1=10, d2=5, h=2.5);
        }
    }
    translate([plate_w/2, plate_w/2, plate_th]) {
        cylinder(d=STALK_DIA, h=STALK_H);
        translate([0, 0, STALK_H + BALL_DIA/2 - 2]) sphere(d=BALL_DIA);
    }
}

// ─── 3. BOX SOCKET (sticks to back of IP65 box, holds wall_mount's ball) ──
module box_socket() {
    plate_w = 55; plate_d = 45;
    difference() {
        _socket(plate_w, plate_d, plate_th=3);
        // 4× optional mounting screw holes
        for (x = [6, plate_w - 6], y = [6, plate_d - 6])
            translate([x, y, -1]) cylinder(d=3.2, h=5);
    }
}

// ─── 4. SOLAR BRACKET (wall arm + ball stalk for panel mounting) ──────────
//   Pairs with panel_socket. Replaces the previous tilt-lock design.
module solar_bracket() {
    arm_l  = 80;
    arm_w  = 25;
    arm_th = 4;

    // Vertical wall plate
    difference() {
        cube([arm_w, arm_th, 100]);
        for (z = [15, 85])
            translate([arm_w/2, -1, z]) rotate([-90, 0, 0]) cylinder(d=5.5, h=6);
    }
    // Horizontal arm
    translate([0, arm_th, 100 - arm_th]) cube([arm_w, arm_l, arm_th]);
    // Gusset
    translate([0, arm_th, 100 - arm_th])
        rotate([0, -90, 0])
            linear_extrude(arm_w)
                polygon([[0,0], [25,0], [0,-25]]);
    // Ball stalk at far end of arm (pointing UP)
    translate([arm_w/2, arm_th + arm_l - 14, 100]) {
        cylinder(d=STALK_DIA, h=STALK_H);
        translate([0, 0, STALK_H + BALL_DIA/2 - 2]) sphere(d=BALL_DIA);
    }
}

// ─── 5. PANEL SOCKET (bolts to back of solar panel, holds bracket's ball) ─
module panel_socket() {
    plate_w = 80; plate_d = 40;
    difference() {
        _socket(plate_w, plate_d, plate_th=4);
        // 4× M4 mounting holes for the solar panel frame
        for (x = [10, plate_w - 10], y = [8, plate_d - 8])
            translate([x, y, -1]) cylinder(d=4.4, h=6);
    }
}

// ═══════════════════════════════════════════════════════════════════════════
//                              LAY OUT FOR EXPORT
// ═══════════════════════════════════════════════════════════════════════════
if (PART == "tray")               electronics_tray();
else if (PART == "wall_mount")    wall_mount();
else if (PART == "box_socket")    box_socket();
else if (PART == "solar_bracket") solar_bracket();
else if (PART == "panel_socket")  panel_socket();
else {
    // "all" → show every part spread out for preview
    electronics_tray();
    translate([BOX_W + 30,  120,    0]) wall_mount();
    translate([BOX_W + 130, 120,    0]) box_socket();
    translate([BOX_W + 30,    0,    0]) solar_bracket();
    translate([BOX_W + 130,   0,    0]) panel_socket();
}
