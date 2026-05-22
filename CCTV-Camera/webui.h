#pragma once
#include <WebServer.h>
#include <WiFiClient.h>
#include "esp_camera.h"
#include "cam_config.h"
#include "motion.h"
#include "recorder.h"
#include "power.h"

// Minimal per-camera web UI — used for debugging individual cameras.
// The main dashboard runs on the Raspberry Pi 4 at http://192.168.4.1:8080/

static const char CAM_PAGE[] PROGMEM = R"rawliteral(
<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Camera __CAM_ID__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e6edf3;font-family:monospace;font-size:13px}
header{background:#161b22;padding:10px 16px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #30363d}
.logo{color:#58a6ff;font-size:14px;font-weight:bold}
.content{padding:12px;max-width:700px;margin:0 auto;display:flex;flex-direction:column;gap:10px}
.stream{background:#000;border-radius:8px;overflow:hidden;border:1px solid #30363d;aspect-ratio:4/3}
.stream img{width:100%;height:100%;object-fit:contain;display:block}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px}
.card h4{font-size:10px;text-transform:uppercase;color:#8b949e;letter-spacing:1px;margin-bottom:10px}
.row{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.badge{padding:3px 9px;border-radius:12px;font-size:11px;font-weight:bold}
.bg{background:#238636;color:#fff}.br{background:#b62324;color:#fff}.bd{background:#21262d;color:#8b949e;border:1px solid #30363d}
.bbar{background:#0d1117;border:1px solid #30363d;border-radius:4px;height:14px;width:100%;overflow:hidden;margin-top:4px}
.bfill{height:100%;background:linear-gradient(90deg,#f85149,#d29922,#3fb950);transition:width .8s}
input[type=range]{width:100%;margin:6px 0;accent-color:#58a6ff}
button{width:100%;padding:7px;border-radius:5px;border:none;cursor:pointer;font-size:12px;font-family:monospace;margin-top:4px}
.btn-g{background:#238636;color:#fff}.btn-r{background:#b62324;color:#fff}.btn-b{background:#1f6feb;color:#fff}
a.back{display:inline-block;padding:5px 12px;background:#1f6feb;color:#fff;border-radius:5px;text-decoration:none;font-size:12px}
</style></head><body>
<header>
  <span class="logo">&#128247; Camera __CAM_ID__ — __CAM_NAME__</span>
  <a class="back" href="http://192.168.4.1:8080/">&#8592; Dashboard</a>
</header>
<div class="content">
  <div class="stream"><img id="s" src="" onerror="this.src='/snapshot'"></div>
  <div class="card">
    <h4>&#9889; Battery</h4>
    <div class="bbar"><div class="bfill" id="bf" style="width:50%"></div></div>
    <div style="display:flex;justify-content:space-between;margin-top:4px;font-size:11px;color:#8b949e">
      <span id="bp">--%</span><span id="bv">--V</span>
    </div>
  </div>
  <div class="card">
    <h4>&#128065; Motion</h4>
    <div class="row">
      <span class="badge bd" id="mb">--</span>
      <label><input type="checkbox" id="me" checked onchange="applyMotion()"> Enable</label>
    </div>
    <div style="font-size:11px;color:#8b949e">Sensitivity <span id="sv">15</span>%</div>
    <input type="range" id="sr" min="5" max="50" value="15"
      oninput="document.getElementById('sv').textContent=this.value" onchange="applyMotion()">
  </div>
  <div class="card">
    <h4>&#9679; Recording</h4>
    <div style="text-align:center;padding:6px 0">
      <div style="font-size:28px" id="ri">&#9209;</div>
      <div style="font-size:10px;color:#8b949e" id="rl">Idle</div>
    </div>
    <button class="btn-g" onclick="fetch('/record/start',{method:'POST'})">&#9679; Start</button>
    <button class="btn-r" onclick="fetch('/record/stop',{method:'POST'})">&#9632; Stop</button>
    <button class="btn-b" onclick="window.open('/snapshot','_blank')">&#128247; Snapshot</button>
  </div>
</div>
<script>
document.getElementById('s').src='http://'+location.hostname+':81/?'+Date.now();
function applyMotion(){
  fetch('/motion',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({enable:document.getElementById('me').checked,
      threshold:parseInt(document.getElementById('sr').value)})});
}
function update(){
  fetch('/status').then(r=>r.json()).then(d=>{
    document.getElementById('bf').style.width=d.batt_pct+'%';
    document.getElementById('bp').textContent=d.batt_pct+'%';
    document.getElementById('bv').textContent=d.batt_v.toFixed(2)+'V';
    var m=d.motion,r=d.recording;
    document.getElementById('mb').textContent=m?'MOTION':'IDLE';
    document.getElementById('mb').className='badge '+(m?'br':'bg');
    document.getElementById('ri').textContent=r?'⏺':'⏹';
    document.getElementById('rl').textContent=r?'Recording...':'Idle';
  }).catch(()=>{});
}
setInterval(update,3000); update();
</script></body></html>
)rawliteral";

// ── MJPEG stream handler — runs on Core 0 ────────────────────────────────
void handleStreamClient(WiFiClient client) {
  uint32_t t0 = millis();
  while (client.connected() && millis() - t0 < 1000) {
    if (client.available()) { if (client.readStringUntil('\n') == "\r") break; }
  }
  client.print(
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
    "Access-Control-Allow-Origin: *\r\n"
    "Cache-Control: no-cache\r\n\r\n");

  while (client.connected()) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) { delay(30); continue; }
    if (checkMotion(fb) && !isRecording()) startRecording();
    saveFrame(fb);
    client.print("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ");
    client.print((int)fb->len);
    client.print("\r\n\r\n");
    client.write(fb->buf, fb->len);
    client.print("\r\n");
    esp_camera_fb_return(fb);
    delay(33);
  }
  client.stop();
}

// ── REST API ─────────────────────────────────────────────────────────────
void setupWebServer(WebServer& srv) {
  srv.on("/", HTTP_GET, [&]() {
    String p = FPSTR(CAM_PAGE);
    p.replace("__CAM_ID__",   String(CAM_ID));
    p.replace("__CAM_NAME__", String(CAM_NAME));
    srv.send(200, "text/html", p);
  });

  srv.on("/snapshot", HTTP_GET, [&]() {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) { srv.send(503, "text/plain", "Camera error"); return; }
    srv.send_P(200, "image/jpeg", (const char*)fb->buf, fb->len);
    esp_camera_fb_return(fb);
  });

  srv.on("/status", HTTP_GET, [&]() {
    char buf[192];
    snprintf(buf, sizeof(buf),
      "{\"cam_id\":%d,\"cam_name\":\"%s\","
      "\"batt_pct\":%d,\"batt_v\":%.2f,"
      "\"motion\":%s,\"recording\":%s,\"sd\":%s}",
      CAM_ID, CAM_NAME,
      getBattPct(), getBattV(),
      isMotionSeen() ? "true" : "false",
      isRecording()  ? "true" : "false",
      isSDReady()    ? "true" : "false");
    srv.send(200, "application/json", buf);
  });

  srv.on("/motion", HTTP_POST, [&]() {
    String b = srv.arg("plain");
    if      (b.indexOf("\"enable\":false") >= 0) setMotionOn(false);
    else if (b.indexOf("\"enable\":true")  >= 0) setMotionOn(true);
    int ti = b.indexOf("\"threshold\":");
    if (ti >= 0) setMotionThr(b.substring(ti + 12).toInt());
    srv.send(200, "application/json", "{\"ok\":true}");
  });

  srv.on("/record/start", HTTP_POST, [&]() { startRecording(); srv.send(200, "application/json", "{\"ok\":true}"); });
  srv.on("/record/stop",  HTTP_POST, [&]() { stopRecording();  srv.send(200, "application/json", "{\"ok\":true}"); });
  srv.on("/files", HTTP_GET, [&]() { srv.send(200, "application/json", listLocalRecs()); });
}
