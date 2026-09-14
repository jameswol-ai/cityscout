"""Architecture and urban design analysis tools for CityScout.

The module intentionally uses transparent, assumption-driven calculations. It is
an early-stage planning aid, not a substitute for statutory planning, surveying,
engineering, environmental, or fire-safety review.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import asin, cos, isfinite, radians, sin, sqrt
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


def _finite_number(value: Any, default: float = 0.0) -> float:
    """Return a finite numeric value, falling back safely for bad input."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if isfinite(number) else default


def _valid_lat_lon(lat: Any, lon: Any) -> tuple[float, float] | None:
    latitude = _finite_number(lat, float("nan"))
    longitude = _finite_number(lon, float("nan"))
    if not (isfinite(latitude) and isfinite(longitude)):
        return None
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return None
    return latitude, longitude


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres for valid coordinates."""
    first = _valid_lat_lon(lat1, lon1)
    second = _valid_lat_lon(lat2, lon2)
    if first is None or second is None:
        return float("inf")
    r = 6371.0088
    p1, p2 = radians(first[0]), radians(second[0])
    dp = radians(second[0] - first[0])
    dl = radians(second[1] - first[1])
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    a = max(0.0, min(1.0, a))
    return 2 * r * asin(sqrt(a))


def site_metrics(params: SiteParameters) -> dict[str, float]:
    """Calculate transparent concept-stage development metrics."""
    area = max(0.0, _finite_number(params.site_area_m2))
    coverage = max(0.0, min(100.0, _finite_number(params.site_coverage_pct))) / 100.0
    green = max(0.0, min(100.0, _finite_number(params.green_ratio_pct))) / 100.0
    floors = max(1, int(_finite_number(params.floors, 1.0)))
    floor_height = max(0.0, _finite_number(params.floor_height_m))
    parking_rate = max(0.0, _finite_number(params.parking_per_100m2))

    footprint = area * coverage
    gross_floor_area = footprint * floors
    green_area = area * green
    paved_or_other = max(0.0, area - footprint - green_area)
    building_height = floors * floor_height
    far = gross_floor_area / area if area else 0.0
    parking_spaces = gross_floor_area / 100.0 * parking_rate
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


def classify_land_use(places: Iterable[dict[str, Any]] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    mapping = {
        "Food": "Commercial",
        "Shopping": "Commercial",
        "Nightlife": "Entertainment",
        "Attractions": "Civic / Culture",
        "Parks": "Open Space",
        "Transit": "Transport",
    }
    for place in places or []:
        if not isinstance(place, dict):
            continue
        category = str(place.get("category") or "Other").strip() or "Other"
        key = mapping.get(category, "Other")
        counts[key] = counts.get(key, 0) + 1
    return counts


def walkability_score(places: list[dict[str, Any]] | None, center_lat: float, center_lon: float) -> dict[str, float]:
    """Calculate a simple proximity-based walkability indicator."""
    center = _valid_lat_lon(center_lat, center_lon)
    if center is None:
        return {"score": 0.0, "within_400m": 0, "within_800m": 0, "average_distance_km": 0.0}

    distances: list[float] = []
    for place in places or []:
        if not isinstance(place, dict):
            continue
        coords = _valid_lat_lon(place.get("latitude"), place.get("longitude"))
        if coords is None:
            continue
        distance = haversine_km(center[0], center[1], coords[0], coords[1])
        if isfinite(distance):
            distances.append(distance)

    if not distances:
        return {"score": 0.0, "within_400m": 0, "within_800m": 0, "average_distance_km": 0.0}

    within_400 = sum(d <= 0.4 for d in distances)
    within_800 = sum(d <= 0.8 for d in distances)
    score = min(100.0, (within_400 / len(distances)) * 60 + (within_800 / len(distances)) * 40)
    return {
        "score": score,
        "within_400m": within_400,
        "within_800m": within_800,
        "average_distance_km": sum(distances) / len(distances),
    }


def solar_guidance(latitude: float, orientation_deg: float) -> dict[str, str]:
    """Provide high-level solar-orientation guidance."""
    latitude_value = _finite_number(latitude)
    orientation = _finite_number(orientation_deg) % 360
    if latitude_value >= 0:
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


def build_analysis(params: SiteParameters, places: list[dict[str, Any]] | None, center: tuple[float, float] | None = None) -> dict[str, Any]:
    """Build the complete concept-stage architecture analysis."""
    result = urban_indicators(params)
    result["land_use"] = classify_land_use(places)
    if center and len(center) == 2:
        result["walkability"] = walkability_score(places, center[0], center[1])
    else:
        result["walkability"] = {"score": 0.0, "within_400m": 0, "within_800m": 0, "average_distance_km": 0.0}
    result["solar"] = solar_guidance(0.0, params.orientation_deg)
    result["parameters"] = asdict(params)
    return result
