#!/usr/bin/env python3
"""
WHOOP BLE Monitor — real-time heart rate via Bluetooth + activity intervals
Run: ./run.sh
"""

import asyncio, threading
from datetime import datetime
from collections import deque
from flask import Flask, jsonify, Response

app = Flask(__name__)

state = {
    "heart_rate": None,
    "updated_at": "--",
    "error":      None,
    "status":     "scanning",
    "device_name": None,
}
hr_history = deque(maxlen=7200)
_lock = threading.Lock()

HR_SERVICE_UUID  = "0000180d-0000-1000-8000-00805f9b34fb"
HR_CHAR_UUID     = "00002a37-0000-1000-8000-00805f9b34fb"
WHOOP_NAME_HINTS = ["whoop", "strap"]


def parse_hr(data: bytearray) -> int:
    flags = data[0]
    return int.from_bytes(data[1:3], "little") if flags & 0x01 else data[1]


async def ble_loop():
    from bleak import BleakScanner, BleakClient
    from bleak.exc import BleakError

    while True:
        with _lock:
            state.update(status="scanning", error=None, device_name=None)
        print("[scan] Looking for Whoop...")

        device = None
        try:
            devices = await BleakScanner.discover(timeout=8.0)
            for d in devices:
                name = (d.name or "").lower()
                print(f"[scan] Found: {d.name} ({d.address})")
                if any(h in name for h in WHOOP_NAME_HINTS):
                    device = d
                    break
            if not device:
                devs2 = await BleakScanner.discover(timeout=8.0, service_uuids=[HR_SERVICE_UUID])
                if devs2:
                    device = devs2[0]
        except Exception as e:
            print(f"[scan error] {e}")
            with _lock:
                state.update(status="error", error=f"Scan error: {e}")
            await asyncio.sleep(5)
            continue

        if not device:
            with _lock:
                state.update(status="scanning",
                             error="Whoop not found. Make sure the strap is on and Bluetooth is enabled.")
            await asyncio.sleep(10)
            continue

        print(f"[scan] Connecting to {device.name} ({device.address})...")
        with _lock:
            state.update(status="connecting", device_name=device.name, error=None)

        try:
            async with BleakClient(device.address, timeout=15.0) as client:
                print(f"[ble] Connected: {device.name}")
                with _lock:
                    state.update(status="ok", error=None)

                def hr_handler(_, data):
                    hr  = parse_hr(bytearray(data))
                    ts  = datetime.now().strftime("%H:%M:%S")
                    print(f"[hr] {hr} bpm @ {ts}")
                    with _lock:
                        state.update(heart_rate=hr, updated_at=ts, status="ok", error=None)
                        hr_history.append({"t": ts, "hr": hr})

                await client.start_notify(HR_CHAR_UUID, hr_handler)
                print("[ble] Receiving live heart rate...")

                while client.is_connected:
                    await asyncio.sleep(1)
                print("[ble] Connection lost, reconnecting...")

        except BleakError as e:
            print(f"[ble error] {e}")
            with _lock:
                state.update(status="error", error=f"BLE error: {e}", heart_rate=None)
        except Exception as e:
            print(f"[ble error] {e}")
            with _lock:
                state.update(status="error", error=str(e), heart_rate=None)

        await asyncio.sleep(3)


def ble_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ble_loop())


# ── Dashboard HTML ─────────────────────────────────────────────────────────────
DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WHOOP Live</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg:      #07080f;
  --surface: #0e0f1a;
  --border:  #181929;
  --text:    #e0e3ff;
  --muted:   #44476a;
  --green:   #3df598;
  --red:     #ff4d6d;
  --orange:  #ff9f1c;
  --cyan:    #00d4ff;
  --yellow:  #ffe066;
}
body {
  background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif;
  min-height: 100vh;
  display: flex; flex-direction: column; align-items: center;
  padding: 28px 16px 48px; gap: 14px;
}
.logo { font-size: 11px; letter-spacing: 5px; text-transform: uppercase; color: var(--muted); }
.badge {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--muted);
  padding: 5px 14px; border: 1px solid var(--border); border-radius: 20px;
}
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); }
.dot.scanning { background: var(--yellow); animation: blink 1.2s ease-in-out infinite; }
.dot.error    { background: var(--red); }
.dot.ok       { animation: blink 1.2s ease-in-out infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.2} }

