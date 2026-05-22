#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# CCTV-RPi  —  One-shot setup for Raspberry Pi 4 or 5  (any RAM, even 1 GB)
# ═══════════════════════════════════════════════════════════════════════════════
# Run once as root on a fresh Raspberry Pi OS (64-bit, Bookworm):
#
#   sudo bash install.sh
#
# What this does
# ──────────────
#  1. Detects board model + total RAM → picks an adaptive config:
#       LITE  (RAM <  1.5 GB) → native pygame HDMI display (~80 MB), gpu_mem=32, zram on
#       MID   (RAM 1.5–3 GB)  → Chromium kiosk (trimmed flags), gpu_mem=64
#       FULL  (RAM ≥ 4 GB)    → full Chromium kiosk, gpu_mem=128
#  2. Installs core packages (hostapd, dnsmasq, flask).
#       LITE → adds python3-pygame for the native HDMI grid display
#       MID/FULL → adds chromium-browser + unclutter for kiosk mode
#  3. Configures wlan0 → 192.168.4.1, WPA2 AP "CCTV_Network"
#  4. dnsmasq DHCP pool 192.168.4.10–200
#  5. Patches /boot/firmware/config.txt (gpu_mem, hdmi_blanking, fan for RPi 5)
#  6. Adds 512 MB zram swap (compressed in-RAM swap, free extra memory headroom)
#  7. Disables bluetooth + avahi + cups + triggerhappy (saves ~80 MB RAM)
#  8. Deploys cctv_server.py as a systemd service with strict MemoryMax limit
#  9. LITE → deploys display.py as cctv-display.service on tty1 (HDMI works on 1 GB!)
# 10. MID/FULL → enables auto-login + Chromium kiosk autostart on HDMI
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}  $*"; }
info() { echo -e "${YELLOW}[..] $*${NC}"; }
note() { echo -e "${BLUE}[i ]${NC}  $*"; }
err()  { echo -e "${RED}[ERR]${NC} $*" >&2; }

# ── Root check ────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  err "Run as root:  sudo bash install.sh"
  exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# 0. DETECT BOARD + RAM → pick install mode
# ─────────────────────────────────────────────────────────────────────────────
RAM_MB=$(awk '/MemTotal/{printf "%d", $2/1024}' /proc/meminfo)
MODEL=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo "Unknown")
IS_RPI5=0
[[ "$MODEL" == *"Raspberry Pi 5"* ]] && IS_RPI5=1

# Pick mode based on RAM
if   (( RAM_MB <  1500 )); then MODE="LITE"; GPU_MEM=32;  KIOSK=0
elif (( RAM_MB <= 3000 )); then MODE="MID";  GPU_MEM=64;  KIOSK=1
else                            MODE="FULL"; GPU_MEM=128; KIOSK=1
fi

echo ""
echo -e "${BLUE}══════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Board : ${NC}$MODEL"
echo -e "${BLUE}  RAM   : ${NC}${RAM_MB} MB"
echo -e "${BLUE}  Mode  : ${NC}$MODE   (gpu_mem=${GPU_MEM}, kiosk=$([[ $KIOSK == 1 ]] && echo yes || echo no))"
echo -e "${BLUE}══════════════════════════════════════════════════${NC}"
echo ""

# ── Detect desktop user (the one who runs Chromium when applicable) ──────────
DESK_USER="${SUDO_USER:-pi}"
DESK_HOME=$(eval echo "~$DESK_USER")
note "Desktop user: $DESK_USER  (home: $DESK_HOME)"

# ─────────────────────────────────────────────────────────────────────────────
# 1. PACKAGES
# ─────────────────────────────────────────────────────────────────────────────
info "Installing core packages..."
apt-get update -qq
CORE_PKGS="hostapd dnsmasq python3-flask zram-tools"
EXTRA_PKGS=""
if [[ $KIOSK == 1 ]]; then
  EXTRA_PKGS="unclutter xdotool chromium-browser"
else
  # LITE mode → native pygame HDMI display (no browser, no X server)
  EXTRA_PKGS="python3-pygame fonts-dejavu-core"
fi

