"""
autoroute2.py — 2-layer Manhattan router for CCTV_Power.kicad_pcb
Board: 86 x 50 mm

Layer strategy (THT pads bridge both Cu layers — no explicit vias needed):
  GND   → B.Cu entirely, bus at Y=51
  BATT+ → F.Cu, bus at Y=34
  +5V   → F.Cu, SENSE-zone-aware routing (avoids X=34..58, Y=19..36)
  SOLAR+→ F.Cu, simple L
  SENSE → F.Cu, L-shape per pair (horiz-first then vert-first for 2nd pair)
"""

import re, math, uuid as _uuid

BOARD_FILE = r"C:\Users\Admin\OneDrive\Desktop\Arduino Projects\CCTV-RPi4\KiCad\CCTV_Power.kicad_pcb"
POWER_W  = 1.0
SIGNAL_W = 1.0

# SENSE zone — +5V routes must not cross this region
SENSE_XMIN, SENSE_XMAX = 34.0, 58.0
SENSE_YMIN, SENSE_YMAX = 19.0, 36.0
BYPASS_X = 61.0   # vertical transit column, right of SENSE zone

# ── helpers ───────────────────────────────────────────────────────────────
def new_uuid():
    return str(_uuid.uuid4())

def seg(x1, y1, x2, y2, net, width, layer="F.Cu"):
    """One kicad_pcb (segment …) string; empty string if zero-length."""
    if abs(x1-x2) < 0.001 and abs(y1-y2) < 0.001:
        return ""
    return (f'\t(segment\n'
            f'\t\t(start {x1:.4f} {y1:.4f})\n'
            f'\t\t(end   {x2:.4f} {y2:.4f})\n'
            f'\t\t(width {width})\n'
            f'\t\t(layer "{layer}")\n'
            f'\t\t(net "{net}")\n'
            f'\t\t(uuid "{new_uuid()}")\n'
            f'\t)')

def route_via_y(x1, y1, x2, y2, net, w, via_y, layer="F.Cu"):
    """Z-shape: vert→ horiz at via_y → vert."""
    return [s for s in [
        seg(x1, y1,    x1, via_y, net, w, layer),
        seg(x1, via_y, x2, via_y, net, w, layer),
        seg(x2, via_y, x2, y2,   net, w, layer),
    ] if s]

def route_L(x1, y1, x2, y2, net, w, layer="F.Cu", horiz_first=True):
    """Simple L-shape (or straight if already aligned)."""
    if abs(x1-x2) < 0.001:
        return [s for s in [seg(x1,y1,x2,y2,net,w,layer)] if s]
    if abs(y1-y2) < 0.001:
        return [s for s in [seg(x1,y1,x2,y2,net,w,layer)] if s]
    if horiz_first:
        return [s for s in [seg(x1,y1,x2,y1,net,w,layer),
                             seg(x2,y1,x2,y2,net,w,layer)] if s]
    else:
        return [s for s in [seg(x1,y1,x1,y2,net,w,layer),
                             seg(x1,y2,x2,y2,net,w,layer)] if s]

def dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

def nn_order(pads):
    """Nearest-neighbour chain through pads."""
    if len(pads) <= 1:
        return list(pads)
    rem = list(pads)
    ordered = [rem.pop(0)]
    while rem:
        last = ordered[-1]
        closest = min(rem, key=lambda p: dist(p[:2], last[:2]))
        rem.remove(closest)
        ordered.append(closest)
    return ordered

# ── parse pad positions from PCB ──────────────────────────────────────────
with open(BOARD_FILE, 'r', encoding='utf-8') as f:
    text = f.read()

fp_pattern = re.compile(r'\t\(footprint\s+"[^"]*".*?^\t\)', re.DOTALL|re.MULTILINE)
at_fp_re   = re.compile(r'^\t\t\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)', re.MULTILINE)
ref_re     = re.compile(r'\(property\s+"Reference"\s+"([^"]+)"')
pad_re     = re.compile(
    r'\(pad\s+"([^"]*)"\s+\S+\s+\S+\s*\n\s+\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+[-\d.]+)?\)',
    re.MULTILINE)
net_in_pad = re.compile(r'\(net\s+"([^"]+)"\)')

def rotate(px, py, deg):
    if abs(deg) < 0.01:
        return px, py
    r = math.radians(-deg)
    return px*math.cos(r)-py*math.sin(r), px*math.sin(r)+py*math.cos(r)

