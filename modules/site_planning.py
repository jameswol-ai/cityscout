"""Conceptual site-planning helpers for CityScout."""
from __future__ import annotations

from math import cos, radians, sin
from typing import Any

from .architecture import SiteParameters
from .massing import build_massing_options


def orientation_vector(orientation_deg: float, length_m: float = 1.0) -> tuple[float, float]:
    """Return an east/north unit vector for a bearing-like orientation."""
    angle = radians(float(orientation_deg) % 360.0)
    return sin(angle) * length_m, cos(angle) * length_m


def site_plan_summary(params: SiteParameters) -> dict[str, Any]:
    """Build a compact site-planning comparison package."""
    options = build_massing_options(params)
    preferred = max(options, key=lambda item: (item["open_ground_m2"], -abs(item["gfa_delta_m2"]))) if options else None
    return {
        "options": options,
        "recommended_concept": preferred["option"] if preferred else None,
        "orientation_vector": orientation_vector(params.orientation_deg, 1.0),
    }