# shellcheck disable=SC2086
apt-get install -y --no-install-recommends $CORE_PKGS $EXTRA_PKGS
systemctl unmask hostapd
ok "Packages installed."

# ─────────────────────────────────────────────────────────────────────────────
# 2. DISABLE UNUSED SERVICES → reclaim ~80 MB RAM
# ─────────────────────────────────────────────────────────────────────────────
info "Disabling unused services..."
for svc in bluetooth hciuart avahi-daemon triggerhappy cups cups-browsed ModemManager; do
  systemctl disable --now "$svc" 2>/dev/null || true
done
ok "Background services trimmed."

# ─────────────────────────────────────────────────────────────────────────────
# 3. ZRAM — compressed swap in RAM (huge win on 1 GB boards)
# ─────────────────────────────────────────────────────────────────────────────
info "Configuring zram (compressed swap)..."
cat > /etc/default/zramswap <<'EOF'
# CCTV-RPi zramswap — gives ~50% more usable memory via compression
ALGO=zstd
PERCENT=50
PRIORITY=100
EOF
systemctl enable --now zramswap.service 2>/dev/null || true
ok "zram swap enabled (50% of RAM, zstd compressed)."

# ─────────────────────────────────────────────────────────────────────────────
# 4. WiFi AP — static IP for wlan0 (handles both NetworkManager and dhcpcd)
# ─────────────────────────────────────────────────────────────────────────────
info "Configuring wlan0 static IP (192.168.4.1)..."

if systemctl is-active --quiet NetworkManager; then
  # Bookworm 2023+ default: NetworkManager
  nmcli con delete cctv-ap 2>/dev/null || true
  nmcli con add type wifi ifname wlan0 con-name cctv-ap autoconnect yes \
        ssid CCTV_Network 802-11-wireless.mode ap 802-11-wireless.band bg \
        ipv4.method shared ipv4.addresses 192.168.4.1/24 \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "cctv1234!!"
  ok "NetworkManager AP profile created."
else
  # Older dhcpcd path
  DHCPCD=/etc/dhcpcd.conf
  if ! grep -q "# CCTV-AP" "$DHCPCD" 2>/dev/null; then
    cat >> "$DHCPCD" <<'EOF'

# CCTV-AP — added by install.sh
interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
EOF
  fi
  ok "dhcpcd configured."

  # hostapd config (only needed in dhcpcd mode; NM handles it internally)
  cat > /etc/hostapd/hostapd.conf <<'EOF'
interface=wlan0
driver=nl80211
ssid=CCTV_Network
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=cctv1234!!
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF
  sed -i 's|#\?DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd
  systemctl enable hostapd

  # dnsmasq
  [[ -f /etc/dnsmasq.conf.orig ]] || cp /etc/dnsmasq.conf /etc/dnsmasq.conf.orig
  cat > /etc/dnsmasq.conf <<'EOF'
# CCTV-RPi dnsmasq
interface=wlan0
dhcp-range=192.168.4.10,192.168.4.200,255.255.255.0,24h
domain=cctv.local
address=/cctv.local/192.168.4.1
EOF
  systemctl enable dnsmasq
  ok "hostapd + dnsmasq configured."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 5. config.txt — GPU memory, HDMI, RPi 5 fan curve
# ─────────────────────────────────────────────────────────────────────────────
CONFIG_TXT=/boot/firmware/config.txt
[[ -f $CONFIG_TXT ]] || CONFIG_TXT=/boot/config.txt
info "Patching $CONFIG_TXT..."

# GPU memory — depends on mode
if grep -q "^gpu_mem=" "$CONFIG_TXT"; then
  sed -i "s/^gpu_mem=.*/gpu_mem=${GPU_MEM}/" "$CONFIG_TXT"
else
  echo "gpu_mem=${GPU_MEM}" >> "$CONFIG_TXT"
fi

# HDMI never blank (only needed if kiosk enabled, but harmless otherwise)
grep -q "^hdmi_blanking=" "$CONFIG_TXT" || echo "hdmi_blanking=2" >> "$CONFIG_TXT"

