"""Conceptual building program, core and circulation engine for CityScout.

This module provides transparent early-stage planning ratios. It is not a
code-compliance, life-safety, accessibility, structural, or construction tool.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import isfinite, sqrt
from typing import Any


@dataclass
class ProgramParameters:
    gfa_m2: float = 4000.0
    floors: int = 4
    efficiency_pct: float = 82.0
    core_ratio_pct: float = 12.0
    circulation_ratio_pct: float = 8.0
    service_ratio_pct: float = 5.0
    public_ratio_pct: float = 20.0
    residential_ratio_pct: float = 0.0
    commercial_ratio_pct: float = 55.0
    office_ratio_pct: float = 25.0
    amenity_ratio_pct: float = 20.0
    core_location: str = "Central"


def _num(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if isfinite(value) else default


def normalise_program(params: ProgramParameters) -> ProgramParameters:
    return ProgramParameters(
        gfa_m2=max(1.0, _num(params.gfa_m2, 4000.0)),
        floors=max(1, min(200, int(_num(params.floors, 4)))),
        efficiency_pct=max(40.0, min(95.0, _num(params.efficiency_pct, 82.0))),
        core_ratio_pct=max(5.0, min(30.0, _num(params.core_ratio_pct, 12.0))),
        circulation_ratio_pct=max(0.0, min(30.0, _num(params.circulation_ratio_pct, 8.0))),
        service_ratio_pct=max(0.0, min(25.0, _num(params.service_ratio_pct, 5.0))),
        public_ratio_pct=max(0.0, min(100.0, _num(params.public_ratio_pct, 20.0))),
        residential_ratio_pct=max(0.0, min(100.0, _num(params.residential_ratio_pct, 0.0))),
        commercial_ratio_pct=max(0.0, min(100.0, _num(params.commercial_ratio_pct, 55.0))),
        office_ratio_pct=max(0.0, min(100.0, _num(params.office_ratio_pct, 25.0))),
        amenity_ratio_pct=max(0.0, min(100.0, _num(params.amenity_ratio_pct, 20.0))),
        core_location=str(params.core_location or "Central").strip() or "Central",
    )


def program_allocation(params: ProgramParameters) -> dict[str, Any]:
    p = normalise_program(params)
    gfa = p.gfa_m2
    net_area = gfa * p.efficiency_pct / 100.0
    core = gfa * p.core_ratio_pct / 100.0
    circulation = gfa * p.circulation_ratio_pct / 100.0
    service = gfa * p.service_ratio_pct / 100.0
    functional = max(0.0, net_area - core - circulation - service)
    weights = {
        "Public": p.public_ratio_pct,
        "Residential": p.residential_ratio_pct,
        "Commercial": p.commercial_ratio_pct,
        "Office": p.office_ratio_pct,
        "Amenity": p.amenity_ratio_pct,
    }
    total_weight = sum(weights.values()) or 1.0
    program = {name: functional * weight / total_weight for name, weight in weights.items() if weight > 0}
    floor_plate = gfa / p.floors
    core_area_per_floor = core / p.floors
    return {
        "parameters": asdict(p),
        "gfa_m2": gfa,
        "net_area_m2": net_area,
        "floor_plate_m2": floor_plate,
        "core_area_m2": core,
        "core_area_per_floor_m2": core_area_per_floor,
        "circulation_area_m2": circulation,
        "service_area_m2": service,
        "functional_area_m2": functional,
        "program_area_m2": program,
        "program_balance_pct": {name: value / functional * 100.0 if functional else 0.0 for name, value in program.items()},
    }


def core_geometry(floor_plate_m2: float, core_area_m2: float, location: str = "Central") -> dict[str, Any]:
    plate = max(1.0, _num(floor_plate_m2, 1.0))
    core = max(1.0, min(plate * 0.5, _num(core_area_m2, plate * 0.12)))
    core_side = sqrt(core)
    plate_side = sqrt(plate)
    loc = str(location or "Central").strip().title()
    positions = {
        "Central": (0.5, 0.5),
        "North": (0.5, 0.72),
        "South": (0.5, 0.28),
        "East": (0.72, 0.5),
        "West": (0.28, 0.5),
    }
    x, y = positions.get(loc, positions["Central"])
    return {
        "location": loc if loc in positions else "Central",
        "core_area_m2": core,
        "core_side_m": core_side,
        "floor_plate_side_m": plate_side,
        "center_x_fraction": x,
        "center_y_fraction": y,
    }


def circulation_assessment(params: ProgramParameters) -> dict[str, float | str]:
    p = normalise_program(params)
    score = 100.0
    if p.circulation_ratio_pct < 5:
        score -= 20
    elif p.circulation_ratio_pct > 15:
        score -= 8
    if p.core_ratio_pct < 8:
        score -= 15
    if p.efficiency_pct < 70:
        score -= 10
    return {
        "score": max(0.0, min(100.0, score)),
        "circulation_ratio_pct": p.circulation_ratio_pct,
        "core_ratio_pct": p.core_ratio_pct,
        "efficiency_pct": p.efficiency_pct,
        "assessment": "Strong" if score >= 80 else "Good" if score >= 60 else "Review",
    }
