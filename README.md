# CrowdFlow Management

CrowdFlow is a prototype decision-support application for exploring crowd movement at a venue. It combines a React dashboard, FastAPI service, graph-based simulation, deterministic congestion indicators, emergency route closures, public geospatial context adapters, configured CCTV source metadata, WebSocket snapshots, and persisted simulation history.

## Current capabilities

- **Venue digital twin:** a demo stadium represented as nodes and bidirectional corridor edges.
- **Crowd simulation:** individual virtual agents move along graph paths. Arrival rates use fractional per-tick accumulation, and exits are constrained by per-minute throughput budgets.
- **Deterministic risk indicators:** corridor flow/density, bottleneck IDs, incident state and a heuristic score from the simulation engine. These values are not certified life-safety predictions.
- **Emergency exercise:** close a venue node, reroute agents when a route remains available, expose stranded agents, and clear the incident.
- **Scenario interpretation:** a deterministic text parser converts plain-language input into scenario parameters. It is not an external LLM and does not generate safety scores.
- **Persistence and realtime:** SQLAlchemy snapshot history and WebSocket state updates are included.
- **Geospatial context:** provider-backed public OpenStreetMap/Nominatim/Overpass context, subject to provider availability, rate limits and attribution.
- **CCTV adapter:** lists operator-configured camera metadata and can perform a configured endpoint reachability check. No arbitrary camera discovery or computer-vision analytics is implemented.

## Architecture

- `frontend/`: React, TypeScript and Vite dashboard.
- `backend/app/main.py`: FastAPI routes, simulation lifecycle and WebSocket.
- `backend/app/engine.py`: deterministic agent movement, throughput budgets, emergency routing, density and risk indicators.
- `backend/app/graph/`: venue graph and graph-to-domain bridge.
- `backend/app/geo/` and `backend/app/cctv/`: external provider adapters.
- `backend/app/db/`: SQLAlchemy persistence and snapshot history.
- `backend/tests/`: engine, graph, adapter and API tests.

## Run locally

Requirements: Python 3.11+ and Node.js 20+.

Terminal 1:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

Terminal 2:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal. The dashboard defaults to the backend at `http://localhost:8000`. API docs are at `http://localhost:8000/docs`.

## Run with Docker Compose

```bash
docker compose up --build
```

Open `http://localhost:8080`. The demo backend is also exposed at `http://localhost:8000`; SQLite data is persisted in the `crowdflow-data` volume. This compose file is for local demonstration, not a hardened public production deployment.

## Configuration

Copy `.env.example` to `.env` at the repository root for local configuration. Important settings include `DATABASE_URL`, `CORS_ORIGINS`, `SIMULATION_HZ`, `MAX_AGENTS`, geospatial provider URLs/timeouts, and operator-supplied CCTV configuration. Never commit credentials or private camera URLs.

## Validation

CI runs backend package installation and pytest, plus frontend install, TypeScript type-check and production build. Docker image build should also be checked in an environment with Docker available. A green software test suite is not validation of real-world crowd safety.

## Safety, privacy and known limitations

- This is a prototype and **not** a certified emergency-control or evacuation system. Never use it as the sole basis for live crowd-safety decisions.
- The risk score is a transparent deterministic heuristic; it is not calibrated against a validated real-world dataset.
- The default venue is synthetic/demo geometry. Real venues require surveyed layouts, verified corridor widths/capacities and local operational validation.
- Geospatial provider data may be incomplete, stale, rate-limited or unavailable; attribution and provider terms apply.
- CCTV support is currently metadata/configuration and reachability only. There is no live video ingest, object detection, people counting or camera-derived density calculation.
- Authentication/authorization for multi-user public operation, production-grade rate limiting, multi-venue isolation and hardened deployment remain future work.
- Agent simulation has a configurable cap to protect resource use. Check `GET /health` for the configured limit.
- Incident actions and routing recommendations must be independently assessed by qualified personnel.

## Development log

- 2026-10-11: configured explicit Hatchling package selection; corrected arrival/exit budget handling, occupancy, stranded-agent behavior, bounded incident history and emergency clearing; expanded engine regression tests; documented actual integration limitations.