/* ── Top row ── */
.top-row {
  display: flex; gap: 12px;
  width: 100%; max-width: 820px; align-items: stretch;
}
.hr-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 24px; padding: 26px 26px;
  text-align: center; position: relative; overflow: hidden;
  flex-shrink: 0; width: 192px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
}
.hr-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, #ff4d6d, #ff9f1c); border-radius: 24px 24px 0 0;
}
.hr-value { font-size: 68px; font-weight: 100; letter-spacing: -5px; line-height: 1; color: #ff6b85; transition: color .3s; }
.hr-lbl   { font-size: 10px; letter-spacing: 3px; text-transform: uppercase; color: var(--muted); margin-top: 6px; }
.hr-unit  { font-size: 11px; color: var(--muted); margin-top: 4px; }
.zone-bar { display: flex; gap: 3px; margin-top: 16px; }
.zone { height: 3px; border-radius: 2px; width: 26px; background: var(--border); transition: background .4s; }
@keyframes hb { 0%,100%{transform:scale(1)} 15%{transform:scale(1.06)} 30%{transform:scale(1)} 45%{transform:scale(1.03)} }
.beat { animation: hb var(--bpm-interval,1s) ease-in-out infinite; }

.mini-stats {
  display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr;
  gap: 10px; flex: 1;
}
.stat {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 18px; padding: 15px 18px;
  display: flex; flex-direction: column; justify-content: center;
}
.stat-val { font-size: 30px; font-weight: 200; letter-spacing: -2px; color: var(--cyan); }
.stat-lbl { font-size: 9px; letter-spacing: 2px; text-transform: uppercase; color: var(--muted); margin-top: 3px; }

/* ── Chart card ── */
.chart-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 24px; padding: 20px 24px 18px;
  width: 100%; max-width: 820px; position: relative;
}
.chart-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, #7c3aed, #00d4ff); border-radius: 24px 24px 0 0;
}
.chart-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.chart-title  { font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase; color: var(--muted); }
.win-btns { display: flex; gap: 5px; }
.win-btn {
  font-size: 10px; padding: 4px 10px; border-radius: 8px;
  border: 1px solid var(--border); background: transparent;
  color: var(--muted); cursor: pointer; transition: all .2s; font-family: inherit;
}
.win-btn.active, .win-btn:hover { border-color: rgba(0,212,255,.4); color: var(--cyan); background: rgba(0,212,255,.07); }
canvas { width: 100% !important; }

/* ── Activity controls ── */
.activity-controls {
  display: flex; gap: 8px; margin-top: 16px; align-items: center;
}
.activity-input {
  flex: 1; background: var(--bg); border: 1px solid var(--border);
  border-radius: 10px; padding: 9px 13px;
  color: var(--text); font-size: 13px; font-family: inherit; outline: none;
}
.activity-input::placeholder { color: var(--muted); }
.activity-input:focus { border-color: rgba(0,212,255,.4); }
.activity-input:disabled { opacity: .4; cursor: not-allowed; }

.btn-start {
  background: rgba(61,245,152,.12); border: 1px solid rgba(61,245,152,.35);
  border-radius: 10px; padding: 9px 18px; color: var(--green);
  font-size: 12px; font-family: inherit; cursor: pointer; white-space: nowrap;
  transition: all .2s; font-weight: 500;
}
.btn-start:hover  { background: rgba(61,245,152,.22); }
.btn-start:disabled { opacity: .35; cursor: not-allowed; }

