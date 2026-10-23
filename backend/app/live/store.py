"""Live zone observations from camera people-counting.

Only integer counts and calibration numbers are kept (never frames or images). Risk is computed with the same
deterministic rules and thresholds as the simulation, from the *camera's own view*:

    capacity_people = view_area_m2 * SAFE_PERSONS_PER_M2        (stated assumption, see below)
    density         = people / capacity_people                  (1.0 = view at its safe limit)
    level           = THRESHOLDS.classify(density)
    score           = score_density(density, 0)

SAFE_PERSONS_PER_M2 = 2.0 is a planning assumption for comfortable standing density, not a certified standard.
A zone is reported STALE when no fresh observation arrived within live_stale_after_sec.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from app.core.config import settings
from app.risk.deterministic import score_density
from app.risk.thresholds import THRESHOLDS

SAFE_PERSONS_PER_M2 = 2.0


@dataclass
class Observation:
    zone_id: str
    camera_id: str
    people: int
    view_area_m2: float
    received_at: float  # monotonic seconds


class LiveStore:
    def __init__(self):
        self._zones: dict[str, Observation] = {}

    def record(self, zone_id: str, camera_id: str, people: int, view_area_m2: float) -> Observation:
        obs = Observation(zone_id, camera_id, people, view_area_m2, time.monotonic())
        self._zones[zone_id] = obs
        return obs

    def forget_zone(self, zone_id: str) -> None:
        self._zones.pop(zone_id, None)

    def forget_camera(self, camera_id: str) -> None:
        for z in [z for z, o in self._zones.items() if o.camera_id == camera_id]:
            del self._zones[z]

    def clear(self) -> None:
        self._zones.clear()

    def snapshot(self) -> list[dict]:
        now = time.monotonic()
        out = []
        for o in sorted(self._zones.values(), key=lambda o: o.zone_id):
            age = now - o.received_at
            capacity = max(1.0, o.view_area_m2 * SAFE_PERSONS_PER_M2)
            density = o.people / capacity
            score, level = score_density(density, 0)
            stale = age > settings.live_stale_after_sec
            out.append({
                "zone_id": o.zone_id, "camera_id": o.camera_id, "source": "camera-count",
                "people": o.people, "view_area_m2": o.view_area_m2, "capacity_people": round(capacity, 1),
                "density": round(density, 3), "density_level": THRESHOLDS.classify(density),
                "risk_score": score, "risk_level": level,
                "age_sec": round(age, 1), "stale": stale, "status": "STALE" if stale else "LIVE",
            })
        return out


store = LiveStore()