pads_by_net = {}
for fp_m in fp_pattern.finditer(text):
    block = fp_m.group()
    at_m  = at_fp_re.search(block)
    if not at_m:
        continue
    cx, cy = float(at_m.group(1)), float(at_m.group(2))
    rot    = float(at_m.group(3)) if at_m.group(3) else 0.0
    ref_m  = ref_re.search(block)
    ref    = ref_m.group(1) if ref_m else "?"

    for pad_m in pad_re.finditer(block):
        lpx, lpy = float(pad_m.group(2)), float(pad_m.group(3))
        pad_start = pad_m.start()
        depth, pos = 0, pad_start
        for ch in block[pad_start:]:
            if ch == '(':  depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0: break
            pos += 1
        pad_block = block[pad_start:pos+1]
        net_m = net_in_pad.search(pad_block)
        if not net_m or not net_m.group(1):
            continue
        net_name = net_m.group(1)
        rx, ry = rotate(lpx, lpy, rot)
        pads_by_net.setdefault(net_name, []).append(
            (cx+rx, cy+ry, ref, pad_m.group(1)))

print("Pads found:")
for name, pl in sorted(pads_by_net.items()):
    print(f"  {name:10s}: " + ", ".join(f"{r}.{n}({x:.2f},{y:.2f})" for x,y,r,n in pl))

# ── routing helpers ───────────────────────────────────────────────────────
all_segs = []

def chain(pads, net, w, layer, via_y=None):
    """Chain pads in NN order; use via_y bus if given, else simple L."""
    ordered = nn_order([(x,y,r,n) for x,y,r,n in pads])
    segs = []
    for i in range(len(ordered)-1):
        x1,y1,r1,n1 = ordered[i]
        x2,y2,r2,n2 = ordered[i+1]
        print(f"    {r1}.{n1}({x1:.2f},{y1:.2f}) → {r2}.{n2}({x2:.2f},{y2:.2f})")
        if via_y is not None:
            segs += route_via_y(x1,y1,x2,y2,net,w,via_y,layer)
        else:
            segs += route_L(x1,y1,x2,y2,net,w,layer)
    return segs

# ── SOLAR+ ── simple L on F.Cu ────────────────────────────────────────────
print("\nSOLAR+:")
all_segs += chain(pads_by_net.get("SOLAR+",[]), "SOLAR+", POWER_W, "F.Cu")

# ── BATT+ ── bus at Y=34 on F.Cu ─────────────────────────────────────────
print("\nBATT+:")
all_segs += chain(pads_by_net.get("BATT+",[]), "BATT+", POWER_W, "F.Cu", via_y=34)

# ── +5V ── SENSE-zone-aware routing on F.Cu ──────────────────────────────
# SENSE zone: X=34..58, Y=19..36.
# SENSE traces within the zone:
#   • Horiz at Y=20 from X=42.62→57.07
#   • Vert  at X=57.07 from Y=20→35
#   • Horiz at Y=35 from X=57.07→35
#
# Safe transit columns / rows (all on F.Cu, no SENSE or BATT+ traces):
#   BYPASS_X_LEFT = 33   (left of zone; BATT+ bus ends at X=41.43 so Y=34 is blocked
#                          at X=33 — we stay above zone at Y=18 when crossing X=33)
#   BYPASS_Y_TOP  = 18   (above SENSE_YMIN=19 AND above SOLAR+ horiz at Y=18.73
#                          AND above BATT+ bus at Y=34)
#   BYPASS_X      = 61   (right of zone AND right of BATT+ bus which ends at X=41.43)
#
# Routing rules per pair:
#   Pad in zone → exit LEFT (horiz to X=33), UP (vert to Y=18), RIGHT (horiz
#                 to BYPASS_X=61), then L-shape to destination.
#   Pad outside zone but route clips zone → use bypass right (BYPASS_X) or
#                 bypass via top (BYPASS_Y_TOP) as appropriate.

BYPASS_X_LEFT = 33.0
BYPASS_Y_TOP  = 18.0

def in_sx(x): return SENSE_XMIN < x < SENSE_XMAX
def in_sy(y): return SENSE_YMIN < y < SENSE_YMAX
def in_zone(x, y): return in_sx(x) and in_sy(y)