.btn-stop {
  display: none;
  background: rgba(255,77,109,.12); border: 1px solid rgba(255,77,109,.35);
  border-radius: 10px; padding: 9px 18px; color: var(--red);
  font-size: 12px; font-family: inherit; cursor: pointer; white-space: nowrap;
  transition: all .2s; font-weight: 500;
}
.btn-stop:hover { background: rgba(255,77,109,.22); }

/* Live activity pill */
.live-activity {
  display: none;
  align-items: center; gap: 8px;
  background: rgba(255,77,109,.08); border: 1px solid rgba(255,77,109,.25);
  border-radius: 10px; padding: 6px 12px;
  font-size: 11px; color: #ff8fa3;
}
.live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--red); animation: blink .8s ease-in-out infinite; }

/* ── Activity log ── */
.section-title {
  width: 100%; max-width: 820px;
  font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase; color: var(--muted);
  padding-left: 4px;
}
.activity-list { width: 100%; max-width: 820px; display: flex; flex-direction: column; gap: 8px; }

.activity-card {
  border-radius: 16px; padding: 14px 18px;
  display: flex; align-items: center; gap: 16px;
  border-left: 3px solid;
}
.act-color-strip { width: 4px; border-radius: 2px; align-self: stretch; flex-shrink: 0; }
.act-name  { font-size: 14px; font-weight: 500; flex: 1; }
.act-time  { font-size: 11px; color: var(--muted); margin-top: 2px; }
.act-stats { display: flex; gap: 16px; flex-shrink: 0; text-align: center; }
.act-stat-val { font-size: 20px; font-weight: 300; }
.act-stat-lbl { font-size: 8px; letter-spacing: 1.5px; text-transform: uppercase; color: var(--muted); margin-top: 1px; }
.act-del { background: none; border: none; color: var(--muted); cursor: pointer; font-size: 16px; padding: 0 2px; transition: color .2s; }
.act-del:hover { color: var(--red); }

.err {
  display: none; max-width: 820px; width: 100%;
  background: rgba(255,77,109,.08); border: 1px solid rgba(255,77,109,.2);
  border-radius: 12px; padding: 12px 16px;
  font-size: 12px; color: #ff8fa3; text-align: center; line-height: 1.6;
}
.footer { font-size: 11px; color: var(--muted); }
</style>
</head>
<body>

<div class="logo">⌁ &nbsp; W H O O P &nbsp; L I V E</div>
<div class="badge"><span class="dot scanning" id="dot"></span><span id="status-text">Scanning...</span></div>
<div class="err" id="err"></div>

<div class="top-row">
  <div class="hr-card">
    <div class="beat" id="beat-el">
      <div class="hr-value" id="hr">--</div>
    </div>
    <div class="hr-lbl">❤ Heart Rate</div>
    <div class="hr-unit">bpm</div>
    <div class="zone-bar">
      <div class="zone" id="z1"></div><div class="zone" id="z2"></div>
      <div class="zone" id="z3"></div><div class="zone" id="z4"></div>
      <div class="zone" id="z5"></div>
    </div>
  </div>
  <div class="mini-stats">
    <div class="stat"><div class="stat-val" id="s-min">--</div><div class="stat-lbl">Min</div></div>
    <div class="stat"><div class="stat-val" id="s-max">--</div><div class="stat-lbl">Max</div></div>
    <div class="stat"><div class="stat-val" id="s-avg">--</div><div class="stat-lbl">Average</div></div>
    <div class="stat"><div class="stat-val" id="s-dur">0:00</div><div class="stat-lbl">Session</div></div>
  </div>
</div>

