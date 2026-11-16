#!/usr/bin/env python3
"""
jedi-faatracker - Termux-ready FAA / ADS-B flight tracker backend + simple map UI

Runs a lightweight Flask server that:
- Proxies OpenSky Network live states (bbox filtered)
- Optionally merges military aircraft from adsb.lol
- Tags flights as commercial / private / military using heuristics
- Serves a full-screen Leaflet map with layer toggles
- Designed for Termux (Android) with minimal deps

Usage in Termux:
  pkg update && pkg install python
  pip install flask requests
  python tracker.py

Then open http://127.0.0.1:8080 on the phone (or phone's IP from other devices).
"""

import json
import time
import threading
from datetime import datetime
from flask import Flask, jsonify, request, Response

try:
    import requests
except ImportError:
    print("Missing dependency. In Termux run: pip install flask requests")
    raise

app = Flask(__name__)

# Simple in-memory cache
_cache = {"data": None, "ts": 0, "ttl": 12}
_lock = threading.Lock()

# Known military callsign prefixes / patterns (heuristic)
MILITARY_PREFIXES = (
    "RCH", "CNV", "EVAC", "DUKE", "REACH", "TOPCAT", "IRON", "VIPER",
    "HAWK", "EAGLE", "NAVY", "ARMY", "USAF", "RCAF", "RAF", "GAF",
    "QID", "SAM", "EXEC", "SPAR", "VENUS", "JAKE", "NINJA", "GHOST",
    "SKULL", "BONE", "DEATH", "WAR", "TANKER", "KC", "C17", "C5",
    "B52", "B1", "B2", "F15", "F16", "F18", "F22", "F35", "A10",
    "E3", "E6", "E8", "RC135", "U2", "RQ", "MQ", "PRED", "REAPER",
)

COMMERCIAL_AIRLINES = (
    "AAL", "UAL", "DAL", "SWA", "JBU", "ASA", "NKS", "FFT", "SKW",
    "RPA", "ENY", "ASH", "PDT", "GJS", "EDV", "QXE", "ASQ", "LOF",
    "BAW", "DLH", "AFR", "KLM", "EIN", "RYR", "EZY", "WZZ", "SWR",
    "AUA", "TAP", "IBE", "AZA", "QFA", "SIA", "CPA", "JAL", "ANA",
    "CCA", "CES", "CSN", "KAL", "THA", "MAS", "GIA", "PAL", "EVA",
)


def classify_flight(callsign: str, icao24: str = "") -> str:
    """Heuristic layer classification."""
    if not callsign:
        return "private"
    cs = callsign.strip().upper()
    if any(cs.startswith(p) for p in MILITARY_PREFIXES) or any(p in cs for p in ("MIL", "ARMY", "NAVY", "AF", "USAF")):
        return "military"
    if any(cs.startswith(p) for p in COMMERCIAL_AIRLINES) or (len(cs) >= 3 and cs[:3].isalpha() and any(c.isdigit() for c in cs[3:])):
        return "commercial"
    return "private"


