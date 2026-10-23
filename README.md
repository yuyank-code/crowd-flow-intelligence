# Crowd Flow Intelligence

Real-time crowd intelligence and decision-support platform built from the existing Crowd-O-Holic prototype.

## Vision

Connect four layers:

1. Geospatial context around a venue
2. A venue digital twin represented as a graph
3. Deterministic crowd simulation and risk analysis
4. AI-assisted scenario interpretation and operator decision support

## Architecture

- Frontend: React + TypeScript + Vite
- Backend: FastAPI + Python
- Database: SQLAlchemy/Alembic-ready persistence layer
- Realtime: WebSockets
- Simulation: graph-based deterministic crowd model
- Risk: auditable deterministic thresholds and bottleneck detection
- Scenario parsing & decision support: deterministic, rule-based (no external LLM is connected)
- Geo: provider adapters for permitted public/licensed geospatial data
- Cameras: register RTSP/ONVIF/USB cameras (Cameras tab), protocol-aware connection tests, encrypted credentials, audit log, and live HLS preview through a MediaMTX gateway with signed expiring tokens. No computer vision yet; PTZ/snapshot/discovery are gated off.

## Safety boundary

The platform is decision support, not a certified emergency-control system. Safety-critical calculations remain deterministic and auditable. External data is only presented as live when the configured provider actually supplies current data.

## Development

The original prototype is being migrated and expanded into this repository in coherent milestones. Secrets belong in environment variables and must never be committed.

## Initial target

A working end-to-end vertical slice:

Geospatial context → venue digital twin → crowd simulation → risk/bottleneck detection → realtime dashboard → scenario testing → AI explanation.

## Run locally

```bash
# backend
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -e . && pytest -q
uvicorn app.main:app --reload            # http://localhost:8000/docs

# frontend (second terminal)
cd frontend && cp .env.example .env && npm ci
npm run typecheck && npm run build && npm run dev     # http://localhost:5173
```

## Run with Docker Compose

```bash
export OPERATOR_API_KEY=$(openssl rand -hex 24)
docker compose up --build        # UI http://localhost:8080 (nginx proxies /api and /ws to the backend)
curl localhost:8000/health
```

History is stored in the `crowdflow-data` volume. Live simulation state is in memory and starts in `standby` after a restart.

## Security

- **Operator key.** Set `OPERATOR_API_KEY`. Start/pause/reset/scenario/emergency endpoints then require an `X-API-Key` header (401 otherwise). The UI asks for the key on the first protected action and keeps it for the browser tab only. If the variable is empty, auth is **off** (local dev). `docker compose` refuses to start without it.
- **Public reads.** Dashboard state, history, CCTV catalog and the WebSocket stream stay readable without a key.
- **Rate limits** (per client, sliding window, in memory so per process): operator actions 60/min, geo lookups 20/min, scenario parsing 30/min. Over the limit returns 429 with `Retry-After`. `X-Forwarded-For` is only trusted when `TRUST_PROXY=true`.
- **CORS** allows only `CORS_ORIGINS`, GET/POST, and the `Content-Type` and `X-API-Key` headers; no cookies/credentials.
- **WebSocket** rejects browser connections from origins outside `CORS_ORIGINS` (or the same host), and caps connections (200 total, 10 per IP).
- **TLS.** Terminate HTTPS at your reverse proxy; the key travels in a header and must not go over plain HTTP outside localhost.

## Cameras and live video

1. In `.env` (next to `docker-compose.yml`) set `OPERATOR_API_KEY`, `CCTV_SECRET_KEY` (Fernet key, command in `backend/.env.example`) and `PLAYBACK_SIGNING_KEY` (`openssl rand -hex 32`).
2. Edit `infra/mediamtx/mediamtx.yml`: one `paths:` entry per camera, and `hlsAllowOrigin` to your dashboard URL. Put the camera's RTSP URL in `.env` as `MTX_PATHS_CAM1_SOURCE=rtsp://user:pass@192.168.1.50:554/stream1`.
3. Set `MEDIA_GATEWAY_BASE_URL=http://mediamtx:8888` and `MEDIA_GATEWAY_PUBLIC_URL=http://localhost:8888`, then `docker compose --profile gateway up --build`.
4. Cameras tab: add the camera (playback path `cam1`), **Test connection**, **Start stream**.

No camera? Use your laptop webcam: see `docs/LAPTOP_WEBCAM.md`.

Check the gateway/token flow without a camera: `MEDIAMTX_BIN=/path/to/mediamtx ./scripts/test-gateway-e2e.sh` (needs ffmpeg).
Cameras must be on a network the backend can reach; do not expose camera ports publicly.

## Live camera counting

A registered camera can drive one venue zone with a real people count instead of simulated agents (dashboard, **LIVE CAMERA ZONE** panel).
Detection runs in the operator's browser tab with a bundled model (CenterNet, COCO "person"; `frontend/public/models`), so frames never leave
the browser. Only the integer count and the view area are sent (`POST /api/live/observations`, operator key required). The backend scores it with the same
deterministic density thresholds as the simulation, using the camera's own view as the capacity (view area x 2 people/m2, a planning assumption),
and marks a zone STALE after 10 s without a fresh count. Live zones are shown beside the simulation and labelled LIVE; the rest stays SIMULATED.
Counts are approximate (partly hidden people can be missed), accuracy depends on camera angle and lighting, and counting stops when the tab closes.

## Known limitations

- Prototype / decision support only. Not a certified life-safety system.
- One hard-coded demo venue; one agent = one person, so the crowd is capped at `MAX_AGENTS` (default 20,000).
- Flow/density is a heuristic (agents on an edge scaled against capacity), not a validated pedestrian model.
- Agents at or cut off by a closed node become *stranded* (counted, reported, retried when the incident changes).
- Security is a single shared operator key plus in-memory rate limits (see below). There are no per-user accounts, audit log, or TLS termination in this repo; put it behind an HTTPS reverse proxy before exposing it.