<!-- Chart -->
<div class="chart-card">
  <div class="chart-header">
    <span class="chart-title">Heart Rate History</span>
    <div class="win-btns">
      <button class="win-btn" onclick="setWindow(2,this)">2 min</button>
      <button class="win-btn active" onclick="setWindow(5,this)">5 min</button>
      <button class="win-btn" onclick="setWindow(15,this)">15 min</button>
      <button class="win-btn" onclick="setWindow(60,this)">1 hr</button>
      <button class="win-btn" onclick="setWindow(0,this)">All</button>
    </div>
  </div>
  <canvas id="chart" height="150"></canvas>

  <!-- Activity controls -->
  <div class="activity-controls">
    <input class="activity-input" id="act-input" placeholder="Name your activity: meeting, vibe coding, reading..." maxlength="60">
    <button class="btn-start" id="btn-start" onclick="startActivity()">▶ Start</button>
    <button class="btn-stop"  id="btn-stop"  onclick="stopActivity()">■ Stop</button>
    <div class="live-activity" id="live-pill">
      <span class="live-dot"></span>
      <span id="live-name">—</span>
      <span id="live-timer">0:00</span>
    </div>
  </div>
</div>

<!-- Activity log -->
<div class="section-title" id="log-title" style="display:none">Activity Log</div>
<div class="activity-list" id="activity-list"></div>

<div class="footer" id="footer">Waiting for data...</div>

<script>
// ── Data ────────────────────────────────────────────────────────────────────────
const allLabels = [];   // "HH:MM:SS" per second
const allData   = [];   // bpm values
let windowMinutes = 5;
let sessionStart  = null;
let lastTs        = null;

// ── Activities ──────────────────────────────────────────────────────────────────
const activities   = [];       // completed
let activeActivity = null;     // {name, startIdx, startTime, startTs, color, timerInterval}

const PALETTE = [
  "rgba(61,245,152,",   // green
  "rgba(0,212,255,",    // cyan
  "rgba(176,106,240,",  // purple
  "rgba(255,159,28,",   // orange
  "rgba(232,79,170,",   // pink
  "rgba(255,224,102,",  // yellow
  "rgba(255,77,109,",   // red
];
let paletteIdx = 0;
function nextColor() { return PALETTE[paletteIdx++ % PALETTE.length]; }

// ── Zones ───────────────────────────────────────────────────────────────────────
const ZONES = [
  { max: 114, color: "#3df598" },
  { max: 133, color: "#00d4ff" },
  { max: 152, color: "#ffe066" },
  { max: 171, color: "#ff9f1c" },
  { max: 999, color: "#ff4d6d" },
];
function getZone(hr) { for (let i=0;i<ZONES.length;i++) if(hr<=ZONES[i].max) return i; return 4; }
function setZoneBars(z) {
  for (let i=1;i<=5;i++) {
    const el = document.getElementById("z"+i);
    el.style.background = (i-1)<=z ? ZONES[z].color : "var(--border)";
    el.style.opacity    = (i-1)<=z ? String(0.35+0.12*i) : "1";
  }
}

// ── Chart with activity background bands ─────────────────────────────────────
const ctx = document.getElementById("chart").getContext("2d");

