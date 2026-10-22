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

## Milestone 3 — stabilisation (22 Oct 2026)
Baseline on this snapshot: backend did not install (Hatchling package config), `engine.py` had a SyntaxError (literal `\n`), `app/graph/nodes.py` was missing, and `frontend/src/main.tsx` + `vite.config.ts` were empty — so CI could not have passed on `main`.
- Packaging fixed; engine syntax fixed; `graph/nodes.py` added.
- Engine core rewritten: exit throughput is the only way people leave; stranded agents are counted, not dropped; fractional arrival/exit carry; crowd capped at `max_agents` and reported; node occupancy derived from agents; bounded event log; selective `clear_emergency(node_id)` that recomputes edge state.
- Fixed ordering bug where cleared edges stayed closed in the routing graph.
- Persistence: snapshots every `SNAPSHOT_INTERVAL_SEC`, retention pruning, offset/risk filters; simulation loop survives tick/DB errors.
- Interpreter: "5 min" no longer parsed as 5 million; text inputs length-limited.
- Frontend: entry point + Vite config, shared API client, busy/offline/stale/error states, per-incident clear, history panel, provenance labels.
- Deployment: nginx proxies `/api` and `/ws`; backend Dockerfile copies README, runs as non-root with healthcheck; `package-lock.json` committed, CI uses `npm ci`.
- Tests: 6 -> 43 (invariants, throughput, stranded recovery, 20k-agent stress, history, API validation, parser edge cases).
- Verified: pytest, `tsc`, `vite build`, live uvicorn smoke test incl. WebSocket and history surviving restart.
- NOT verified: Docker build/Compose (no Docker in the working environment), browser end-to-end tests.

## Milestone 4 — security hardening
- Operator API key on all state-changing routes (constant-time compare, 401 before any state change); read routes stay public.
- Sliding-window rate limits for operator, geo and parse routes; proxy-aware client IP only with `TRUST_PROXY`.
- CORS narrowed (methods, headers, no credentials); WebSocket origin check and connection caps.
- Frontend sends the key (tab-scoped sessionStorage) and shows friendly 401/429 messages.
- Compose requires `OPERATOR_API_KEY`; debug port bound to 127.0.0.1.
- Tests: 43 -> 56 (`tests/test_security.py`).
- Limits: single shared key, in-memory limiter (not shared across workers), no audit log, no TLS in-repo.

## Next
- Migrate the richer original simulation/routing/CCTV/AI modules from the uploaded prototype.
- Replace the placeholder scenario parser with validated AI provider output.
- Connect geospatial context to arrival/routing scenarios.
- Replace the shared key with per-operator accounts and add audit logging.
- Add production PostgreSQL configuration and deployment observability.
