"""Conceptual site-massing engine for CityScout.

The engine generates transparent, comparative massing options from site
parameters. It is a planning aid, not a statutory, structural, fire, or
construction design calculation.
"""
from __future__ import annotations

from dataclasses import asdict
from math import isfinite
from typing import Any

from .architecture import SiteParameters, site_metrics


def _num(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if isfinite(value) else default


def build_massing_options(params: SiteParameters) -> list[dict[str, Any]]:
    """Return low/mid/high-rise concept options with comparable metrics."""
    area = max(1.0, _num(params.site_area_m2, 1000.0))
    target_gfa = site_metrics(params)["gross_floor_area_m2"]
    base_coverage = max(0.05, min(1.0, _num(params.site_coverage_pct, 40.0) / 100.0))
    green = max(0.0, min(0.95, _num(params.green_ratio_pct, 20.0) / 100.0))
    requested_floors = max(1, int(_num(params.floors, 4)))
    floor_height = max(2.0, _num(params.floor_height_m, 3.2))

    candidates = [
        ("Compact", max(1, min(requested_floors, 3)), min(0.60, max(base_coverage, 0.45)), "Lower-rise, larger ground-plane footprint"),
        ("Balanced", requested_floors, base_coverage, "Balanced footprint, height and open-space strategy"),
        ("Vertical", max(requested_floors + 2, 6), max(0.20, min(base_coverage * 0.70, 0.40)), "Smaller footprint with greater vertical intensity"),
    ]
    options: list[dict[str, Any]] = []
    for name, floors, coverage, strategy in candidates:
        footprint = area * coverage
        gfa = footprint * floors
        options.append({
            "option": name,
            "strategy": strategy,
            "floors": floors,
            "coverage_pct": coverage * 100.0,
            "footprint_m2": footprint,
            "gfa_m2": gfa,
            "height_m": floors * floor_height,
            "far": gfa / area,
            "green_area_m2": area * green,
            "open_ground_m2": max(0.0, area - footprint),
            "gfa_delta_m2": gfa - target_gfa,
        })
    return options


def select_massing_option(options: list[dict[str, Any]], preferred: str) -> dict[str, Any] | None:
    """Select a named option safely."""
    wanted = str(preferred or "").strip().lower()
    for option in options:
        if str(option.get("option", "")).lower() == wanted:
            return option
    return options[0] if options else None


def massing_summary(params: SiteParameters) -> dict[str, Any]:
    """Return a serializable massing comparison package."""
    return {"parameters": asdict(params), "options": build_massing_options(params)}
