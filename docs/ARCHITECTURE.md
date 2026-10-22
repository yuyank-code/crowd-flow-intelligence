# Architecture

## Product layers

### 1. Geospatial context
Provider adapters expose permitted map/geospatial data. The core application never assumes a specific vendor.

### 2. Venue digital twin
A venue is a graph:
- nodes = gates, zones, junctions, exits and facilities
- edges = walkable connections with capacity, length, status and flow

### 3. Simulation
A deterministic simulation produces occupancy, density, flow, speed and route utilization over time.

### 4. Risk engine
Risk is computed from explicit thresholds and persistence rules. AI cannot directly modify safety scores.

### 5. AI analyst
Natural-language input is translated into validated scenario parameters. The AI can explain deterministic outputs and compare tested scenarios.

### 6. Realtime
Simulation snapshots and operator events are broadcast over WebSockets.

### 7. Persistence
SQLAlchemy/Alembic provide the persistence boundary for venues, scenarios, runs, snapshots and alerts.

## External-data principle

External feeds are adapters. If a source is unavailable, the application must say so rather than fabricate live state.

## Build order

1. Migrate the existing simulation/risk/CCTV prototype
2. Establish database persistence
3. Add geospatial context
4. Connect external context to scenario generation
5. Add what-if comparison
6. Harden realtime behavior and tests
7. Deployment and observability

## Camera management (CCTV)

```
Browser (Cameras tab) --X-API-Key--> FastAPI /api/cctv/*  --> adapters (RTSP OPTIONS / ONVIF SOAP / USB: agent required)
                                          |                          \-> SSRF guard + re-resolve at connect time
                                          +--> SQLite/SQLAlchemy: cameras (credentials Fernet-encrypted), camera_audit
                                          +--> streams.py: session only "live" if the gateway serves the HLS manifest
Browser <-- short-lived signed HLS URL -- MediaMTX (pulls RTSP itself; browser never sees RTSP URL or credentials)
                                              |  every HLS request: POST /api/cctv/gateway/auth  (token + path + active stream)
                                              v
                                          FastAPI gateway hook: 200 allow / 401 deny
```

Gateway: MediaMTX v1.12.3 (`infra/mediamtx/mediamtx.yml`). Only HLS is exposed; RTSP/RTMP/SRT/WebRTC/API/metrics are off.
The hook allows only HLS *reads* of a path whose camera has an active stream and a valid, unexpired HMAC token bound to that
camera and path. Stopping a stream revokes access immediately; tokens expire after `PLAYBACK_TOKEN_TTL_SEC` (60 s) and the
player renews them. MediaMTX copies the token into the playlist's segment URLs. Camera RTSP credentials belong in the
`MTX_PATHS_<NAME>_SOURCE` environment variable, never in the YAML.

What is implemented: registration/CRUD, accurate status via protocol-specific checks (no HTTP HEAD for RTSP),
stream session lifecycle with a concurrency cap, signed expiring playback references, operator-key auth (fail-closed),
SSRF guard, encrypted credentials, audit log, capability-gated controls.

What is NOT implemented or verified: a run against a real physical camera (the gateway flow was verified with a real MediaMTX binary and an ffmpeg test stream, `scripts/test-gateway-e2e.sh`); the MediaMTX Docker image/compose service; playback in a real browser (hls.js token renewal and Safari native renewal are untested); PTZ, snapshot and ONVIF discovery (reported as
unsupported); USB capture and the local agent / cloud bridge (Phases 4-5); computer-vision analytics (Phase 6 - cameras
have no effect on the simulation or risk engine); Alembic migrations; rate limiting; per-user RBAC (one shared operator key);
Status is refreshed on demand ("Test connection"), not by background polling.

Deployment boundary: a cloud backend cannot reach private-LAN cameras or a laptop's USB device. Run the backend (or a local
connector) on the camera network; do not expose camera ports publicly.