// Custom plugin to draw activity bands behind the line
const activityBandsPlugin = {
  id: "activityBands",
  beforeDatasetsDraw(chart) {
    const { ctx: c, chartArea, data } = chart;
    if (!chartArea) return;
    const xScale = chart.scales.x;
    const visibleLabels = data.labels;
    if (!visibleLabels || visibleLabels.length === 0) return;

    const toDraw = [...activities];
    if (activeActivity) {
      toDraw.push({
        ...activeActivity,
        endTime: allLabels[allData.length - 1] || visibleLabels[visibleLabels.length - 1],
      });
    }

    toDraw.forEach(act => {
      if (!act.startTime) return;
      const endTime = act.endTime || visibleLabels[visibleLabels.length - 1];

      // Find nearest indices in visible labels
      let si = 0;
      for (let i = 0; i < visibleLabels.length; i++) {
        if (visibleLabels[i] >= act.startTime) { si = i; break; }
        si = visibleLabels.length - 1;
      }
      let ei = visibleLabels.length - 1;
      for (let i = visibleLabels.length - 1; i >= 0; i--) {
        if (visibleLabels[i] <= endTime) { ei = i; break; }
      }
      if (si > ei) return;

      // Chart.js 4: getPixelForValue on category scale takes numeric index
      const x1 = xScale.getPixelForValue(si);
      const x2 = xScale.getPixelForValue(ei);
      if (isNaN(x1) || isNaN(x2)) return;

      c.save();
      // Slightly inset each band by 1px so adjacent bands have a visible gap
      c.fillStyle = act.color + "0.13)";
      c.fillRect(x1 + 1, chartArea.top, x2 - x1 - 2, chartArea.bottom - chartArea.top);
      // Left border (strong)
      c.strokeStyle = act.color + "0.7)";
      c.lineWidth = 2;
      c.beginPath(); c.moveTo(x1 + 1, chartArea.top); c.lineTo(x1 + 1, chartArea.bottom); c.stroke();
      // Right border (faint)
      c.strokeStyle = act.color + "0.25)";
      c.lineWidth = 1;
      c.beginPath(); c.moveTo(x2 - 1, chartArea.top); c.lineTo(x2 - 1, chartArea.bottom); c.stroke();
      // Label with background pill
      const label = act.name;
      c.font = "bold 10px -apple-system, sans-serif";
      const tw = c.measureText(label).width;
      c.fillStyle = act.color + "0.18)";
      c.beginPath();
      c.roundRect(x1 + 6, chartArea.top + 4, tw + 10, 17, 4);
      c.fill();
      c.fillStyle = act.color + "0.9)";
      c.fillText(label, x1 + 11, chartArea.top + 15);
      c.restore();
    });
  }
};

Chart.register(activityBandsPlugin);

const chart = new Chart(ctx, {
  type: "line",
  data: { labels: [], datasets: [{
    data: [], borderColor: "#ff6b85", borderWidth: 2,
    pointRadius: 0, pointHoverRadius: 5,
    fill: true,
    backgroundColor: (c) => {
      const g = c.chart.ctx.createLinearGradient(0, 0, 0, c.chart.height);
      g.addColorStop(0,   "rgba(255,77,109,0.28)");
      g.addColorStop(0.7, "rgba(255,77,109,0.04)");
      g.addColorStop(1,   "rgba(255,77,109,0)");
      return g;
    },
    tension: 0.35,
  }]},
  options: {
    responsive: true,
    animation: { duration: 0 },
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "#0e0f1a", borderColor: "#181929", borderWidth: 1,
        titleColor: "#44476a", bodyColor: "#e0e3ff",
        callbacks: { label: c => " " + c.parsed.y + " bpm" }
      }
    },
    scales: {
      x: {
        ticks: { color: "#44476a", font: { size: 10 }, maxTicksLimit: 8, maxRotation: 0 },
        grid:  { color: "rgba(255,255,255,0.04)" },
        border:{ color: "#181929" },
      },
      y: {
        ticks: { color: "#44476a", font: { size: 10 } },
        grid:  { color: "rgba(255,255,255,0.05)" },
        border:{ color: "#181929" },
        suggestedMin: 45, suggestedMax: 120,
      }
    }
  }
});

