#!/usr/bin/env python3
"""
CCTV Server — Raspberry Pi 4
Supports 1–5 ESP32-CAM cameras.
Frames stored on RPi storage AND on each camera's SD card simultaneously.

Routes
  GET  /                        Web dashboard  (phone / laptop / PC)
  GET  /display                 Fullscreen HDMI kiosk view
  POST /upload                  Receive JPEG frame from a camera
  GET  /recordings              List all sessions — JSON
  GET  /recordings/<c>/<s>      List frames in session — JSON
  GET  /recordings/<c>/<s>/<f>  Serve a frame image
  DEL  /recordings/<c>/<s>      Delete a session folder
  GET  /download/<c>/<s>/<f>    Download frame as file attachment
  GET  /sysinfo                 CPU temp, uptime, network, disk — JSON
"""

import os, sys, re, json, shutil, subprocess, threading, time, gc
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, abort, Response

app = Flask(__name__)

# Cap incoming request size to a single JPEG frame (~512 KB max).
# Prevents a misbehaving / malicious client from filling RAM on low-RAM boards.
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024

BASE_DIR = Path.home() / "cctv"
REC_DIR  = BASE_DIR / "recordings"
REC_DIR.mkdir(parents=True, exist_ok=True)

# Lite-mode detection: if total RAM < 1.5 GB, run lean (no extra workers, aggressive GC).
try:
    _TOTAL_MB = int(open("/proc/meminfo").readline().split()[1]) // 1024
except Exception:
    _TOTAL_MB = 4096
LITE_MODE = _TOTAL_MB < 1500

# ── Camera list — edit names to match your installation ───────────────────
CAMERAS = [
    {"id": 1, "name": "Front Door",  "ip": "192.168.4.101"},
    {"id": 2, "name": "Back Yard",   "ip": "192.168.4.102"},
    {"id": 3, "name": "Garage",      "ip": "192.168.4.103"},
    {"id": 4, "name": "Side Gate",   "ip": "192.168.4.104"},
    {"id": 5, "name": "Driveway",    "ip": "192.168.4.105"},
    {"id": 6, "name": "Hallway",     "ip": "192.168.4.106"},
]
# ──────────────────────────────────────────────────────────────────────────

RETENTION_DAYS = 30   # auto-delete recordings older than this many days

def safe(s):
    return "".join(c for c in s if c.isalnum() or c in "-_")

def cam_name(cam_id):
    return next((c["name"] for c in CAMERAS if c["id"] == cam_id), f"Camera {cam_id}")

def cleanup_old_recordings():
    """Delete session folders older than RETENTION_DAYS. Returns count deleted."""
    cutoff = datetime.now().timestamp() - RETENTION_DAYS * 86400
    deleted = 0
    try:
        for cam_dir in REC_DIR.iterdir():
            if not cam_dir.is_dir():
                continue
            for sess_dir in cam_dir.iterdir():
                if not sess_dir.is_dir():
                    continue
                if sess_dir.stat().st_mtime < cutoff:
                    shutil.rmtree(sess_dir)
                    deleted += 1
    except Exception:
        pass
    return deleted

def estimate_days_remaining():
    """Estimate days of free storage left based on avg daily usage (last 7 days)."""
    try:
        now      = datetime.now().timestamp()
        week_ago = now - 7 * 86400
        daily_totals: dict = {}
        for cam_dir in REC_DIR.iterdir():
            if not cam_dir.is_dir(): continue
            for sess_dir in cam_dir.iterdir():
                if not sess_dir.is_dir(): continue
                mtime = sess_dir.stat().st_mtime
                if mtime < week_ago: continue
                key  = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                size = sum(f.stat().st_size for f in sess_dir.glob("*.jpg"))
                daily_totals[key] = daily_totals.get(key, 0) + size
        if not daily_totals:
            return None
        avg_daily = sum(daily_totals.values()) / len(daily_totals)
        if avg_daily == 0:
            return None
        free = shutil.disk_usage(str(REC_DIR)).free
        return round(free / avg_daily)
    except Exception:
        return None

def _cleanup_loop():
    """Background thread: run cleanup every hour."""
    while True:
        time.sleep(3600)
        cleanup_old_recordings()

def _gc_loop():
    """LITE mode only: force Python GC every 60 s so freed JPEG buffers don't linger."""
    while True:
        time.sleep(60)
        gc.collect()

threading.Thread(target=_cleanup_loop, daemon=True).start()
if LITE_MODE:
    threading.Thread(target=_gc_loop, daemon=True).start()
cleanup_old_recordings()   # also run once at startup

def get_ip(iface):
    try:
        out = subprocess.check_output(["ip", "addr", "show", iface],
                                      text=True, stderr=subprocess.DEVNULL)
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None
    except:
        return None

# ── Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return Response(
        DASHBOARD_HTML
            .replace("__CAMERAS__",        json.dumps(CAMERAS))
            .replace("__RETENTION_DAYS__", str(RETENTION_DAYS)),
        mimetype="text/html")

@app.route("/display")
def display():
    return Response(
        DISPLAY_HTML.replace("__CAMERAS__", json.dumps(CAMERAS)),
        mimetype="text/html")

@app.route("/upload", methods=["POST"])
def upload():
    cam_id  = request.args.get("cam",     type=int)
    session = safe(request.args.get("session", "unknown"))
    frame_n = request.args.get("frame",   default=0, type=int)

    if not cam_id or not (1 <= cam_id <= 6):
        return jsonify({"error": "invalid cam_id (must be 1–6)"}), 400

    save_dir = REC_DIR / f"cam{cam_id}" / session
    save_dir.mkdir(parents=True, exist_ok=True)

    # Write metadata on first frame
    meta = save_dir / "meta.json"
    if not meta.exists():
        meta.write_text(json.dumps({
            "cam_id":   cam_id,
            "cam_name": cam_name(cam_id),
            "start":    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }, indent=2))

    (save_dir / f"{frame_n:05d}.jpg").write_bytes(request.data)
    return jsonify({"ok": True, "frame": frame_n})