# RPi 5: enable PWM fan curve (uses official Active Cooler)
if (( IS_RPI5 == 1 )); then
  grep -q "^dtparam=fan_temp" "$CONFIG_TXT" || cat >> "$CONFIG_TXT" <<'EOF'

# RPi 5 fan curve — keep CPU below 60°C
dtparam=fan_temp0=50000,fan_temp0_hyst=5000,fan_temp0_speed=80
dtparam=fan_temp1=60000,fan_temp1_hyst=5000,fan_temp1_speed=150
dtparam=fan_temp2=68000,fan_temp2_hyst=5000,fan_temp2_speed=200
dtparam=fan_temp3=75000,fan_temp3_hyst=5000,fan_temp3_speed=255
EOF
  ok "RPi 5 fan curve added."
fi

# Disable Bluetooth at firmware level (saves another ~10 MB)
grep -q "^dtoverlay=disable-bt" "$CONFIG_TXT" || echo "dtoverlay=disable-bt" >> "$CONFIG_TXT"

ok "config.txt patched (gpu_mem=${GPU_MEM}, hdmi_blanking=2, bt off)."

# ─────────────────────────────────────────────────────────────────────────────
# 6. DEPLOY cctv_server.py
# ─────────────────────────────────────────────────────────────────────────────
info "Deploying cctv_server.py..."
install -m 644 "$SCRIPT_DIR/cctv_server.py" /opt/cctv_server.py
RECDIR=/opt/cctv_recordings
mkdir -p "$RECDIR"
chown "$DESK_USER:$DESK_USER" "$RECDIR" /opt/cctv_server.py

# LITE mode → also deploy the native pygame HDMI display
if [[ $KIOSK == 0 && -f "$SCRIPT_DIR/display.py" ]]; then
  install -m 644 "$SCRIPT_DIR/display.py" /opt/cctv_display.py
  chown "$DESK_USER:$DESK_USER" /opt/cctv_display.py
  ok "display.py deployed."
fi

# ─────────────────────────────────────────────────────────────────────────────
# 7. SYSTEMD SERVICE — cctv-server (with strict memory limit)
# ─────────────────────────────────────────────────────────────────────────────
info "Creating systemd service: cctv-server..."

# Memory cap scales with available RAM
if   (( RAM_MB < 1500 )); then MEM_MAX=250M
elif (( RAM_MB < 3000 )); then MEM_MAX=400M
else                           MEM_MAX=600M
fi

cat > /etc/systemd/system/cctv-server.service <<EOF
[Unit]
Description=CCTV Flask Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/cctv_server.py
WorkingDirectory=/opt
Restart=always
User=$DESK_USER
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONHASHSEED=random

# Memory safety net — kill + restart if it ever balloons
MemoryMax=$MEM_MAX
MemoryHigh=$MEM_MAX
OOMScoreAdjust=-100

# Limit number of file descriptors (no need for many)
LimitNOFILE=1024

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable cctv-server
ok "cctv-server service created (MemoryMax=$MEM_MAX)."

# ─────────────────────────────────────────────────────────────────────────────
# 8. CHROMIUM KIOSK — only if we have RAM for it
# ─────────────────────────────────────────────────────────────────────────────
if (( KIOSK == 1 )); then
  info "Setting up Chromium kiosk autostart..."

  # Enable desktop auto-login
  raspi-config nonint do_boot_behaviour B4 2>/dev/null || {
    LXCONF=/etc/lightdm/lightdm.conf
    if [[ -f $LXCONF ]]; then
      sed -i "s/^#\?autologin-user=.*/autologin-user=$DESK_USER/" "$LXCONF"
      sed -i 's/^#\?autologin-user-timeout=.*/autologin-user-timeout=0/' "$LXCONF"
    fi
  }

  AUTOSTART_DIR="$DESK_HOME/.config/autostart"
  mkdir -p "$AUTOSTART_DIR"

  # Trim Chromium memory flags for low-RAM
  if [[ $MODE == "MID" ]]; then
    CHROME_FLAGS="--kiosk --noerrdialogs --disable-infobars --no-first-run \
--js-flags=--max-old-space-size=128 \
--memory-pressure-off \
--renderer-process-limit=1 \
--disable-features=TranslateUI \
--disable-extensions \
--autoplay-policy=no-user-gesture-required"
  else
    CHROME_FLAGS="--kiosk --noerrdialogs --disable-infobars --no-first-run \
--enable-gpu-rasterization --enable-zero-copy --ignore-gpu-blocklist \
--autoplay-policy=no-user-gesture-required"
  fi

  cat > "$AUTOSTART_DIR/cctv-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=CCTV Kiosk