def route_5v_pair(x1, y1, x2, y2):
    p1z = in_zone(x1, y1)
    p2z = in_zone(x2, y2)
    clips = ((in_sx(x1) or in_sx(x2)) and
             min(y1,y2) < SENSE_YMAX and max(y1,y2) > SENSE_YMIN)

    if not clips and not p1z and not p2z:
        # Completely clear — simple L
        return route_L(x1,y1,x2,y2,"+5V",POWER_W,"F.Cu")

    if p1z and p2z:
        # Both pads inside zone: route via left bypass column (X=33), never crosses SENSE vert
        print(f"      → both-in-zone, left bypass X={BYPASS_X_LEFT}")
        return [s for s in [
            seg(x1,y1, BYPASS_X_LEFT,y1,          "+5V",POWER_W,"F.Cu"),
            seg(BYPASS_X_LEFT,y1, BYPASS_X_LEFT,y2, "+5V",POWER_W,"F.Cu"),
            seg(BYPASS_X_LEFT,y2, x2,y2,           "+5V",POWER_W,"F.Cu"),
        ] if s]

    if p1z and not p2z:
        # Start inside zone: exit LEFT→UP→RIGHT, then L-shape down to p2
        print(f"      → zone-exit left+top, then right column to dest")
        return [s for s in [
            seg(x1,y1,  BYPASS_X_LEFT,y1,          "+5V",POWER_W,"F.Cu"),
            seg(BYPASS_X_LEFT,y1,  BYPASS_X_LEFT,BYPASS_Y_TOP, "+5V",POWER_W,"F.Cu"),
            seg(BYPASS_X_LEFT,BYPASS_Y_TOP,  BYPASS_X,BYPASS_Y_TOP, "+5V",POWER_W,"F.Cu"),
            seg(BYPASS_X,BYPASS_Y_TOP,  BYPASS_X,y2,  "+5V",POWER_W,"F.Cu"),
            seg(BYPASS_X,y2,  x2,y2,              "+5V",POWER_W,"F.Cu"),
        ] if s]

    if not p1z and p2z:
        # End inside zone: approach from LEFT via top transit
        print(f"      → approach zone from left via top transit")
        return [s for s in [
            seg(x1,y1,  x1,BYPASS_Y_TOP,            "+5V",POWER_W,"F.Cu"),
            seg(x1,BYPASS_Y_TOP,  BYPASS_X_LEFT,BYPASS_Y_TOP, "+5V",POWER_W,"F.Cu"),
            seg(BYPASS_X_LEFT,BYPASS_Y_TOP,  BYPASS_X_LEFT,y2, "+5V",POWER_W,"F.Cu"),
            seg(BYPASS_X_LEFT,y2,  x2,y2,           "+5V",POWER_W,"F.Cu"),
        ] if s]

    # No pad in zone but route clips it — use right bypass column
    print(f"      → bypass-right via X={BYPASS_X}")
    return [s for s in [
        seg(x1,y1,  BYPASS_X,y1,  "+5V",POWER_W,"F.Cu"),
        seg(BYPASS_X,y1,  BYPASS_X,y2,  "+5V",POWER_W,"F.Cu"),
        seg(BYPASS_X,y2,  x2,y2,        "+5V",POWER_W,"F.Cu"),
    ] if s]

print("\n+5V (SENSE-zone-aware):")
fv_pads = pads_by_net.get("+5V", [])
fv_ord  = nn_order([(x,y,r,n) for x,y,r,n in fv_pads])
for i in range(len(fv_ord)-1):
    x1,y1,r1,n1 = fv_ord[i]
    x2,y2,r2,n2 = fv_ord[i+1]
    print(f"    {r1}.{n1}({x1:.2f},{y1:.2f}) → {r2}.{n2}({x2:.2f},{y2:.2f})")
    all_segs += route_5v_pair(x1,y1,x2,y2)

# ── SENSE ── pair-aware L-routing on F.Cu ────────────────────────────────
# Pair 0→1: horiz-first (goes across then down to mid-pad)
# Pair 1→2: vert-first  (avoids BATT+ horizontal bus at Y=34)
print("\nSENSE:")
sp     = pads_by_net.get("SENSE", [])
sp_ord = nn_order([(x,y,r,n) for x,y,r,n in sp])
for i in range(len(sp_ord)-1):
    x1,y1,r1,n1 = sp_ord[i]
    x2,y2,r2,n2 = sp_ord[i+1]
    print(f"    {r1}.{n1}({x1:.2f},{y1:.2f}) → {r2}.{n2}({x2:.2f},{y2:.2f})")
    # Use vert-first for pairs after the first to avoid crossing BATT+ bus
    hf = (i == 0)
    all_segs += route_L(x1,y1,x2,y2,"SENSE",SIGNAL_W,"F.Cu",horiz_first=hf)

# ── GND ── ALL on B.Cu, bus at Y=47 ──────────────────────────────────────
# B.Cu is GND-only so GND segments never short against other nets.
# Y=47 is ~1.5 mm below the deepest GND pad (C1.2 ≈ Y=45.5) and leaves
# 3 mm clearance to the board bottom at Y=50.
print("\nGND (B.Cu, bus Y=47):")
all_segs += chain(pads_by_net.get("GND",[]), "GND", POWER_W, "B.Cu", via_y=47)

print(f"\nTotal segments: {len(all_segs)}")

# ── write back ────────────────────────────────────────────────────────────
seg_re   = re.compile(r'^\s+\(segment\b.*?^\s+\)\n', re.DOTALL|re.MULTILINE)
text_out = seg_re.sub('', text)
text_out = re.sub(r'\n{3,}', '\n\n', text_out)

insert_re = re.compile(r'^(\t\t\(embedded_fonts no\)\n\))', re.MULTILINE)
new_block = '\n'.join(all_segs) + '\n'
text_out  = insert_re.sub(new_block + r'\1', text_out)

with open(BOARD_FILE, 'w', encoding='utf-8') as f:
    f.write(text_out)

print("Saved. Open in KiCad and run DRC to verify.")
