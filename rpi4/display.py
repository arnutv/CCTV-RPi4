#!/usr/bin/env python3
"""
CCTV Display  —  native HDMI grid renderer for low-RAM Raspberry Pi.

Renders all camera MJPEG streams in a 3×2 grid directly to the framebuffer
via pygame/SDL2 (KMSDRM driver — no X server, no browser).  ~80 MB RAM total.

Auto-starts on boot via cctv-display.service when install.sh runs in LITE mode.
Exit with Esc or Q on a connected keyboard, or `sudo systemctl stop cctv-display`.
"""

import os, io, sys, json, time, threading, urllib.request
from datetime import datetime
import pygame

# ── Config ────────────────────────────────────────────────────────────────
SERVER_BASE      = "http://localhost:8080"   # local Flask server
POLL_INTERVAL    = 3.0     # /status poll every N seconds
STREAM_RECONNECT = 5.0     # seconds before retrying a failed stream
FPS              = 25      # render frame rate
HTTP_TIMEOUT     = 5       # seconds

# Colours
BG     = (10, 12, 15)
WHITE  = (240, 240, 240)
DIM    = (140, 140, 140)
GREEN  = (63, 185, 80)
RED    = (248, 81, 73)
AMBER  = (210, 153, 34)
GREY   = (40, 40, 40)

# Shared state — written by worker threads, read by render loop
CAMERAS  = []
frames   = {}   # cam_id  → pygame.Surface or None  (None = offline)
statuses = {}   # cam_id  → {"motion": bool, "recording": bool, "batt_pct": int}
running  = True

# ── MJPEG stream reader (one thread per camera) ───────────────────────────
def stream_worker(cam):
    """Continuously pull JPEG frames from one camera's MJPEG endpoint."""
    url = f"http://{cam['ip']}:81/"
    while running:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cctv-display/1.0"})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                buf = b""
                while running:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    buf += chunk
                    # Cap buffer size so a misbehaving stream can't fill RAM
                    if len(buf) > 1024 * 1024:
                        buf = buf[-512 * 1024:]
                    # Parse JPEGs: SOI (FF D8) ... EOI (FF D9)
                    while True:
                        soi = buf.find(b"\xff\xd8")
                        if soi < 0:
                            buf = b""
                            break
                        eoi = buf.find(b"\xff\xd9", soi + 2)
                        if eoi < 0:
                            buf = buf[soi:]
                            break
                        jpeg = buf[soi:eoi + 2]
                        buf  = buf[eoi + 2:]
                        try:
                            surf = pygame.image.load(io.BytesIO(jpeg))
                            frames[cam["id"]] = surf.convert()
                        except Exception:
                            pass
        except Exception:
            pass
        frames[cam["id"]] = None        # mark offline
        time.sleep(STREAM_RECONNECT)

# ── Status poller (one thread per camera) ─────────────────────────────────
def status_worker(cam):
    """Poll /status endpoint of each camera for motion / battery / recording."""
    url = f"http://{cam['ip']}/status"
    while running:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                statuses[cam["id"]] = json.loads(resp.read().decode())
        except Exception:
            statuses.pop(cam["id"], None)
        time.sleep(POLL_INTERVAL)

