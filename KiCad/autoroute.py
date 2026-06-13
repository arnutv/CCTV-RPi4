"""
autoroute.py  —  Simple Manhattan auto-router for CCTV_Power.kicad_pcb
Connects every pad in each net using an L-shaped trace (horiz-then-vert).
Power nets get 0.5 mm tracks; signal nets get 0.25 mm.
Run from KiCad Scripting Console:
    exec(open(r'C:/Users/Admin/OneDrive/Desktop/Arduino Projects/CCTV-RPi4/KiCad/autoroute.py').read())
"""

import pcbnew, math, sys

BOARD_FILE = r"C:\Users\Admin\OneDrive\Desktop\Arduino Projects\CCTV-RPi4\KiCad\CCTV_Power.kicad_pcb"
POWER_NETS = {"GND", "BATT+", "SOLAR+", "+5V"}
POWER_WIDTH_MM  = 0.5
SIGNAL_WIDTH_MM = 0.25

# ------------------------------------------------------------------
def mm(v):   return pcbnew.FromMM(v)
def tomm(v): return pcbnew.ToMM(v)

def add_track(board, net_obj, x1, y1, x2, y2, width_mm):
    """Add one straight PCB_TRACK segment (skips zero-length)."""
    if abs(x1 - x2) < 0.001 and abs(y1 - y2) < 0.001:
        return
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(mm(x1), mm(y1)))
    t.SetEnd  (pcbnew.VECTOR2I(mm(x2), mm(y2)))
    t.SetWidth(mm(width_mm))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(net_obj)
    board.Add(t)

def route_pair(board, net_obj, x1, y1, x2, y2, width_mm, via_y=None):
    """
    L-shaped route from (x1,y1) to (x2,y2).
    Goes horizontal first to the midpoint X, then vertical,
    unless via_y is given (route vertical first to via_y then horizontal).
    """
    if abs(x1 - x2) < 0.001:          # same column → straight vertical
        add_track(board, net_obj, x1, y1, x2, y2, width_mm)
        return
    if abs(y1 - y2) < 0.001:          # same row → straight horizontal
        add_track(board, net_obj, x1, y1, x2, y2, width_mm)
        return

    if via_y is not None:
        # vertical leg first then horizontal
        add_track(board, net_obj, x1, y1, x1, via_y, width_mm)
        add_track(board, net_obj, x1, via_y, x2, via_y, width_mm)
        add_track(board, net_obj, x2, via_y, x2, y2, width_mm)
    else:
        # horizontal leg first then vertical
        add_track(board, net_obj, x1, y1, x2, y1, width_mm)
        add_track(board, net_obj, x2, y1, x2, y2, width_mm)

def dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

def nearest_neighbour_order(pads):
    """Return pads in nearest-neighbour visit order (greedy MST chain)."""
    if len(pads) <= 1:
        return pads
    remaining = list(pads)
    ordered = [remaining.pop(0)]
    while remaining:
        last = ordered[-1]
        closest = min(remaining, key=lambda p: dist((last[2], last[3]), (p[2], p[3])))
        remaining.remove(closest)
        ordered.append(closest)
    return ordered

# ------------------------------------------------------------------
print("Loading board …")
board = pcbnew.LoadBoard(BOARD_FILE)

# Remove any existing tracks (start fresh)
for t in list(board.GetTracks()):
    board.Remove(t)
print("Cleared existing tracks.")

# Collect pads grouped by net name
nets_pads = {}
for fp in board.GetFootprints():
    for pad in fp.Pads():
        net = pad.GetNet()
        name = net.GetNetname()
        if not name:
            continue
        pos = pad.GetPosition()
        entry = (fp.GetReference(), pad.GetNumber(),
                 tomm(pos.x), tomm(pos.y), net)
        nets_pads.setdefault(name, []).append(entry)

# Print net summary
print(f"\nFound {len(nets_pads)} nets with pads:")
for name, pads in sorted(nets_pads.items()):
    refs = ", ".join(f"{r}.{n}" for r, n, *_ in pads)
    print(f"  {name:12s} ({len(pads)} pads): {refs}")

# ------------------------------------------------------------------
# Route each net
print("\nRouting …")
routed = 0

for net_name, pads in sorted(nets_pads.items()):
    if len(pads) < 2:
        print(f"  {net_name}: only 1 pad — skip")
        continue

    width = POWER_WIDTH_MM if net_name in POWER_NETS else SIGNAL_WIDTH_MM
    net_obj = pads[0][4]
    ordered = nearest_neighbour_order(pads)

    print(f"  {net_name} ({width} mm): ", end="")

    # Per-net routing hints to avoid obvious overlaps
    for i in range(len(ordered) - 1):
        _, _, x1, y1, _ = ordered[i]
        _, _, x2, y2, _ = ordered[i+1]

        # Choose routing direction based on net + segment to reduce overlaps
        if net_name == "GND":
            # Route GND via a horizontal bus at y=58 (below all modules)
            route_pair(board, net_obj, x1, y1, x2, y2, width, via_y=58)
        elif net_name == "BATT+":
            # Route BATT+ via a horizontal bus at y=36
            route_pair(board, net_obj, x1, y1, x2, y2, width, via_y=36)
        elif net_name == "+5V":
            # Route +5V via a horizontal bus at y=55
            route_pair(board, net_obj, x1, y1, x2, y2, width, via_y=55)
        elif net_name == "SOLAR+":
            # Simple horiz-first
            route_pair(board, net_obj, x1, y1, x2, y2, width)
        else:
            route_pair(board, net_obj, x1, y1, x2, y2, width)
        routed += 1
        print(f"({x1:.1f},{y1:.1f})→({x2:.1f},{y2:.1f}) ", end="")
    print()

# ------------------------------------------------------------------
print(f"\nTotal segments routed: {routed} nets connected.")
print("Saving board …")
board.Save(BOARD_FILE)
print("Done! Open CCTV_Power.kicad_pcb in KiCad to review.")
