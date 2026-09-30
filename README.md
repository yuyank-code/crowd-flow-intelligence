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
- AI: pluggable provider layer; AI interprets scenarios and explains results
- Geo: provider adapters for permitted public/licensed geospatial data
- CCTV: authorized camera adapter with computer-vision analytics

## Safety boundary

The platform is decision support, not a certified emergency-control system. Safety-critical calculations remain deterministic and auditable. External data is only presented as live when the configured provider actually supplies current data.

## Development

The original prototype is being migrated and expanded into this repository in coherent milestones. Secrets belong in environment variables and must never be committed.

## Initial target

A working end-to-end vertical slice:

Geospatial context → venue digital twin → crowd simulation → risk/bottleneck detection → realtime dashboard → scenario testing → AI explanation.
