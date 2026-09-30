# Development Log

## Milestone 1 — working foundation
- FastAPI backend and React/TypeScript frontend established.
- Venue digital twin graph and deterministic simulation loop added.
- Risk and bottleneck calculations remain deterministic.
- WebSocket simulation stream added.
- Emergency events and natural-language scenario parsing added.

## Milestone 2 — persistence + geospatial context
- SQLAlchemy async persistence added for simulation snapshots.
- Simulation history endpoint added.
- OpenStreetMap Nominatim/Overpass adapter added behind a provider boundary.
- Public geospatial context endpoint added.
- Runtime wiring initializes and closes the database cleanly.
- Docker Compose deployment added with persistent database volume.

## Next
- Migrate the richer original simulation/routing/CCTV/AI modules from the uploaded prototype.
- Replace the placeholder scenario parser with validated AI provider output.
- Connect geospatial context to arrival/routing scenarios.
- Add authenticated operator accounts and audit logging.
- Add production PostgreSQL configuration and deployment observability.