# ── Fetch camera list from the local Flask server ─────────────────────────
def load_cameras(timeout=60):
    """Wait for cctv_server to come up, then fetch the camera list."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{SERVER_BASE}/api/cameras", timeout=2) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(2)
    sys.exit(f"display.py: could not reach {SERVER_BASE} — is cctv-server running?")

# ── Rendering ─────────────────────────────────────────────────────────────
def render_cell(screen, cam, rect, font_name, font_hud):
    x, y, w, h = rect
    pygame.draw.rect(screen, (5, 5, 5), rect)

    # Live frame (or NO SIGNAL)
    surf = frames.get(cam["id"])
    if surf:
        sw, sh = surf.get_size()
        scale  = min(w / sw, h / sh)
        nw, nh = int(sw * scale), int(sh * scale)
        scaled = pygame.transform.scale(surf, (nw, nh))
        screen.blit(scaled, (x + (w - nw) // 2, y + (h - nh) // 2))
    else:
        msg = font_name.render("NO SIGNAL", True, GREY)
        screen.blit(msg, (x + (w - msg.get_width()) // 2,
                          y + (h - msg.get_height()) // 2))

    # Bottom gradient overlay
    grad_h = 46
    grad   = pygame.Surface((w, grad_h), pygame.SRCALPHA)
    for i in range(grad_h):
        a = int(220 * (i / grad_h))
        pygame.draw.line(grad, (0, 0, 0, a), (0, i), (w, i))
    screen.blit(grad, (x, y + h - grad_h))

    # Camera name (bottom-left)
    name = font_name.render(cam["name"], True, WHITE)
    screen.blit(name, (x + 10, y + h - 30))

    # Status row (bottom-right)
    st = statuses.get(cam["id"])
    rx = x + w - 12
    ry = y + h - 22
    if st:
        # Status dot
        dot = RED if st.get("motion") else GREEN
        pygame.draw.circle(screen, dot, (rx, ry + 6), 5)
        rx -= 14
        # Battery %
        bp = st.get("batt_pct")
        if bp is not None:
            btxt = font_hud.render(f"{bp}%", True, DIM)
            rx  -= btxt.get_width()
            screen.blit(btxt, (rx, ry))
            rx  -= 10
        # REC indicator
        if st.get("recording"):
            rec = font_hud.render("● REC", True, RED)
            rx -= rec.get_width()
            screen.blit(rec, (rx, ry))
    else:
        # Offline dot
        pygame.draw.circle(screen, GREY, (rx, ry + 6), 5)

    # Motion alert: pulsing red border
    if st and st.get("motion"):
        phase = (time.time() * 2) % 2
        if phase < 1:
            pygame.draw.rect(screen, RED, rect, 3)

def render(screen, fonts, screen_w, screen_h):
    f_name, f_clock, f_hud = fonts
    screen.fill(BG)

    # 3×2 grid layout
    rows, cols = 2, 3
    gap        = 2
    cell_w     = (screen_w - gap * (cols - 1)) // cols
    cell_h     = (screen_h - gap * (rows - 1)) // rows

    for i, cam in enumerate(CAMERAS[: rows * cols]):
        r, c = divmod(i, cols)
        rect = (c * (cell_w + gap), r * (cell_h + gap), cell_w, cell_h)
        render_cell(screen, cam, rect, f_name, f_hud)

    # HUD — clock top-right
    now   = datetime.now()
    clk   = f_clock.render(now.strftime("%H:%M:%S"), True, DIM)
    dte   = f_hud.render(now.strftime("%Y-%m-%d"), True, DIM)
    screen.blit(clk, (screen_w - clk.get_width() - 14, 8))
    screen.blit(dte, (screen_w - dte.get_width() - 14, 30))

    # HUD — count top-left
    online = sum(1 for c in CAMERAS if frames.get(c["id"]) is not None)
    msg    = f_hud.render(f"{online}/{len(CAMERAS)} online", True, DIM)
    screen.blit(msg, (14, 12))

    pygame.display.flip()

# ── Main ──────────────────────────────────────────────────────────────────
def main():
    global CAMERAS, running

    # Use KMSDRM driver — direct framebuffer access, no X server needed
    os.environ.setdefault("SDL_VIDEODRIVER", "kmsdrm")
    # Hide the SDL audio init (we don't use sound)
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    pygame.init()
    pygame.mouse.set_visible(False)

    try:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN | pygame.NOFRAME)
    except pygame.error as e:
        sys.exit(f"display.py: pygame display init failed — {e}\n"
                 f"Is an HDMI monitor connected? Is the user in 'video','render' groups?")
    screen_w, screen_h = screen.get_size()
    pygame.display.set_caption("CCTV Display")

    # Fonts (default DejaVu shipped with pygame)
    f_name  = pygame.font.Font(None, 22)
    f_clock = pygame.font.Font(None, 26)
    f_hud   = pygame.font.Font(None, 16)

    # Get camera list from local Flask
    CAMERAS = load_cameras()
    print(f"display.py: rendering {len(CAMERAS)} cameras at {screen_w}×{screen_h}")

    # Spawn worker threads
    for cam in CAMERAS:
        threading.Thread(target=stream_worker, args=(cam,), daemon=True).start()
        threading.Thread(target=status_worker, args=(cam,), daemon=True).start()

    clock = pygame.time.Clock()
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN and ev.key in (pygame.K_ESCAPE, pygame.K_q):
                running = False
        render(screen, (f_name, f_clock, f_hud), screen_w, screen_h)
        clock.tick(FPS)

    pygame.quit()

if __name__ == "__main__":
    main()
