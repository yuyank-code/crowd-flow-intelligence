# Crowd Flow Intelligence — Backend

FastAPI service for the Crowd Flow Intelligence platform.

## Local setup

Run from the repository root:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

API documentation: http://localhost:8000/docs

## Key endpoints

- `GET /health` — service and configured agent limit
- `GET /api/simulation` — current deterministic simulation snapshot
- `POST /api/simulation/scenario` — validate and apply a scenario
- `POST /api/simulation/start|pause|reset` — control the demo simulation
- `POST /api/simulation/emergency` and `POST /api/simulation/emergency/clear` — exercise incident routing
- `GET /api/simulation/history?limit=50` — recent persisted snapshots
- `POST /api/scenarios/interpret` — deterministic scenario text parsing
- `GET /api/decision-support` — explanation derived from engine output
- `WS /ws/simulation` — current snapshots over WebSocket

The simulation uses individual virtual agents and caps the configured crowd at `MAX_AGENTS`. Arrival and exit rates are applied as per-minute budgets; fractional arrivals are carried between ticks, and unused whole exit capacity is not banked for a later burst. Risk is a deterministic demo heuristic, not a certified crowd-safety assessment.

Geospatial endpoints use configured public providers. CCTV endpoints currently expose operator-configured source metadata and optional reachability checks; they do not perform computer vision or claim live video analytics.