@app.route("/recordings")
def list_recordings():
    result = []
    for cam in CAMERAS:
        cdir = REC_DIR / f"cam{cam['id']}"
        sessions = []
        if cdir.is_dir():
            dirs = sorted(cdir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            for d in dirs[:30]:
                if not d.is_dir():
                    continue
                frames = list(d.glob("*.jpg"))
                if not frames:
                    continue
                meta = {}
                mp = d / "meta.json"
                if mp.exists():
                    try:
                        meta = json.loads(mp.read_text())
                    except:
                        pass
                sessions.append({
                    "name":    d.name,
                    "start":   meta.get("start", ""),
                    "frames":  len(frames),
                    "size_mb": round(sum(f.stat().st_size for f in frames) / 1e6, 1),
                })
        result.append({
            "cam_id":   cam["id"],
            "cam_name": cam["name"],
            "sessions": sessions,
        })
    return jsonify(result)

@app.route("/recordings/<int:cam_id>/<session>")
def list_frames(cam_id, session):
    d = REC_DIR / f"cam{cam_id}" / safe(session)
    if not d.is_dir():
        abort(404)
    return jsonify(sorted(f.name for f in d.glob("*.jpg")))

@app.route("/recordings/<int:cam_id>/<session>/<filename>")
def serve_frame(cam_id, session, filename):
    return send_from_directory(
        str(REC_DIR / f"cam{cam_id}" / safe(session)), filename)

@app.route("/api/cameras")
def api_cameras():
    """Camera list — used by display.py and other clients."""
    return jsonify(CAMERAS)

@app.route("/cleanup", methods=["POST"])
def run_cleanup():
    deleted = cleanup_old_recordings()
    return jsonify({"ok": True, "deleted_sessions": deleted,
                    "retention_days": RETENTION_DAYS})

@app.route("/recordings/<int:cam_id>/<session>", methods=["DELETE"])
def delete_session(cam_id, session):
    d = REC_DIR / f"cam{cam_id}" / safe(session)
    if d.is_dir():
        shutil.rmtree(d)
    return jsonify({"ok": True})

@app.route("/download/<int:cam_id>/<session>/<filename>")
def download_frame(cam_id, session, filename):
    return send_from_directory(
        str(REC_DIR / f"cam{cam_id}" / safe(session)),
        filename, as_attachment=True)

@app.route("/sysinfo")
def sysinfo():
    info = {}
    try:
        info["cpu_temp"] = round(
            int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 1)
    except:
        info["cpu_temp"] = None
    try:
        up = float(Path("/proc/uptime").read_text().split()[0])
        info["uptime_h"] = round(up / 3600, 1)
    except:
        info["uptime_h"] = None
    info["eth0_ip"]  = get_ip("eth0")
    info["wlan1_ip"] = get_ip("wlan1")   # USB WiFi dongle (if used)
    info["wlan0_ip"] = "192.168.4.1"
    s = shutil.disk_usage(str(REC_DIR))
    info["disk_total_gb"] = round(s.total / 1e9, 1)
    info["disk_used_gb"]  = round(s.used  / 1e9, 1)
    info["disk_free_gb"]  = round(s.free  / 1e9, 1)
    info["disk_pct"]       = round(s.used  / s.total * 100, 1)
    info["retention_days"] = RETENTION_DAYS
    info["days_remaining"] = estimate_days_remaining()
    return jsonify(info)


# ══════════════════════════════════════════════════════════════════════════════
#  FULLSCREEN HDMI DISPLAY   /display
#  5-camera layout:  row 1 → 3 equal columns
#                    row 2 → 2 columns, centred
# ══════════════════════════════════════════════════════════════════════════════

DISPLAY_HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><title>CCTV Monitor</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{width:100%;height:100%;overflow:hidden;background:#000;
  font-family:'Courier New',monospace}

/* ── 3×2 fullscreen grid (3 cameras per row, 2 rows) ── */
.grid{display:grid;
  grid-template-columns:repeat(3,1fr);
  grid-template-rows:repeat(2,50vh);
  gap:2px;background:#0d0d0d;
  width:100vw;height:100vh}
.cell{position:relative;background:#050505;overflow:hidden}
.cell img{width:100%;height:100%;object-fit:cover;display:block}

/* ── No signal ── */
.nosig{position:absolute;inset:0;display:none;flex-direction:column;
  align-items:center;justify-content:center;
  color:#1e1e1e;font-size:clamp(11px,1.5vw,20px);letter-spacing:3px;gap:10px}
.nosig svg{opacity:.15}

/* ── Bottom gradient overlay ── */
.overlay{position:absolute;bottom:0;left:0;right:0;
  padding:28px 12px 9px;
  background:linear-gradient(to top,rgba(0,0,0,.88) 0%,transparent 100%);
  display:flex;justify-content:space-between;align-items:flex-end}
.cam-label{color:#fff;font-size:clamp(10px,1.1vw,15px);
  font-weight:bold;text-shadow:0 1px 4px rgba(0,0,0,.9);letter-spacing:.3px}
.cam-right{display:flex;align-items:center;gap:7px}
.rec-badge{font-size:clamp(9px,.9vw,12px);color:#f85149;font-weight:bold}
.batt-txt {font-size:clamp(9px,.9vw,12px);color:rgba(255,255,255,.55)}

/* ── Status dot ── */
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot-live  {background:#3fb950;box-shadow:0 0 6px #3fb950;animation:dpulse 2s infinite}
.dot-motion{background:#f85149;box-shadow:0 0 9px #f85149;animation:dblink .5s infinite}
.dot-off   {background:#292929}
@keyframes dpulse{0%,100%{opacity:1}50%{opacity:.25}}
@keyframes dblink{0%,100%{opacity:1}50%{opacity:.08}}

/* ── Motion alert ring ── */
.cell.alert{outline:3px solid #f85149;outline-offset:-3px;
  animation:aring .7s infinite}
@keyframes aring{0%,100%{outline-color:#f85149}50%{outline-color:transparent}}

/* ── Top-corner HUD ── */
#hud-clock{position:fixed;top:10px;right:14px;z-index:20;
  color:rgba(255,255,255,.5);font-size:clamp(12px,1.1vw,17px);letter-spacing:.5px}
#hud-temp{position:fixed;top:10px;left:14px;z-index:20;
  font-size:clamp(10px,.95vw,14px);color:rgba(255,255,255,.38);transition:color .5s}
#hud-cams{position:fixed;top:30px;left:14px;z-index:20;
  font-size:clamp(9px,.8vw,11px);color:rgba(255,255,255,.22)}

/* ── Nav bar ── */
#nav{position:fixed;bottom:14px;left:50%;transform:translateX(-50%);
  z-index:20;display:flex;gap:8px;opacity:0;transition:opacity .3s}
body:hover #nav{opacity:1}
@media(pointer:coarse){#nav{opacity:1}}
.nbtn{padding:6px 16px;border-radius:6px;cursor:pointer;font-family:monospace;
  font-size:12px;text-decoration:none;border:1px solid rgba(255,255,255,.12);
  background:rgba(13,17,23,.9);color:#e6edf3;backdrop-filter:blur(4px)}
.nbtn:hover{background:rgba(31,111,235,.85);border-color:#1f6feb}
</style></head><body>

<div id="hud-clock"></div>
<div id="hud-temp"></div>
<div id="hud-cams"></div>
<div class="grid" id="grid"></div>
<nav id="nav">
  <a class="nbtn" href="/">&#9776;&nbsp;Dashboard</a>
  <button class="nbtn" id="fsBtn">&#x26F6;&nbsp;Fullscreen</button>
</nav>

<script>
var CAMERAS=__CAMERAS__;

/* build cells */
(function(){
  var g=document.getElementById('grid');
  CAMERAS.forEach(function(cam){
    g.innerHTML+=[
      '<div class="cell" id="c'+cam.id+'">',
        '<img id="img'+cam.id+'" alt="">',
        '<div class="nosig" id="ns'+cam.id+'">',
          '<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">',
            '<rect x="2" y="7" width="20" height="15" rx="2"/><polyline points="17 2 12 7 7 2"/>',
          '</svg>',
          'NO SIGNAL',
        '</div>',
        '<div class="overlay">',
          '<span class="cam-label">'+cam.name+'</span>',
          '<div class="cam-right">',
            '<span class="rec-badge" id="rec'+cam.id+'"></span>',
            '<span class="batt-txt" id="bt'+cam.id+'"></span>',
            '<span class="dot dot-off" id="dot'+cam.id+'"></span>',
          '</div>',
        '</div>',
      '</div>'
    ].join('');
    streamStart(cam);
  });
  document.getElementById('hud-cams').textContent=CAMERAS.length+' cameras';
})();

function streamStart(cam){
  var img=document.getElementById('img'+cam.id),ns=document.getElementById('ns'+cam.id);
  img.onload =function(){ns.style.display='none';img.style.display='block'};
  img.onerror=function(){img.style.display='none';ns.style.display='flex';
    setTimeout(function(){streamStart(cam);},5000)};
  img.src='http://'+cam.ip+':81/?t='+Date.now();
}

function pollCams(){
  CAMERAS.forEach(function(cam){
    fetch('http://'+cam.ip+'/status',{signal:AbortSignal.timeout(2000)})
      .then(function(r){return r.json()})
      .then(function(d){
        var m=d.motion,r=d.recording;
        document.getElementById('dot'+cam.id).className='dot '+(m?'dot-motion':'dot-live');
        document.getElementById('c'+cam.id).classList.toggle('alert',!!m);
        document.getElementById('bt'+cam.id).textContent=d.batt_pct+'%';
        document.getElementById('rec'+cam.id).textContent=r?'⏺ REC':'';
      })
      .catch(function(){
        document.getElementById('dot'+cam.id).className='dot dot-off';
        document.getElementById('c'+cam.id).classList.remove('alert');
      });
  });
}

function pollSys(){
  fetch('/sysinfo').then(function(r){return r.json()}).then(function(d){
    var el=document.getElementById('hud-temp');
    if(d.cpu_temp!==null){
      el.textContent='CPU '+d.cpu_temp+'°C';
      el.style.color=d.cpu_temp>75?'#f85149':d.cpu_temp>60?'#d29922':'rgba(255,255,255,.38)';
    }
  }).catch(function(){});
}

function tick(){
  var n=new Date();
  document.getElementById('hud-clock').textContent=
    n.toLocaleDateString('en-GB')+' '+
    n.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'});
}

var fsBtn=document.getElementById('fsBtn');
fsBtn.onclick=function(){
  if(!document.fullscreenElement){
    document.documentElement.requestFullscreen();fsBtn.textContent='⛶ Exit';
  }else{document.exitFullscreen();}
};
document.addEventListener('fullscreenchange',function(){
  if(!document.fullscreenElement)fsBtn.textContent='⛶ Fullscreen';
});

tick();setInterval(tick,1000);
pollCams();setInterval(pollCams,4000);
pollSys();setInterval(pollSys,15000);
</script></body></html>"""


# ══════════════════════════════════════════════════════════════════════════════
#  WEB DASHBOARD   /
#  Full responsive dashboard: live cameras, system stats, recordings browser.
# ══════════════════════════════════════════════════════════════════════════════

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CCTV Dashboard</title>
<style>
/* ── Design tokens ─────────────────────────────────────────────────────── */
:root{
  --bg:       #f0f4f8;
  --surface:  #ffffff;
  --surface2: #f6f8fa;
  --border:   #d0d7de;
  --border2:  #96a3b0;
  --text:     #1c2128;
  --dim:      #57606a;
  --blue:     #0969da;
  --green:    #1a7f37;
  --red:      #cf222e;
  --amber:    #9a6700;
  --radius:   10px;
}

/* ── Reset ─────────────────────────────────────────────────────────────── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:'Courier New',monospace;
  font-size:13px;line-height:1.5;min-height:100vh}

/* ── Header ────────────────────────────────────────────────────────────── */
.hdr{position:sticky;top:0;z-index:50;background:var(--surface);
  border-bottom:1px solid var(--border);
  padding:10px 20px;display:flex;align-items:center;
  justify-content:space-between;flex-wrap:wrap;gap:8px}
.hdr-logo{display:flex;align-items:center;gap:10px}
.logo-icon{font-size:20px}
.logo-text{color:var(--blue);font-size:15px;font-weight:bold;letter-spacing:.3px}
.logo-sub{color:var(--dim);font-size:11px}
.hdr-stats{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.stat{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--dim);
  padding:3px 0;white-space:nowrap}
.stat.hot{color:var(--red)}.stat.warm{color:var(--amber)}
.stat-icon{font-size:13px}
.disk-wrap{display:flex;align-items:center;gap:5px}
.disk-track{width:64px;height:6px;background:var(--bg);border:1px solid var(--border);
  border-radius:3px;overflow:hidden}
.disk-bar{height:100%;background:var(--green);transition:width 1s,background 1s}
.hdr-btns{display:flex;gap:6px}
.hbtn{padding:5px 14px;border-radius:6px;border:none;cursor:pointer;
  font-family:monospace;font-size:12px;text-decoration:none;
  transition:opacity .15s,transform .1s}
.hbtn:hover{opacity:.85;transform:translateY(-1px)}
.hbtn-mon{background:var(--blue);color:#fff}
.hbtn-rfs{background:var(--surface2);color:var(--text);border:1px solid var(--border)}

/* ── Section ───────────────────────────────────────────────────────────── */
.wrap{max-width:1380px;margin:0 auto;padding:18px 18px 0}
.sec-title{font-size:10px;text-transform:uppercase;letter-spacing:1.8px;
  color:var(--dim);margin-bottom:14px;
  display:flex;align-items:center;gap:10px}
.sec-title::after{content:'';flex:1;height:1px;background:var(--border)}

/* ── Camera grid — 3×2 (3 per row, 2 rows) ─────────────────────────────── */
.cam-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;
  margin-bottom:28px}

/* Camera card */
.cam-card{background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);overflow:hidden;
  transition:border-color .2s,box-shadow .2s}
.cam-card:hover{border-color:#0969da40;box-shadow:0 2px 8px rgba(0,0,0,.08)}
.cam-card.alert{border-color:var(--red);box-shadow:0 0 0 1px var(--red);
  animation:calert .7s infinite}
@keyframes calert{0%,100%{border-color:var(--red)}50%{border-color:transparent}}

/* Card header */
.card-hd{padding:9px 13px;
  background:linear-gradient(135deg,var(--surface2) 0%,var(--surface) 100%);
  border-bottom:1px solid var(--border);
  display:flex;justify-content:space-between;align-items:center;gap:6px}
.card-title{display:flex;align-items:baseline;gap:5px}
.card-name{font-weight:bold;font-size:13px}
.card-id{font-size:10px;color:var(--dim)}
.card-badges{display:flex;align-items:center;gap:5px}

/* Status dot */
.dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.dot-live  {background:var(--green);animation:dpulse 2s infinite}
.dot-motion{background:var(--red);animation:dblink .5s infinite}
.dot-off   {background:#b0b8c1}
@keyframes dpulse{0%,100%{opacity:1}50%{opacity:.2}}
@keyframes dblink{0%,100%{opacity:1}50%{opacity:.08}}

/* Badge pill */
.pill{padding:2px 8px;border-radius:10px;font-size:10px;font-weight:bold}
.pill-live  {background:#dafbe1;color:#1a7f37;border:1px solid #aef0b5}
.pill-motion{background:#ffebe9;color:#cf222e;border:1px solid #ffcecb}
.pill-off   {background:var(--surface2);color:var(--dim);border:1px solid var(--border)}
.pill-rec   {background:#ffebe9;color:#cf222e;border:1px solid #ffcecb}
.pill-blank {display:none}

/* Stream box */
.stream{background:#000;aspect-ratio:4/3;position:relative;overflow:hidden;cursor:pointer}
.stream img{width:100%;height:100%;object-fit:contain;display:block}
.stream::after{content:'\26F6';position:absolute;top:7px;right:8px;
  color:rgba(255,255,255,.5);font-size:17px;opacity:0;
  transition:opacity .2s;pointer-events:none;z-index:2}
.stream:hover::after{opacity:1}
.nosig{position:absolute;inset:0;display:none;flex-direction:column;
  align-items:center;justify-content:center;color:#2a2a2a;
  font-size:11px;letter-spacing:1.5px;gap:8px}

/* Card footer */
.card-ft{padding:8px 13px;display:flex;justify-content:space-between;
  align-items:center;flex-wrap:wrap;gap:6px;
  border-top:1px solid var(--border)}

/* Battery */
.batt{display:flex;align-items:center;gap:6px}
.batt-track{width:38px;height:8px;background:var(--bg);
  border:1px solid var(--border);border-radius:2px;overflow:hidden}
.batt-fill{height:100%;
  background:linear-gradient(90deg,var(--red) 0%,var(--amber) 45%,var(--green) 100%);
  transition:width 1s}
.batt-pct{font-size:11px;color:var(--dim);min-width:28px}

/* Action buttons */
.btns{display:flex;gap:4px}
.btn{padding:4px 8px;border-radius:5px;border:none;cursor:pointer;
  font-size:11px;font-family:monospace;transition:opacity .15s}
.btn:hover{opacity:.8}
.btn-g{background:#dafbe1;color:#1a7f37;border:1px solid #aef0b5}
.btn-r{background:#ffebe9;color:#cf222e;border:1px solid #ffcecb}
.btn-b{background:#ddf4ff;color:#0969da;border:1px solid #80ccff}
.btn-d{background:var(--surface2);color:var(--text);border:1px solid var(--border)}

/* ── Recordings ────────────────────────────────────────────────────────── */
.rec-section{padding-bottom:24px}
.rec-tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.tab{padding:5px 13px;border-radius:6px;border:1px solid var(--border);
  background:var(--surface);color:var(--dim);
  cursor:pointer;font-size:12px;font-family:monospace;transition:all .15s}
.tab:hover:not(.on){border-color:var(--border2);color:var(--text)}
.tab.on{background:var(--blue);color:#fff;border-color:var(--blue)}

.rec-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:10px}
.rec-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;
  overflow:hidden;cursor:pointer;transition:border-color .18s,transform .15s}
.rec-card:hover{border-color:var(--blue);transform:translateY(-2px)}
.rec-thumb{background:#000;aspect-ratio:4/3;overflow:hidden;
  display:flex;align-items:center;justify-content:center}
.rec-thumb img{width:100%;height:100%;object-fit:cover}
.rec-thumb-miss{color:#2a2a2a;font-size:11px;letter-spacing:1px}
.rec-body{padding:8px 10px}
.rec-time{font-size:10px;color:var(--blue);margin-bottom:2px}
.rec-cam {font-size:10px;color:var(--dim)}
.rec-meta{font-size:11px;color:var(--text);margin-top:4px}
.rec-del{float:right;background:var(--red);color:#fff;border:none;border-radius:3px;
  cursor:pointer;font-size:9px;padding:2px 5px;transition:opacity .15s}
.rec-del:hover{opacity:.8}
.rec-empty{color:var(--dim);text-align:center;padding:36px 0;
  font-size:12px;grid-column:1/-1;letter-spacing:.5px}

/* ── Modal viewer ──────────────────────────────────────────────────────── */
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.93);z-index:200;
  align-items:center;justify-content:center;flex-direction:column;gap:14px;
  padding:16px}
.modal.open{display:flex}
.modal-img{max-width:90vw;max-height:72vh;border-radius:8px;
  border:1px solid var(--border);display:block}
.modal-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;justify-content:center}
.mbtn{padding:7px 16px;border-radius:6px;border:none;cursor:pointer;
  font-family:monospace;font-size:13px;transition:opacity .15s}
.mbtn:hover{opacity:.8}
.modal-ctr{color:var(--dim);font-size:12px;min-width:80px;text-align:center}
.modal-hint{color:var(--dim);font-size:10px;letter-spacing:.5px;
  margin-top:4px;text-align:center}

/* ── Storage info bar ──────────────────────────────────────────────────── */
.store-bar{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
.store-chip{background:var(--surface);border:1px solid var(--border);
  border-radius:6px;padding:7px 13px;font-size:11px;
  display:flex;align-items:center;gap:7px}
.store-icon{font-size:14px}
.store-label{color:var(--dim)}
.store-val{color:var(--text);font-weight:bold}

/* ── Camera expand modal ────────────────────────────────────────────────── */
.cx-modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);
  z-index:300;align-items:center;justify-content:center;padding:20px}
.cx-modal.open{display:flex;animation:cxfade .18s ease}
@keyframes cxfade{from{opacity:0;transform:scale(.97)}to{opacity:1;transform:scale(1)}}
.cx-box{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  overflow:hidden;display:flex;flex-direction:column;
  width:min(95vw,1100px)}
.cx-hd{padding:11px 16px;
  background:linear-gradient(135deg,var(--surface2) 0%,var(--surface) 100%);
  border-bottom:1px solid var(--border);
  display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.cx-title{display:flex;align-items:baseline;gap:7px}
.cx-name{font-weight:bold;font-size:15px}
.cx-id{font-size:11px;color:var(--dim)}
.cx-badges{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.cx-stream{background:#000;position:relative;overflow:hidden;
  width:100%;aspect-ratio:4/3;max-height:65vh}
.cx-stream img{width:100%;height:100%;object-fit:contain;display:block}
.cx-nosig{position:absolute;inset:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center;color:#2a2a2a;
  font-size:13px;letter-spacing:1.5px;gap:10px}
.cx-ft{padding:10px 16px;border-top:1px solid var(--border);
  display:flex;justify-content:space-between;align-items:center;
  flex-wrap:wrap;gap:8px}
.cx-close{padding:6px 14px;border-radius:6px;background:var(--surface2);
  color:var(--text);border:1px solid var(--border);cursor:pointer;
  font-family:monospace;font-size:12px;transition:opacity .15s}
.cx-close:hover{opacity:.8}

/* ── Responsive ────────────────────────────────────────────────────────── */
@media(max-width:1020px){
  .cam-grid{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:560px){
  .cam-grid{grid-template-columns:1fr}
  .wrap{padding:12px 12px 0}
  .hdr{padding:8px 12px}
  .hdr-stats{gap:8px}
}
</style></head>
<body>

<!-- ── Header ──────────────────────────────────────────────────────────── -->
<header class="hdr">
  <div class="hdr-logo">
    <span class="logo-icon">&#128247;</span>
    <div>
      <div class="logo-text">CCTV System</div>
      <div class="logo-sub" id="logo-sub">Raspberry Pi 4</div>
    </div>
  </div>
  <div class="hdr-stats">
    <div class="stat" id="stat-temp"><span class="stat-icon">&#127777;</span><span>--°C</span></div>
    <div class="stat" id="stat-upt"><span class="stat-icon">&#8987;</span><span>--h</span></div>
    <div class="stat" id="stat-net"><span class="stat-icon">&#127760;</span><span>No internet</span></div>
    <div class="stat">
      <div class="disk-wrap">
        <span class="stat-icon">&#128190;</span>
        <div class="disk-track"><div class="disk-bar" id="disk-bar" style="width:0%"></div></div>
        <span id="disk-txt" style="color:var(--dim)">--</span>
      </div>
    </div>
  </div>
  <div class="hdr-btns">
    <a class="hbtn hbtn-mon" href="/display">&#x26F6;&nbsp;Monitor</a>
    <button class="hbtn hbtn-rfs" onclick="refresh()">&#8635;&nbsp;Refresh</button>
  </div>
</header>

<!-- ── Camera grid ──────────────────────────────────────────────────────── -->
<div class="wrap">
  <div class="sec-title">&#128247;&nbsp;Live Cameras <span id="online-badge" style="font-size:11px;text-transform:none;letter-spacing:0;color:var(--green)"></span></div>
  <div class="cam-grid" id="cam-grid"></div>

  <!-- ── Recordings ──────────────────────────────────────────────────── -->
  <div class="rec-section">
    <div class="sec-title">&#128193;&nbsp;Recordings</div>

    <!-- Storage chips -->
    <div class="store-bar">
      <div class="store-chip">
        <span class="store-icon">&#128190;</span>
        <span class="store-label">RPi storage</span>
        <span class="store-val" id="store-rpi">--</span>
      </div>
      <div class="store-chip">
        <span class="store-icon">&#128278;</span>
        <span class="store-label">SD card&nbsp;</span>
        <span class="store-val" style="color:var(--dim)">on each camera</span>
      </div>
      <div class="store-chip">
        <span class="store-icon">&#128197;</span>
        <span class="store-label">Est. remaining</span>
        <span class="store-val" id="store-days">--</span>
      </div>
      <div class="store-chip">
        <span class="store-icon">&#128465;</span>
        <span class="store-label">Auto-cleanup</span>
        <span class="store-val" id="store-ret">-- days</span>
      </div>
      <button class="hbtn" style="background:#ffebe9;color:#cf222e;border:1px solid #ffcecb;font-size:11px;padding:5px 12px;margin-left:auto" onclick="doCleanup()">&#128465;&nbsp;Clean now</button>
    </div>

    <div class="rec-tabs" id="rec-tabs"></div>
    <div class="rec-grid" id="rec-grid"></div>
  </div>
</div>

<!-- ── Frame viewer modal ───────────────────────────────────────────────── -->
<div class="modal" id="modal">
  <img class="modal-img" id="modal-img" alt="">
  <div class="modal-bar">
    <button class="mbtn" style="background:var(--surface2);color:var(--text)" onclick="mPrev()">&#9664;</button>
    <span class="modal-ctr" id="modal-ctr">0/0</span>
    <button class="mbtn" style="background:var(--surface2);color:var(--text)" onclick="mNext()">&#9654;</button>
    <button class="mbtn" style="background:#ddf4ff;color:#0969da;border:1px solid #80ccff" id="play-btn" onclick="mTogglePlay()">&#9654;&nbsp;Play</button>
    <button class="mbtn" style="background:#dafbe1;color:#1a7f37;border:1px solid #aef0b5" onclick="mDownload()">&#8681;&nbsp;Save</button>
    <button class="mbtn" style="background:var(--surface2);color:var(--text)" onclick="mClose()">&#10005;</button>
  </div>
  <div class="modal-hint">&#8592;&#8594; navigate &nbsp;&#9251; play/pause &nbsp;S save &nbsp;Esc close</div>
</div>

<!-- ── Camera expand modal ───────────────────────────────────────────────── -->
<div class="cx-modal" id="cx-modal" onclick="if(event.target===this)cxClose()">
  <div class="cx-box">
    <div class="cx-hd">
      <div class="cx-title">
        <span class="cx-name" id="cx-name"></span>
        <span class="cx-id" id="cx-id"></span>
      </div>
      <div class="cx-badges">
        <span class="dot" id="cx-dot"></span>
        <span class="pill" id="cx-pill"></span>
        <span class="pill pill-rec" id="cx-rec" style="display:none">REC</span>
        <button class="cx-close" onclick="cxClose()">&#10005;</button>
      </div>
    </div>
    <div class="cx-stream">
      <img id="cx-img" alt="" style="display:none">
      <div class="cx-nosig" id="cx-nosig">
        <span style="font-size:28px;opacity:.25">&#128247;</span>
        NO SIGNAL
      </div>
    </div>
    <div class="cx-ft">
      <div class="batt">
        <div class="batt-track" style="width:52px">
          <div class="batt-fill" id="cx-bfill" style="width:0%"></div>
        </div>
        <span class="batt-pct" id="cx-bpct">--%</span>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
        <button class="btn btn-b" id="cx-snap">&#128247;&nbsp;Snapshot</button>
        <button class="btn btn-d" id="cx-link">&#128279;&nbsp;Camera page</button>
        <button class="cx-close" onclick="cxClose()">&#10005;&nbsp;Close</button>
      </div>
    </div>
  </div>
</div>

<script>
/* ═══════════════════════════════════════════════════════════════════════ */
var CAMERAS=__CAMERAS__;
var RETENTION_DAYS=__RETENTION_DAYS__;
var recData=[],activeTab=0;
var vCam=0,vSess='',vFrames=[],vIdx=0,vTimer=null;
var onlineCount=0;

/* ── Build camera cards ─────────────────────────────────────────────── */
(function(){
  var g=document.getElementById('cam-grid');
  CAMERAS.forEach(function(cam){
    g.innerHTML+=[
      '<div class="cam-card" id="card'+cam.id+'">',
        '<div class="card-hd">',
          '<div class="card-title">',
            '<span class="card-name">'+cam.name+'</span>',
            '<span class="card-id">#'+cam.id+'</span>',
          '</div>',
          '<div class="card-badges">',
            '<span class="dot dot-off" id="dot'+cam.id+'"></span>',
            '<span class="pill pill-off" id="pill'+cam.id+'">--</span>',
            '<span class="pill pill-blank" id="rec-pill'+cam.id+'">REC</span>',
          '</div>',
        '</div>',
        '<div class="stream" onclick="cxOpen('+cam.id+')" title="Click to enlarge">',
          '<img id="img'+cam.id+'" alt="">',
          '<div class="nosig" id="ns'+cam.id+'">NO&nbsp;SIGNAL</div>',
        '</div>',
        '<div class="card-ft">',
          '<div class="batt">',
            '<div class="batt-track"><div class="batt-fill" id="bfill'+cam.id+'" style="width:50%"></div></div>',
            '<span class="batt-pct" id="bpct'+cam.id+'">--%</span>',
          '</div>',
          '<div class="btns">',
            '<button class="btn btn-g" title="Start recording" onclick="camPost(\''+cam.ip+'\',\'/record/start\')">&#9679;</button>',
            '<button class="btn btn-r" title="Stop recording"  onclick="camPost(\''+cam.ip+'\',\'/record/stop\')">&#9632;</button>',
            '<button class="btn btn-b" title="Snapshot"        onclick="window.open(\'http://'+cam.ip+'/snapshot\',\'_blank\')">&#128247;</button>',
            '<button class="btn btn-d" title="Camera page"     onclick="window.open(\'http://'+cam.ip+'\',\'_blank\')">&#128279;</button>',
          '</div>',
        '</div>',
      '</div>'
    ].join('');
    streamLoad(cam);
  });
})();

function streamLoad(cam){
  var img=document.getElementById('img'+cam.id),ns=document.getElementById('ns'+cam.id);
  img.onload =function(){ns.style.display='none';img.style.display='block'};
  img.onerror=function(){img.style.display='none';ns.style.display='flex';
    setTimeout(function(){streamLoad(cam);},5000)};
  img.src='http://'+cam.ip+':81/?t='+Date.now();
}
function camPost(ip,path){
  fetch('http://'+ip+path,{method:'POST'}).catch(function(){});
}

/* ── Status polling ─────────────────────────────────────────────────── */
function pollCams(){
  onlineCount=0;
  CAMERAS.forEach(function(cam){
    fetch('http://'+cam.ip+'/status',{signal:AbortSignal.timeout(2000)})
      .then(function(r){return r.json()})
      .then(function(d){applyStatus(cam.id,d,true)})
      .catch(function(){applyStatus(cam.id,null,false)});
  });
}
function applyStatus(id,d,ok){
  var card=document.getElementById('card'+id);
  if(!ok){
    document.getElementById('dot'+id).className='dot dot-off';
    document.getElementById('pill'+id).className='pill pill-off';
    document.getElementById('pill'+id).textContent='OFFLINE';
    document.getElementById('rec-pill'+id).className='pill pill-blank';
    card.classList.remove('alert');
    return;
  }
  onlineCount++;
  document.getElementById('online-badge').textContent='('+onlineCount+'/'+CAMERAS.length+' online)';
  var m=d.motion,r=d.recording;
  document.getElementById('dot'+id).className='dot '+(m?'dot-motion':'dot-live');
  document.getElementById('pill'+id).className='pill '+(m?'pill-motion':'pill-live');
  document.getElementById('pill'+id).textContent=m?'MOTION':'LIVE';
  document.getElementById('rec-pill'+id).className=r?'pill pill-rec':'pill pill-blank';
  document.getElementById('rec-pill'+id).textContent='REC';
  card.classList.toggle('alert',!!m);
  document.getElementById('bfill'+id).style.width=d.batt_pct+'%';
  document.getElementById('bpct'+id).textContent=d.batt_pct+'%';
}

/* ── System info ────────────────────────────────────────────────────── */
function pollSys(){
  fetch('/sysinfo').then(function(r){return r.json()}).then(function(d){
    /* Temperature */
    var ts=document.getElementById('stat-temp');
    if(d.cpu_temp!==null){
      ts.innerHTML='<span class="stat-icon">&#127777;</span><span>'+d.cpu_temp+'°C</span>';
      ts.className='stat'+(d.cpu_temp>75?' hot':d.cpu_temp>60?' warm':'');
    }
    /* Uptime */
    if(d.uptime_h!==null)
      document.getElementById('stat-upt').innerHTML=
        '<span class="stat-icon">&#8987;</span><span>'+d.uptime_h+'h uptime</span>';
    /* Internet */
    var ni=document.getElementById('stat-net');
    var ip=d.eth0_ip||d.wlan1_ip;
    if(ip){
      ni.innerHTML='<span class="stat-icon">&#127760;</span><span>'+ip+'</span>';
      ni.title='Access dashboard at http://'+ip+':8080/';
    }else{
      ni.innerHTML='<span class="stat-icon">&#127760;</span><span>No internet</span>';
      ni.title='Connect ethernet or USB WiFi for internet access';
    }
    /* Disk */
    var pct=d.disk_pct,free=d.disk_free_gb;
    document.getElementById('disk-bar').style.width=pct+'%';
    document.getElementById('disk-bar').style.background=
      pct>85?'var(--red)':pct>65?'var(--amber)':'var(--green)';
    document.getElementById('disk-txt').textContent=free+' GB free';
    document.getElementById('store-rpi').textContent=free+' GB free / '+d.disk_total_gb+' GB';
    /* Days remaining */
    var drEl=document.getElementById('store-days');
    if(d.days_remaining!==null&&d.days_remaining!==undefined){
      drEl.textContent=d.days_remaining+' days';
      drEl.style.color=d.days_remaining<3?'var(--red)':
                       d.days_remaining<7?'var(--amber)':'var(--green)';
    } else {
      drEl.textContent='calculating…';drEl.style.color='var(--dim)';
    }
    /* Retention setting */
    var ret=d.retention_days||RETENTION_DAYS;
    document.getElementById('store-ret').textContent='after '+ret+' days';
    document.getElementById('logo-sub').textContent=
      'Raspberry Pi  ·  '+CAMERAS.length+' cameras  ·  192.168.4.1';
  }).catch(function(){});
}

/* ── Recordings ─────────────────────────────────────────────────────── */
function buildTabs(){
  var el=document.getElementById('rec-tabs');
  el.innerHTML='<span class="tab on" onclick="switchTab(0)">ALL</span>';
  CAMERAS.forEach(function(cam){
    el.innerHTML+='<span class="tab" onclick="switchTab('+cam.id+')">'+cam.name+'</span>';
  });
}
function switchTab(id){
  activeTab=id;
  document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('on')});
  var tabs=document.querySelectorAll('.tab');
  if(id===0){tabs[0].classList.add('on')}
  else{var i=CAMERAS.findIndex(function(c){return c.id===id});
    if(i>=0)tabs[i+1].classList.add('on')}
  renderRecs();
}
function loadRecs(){
  fetch('/recordings').then(function(r){return r.json()})
    .then(function(d){recData=d;renderRecs()}).catch(function(){});
}
function renderRecs(){
  var items=[];
  recData.forEach(function(cr){
    if(activeTab!==0&&cr.cam_id!==activeTab)return;
    cr.sessions.forEach(function(s){
      items.push({cam_id:cr.cam_id,cam_name:cr.cam_name,s:s});
    });
  });
  var g=document.getElementById('rec-grid');
  if(!items.length){
    g.innerHTML='<div class="rec-empty">&#128193;&nbsp;No recordings yet</div>';return;
  }
  g.innerHTML=items.map(function(item){
    var thumb='/recordings/'+item.cam_id+'/'+item.s.name+'/00000.jpg';
    return [
      '<div class="rec-card" onclick="mOpen('+item.cam_id+',\''+item.s.name+'\')">',
        '<div class="rec-thumb">',
          '<img src="'+thumb+'" alt="" onerror="this.style.display=\'none\';'+
            'this.nextSibling.style.display=\'flex\'">',
          '<div class="rec-thumb-miss" style="display:none">NO PREVIEW</div>',
        '</div>',
        '<div class="rec-body">',
          '<div class="rec-time">'+(item.s.start||item.s.name)+'</div>',
          '<div class="rec-cam">'+item.cam_name,
            '<button class="rec-del" onclick="event.stopPropagation();delRec('+item.cam_id+',\''+item.s.name+'\')">&#128465;</button>',
          '</div>',
          '<div class="rec-meta">&#127902;&nbsp;'+item.s.frames+' fr &nbsp; '+item.s.size_mb+' MB</div>',
        '</div>',
      '</div>'
    ].join('');
  }).join('');
}
function delRec(c,s){
  if(!confirm('Delete this recording?'))return;
  fetch('/recordings/'+c+'/'+s,{method:'DELETE'}).then(loadRecs);
}

/* ── Frame viewer ───────────────────────────────────────────────────── */
function mOpen(c,s){
  vCam=c;vSess=s;vIdx=0;
  fetch('/recordings/'+c+'/'+s)
    .then(function(r){return r.json()})
    .then(function(f){
      vFrames=f;mShow(0);document.getElementById('modal').classList.add('open');
    });
}
function mShow(i){
  if(!vFrames.length)return;
  vIdx=Math.max(0,Math.min(i,vFrames.length-1));
  document.getElementById('modal-img').src='/recordings/'+vCam+'/'+vSess+'/'+vFrames[vIdx];
  document.getElementById('modal-ctr').textContent=(vIdx+1)+' / '+vFrames.length;
}
function mPrev(){mStop();mShow(vIdx-1)}
function mNext(){mStop();mShow(vIdx+1)}
function mTogglePlay(){
  if(vTimer){mStop();return}
  document.getElementById('play-btn').innerHTML='&#9646;&#9646;&nbsp;Pause';
  vTimer=setInterval(function(){vIdx>=vFrames.length-1?mStop():mShow(vIdx+1)},200);
}
function mStop(){
  clearInterval(vTimer);vTimer=null;
  document.getElementById('play-btn').innerHTML='&#9654;&nbsp;Play';
}
function mDownload(){
  var a=document.createElement('a');
  a.href='/download/'+vCam+'/'+vSess+'/'+vFrames[vIdx];
  a.download='cam'+vCam+'_'+vFrames[vIdx];
  a.click();
}
function mClose(){
  mStop();document.getElementById('modal').classList.remove('open');
}
document.getElementById('modal').addEventListener('click',function(e){
  if(e.target===this)mClose();
});
document.addEventListener('keydown',function(e){
  if(e.key==='Escape'){
    if(document.getElementById('cx-modal').classList.contains('open')){cxClose();return;}
    if(document.getElementById('modal').classList.contains('open')){mClose();}
    return;
  }
  if(!document.getElementById('modal').classList.contains('open'))return;
  if(e.key==='ArrowLeft')mPrev();
  if(e.key==='ArrowRight')mNext();
  if(e.key===' '){e.preventDefault();mTogglePlay();}
  if(e.key==='s'||e.key==='S')mDownload();
});

/* ── Camera expand ──────────────────────────────────────────────────── */
var cxCamId=0,cxIp='',cxPoll=null;
function cxOpen(id){
  var cam=CAMERAS.find(function(c){return c.id===id});
  if(!cam)return;
  cxCamId=id;cxIp=cam.ip;
  document.getElementById('cx-name').textContent=cam.name;
  document.getElementById('cx-id').textContent='#'+id;
  /* Copy current status from card */
  var dotEl =document.getElementById('dot'+id);
  var pillEl=document.getElementById('pill'+id);
  var recEl =document.getElementById('rec-pill'+id);
  document.getElementById('cx-dot').className=dotEl.className;
  document.getElementById('cx-pill').className=pillEl.className;
  document.getElementById('cx-pill').textContent=pillEl.textContent;
  var recOn=recEl&&!recEl.classList.contains('pill-blank');
  document.getElementById('cx-rec').style.display=recOn?'inline':'none';
  document.getElementById('cx-bfill').style.width=
    document.getElementById('bfill'+id).style.width;
  document.getElementById('cx-bpct').textContent=
    document.getElementById('bpct'+id).textContent;
  /* Action buttons */
  document.getElementById('cx-snap').onclick=function(){
    window.open('http://'+cam.ip+'/snapshot','_blank')};
  document.getElementById('cx-link').onclick=function(){
    window.open('http://'+cam.ip,'_blank')};
  /* Stream */
  var img=document.getElementById('cx-img');
  img.style.display='none';
  document.getElementById('cx-nosig').style.display='flex';
  img.onload=function(){
    document.getElementById('cx-nosig').style.display='none';
    img.style.display='block'};
  img.onerror=function(){
    img.style.display='none';
    document.getElementById('cx-nosig').style.display='flex';
    setTimeout(function(){img.src='http://'+cam.ip+':81/?t='+Date.now();},5000)};
  img.src='http://'+cam.ip+':81/?t='+Date.now();
  /* Show modal */
  document.getElementById('cx-modal').classList.add('open');
  document.body.style.overflow='hidden';
  /* Live status poll while open */
  cxPoll=setInterval(function(){
    fetch('http://'+cam.ip+'/status',{signal:AbortSignal.timeout(2000)})
      .then(function(r){return r.json()})
      .then(function(d){
        document.getElementById('cx-dot').className=
          'dot '+(d.motion?'dot-motion':'dot-live');
        document.getElementById('cx-pill').className=
          'pill '+(d.motion?'pill-motion':'pill-live');
        document.getElementById('cx-pill').textContent=d.motion?'MOTION':'LIVE';
        document.getElementById('cx-rec').style.display=d.recording?'inline':'none';
        document.getElementById('cx-bfill').style.width=d.batt_pct+'%';
        document.getElementById('cx-bpct').textContent=d.batt_pct+'%';
      }).catch(function(){});
  },3000);
}
function cxClose(){
  clearInterval(cxPoll);cxPoll=null;
  document.getElementById('cx-img').src='';
  document.getElementById('cx-modal').classList.remove('open');
  document.body.style.overflow='';
}

/* ── Cleanup ────────────────────────────────────────────────────────── */
function doCleanup(){
  if(!confirm('Delete all recordings older than '+RETENTION_DAYS+' days?'))return;
  fetch('/cleanup',{method:'POST'})
    .then(function(r){return r.json()})
    .then(function(d){
      var n=d.deleted_sessions;
      alert('Done — removed '+n+' old session'+(n===1?'':'s')+'.');
      loadRecs();pollSys();
    }).catch(function(){alert('Cleanup request failed.');});
}

/* ── Global refresh ─────────────────────────────────────────────────── */
function refresh(){pollCams();pollSys();loadRecs();}

/* ── Boot ───────────────────────────────────────────────────────────── */
buildTabs();
pollCams();   setInterval(pollCams,  4000);
pollSys();    setInterval(pollSys,  15000);
loadRecs();   setInterval(loadRecs, 30000);
</script>
</body></html>"""


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    mode = "LITE (≤1.5 GB RAM)" if LITE_MODE else "STANDARD"
    print(f"CCTV Server  —  {len(CAMERAS)} cameras configured  ({mode})")
    print(f"  Dashboard  →  http://0.0.0.0:{port}/")
    print(f"  HDMI view  →  http://0.0.0.0:{port}/display")
    print(f"  Recordings →  {REC_DIR}   (retention: {RETENTION_DAYS} days)")
    # On LITE mode use Flask's threaded server but request a tighter idle timeout
    # to release JPEG memory faster between motion bursts.
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
