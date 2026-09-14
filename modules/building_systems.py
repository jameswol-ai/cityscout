"""Conceptual building systems and circulation engine for CityScout.

Provides early-stage planning proxies for cores, stairs, lifts, circulation,
service shafts and floor-by-floor vertical organization. It is not a life
safety, accessibility, structural, MEP or code-compliance calculation.
"""
from __future__ import annotations

from math import ceil, isfinite, sqrt
from typing import Any


def _bounded(value: Any, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not isfinite(number):
        return default
    return max(low, min(high, number))


def vertical_core_schedule(
    gross_floor_area_m2: float,
    floors: int,
    occupancy_load_per_100m2: float = 10.0,
    lifts_per_250_persons: float = 1.0,
) -> dict[str, Any]:
    """Estimate a conceptual lift/stair/shaft schedule."""
    area = _bounded(gross_floor_area_m2, 1.0, 10_000_000.0, 100.0)
    levels = int(_bounded(floors, 1, 200, 1))
    load_factor = _bounded(occupancy_load_per_100m2, 1.0, 100.0, 10.0)
    lift_factor = _bounded(lifts_per_250_persons, 0.25, 10.0, 1.0)
    persons = area / 100.0 * load_factor
    lifts = max(1, int(ceil(persons / 250.0 * lift_factor)))
    stairs = 2 if levels >= 2 else 1
    shafts = max(1, int(ceil(area / 1200.0)))
    return {
        "floors": levels,
        "conceptual_population": persons,
        "lifts": lifts,
        "stairs": stairs,
        "service_shafts": shafts,
        "vertical_core_count": 1 if levels <= 8 else 2,
        "note": "Conceptual quantities only. Confirm occupant loads, travel distances, fire strategy, accessibility and local code requirements separately.",
    }


def circulation_model(
    floor_plate_m2: float,
    core_area_m2: float,
    circulation_ratio_pct: float = 12.0,
) -> dict[str, float]:
    plate = _bounded(floor_plate_m2, 1.0, 10_000_000.0, 100.0)
    core = _bounded(core_area_m2, 0.0, plate * 0.8, plate * 0.12)
    ratio = _bounded(circulation_ratio_pct, 5.0, 30.0, 12.0)
    circulation = max(0.0, (plate - core) * ratio / 100.0)
    usable = max(0.0, plate - core - circulation)
    return {
        "floor_plate_m2": plate,
        "core_area_m2": core,
        "circulation_area_m2": circulation,
        "usable_program_area_m2": usable,
        "usable_efficiency_pct": usable / plate * 100.0,
    }


def system_summary(
    floor_plate_m2: float,
    core_area_m2: float,
    floors: int,
    gross_floor_area_m2: float | None = None,
) -> dict[str, Any]:
    gross = floor_plate_m2 * max(1, int(floors)) if gross_floor_area_m2 is None else gross_floor_area_m2
    return {
        "vertical": vertical_core_schedule(gross, floors),
        "circulation": circulation_model(floor_plate_m2, core_area_m2),
    }
