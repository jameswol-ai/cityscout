"""Conceptual lateral structural design and stability checks.

Planning-level proxies only. Not a substitute for wind/seismic analysis,
finite-element modelling, geotechnical design, or applicable structural codes.
"""
from __future__ import annotations
from math import isfinite
from typing import Any


def _bounded(value: Any, low: float, high: float, default: float) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, n)) if isfinite(n) else default


def lateral_system_options(height_m: float, width_m: float, depth_m: float) -> list[dict[str, Any]]:
    height = _bounded(height_m, 3.0, 500.0, 20.0)
    width = _bounded(width_m, 3.0, 200.0, 30.0)
    depth = _bounded(depth_m, 3.0, 200.0, 20.0)
    slenderness = height / max(min(width, depth), 1.0)
    systems = [
        ("Moment frame", 8.0, "Flexible architectural planning with higher frame demand"),
        ("Shear wall core", 15.0, "Efficient lateral resistance concentrated around the core"),
        ("Braced frame", 12.0, "Efficient steel-oriented lateral system with brace coordination"),
        ("Dual system", 20.0, "Combined frame and wall/bracing strategy for taller buildings"),
    ]
    results = []
    for name, nominal_limit, description in systems:
        height_factor = min(100.0, nominal_limit / max(slenderness, 0.1) * 100.0)
        aspect_penalty = max(0.0, (depth / width - 2.5) * 10.0)
        score = max(0.0, min(100.0, height_factor - aspect_penalty))
        results.append({"system": name, "description": description, "height_m": height, "slenderness": slenderness, "conceptual_height_limit_ratio": nominal_limit, "stability_score": score})
    return results


def wind_seismic_proxy(height_m: float, width_m: float, wind_speed_mps: float = 30.0, seismic_factor: float = 0.10) -> dict[str, float]:
    height = _bounded(height_m, 3.0, 500.0, 20.0)
    width = _bounded(width_m, 3.0, 200.0, 30.0)
    wind = _bounded(wind_speed_mps, 10.0, 80.0, 30.0)
    seismic = _bounded(seismic_factor, 0.0, 1.0, 0.10)
    wind_pressure_kpa = 0.000613 * wind * wind
    base_shear_proxy = seismic * height * width * 10.0
    drift_index = height / max(width, 1.0) * (wind / 30.0) ** 2
    return {"wind_speed_mps": wind, "wind_pressure_kpa": wind_pressure_kpa, "seismic_factor": seismic, "base_shear_proxy": base_shear_proxy, "drift_index": drift_index}


def lateral_summary(height_m: float, width_m: float, depth_m: float, wind_speed_mps: float = 30.0, seismic_factor: float = 0.10, preferred_system: str = "Shear wall core") -> dict[str, Any]:
    options = lateral_system_options(height_m, width_m, depth_m)
    preferred = next((x for x in options if x["system"] == preferred_system), options[0])
    return {"options": options, "selected": preferred, "actions": wind_seismic_proxy(height_m, width_m, wind_speed_mps, seismic_factor)}
