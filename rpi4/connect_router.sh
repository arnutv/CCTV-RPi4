#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# CCTV-RPi4  —  Optional internet connection (home router bridge)
# ═══════════════════════════════════════════════════════════════════════════════
# Run AFTER install.sh.  Two ways to connect:
#
#   ① Ethernet cable (easiest):
#       sudo bash connect_router.sh eth
#
#   ② USB WiFi dongle (no cable needed):
#       sudo bash connect_router.sh wifi "YourSSID" "YourPassword"
#
#   Auto-detect (tries ethernet first, then USB WiFi):
#       sudo bash connect_router.sh
#
#   Remove internet bridge:
#       sudo bash connect_router.sh --remove
#
# After connecting, cameras on CCTV_Network can reach the internet, and you
# can access the dashboard from your home network as well as the CCTV AP.
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}  $*"; }
info() { echo -e "${YELLOW}[..] $*${NC}"; }
err()  { echo -e "${RED}[ERR]${NC} $*" >&2; }
hdr()  { echo -e "\n${CYAN}── $* ──${NC}"; }

LAN=wlan0          # camera AP interface (never changes)
RULES_FILE=/etc/iptables/rules.v4
WAN=""             # filled in below
MODE=""            # eth | wifi

# ── Root check ────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && { err "Run as root:  sudo bash connect_router.sh [eth|wifi SSID PASS]"; exit 1; }

# ─────────────────────────────────────────────────────────────────────────────
# REMOVE MODE
# ─────────────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--remove" ]]; then
  hdr "Removing internet bridge"

  iptables -t nat -D POSTROUTING -o eth0  -j MASQUERADE 2>/dev/null || true
  iptables -t nat -D POSTROUTING -o wlan1 -j MASQUERADE 2>/dev/null || true
  iptables -D FORWARD -i eth0  -o "$LAN" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
  iptables -D FORWARD -i wlan1 -o "$LAN" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
  iptables -D FORWARD -i "$LAN" -o eth0  -j ACCEPT 2>/dev/null || true
  iptables -D FORWARD -i "$LAN" -o wlan1 -j ACCEPT 2>/dev/null || true

  sysctl -w net.ipv4.ip_forward=0
  sed -i 's/^net\.ipv4\.ip_forward=1/net.ipv4.ip_forward=0/' /etc/sysctl.conf 2>/dev/null || true

  # Stop USB WiFi client if running
  systemctl stop  "wpa_supplicant@wlan1" 2>/dev/null || true
  systemctl disable "wpa_supplicant@wlan1" 2>/dev/null || true

  command -v netfilter-persistent &>/dev/null && netfilter-persistent save
  ok "Internet bridge removed. Cameras still connected to CCTV_Network."
  exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# DETECT MODE
# ─────────────────────────────────────────────────────────────────────────────
ARG1="${1:-auto}"

if [[ "$ARG1" == "eth" ]]; then
  MODE="eth"
  WAN="eth0"

elif [[ "$ARG1" == "wifi" ]]; then
  MODE="wifi"
  WIFI_SSID="${2:-}"
  WIFI_PASS="${3:-}"
  if [[ -z "$WIFI_SSID" || -z "$WIFI_PASS" ]]; then
    err "Usage:  sudo bash connect_router.sh wifi \"SSID\" \"Password\""
    exit 1
  fi
  # Find USB WiFi adapter (wlan1, wlan2, …)
  WAN=$(ip link show 2>/dev/null | grep -oP '(?<=\d: )wlan[1-9]\w*' | head -1 || true)
  if [[ -z "$WAN" ]]; then
    err "No USB WiFi adapter found (expected wlan1+)."
    err "Plug in a USB WiFi dongle and try again."
    exit 1
  fi
  info "USB WiFi adapter found: $WAN"

else
  # Auto-detect: prefer ethernet, fall back to USB WiFi
  info "Auto-detecting internet interface..."
  if ip link show eth0 &>/dev/null && ip link show eth0 | grep -q "state UP"; then
    MODE="eth"; WAN="eth0"
    info "Found: ethernet (eth0)"
  else
    USB_WLAN=$(ip link show 2>/dev/null | grep -oP '(?<=\d: )wlan[1-9]\w*' | head -1 || true)
    if [[ -n "$USB_WLAN" ]]; then
      MODE="wifi"; WAN="$USB_WLAN"
      info "Found: USB WiFi ($WAN)"
      err "For WiFi mode, provide SSID and password:"
      err "  sudo bash connect_router.sh wifi \"SSID\" \"Password\""
      exit 1
    else
      err "No internet interface found."
      echo "  Option 1 — plug in ethernet cable, then:  sudo bash connect_router.sh eth"
      echo "  Option 2 — plug in USB WiFi dongle, then: sudo bash connect_router.sh wifi \"SSID\" \"Pass\""
      exit 1
    fi
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# ETHERNET MODE
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$MODE" == "eth" ]]; then
  hdr "Connecting via Ethernet ($WAN)"

  ip link show "$WAN" &>/dev/null || { err "Interface $WAN not found. Is the cable plugged in?"; exit 1; }

  info "Requesting DHCP lease on $WAN..."
  dhclient -v "$WAN" 2>&1 | grep -E "bound|DHCPACK" || true

  ETH_IP=$(ip -4 addr show "$WAN" | grep -oP '(?<=inet )\d+\.\d+\.\d+\.\d+' | head -1 || true)
  [[ -z "$ETH_IP" ]] && { err "No IP on $WAN — check cable and home router."; exit 1; }
  ok "Ethernet IP: $ETH_IP"
