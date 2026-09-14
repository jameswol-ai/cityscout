"""Conceptual parametric building-design engine for CityScout.

This module generates transparent planning-level floor plates, cores and
program allocations. It is not a substitute for architectural, structural,
fire, accessibility, MEP, energy or statutory design.
"""
from __future__ import annotations

from dataclasses import asdict
from math import cos, radians, sin, sqrt
from typing import Any

from .architecture import SiteParameters, site_metrics
from .massing import build_massing_options


def _bounded(value: Any, low: float, high: float, default: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    if not value == value or value in (float("inf"), float("-inf")):
        return default
    return max(low, min(high, value))


def _rotate(x: float, y: float, degrees: float) -> tuple[float, float]:
    a = radians(degrees % 360.0)
    return x * cos(a) - y * sin(a), x * sin(a) + y * cos(a)


def floor_plate_dimensions(footprint_m2: float, aspect_ratio: float = 1.4) -> dict[str, float]:
    area = max(1.0, _bounded(footprint_m2, 1.0, 10_000_000.0, 100.0))
    ratio = _bounded(aspect_ratio, 0.35, 4.0, 1.4)
    width = sqrt(area / ratio)
    depth = area / width
    return {"width_m": width, "depth_m": depth, "area_m2": area, "aspect_ratio": depth / width}


def core_model(floor_area_m2: float, core_ratio_pct: float = 12.0) -> dict[str, float]:
    area = max(1.0, _bounded(floor_area_m2, 1.0, 10_000_000.0, 100.0))
    ratio = _bounded(core_ratio_pct, 5.0, 30.0, 12.0)
    core_area = area * ratio / 100.0
    side = sqrt(core_area)
    return {"core_ratio_pct": ratio, "core_area_m2": core_area, "core_width_m": side, "core_depth_m": side}


def program_allocation(net_area_m2: float) -> dict[str, float]:
    area = max(0.0, _bounded(net_area_m2, 0.0, 10_000_000.0, 0.0))
    shares = {
        "primary_program": 0.68,
        "circulation": 0.12,
        "service_support": 0.08,
        "shared_amenity": 0.07,
        "flexible_reserve": 0.05,
    }
    return {key: area * share for key, share in shares.items()}


def generate_design_options(
    params: SiteParameters,
    preferred_form: str = "Balanced",
    core_ratio_pct: float = 12.0,
    aspect_ratio: float = 1.4,
) -> list[dict[str, Any]]:
    """Generate comparable conceptual building options."""
    options = build_massing_options(params)
    results: list[dict[str, Any]] = []
    forms = {"Compact": "courtyard", "Balanced": "bar", "Vertical": "tower"}
    for item in options:
        dims = floor_plate_dimensions(item["footprint_m2"], aspect_ratio)
        core = core_model(item["footprint_m2"], core_ratio_pct)
        net_floor = max(0.0, item["footprint_m2"] - core["core_area_m2"])
        program = program_allocation(net_floor)
        efficiency = net_floor / item["footprint_m2"] * 100.0 if item["footprint_m2"] else 0.0
        daylight_proxy = min(100.0, 35.0 + (item["footprint_m2"] ** 0.5 / max(dims["depth_m"], 1.0)) * 65.0)
        verticality = min(100.0, item["height_m"] / 60.0 * 100.0)
        score = (efficiency * 0.35) + (daylight_proxy * 0.30) + ((100.0 - verticality * 0.35) * 0.20) + (min(100.0, item["open_ground_m2"] / max(params.site_area_m2, 1.0) * 100.0) * 0.15)
        results.append({
            **item,
            "form": forms.get(item["option"], "bar"),
            "plate_width_m": dims["width_m"],
            "plate_depth_m": dims["depth_m"],
            "core_area_m2": core["core_area_m2"],
            "core_width_m": core["core_width_m"],
            "core_depth_m": core["core_depth_m"],
            "net_floor_area_m2": net_floor,
            "net_to_gross_pct": efficiency,
            "daylight_perimeter_proxy": daylight_proxy,
            "design_score": score,
            "program": program,
            "selected": item["option"].lower() == str(preferred_form).strip().lower(),
        })
    return results


def design_summary(params: SiteParameters, preferred_form: str = "Balanced", core_ratio_pct: float = 12.0, aspect_ratio: float = 1.4) -> dict[str, Any]:
    return {
        "parameters": asdict(params),
        "site_metrics": site_metrics(params),
        "options": generate_design_options(params, preferred_form, core_ratio_pct, aspect_ratio),
    }


def floor_plate_polygon(option: dict[str, Any], orientation_deg: float = 0.0) -> list[tuple[float, float]]:
    """Return local metre coordinates for a rotated rectangular conceptual plate."""
    half_w = max(0.1, float(option.get("plate_width_m", 1.0))) / 2.0
    half_d = max(0.1, float(option.get("plate_depth_m", 1.0))) / 2.0
    points = [(-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d)]
    return [_rotate(x, y, orientation_deg) for x, y in points]
