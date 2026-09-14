"""Spatial Intelligence 2.0 helpers for CityScout.

These are transparent GIS proxies based only on the saved-place dataset. They are
not population, traffic, accessibility, or statutory planning measurements.
"""
from __future__ import annotations

from math import cos, radians, sqrt
from typing import Any

from .gis import valid_places


def distance_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1, lon1 = float(a["latitude"]), float(a["longitude"])
    lat2, lon2 = float(b["latitude"]), float(b["longitude"])
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    x = dlon * cos(radians((lat1 + lat2) / 2.0))
    return 111.32 * sqrt(x * x + dlat * dlat)


def catchment_counts(places: list[dict], radius_m: float) -> dict[str, Any]:
    """Count saved places falling inside each place's circular catchment."""
    items = valid_places(places)
    radius_km = max(0.0, float(radius_m)) / 1000.0
    rows = []
    for place in items:
        neighbors = [other for other in items if other is not place and distance_km(place, other) <= radius_km]
        rows.append({
            "name": place.get("name", "Unnamed"),
            "category": place.get("category", "Other"),
            "places_in_catchment": len(neighbors),
            "categories_in_catchment": len({str(p.get("category") or "Other") for p in neighbors}),
        })
    return {"radius_m": radius_m, "places": len(items), "rows": rows,
            "covered_places": sum(r["places_in_catchment"] > 0 for r in rows),
            "coverage_pct": 100.0 * sum(r["places_in_catchment"] > 0 for r in rows) / len(rows) if rows else 0.0}


def category_service_coverage(places: list[dict], radius_m: float = 400.0) -> list[dict]:
    """Measure how many places of each category have another saved place nearby."""
    items = valid_places(places)
    radius_km = max(0.0, float(radius_m)) / 1000.0
    categories = sorted({str(p.get("category") or "Other") for p in items})
    result = []
    for category in categories:
        group = [p for p in items if str(p.get("category") or "Other") == category]
        covered = sum(any(other is not p and distance_km(p, other) <= radius_km for other in items) for p in group)
        result.append({"category": category, "places": len(group), "covered": covered,
                       "coverage_pct": round(100.0 * covered / len(group), 1) if group else 0.0})
    return result


def density_hotspots(places: list[dict], radius_m: float = 400.0, top_n: int = 10) -> list[dict]:
    """Rank saved places by local saved-place density within a radius."""
    items = valid_places(places)
    radius_km = max(0.0, float(radius_m)) / 1000.0
    ranked = []
    for place in items:
        nearby = [other for other in items if other is not place and distance_km(place, other) <= radius_km]
        ranked.append({"name": place.get("name", "Unnamed"), "category": place.get("category", "Other"),
                       "nearby_places": len(nearby), "nearby_categories": len({str(p.get("category") or "Other") for p in nearby})})
    ranked.sort(key=lambda row: (-row["nearby_places"], -row["nearby_categories"], str(row["name"])))
    return ranked[:max(1, int(top_n))]


def category_gaps(places: list[dict], expected_categories: list[str]) -> list[dict]:
    """Return absent categories plus simple spatial opportunity counts."""
    items = valid_places(places)
    observed = {str(p.get("category") or "Other") for p in items}
    return [{"category": category, "places": 0, "status": "Gap"} for category in expected_categories if category not in observed]


def spatial_report(places: list[dict], expected_categories: list[str] | None = None) -> dict[str, Any]:
    """Build the complete Spatial Intelligence 2.0 report."""
    expected = expected_categories or ["Food", "Nightlife", "Shopping", "Attractions", "Parks", "Transit", "Other"]
    c400 = catchment_counts(places, 400)
    c800 = catchment_counts(places, 800)
    return {
        "dataset_places": len(valid_places(places)),
        "catchment_400m": c400,
        "catchment_800m": c800,
        "service_coverage_400m": category_service_coverage(places, 400),
        "hotspots_400m": density_hotspots(places, 400),
        "category_gaps": category_gaps(places, expected),
    }