fi

# ─────────────────────────────────────────────────────────────────────────────
# USB WIFI MODE
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$MODE" == "wifi" ]]; then
  hdr "Connecting via USB WiFi ($WAN → $WIFI_SSID)"

  # Write wpa_supplicant config for this interface
  WPA_CONF="/etc/wpa_supplicant/wpa_supplicant-${WAN}.conf"
  cat > "$WPA_CONF" <<EOF
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="$WIFI_SSID"
    psk="$WIFI_PASS"
    key_mgmt=WPA-PSK
}
EOF
  chmod 600 "$WPA_CONF"

  # Start / restart wpa_supplicant for this interface
  systemctl enable  "wpa_supplicant@${WAN}" 2>/dev/null || true
  systemctl restart "wpa_supplicant@${WAN}"

  info "Waiting for $WAN to associate..."
  for i in $(seq 1 20); do
    sleep 1
    STATE=$(wpa_cli -i "$WAN" status 2>/dev/null | grep "^wpa_state=" | cut -d= -f2 || true)
    [[ "$STATE" == "COMPLETED" ]] && break
    echo -n "."
  done
  echo ""

  STATE=$(wpa_cli -i "$WAN" status 2>/dev/null | grep "^wpa_state=" | cut -d= -f2 || true)
  if [[ "$STATE" != "COMPLETED" ]]; then
    err "Could not connect to '$WIFI_SSID'. Check SSID and password."
    exit 1
  fi

  info "Requesting DHCP lease on $WAN..."
  dhclient -v "$WAN" 2>&1 | grep -E "bound|DHCPACK" || true

  ETH_IP=$(ip -4 addr show "$WAN" | grep -oP '(?<=inet )\d+\.\d+\.\d+\.\d+' | head -1 || true)
  [[ -z "$ETH_IP" ]] && { err "No IP on $WAN after WiFi connect."; exit 1; }
  ok "WiFi IP on $WAN: $ETH_IP"
fi

# ─────────────────────────────────────────────────────────────────────────────
# ENABLE IP FORWARDING  (same for both modes)
# ─────────────────────────────────────────────────────────────────────────────
hdr "Enabling IP forwarding and NAT"
sysctl -w net.ipv4.ip_forward=1
if grep -q "^net.ipv4.ip_forward" /etc/sysctl.conf 2>/dev/null; then
  sed -i 's/^net\.ipv4\.ip_forward=.*/net.ipv4.ip_forward=1/' /etc/sysctl.conf
else
  echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
fi
ok "IP forwarding enabled."

# ─────────────────────────────────────────────────────────────────────────────
# IPTABLES NAT
# ─────────────────────────────────────────────────────────────────────────────
# Remove any existing rules first to avoid duplicates
iptables -t nat -D POSTROUTING -o "$WAN" -j MASQUERADE 2>/dev/null || true
iptables -D FORWARD -i "$WAN" -o "$LAN" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
iptables -D FORWARD -i "$LAN" -o "$WAN" -j ACCEPT 2>/dev/null || true

# Add NAT + forward rules
iptables -t nat -A POSTROUTING -o "$WAN" -j MASQUERADE
iptables -A FORWARD -i "$WAN" -o "$LAN" -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i "$LAN" -o "$WAN" -j ACCEPT
ok "NAT masquerade active: $LAN → $WAN"

# ─────────────────────────────────────────────────────────────────────────────
# PERSIST RULES
# ─────────────────────────────────────────────────────────────────────────────
if ! command -v netfilter-persistent &>/dev/null; then
  info "Installing iptables-persistent..."
  echo iptables-persistent iptables-persistent/autosave_v4 boolean true | debconf-set-selections
  echo iptables-persistent iptables-persistent/autosave_v6 boolean false | debconf-set-selections
  apt-get install -y --no-install-recommends iptables-persistent netfilter-persistent
fi
mkdir -p /etc/iptables
netfilter-persistent save
ok "Rules saved → load on boot automatically."

# ─────────────────────────────────────────────────────────────────────────────
# VERIFY INTERNET
# ─────────────────────────────────────────────────────────────────────────────
hdr "Verifying internet"
if ping -c 2 -W 3 8.8.8.8 &>/dev/null; then
  ok "Internet reachable (8.8.8.8)"
else
  echo -e "${YELLOW}[!]${NC}  Internet ping failed — check home router/credentials."
fi

GATEWAY=$(ip route show dev "$WAN" | awk '/default/{print $3}' | head -1 || true)

# ─────────────────────────────────────────────────────────────────────────────
# DONE
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Internet bridge active  (${MODE^^})${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo ""
if [[ "$MODE" == "wifi" ]]; then
  echo "  Connected to  : $WIFI_SSID"
fi
echo "  RPi internet IP : $ETH_IP"
echo "  Gateway          : ${GATEWAY:-unknown}"
echo ""
echo "  Dashboard (CCTV network) : http://192.168.4.1:8080/"
echo "  Dashboard (home network) : http://${ETH_IP}:8080/"
echo ""
echo "  Cameras on CCTV_Network can now reach the internet."
echo ""
echo -e "  To remove: ${YELLOW}sudo bash connect_router.sh --remove${NC}"
echo ""
