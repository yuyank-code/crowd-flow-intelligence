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
- CCTV: operator-configured source catalog + URL health check only (no video ingestion or computer vision yet)

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

## Known limitations

- Prototype / decision support only. Not a certified life-safety system.
- One hard-coded demo venue; one agent = one person, so the crowd is capped at `MAX_AGENTS` (default 20,000).
- Flow/density is a heuristic (agents on an edge scaled against capacity), not a validated pedestrian model.
- Agents at or cut off by a closed node become *stranded* (counted, reported, retried when the incident changes).
- Security is a single shared operator key plus in-memory rate limits (see below). There are no per-user accounts, audit log, or TLS termination in this repo; put it behind an HTTPS reverse proxy before exposing it.
