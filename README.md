# jedi-faatracker

Web interface for tracking FAA flights: live (current), past, and future/scheduled. Displays flight courses/paths over an expanded interactive map with selectable layers for commercial, military, and private flights.

## Goals
- Full-viewport interactive map (Leaflet / MapLibre preferred)
- Aircraft markers with near-real-time updates
- Path/course overlays (track history, estimated routes, great-circle)
- Time modes: Live / Past / Future
- Toggleable layers: Commercial, Military, Private
- Click details, search, bbox filtering, responsive dark UI

## Data Sources (planned)
- Live + limited history: OpenSky Network, adsb.lol, airplanes.live, or self-hosted free-flight-api merger
- Schedules/future: Aviationstack free tier, AeroDataBox, or similar
- Backend proxy recommended for keys, CORS, caching, and rate limits

## Termux-friendly
Designed so the backend proxy can run locally inside Termux on Android (FastAPI/Flask or Node) for personal use, or be deployed elsewhere.

## Status
Initial repo. Implementation coming next.

## License
MIT (or specify later)