Comment=Open CCTV display in fullscreen Chromium
Exec=bash -c 'sleep 5 && chromium-browser $CHROME_FLAGS http://192.168.4.1:8080/display'
X-GNOME-Autostart-enabled=true
EOF

  cat > "$AUTOSTART_DIR/unclutter.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Unclutter
Exec=unclutter -idle 3 -root
X-GNOME-Autostart-enabled=true
EOF

  cat > "$AUTOSTART_DIR/disable-screensaver.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Disable Screensaver
Exec=bash -c 'xset s off && xset -dpms && xset s noblank'
X-GNOME-Autostart-enabled=true
EOF

  chown -R "$DESK_USER:$DESK_USER" "$AUTOSTART_DIR"
  ok "Chromium kiosk autostart created ($MODE mode flags)."
else
  # ────────────────────────────────────────────────────────────────────
  # LITE mode → native pygame HDMI display on tty1 (no X, no browser)
  # ────────────────────────────────────────────────────────────────────
  info "LITE mode: setting up native pygame display on tty1..."
  systemctl set-default multi-user.target          # boot to text console (no GUI)
  systemctl disable lightdm 2>/dev/null || true    # ensure no X server starts

  # Add user to groups needed for KMSDRM framebuffer access
  usermod -aG video,render,input "$DESK_USER" 2>/dev/null || true

  # Stop login prompt on tty1 — display takes it over
  systemctl disable getty@tty1.service 2>/dev/null || true

  cat > /etc/systemd/system/cctv-display.service <<EOF
[Unit]
Description=CCTV HDMI Display (native pygame)
After=cctv-server.service
Wants=cctv-server.service
Conflicts=getty@tty1.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/cctv_display.py
Restart=on-failure
RestartSec=5
User=$DESK_USER
SupplementaryGroups=video render input
Environment=SDL_VIDEODRIVER=kmsdrm
Environment=SDL_AUDIODRIVER=dummy
Environment=PYTHONUNBUFFERED=1
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
StandardInput=tty
StandardOutput=journal
StandardError=journal

# Memory cap — display.py should never exceed 200 MB
MemoryMax=200M

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable cctv-display
  ok "cctv-display service created (MemoryMax=200M, auto-starts on tty1)."
  note "After reboot, HDMI shows the 3×2 grid automatically — no login screen."
fi

# ─────────────────────────────────────────────────────────────────────────────
# DONE
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  CCTV-RPi installation complete  —  Mode: $MODE${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  WiFi AP  : ${YELLOW}SSID=CCTV_Network  Pass=cctv1234!!${NC}"
echo -e "  RPi IP   : ${YELLOW}192.168.4.1${NC}"
echo -e "  Dashboard: ${YELLOW}http://192.168.4.1:8080/${NC}   (from phone / laptop)"
if (( KIOSK == 1 )); then
  echo -e "  HDMI view: ${YELLOW}Chromium kiosk @ /display (auto-starts on HDMI)${NC}"
else
  echo -e "  HDMI view: ${YELLOW}native pygame grid (auto-starts on HDMI, ~80 MB RAM)${NC}"
  echo -e "             ${BLUE}Press Esc/Q on a keyboard to exit, or:${NC}"
  echo -e "             ${BLUE}sudo systemctl stop cctv-display${NC}"
fi
echo ""
echo -e "  RAM after boot will show as:  total ${RAM_MB} MB + ~${RAM_MB}/2 MB zram swap"
echo -e "  cctv-server is capped at:      $MEM_MAX (auto-restart if exceeded)"
echo ""
echo -e "  ${YELLOW}Reboot now to apply all changes:${NC}  sudo reboot"
echo ""
echo "  Optional: bridge internet from your home router after reboot:"
echo "            sudo bash connect_router.sh"
echo ""
