"""Architecture and urban design analysis tools for CityScout.

The module intentionally uses transparent, assumption-driven calculations. It is
an early-stage planning aid, not a substitute for statutory planning, surveying,
engineering, environmental, or fire-safety review.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import radians, sin, cos, asin, sqrt
from typing import Any, Iterable


@dataclass
class SiteParameters:
    site_area_m2: float = 1000.0
    site_coverage_pct: float = 40.0
    floors: int = 4
    floor_height_m: float = 3.2
    setback_front_m: float = 5.0
    setback_side_m: float = 3.0
    setback_rear_m: float = 5.0
    green_ratio_pct: float = 20.0
    parking_per_100m2: float = 1.0
    orientation_deg: float = 0.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))


def site_metrics(params: SiteParameters) -> dict[str, float]:
    area = max(0.0, params.site_area_m2)
    coverage = max(0.0, min(100.0, params.site_coverage_pct)) / 100.0
    green = max(0.0, min(100.0, params.green_ratio_pct)) / 100.0
    footprint = area * coverage
    gross_floor_area = footprint * max(1, int(params.floors))
    green_area = area * green
    paved_or_other = max(0.0, area - footprint - green_area)
    building_height = max(0, int(params.floors)) * max(0.0, params.floor_height_m)
    far = gross_floor_area / area if area else 0.0
    parking_spaces = gross_floor_area / 100.0 * max(0.0, params.parking_per_100m2)
    return {
        "site_area_m2": area,
        "building_footprint_m2": footprint,
        "gross_floor_area_m2": gross_floor_area,
        "green_area_m2": green_area,
        "other_open_area_m2": paved_or_other,
        "building_height_m": building_height,
        "floor_area_ratio": far,
        "estimated_parking_spaces": parking_spaces,
        "coverage_pct": coverage * 100,
        "green_ratio_pct": green * 100,
    }


def urban_indicators(params: SiteParameters) -> dict[str, Any]:
    m = site_metrics(params)
    scores = {
        "density": min(100.0, m["floor_area_ratio"] / 4.0 * 100.0),
        "green_space": min(100.0, m["green_ratio_pct"] / 30.0 * 100.0),
        "site_efficiency": min(100.0, m["coverage_pct"] / 60.0 * 100.0),
        "height": min(100.0, m["building_height_m"] / 60.0 * 100.0),
    }
    scores["overall"] = sum(scores.values()) / len(scores)
    return {"scores": scores, "metrics": m}


def classify_land_use(places: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    mapping = {
        "Food": "Commercial",
        "Shopping": "Commercial",
        "Nightlife": "Entertainment",
        "Attractions": "Civic / Culture",
        "Parks": "Open Space",
        "Transit": "Transport",
    }
    for place in places:
        category = place.get("category", "Other")
        key = mapping.get(category, "Other")
        counts[key] = counts.get(key, 0) + 1
    return counts


def walkability_score(places: list[dict[str, Any]], center_lat: float, center_lon: float) -> dict[str, float]:
    if not places:
        return {"score": 0.0, "within_400m": 0, "within_800m": 0, "average_distance_km": 0.0}
    distances = []
    for place in places:
        try:
            distances.append(haversine_km(center_lat, center_lon, float(place["latitude"]), float(place["longitude"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not distances:
        return {"score": 0.0, "within_400m": 0, "within_800m": 0, "average_distance_km": 0.0}
    within_400 = sum(d <= 0.4 for d in distances)
    within_800 = sum(d <= 0.8 for d in distances)
    score = min(100.0, (within_400 / len(distances)) * 60 + (within_800 / len(distances)) * 40)
    return {"score": score, "within_400m": within_400, "within_800m": within_800, "average_distance_km": sum(distances) / len(distances)}


def solar_guidance(latitude: float, orientation_deg: float) -> dict[str, str]:
    orientation = orientation_deg % 360
    if latitude >= 0:
        preferred = "South / southeast façades generally provide strong winter solar access; control summer gains with shading."
    else:
        preferred = "North / northeast façades generally provide strong winter solar access; control summer gains with shading."
    if 135 <= orientation <= 225:
        note = "Primary orientation is broadly toward the south. Evaluate glazing, shading and daylight carefully."
    elif 315 <= orientation or orientation <= 45:
        note = "Primary orientation is broadly toward the north. Consider daylight distribution and solar access to outdoor spaces."
    else:
        note = "East/west exposure can create significant low-angle solar gain. External shading may be valuable."
    return {"guidance": preferred, "orientation_note": note}


def build_analysis(params: SiteParameters, places: list[dict[str, Any]], center: tuple[float, float] | None = None) -> dict[str, Any]:
    result = urban_indicators(params)
    result["land_use"] = classify_land_use(places)
    if center:
        result["walkability"] = walkability_score(places, center[0], center[1])
    else:
        result["walkability"] = {"score": 0.0, "within_400m": 0, "within_800m": 0, "average_distance_km": 0.0}
    result["solar"] = solar_guidance(params.orientation_deg)
    result["parameters"] = asdict(params)
    return result
