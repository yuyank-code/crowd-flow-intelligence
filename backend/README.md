# Backend

FastAPI service for the Crowd Flow Intelligence platform.

## Run

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

The current vertical slice contains a deterministic stadium graph, simulation loop, risk/bottleneck calculation, emergency events, scenario parsing, and WebSocket snapshots.