def fetch_opensky(lamin, lomin, lamax, lomax):
    url = "https://opensky-network.org/api/states/all"
    params = {
        "lamin": lamin,
        "lomin": lomin,
        "lamax": lamax,
        "lomax": lomax,
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        states = data.get("states") or []
        flights = []
        for s in states:
            if not s or len(s) < 11:
                continue
            icao24 = s[0]
            callsign = (s[1] or "").strip()
            lon = s[5]
            lat = s[6]
            alt = s[7]  # baro meters
            on_ground = s[8]
            velocity = s[9]  # m/s
            track = s[10]  # degrees
            if lat is None or lon is None:
                continue
            layer = classify_flight(callsign, icao24)
            flights.append({
                "icao24": icao24,
                "callsign": callsign or "N/A",
                "lat": lat,
                "lon": lon,
                "alt_m": alt,
                "alt_ft": round(alt * 3.28084) if alt else None,
                "on_ground": on_ground,
                "velocity_ms": velocity,
                "velocity_kt": round(velocity * 1.94384) if velocity else None,
                "track": track,
                "layer": layer,
                "source": "opensky",
            })
        return flights
    except Exception as e:
        print(f"OpenSky error: {e}")
        return []


def fetch_military():
    """Pull known military from adsb.lol (unfiltered community feed)."""
    try:
        r = requests.get("https://api.adsb.lol/v2/mil", timeout=12)
        r.raise_for_status()
        data = r.json()
        ac = data.get("ac") or []
        flights = []
        for a in ac:
            lat = a.get("lat")
            lon = a.get("lon")
            if lat is None or lon is None:
                continue
            callsign = (a.get("flight") or a.get("r") or "").strip()
            flights.append({
                "icao24": a.get("hex", "").lower(),
                "callsign": callsign or "MIL",
                "lat": lat,
                "lon": lon,
                "alt_m": a.get("alt_baro"),
                "alt_ft": a.get("alt_baro"),
                "on_ground": a.get("alt_baro", 0) < 100,
                "velocity_ms": (a.get("gs") or 0) * 0.514444,
                "velocity_kt": a.get("gs"),
                "track": a.get("track"),
                "layer": "military",
                "source": "adsb.lol",
            })
        return flights
    except Exception as e:
        print(f"adsb.lol mil error: {e}")
        return []


def get_flights(lamin, lomin, lamax, lomax, layers):
    with _lock:
        now = time.time()
        if _cache["data"] and (now - _cache["ts"]) < _cache["ttl"]:
            all_flights = _cache["data"]
        else:
            opensky = fetch_opensky(lamin, lomin, lamax, lomax)
            military = fetch_military()
            # Merge, prefer military source for duplicates
            by_icao = {}
            for f in opensky + military:
                key = f["icao24"]
                if key not in by_icao or f["source"] == "adsb.lol":
                    by_icao[key] = f
            all_flights = list(by_icao.values())
            _cache["data"] = all_flights
            _cache["ts"] = now

    # Filter by requested layers and rough bbox (military list is global)
    result = []
    for f in all_flights:
        if f["layer"] not in layers:
            continue
        # Rough bbox filter for military entries
        if not (lamin <= f["lat"] <= lamax and lomin <= f["lon"] <= lomax):
            continue
        result.append(f)
    return result


MAP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>jedi-faatracker</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body, #map { height: 100%; margin: 0; padding: 0; background: #0a0a0a; }
  .controls {
    position: absolute; top: 10px; left: 10px; z-index: 1000;
    background: rgba(20,20,20,0.92); color: #eee; padding: 12px; border-radius: 8px;
    font-family: system-ui, sans-serif; font-size: 14px; max-width: 280px;
  }
  .controls label { display: block; margin: 4px 0; cursor: pointer; }
  .controls input { margin-right: 6px; }
  .status { font-size: 12px; color: #aaa; margin-top: 8px; }
  .plane { font-size: 18px; }
</style>
</head>
<body>
<div id="map"></div>
<div class="controls">
  <strong>jedi-faatracker</strong><br>
  <label><input type="checkbox" id="commercial" checked> Commercial</label>
  <label><input type="checkbox" id="private" checked> Private</label>
  <label><input type="checkbox" id="military" checked> Military</label>
  <div class="status" id="status">Loading...</div>
</div>
<script>
const map = L.map('map').setView([32.5, -91.5], 6); // Default near Bastrop, LA area
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; OpenStreetMap &copy; CARTO',
  subdomains: 'abcd',
  maxZoom: 19
}).addTo(map);

const layers = {
  commercial: L.layerGroup().addTo(map),
  private: L.layerGroup().addTo(map),
  military: L.layerGroup().addTo(map),
};
const colors = { commercial: '#3b82f6', private: '#22c55e', military: '#ef4444' };

function updateLayers() {
  const active = [];
  ['commercial','private','military'].forEach(l => {
    if (document.getElementById(l).checked) active.push(l);
  });
  const b = map.getBounds();
  const url = `/api/flights?lamin=${b.getSouth()}&lomin=${b.getWest()}&lamax=${b.getNorth()}&lomax=${b.getEast()}&layers=${active.join(',')}`;
  fetch(url).then(r => r.json()).then(data => {
    Object.values(layers).forEach(g => g.clearLayers());
    data.flights.forEach(f => {
      const icon = L.divIcon({
        className: 'plane',
        html: `<span style="color:${colors[f.layer]||'#fff'};transform:rotate(${f.track||0}deg);display:inline-block;">\u2708</span>`,
        iconSize: [24,24],
        iconAnchor: [12,12]
      });
      const m = L.marker([f.lat, f.lon], {icon}).bindPopup(
        `<b>${f.callsign}</b><br>Layer: ${f.layer}<br>Alt: ${f.alt_ft||'?'} ft<br>Spd: ${f.velocity_kt||'?'} kt<br>ICAO: ${f.icao24}<br>Src: ${f.source}`
      );
      layers[f.layer].addLayer(m);
    });
    document.getElementById('status').textContent = `${data.flights.length} aircraft \u2022 ${new Date().toLocaleTimeString()}`;
  }).catch(e => {
    document.getElementById('status').textContent = 'Error: ' + e;
  });
}

['commercial','private','military'].forEach(id => {
  document.getElementById(id).addEventListener('change', updateLayers);
});
map.on('moveend', updateLayers);
setInterval(updateLayers, 15000);
updateLayers();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return Response(MAP_HTML, mimetype="text/html")


@app.route("/api/flights")
def api_flights():
    try:
        lamin = float(request.args.get("lamin", 20))
        lomin = float(request.args.get("lomin", -130))
        lamax = float(request.args.get("lamax", 50))
        lomax = float(request.args.get("lomax", -60))
    except ValueError:
        return jsonify({"error": "invalid bbox"}), 400

    layers_str = request.args.get("layers", "commercial,private,military")
    layers = [l.strip() for l in layers_str.split(",") if l.strip()]

    flights = get_flights(lamin, lomin, lamax, lomax, layers)
    return jsonify({
        "time": int(time.time()),
        "count": len(flights),
        "flights": flights,
        "bbox": [lamin, lomin, lamax, lomax],
        "layers": layers,
    })


@app.route("/api/health")
def health():
    return jsonify({"ok": True, "ts": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    print("jedi-faatracker starting on http://0.0.0.0:8080")
    print("Termux tip: keep the session open or use nohup / tmux")
    app.run(host="0.0.0.0", port=8080, threaded=True)
