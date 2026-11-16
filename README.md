# jedi-faatracker

Web interface for tracking FAA flights: live (current), past, and future/scheduled. Displays flight courses/paths over an expanded interactive map with selectable layers for commercial, military, and private flights.

## Quick Start (Termux)

```bash
pkg update && pkg install python
pip install flask requests
python tracker.py
```

Open `http://127.0.0.1:8080` in your browser. The page serves a dark Leaflet map with layer toggles. Aircraft update every ~15s.

## What it does
- Proxies OpenSky Network live states (bbox-filtered)
- Merges military aircraft from adsb.lol `/v2/mil`
- Heuristic layer tagging: commercial / private / military
- Embedded full-screen map UI with color-coded planes and popups
- Simple in-memory cache (12s TTL)

## Endpoints
- `GET /` — map UI
- `GET /api/flights?lamin=&lomin=&lamax=&lomax=&layers=commercial,private,military`
- `GET /api/health`

## Notes
- OpenSky is non-commercial / research. Respect their terms.
- Military coverage depends on community feeds (adsb.lol).
- Past/future schedules and full track history are not yet implemented (live positions + heading only for now).
- Keep the Termux session open, or use `tmux` / `nohup`.

## Status
Working live tracker with embedded map. Ready for Termux.

## License
MIT