function setWindow(minutes, btn) {
  windowMinutes = minutes;
  document.querySelectorAll(".win-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  updateChart();
}

function updateChart() {
  const n = windowMinutes === 0 ? allData.length : windowMinutes * 60;
  const labels = allLabels.slice(-n);
  const data   = allData.slice(-n);
  chart.data.labels           = labels;
  chart.data.datasets[0].data = data;
  const step = Math.max(1, Math.floor(labels.length / 8));
  chart.options.scales.x.ticks.callback = function(val, idx) {
    return idx % step === 0 ? this.getLabelForValue(val) : "";
  };
  chart.update("none");
}

// ── Activity start / stop ───────────────────────────────────────────────────────
function startActivity() {
  const input = document.getElementById("act-input");
  const name  = input.value.trim() || "Activity";
  if (allData.length === 0) { input.placeholder = "Wait for HR data first..."; return; }

  const color    = nextColor();
  const startIdx = allData.length - 1;
  const startTime = allLabels[startIdx] || "--";
  const startTs  = Date.now();

  // Live timer
  const timerInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTs) / 1000);
    document.getElementById("live-timer").textContent =
      Math.floor(elapsed/60) + ":" + String(elapsed%60).padStart(2,"0");
  }, 1000);

  activeActivity = { name, color, startIdx, startTime, startTs, timerInterval };

  // UI
  input.disabled = true;
  document.getElementById("btn-start").style.display = "none";
  document.getElementById("btn-stop").style.display  = "inline-block";
  const pill = document.getElementById("live-pill");
  pill.style.display = "flex";
  document.getElementById("live-name").textContent  = name;
  document.getElementById("live-timer").textContent = "0:00";
}

function stopActivity() {
  if (!activeActivity) return;

  clearInterval(activeActivity.timerInterval);

  const endIdx  = allData.length - 1;
  const endTime = allLabels[endIdx] || "--";
  const slice   = allData.slice(activeActivity.startIdx, endIdx + 1);
  const avg     = slice.length ? Math.round(slice.reduce((a,b)=>a+b,0)/slice.length) : null;
  const min     = slice.length ? Math.min(...slice) : null;
  const max     = slice.length ? Math.max(...slice) : null;
  const durSec  = Math.floor((Date.now() - activeActivity.startTs) / 1000);
  const durStr  = Math.floor(durSec/60) + ":" + String(durSec%60).padStart(2,"0");

  const completed = { ...activeActivity, endIdx, endTime, avg, min, max, durStr };
  activities.push(completed);

  // Reset UI
  activeActivity = null;
  const input = document.getElementById("act-input");
  input.disabled = false;
  input.value    = "";
  input.placeholder = "Name your activity: meeting, vibe coding, reading...";
  document.getElementById("btn-start").style.display = "inline-block";
  document.getElementById("btn-stop").style.display  = "none";
  document.getElementById("live-pill").style.display = "none";

  renderActivityLog();
  updateChart();
}

// Enter key to start/stop
document.getElementById("act-input").addEventListener("keydown", e => {
  if (e.key === "Enter") {
    if (activeActivity) stopActivity(); else startActivity();
  }
});

function renderActivityLog() {
  const list = document.getElementById("activity-list");
  list.innerHTML = "";
  document.getElementById("log-title").style.display =
    activities.length > 0 ? "block" : "none";

  [...activities].reverse().forEach((a, ri) => {
    const idx  = activities.length - 1 - ri;
    const c    = a.color;
    const card = document.createElement("div");
    card.className = "activity-card";
    card.style.background   = c + "0.06)";
    card.style.borderColor  = c + "0.4)";
    card.style.borderLeft   = "3px solid " + c + "0.8)";

    card.innerHTML = `
      <div style="flex:1">
        <div class="act-name" style="color:${c}0.9)">${a.name}</div>
        <div class="act-time">${a.startTime} → ${a.endTime} &nbsp;·&nbsp; ${a.durStr}</div>
      </div>
      <div class="act-stats">
        <div>
          <div class="act-stat-val" style="color:${c}0.9)">${a.avg ?? "--"}</div>
          <div class="act-stat-lbl">avg bpm</div>
        </div>
        <div>
          <div class="act-stat-val" style="color:${c}0.7)">${a.min ?? "--"}</div>
          <div class="act-stat-lbl">min</div>
        </div>
        <div>
          <div class="act-stat-val" style="color:${c}0.7)">${a.max ?? "--"}</div>
          <div class="act-stat-lbl">peak</div>
        </div>
      </div>
      <button class="act-del" onclick="deleteActivity(${idx})">×</button>
    `;
    list.appendChild(card);
  });
}

function deleteActivity(idx) {
  activities.splice(idx, 1);
  renderActivityLog();
  updateChart();
}

