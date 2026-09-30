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
