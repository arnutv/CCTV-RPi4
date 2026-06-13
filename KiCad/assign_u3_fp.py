import sys, os
sys.path.insert(0, r"C:\Program Files\KiCad\10.0\bin")
import pcbnew

OUT     = r"C:\Users\Admin\OneDrive\Desktop\Arduino Projects\CCTV-RPi4\KiCad"
LIB_DIR = os.path.join(OUT, "CCTV_RPi4.pretty")
pcb_path = os.path.join(OUT, "CCTV_Power.kicad_pcb")

# Step 1: Load custom footprint FIRST (before any board operations)
fp = pcbnew.FootprintLoad(LIB_DIR, "ESP32-CAM_AI-Thinker")
if fp is None:
    print("ERROR: FootprintLoad returned None - check .kicad_mod file")
    sys.exit(1)
print("Footprint loaded OK, pads:", len(list(fp.Pads())))

# Step 2: Load board
board = pcbnew.LoadBoard(pcb_path)
print("Board loaded OK")

# Step 3: Remove old U3
for bfp in list(board.GetFootprints()):
    if bfp.GetReference() == "U3":
        board.Remove(bfp)
        print("Removed old U3")
        break

# Step 4: Assign nets to the new footprint's pads
net_map = {
    "1":  "GND",
    "9":  "+5V",
    "10": "GND",
    "16": "GND",
    "4":  "SENSE",   # IO13 -> battery sense ADC (GPIO33)
}
for pad in list(fp.Pads()):
    net_name = net_map.get(pad.GetNumber())
    if net_name:
        net = board.FindNet(net_name)
        if not net:
            net = pcbnew.NETINFO_ITEM(board, net_name)
            board.Add(net)
        pad.SetNet(net)
        print("  Pad " + pad.GetNumber() + " -> " + net_name)

# Step 5: Set reference, value, position
fp.SetReference("U3")
fp.SetValue("ESP32-CAM")
fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(80), pcbnew.FromMM(25)))

# Step 6: Add to board and save
board.Add(fp)
pcbnew.SaveBoard(pcb_path, board)
print("Saved PCB: " + pcb_path)
print("Done!")