// ── Session timer ────────────────────────────────────────────────────────────────
setInterval(() => {
  if (!sessionStart) return;
  const s = Math.floor((Date.now() - sessionStart) / 1000);
  document.getElementById("s-dur").textContent =
    Math.floor(s/60) + ":" + String(s%60).padStart(2,"0");
}, 1000);

// ── Poll server ──────────────────────────────────────────────────────────────────
async function refresh() {
  try {
    const res = await fetch("/api/data");
    if (!res.ok) throw new Error();
    const d = await res.json();

    const dot   = document.getElementById("dot");
    const stTx  = document.getElementById("status-text");
    const errEl = document.getElementById("err");

    if (d.error) {
      errEl.style.display = "block"; errEl.textContent = d.error;
      dot.className = "dot error"; stTx.textContent = "Error";
    } else {
      errEl.style.display = "none";
      dot.className    = d.status === "ok" ? "dot ok" : "dot scanning";
      stTx.textContent = d.status === "ok"
        ? (d.device_name || "Whoop") + " — LIVE"
        : d.status === "connecting" ? "Connecting..." : "Scanning...";
    }

    if (d.heart_rate !== null && d.updated_at !== "--" && d.updated_at !== lastTs) {
      lastTs = d.updated_at;
      if (!sessionStart) sessionStart = Date.now();

      allLabels.push(d.updated_at);
      allData.push(d.heart_rate);

      const hr   = d.heart_rate;
      const zone = getZone(hr);
      const hrEl = document.getElementById("hr");
      hrEl.textContent = hr;
      hrEl.style.color = ZONES[zone].color;
      document.getElementById("beat-el")
        .style.setProperty("--bpm-interval", Math.max(0.4, 60/hr) + "s");
      setZoneBars(zone);

      document.getElementById("s-min").textContent = Math.min(...allData);
      document.getElementById("s-max").textContent = Math.max(...allData);
      document.getElementById("s-avg").textContent =
        Math.round(allData.reduce((a,b)=>a+b,0)/allData.length);

      updateChart();
    }

    document.getElementById("footer").textContent =
      d.updated_at !== "--"
        ? "Updated: " + d.updated_at + "  ·  " + allData.length + " points"
        : "Waiting for data...";

  } catch(e) {
    document.getElementById("dot").className = "dot error";
    document.getElementById("status-text").textContent = "No connection to server";
  }
}

refresh();
setInterval(refresh, 1000);
</script>
</body>
</html>"""


@app.route("/")
def index():
    return Response(DASHBOARD, content_type="text/html; charset=utf-8")

@app.route("/api/data")
def api_data():
    with _lock:
        return jsonify(dict(state))


def run_flask():
    app.run(host="127.0.0.1", port=8765, debug=False, use_reloader=False)


if __name__ == "__main__":
    # BLE thread
    ble_t = threading.Thread(target=ble_thread, daemon=True)
    ble_t.start()

    # Flask thread
    flask_t = threading.Thread(target=run_flask, daemon=True)
    flask_t.start()

    # Wait for Flask to be ready
    import time as _time
    import urllib.request as _req
    for _ in range(20):
        try:
            _req.urlopen("http://127.0.0.1:8765/api/data", timeout=1)
            break
        except Exception:
            _time.sleep(0.3)

    # Open native window via pywebview
    try:
        import webview
        window = webview.create_window(
            title="WHOOP Live",
            url="http://127.0.0.1:8765",
            width=900,
            height=800,
            min_size=(700, 600),
            resizable=True,
        )
        webview.start(debug=False)
    except ImportError:
        # Fallback: open in browser if pywebview not installed
        import webbrowser
        print("\n⚠  pywebview not found, opening in browser instead.")
        print("   Run:  pip install pywebview\n")
        webbrowser.open("http://127.0.0.1:8765")
        # Keep main thread alive
        import time as _t
        while True:
            _t.sleep(1)
