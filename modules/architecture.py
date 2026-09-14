"""Architecture and urban design analysis tools for CityScout.

The calculations are transparent concept-stage indicators. They are not a
substitute for statutory planning, surveying, engineering, environmental,
accessibility, fire-safety, or energy modelling.
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


def _normalise_params(params: SiteParameters) -> SiteParameters:
    return SiteParameters(
        site_area_m2=max(0.0, _finite_number(params.site_area_m2)),
        site_coverage_pct=max(0.0, min(100.0, _finite_number(params.site_coverage_pct))),
        floors=max(1, min(200, int(_finite_number(params.floors, 1)))),
        floor_height_m=max(2.0, min(10.0, _finite_number(params.floor_height_m, 3.2))),
        setback_front_m=max(0.0, _finite_number(params.setback_front_m)),
        setback_side_m=max(0.0, _finite_number(params.setback_side_m)),
        setback_rear_m=max(0.0, _finite_number(params.setback_rear_m)),
        green_ratio_pct=max(0.0, min(100.0, _finite_number(params.green_ratio_pct))),
        parking_per_100m2=max(0.0, _finite_number(params.parking_per_100m2)),
        orientation_deg=_finite_number(params.orientation_deg) % 360.0,
    )


def site_metrics(params: SiteParameters) -> dict[str, float]:
    """Calculate transparent concept-stage development metrics."""
    p = _normalise_params(params)
    area = p.site_area_m2
    coverage = p.site_coverage_pct / 100.0
    green = p.green_ratio_pct / 100.0
    footprint = area * coverage
    gross_floor_area = footprint * p.floors
    green_area = area * green
    other_open = max(0.0, area - footprint - green_area)
    height = p.floors * p.floor_height_m
    far = gross_floor_area / area if area else 0.0
    parking = gross_floor_area / 100.0 * p.parking_per_100m2

    # A square-equivalent envelope provides a transparent setback stress test.
    # It is deliberately labelled an approximation because real parcels are not squares.
    side_length = sqrt(area) if area else 0.0
    effective_width = max(0.0, side_length - 2.0 * p.setback_side_m)
    effective_depth = max(0.0, side_length - p.setback_front_m - p.setback_rear_m)
    setback_envelope = effective_width * effective_depth
    setback_limited_footprint = min(footprint, setback_envelope)
    setback_reduction_pct = (1.0 - setback_limited_footprint / footprint) * 100.0 if footprint else 0.0
    open_space_pct = max(0.0, 100.0 - p.site_coverage_pct)
    parking_area_ratio = parking * 30.0 / area * 100.0 if area else 0.0

    return {
        "site_area_m2": area,
        "building_footprint_m2": footprint,
        "gross_floor_area_m2": gross_floor_area,
        "green_area_m2": green_area,
        "other_open_area_m2": other_open,
        "building_height_m": height,
        "floor_area_ratio": far,
        "estimated_parking_spaces": parking,
        "coverage_pct": p.site_coverage_pct,
        "green_ratio_pct": p.green_ratio_pct,
        "open_space_pct": open_space_pct,
        "setback_envelope_m2": setback_envelope,
        "setback_limited_footprint_m2": setback_limited_footprint,
        "setback_reduction_pct": max(0.0, setback_reduction_pct),
        "parking_area_ratio_pct": max(0.0, parking_area_ratio),
        "site_efficiency_pct": min(100.0, far / 4.0 * 100.0),
    }


def urban_indicators(params: SiteParameters) -> dict[str, Any]:
    m = site_metrics(params)
    scores = {
        "density": min(100.0, m["floor_area_ratio"] / 4.0 * 100.0),
        "green_space": min(100.0, m["green_ratio_pct"] / 30.0 * 100.0),
        "site_efficiency": min(100.0, m["coverage_pct"] / 60.0 * 100.0),
        "height": min(100.0, m["building_height_m"] / 60.0 * 100.0),
        "open_space": min(100.0, m["open_space_pct"] / 60.0 * 100.0),
        "parking_efficiency": max(0.0, 100.0 - min(100.0, m["parking_area_ratio_pct"])),
    }
    scores["overall"] = sum(scores.values()) / len(scores)
    return {"scores": scores, "metrics": m}


def classify_land_use(places: Iterable[dict[str, Any]] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    mapping = {
        "Food": "Commercial", "Shopping": "Commercial", "Nightlife": "Entertainment",
        "Attractions": "Civic / Culture", "Parks": "Open Space", "Transit": "Transport",
    }
    for place in places or []:
        if not isinstance(place, dict):
            continue
        category = str(place.get("category") or "Other").strip() or "Other"
        key = mapping.get(category, "Other")
        counts[key] = counts.get(key, 0) + 1
    return counts


def walkability_score(places: list[dict[str, Any]] | None, center_lat: float | None = None, center_lon: float | None = None) -> dict[str, float]:
    center = _valid_lat_lon(center_lat, center_lon) if center_lat is not None and center_lon is not None else None
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
    return {"score": score, "within_400m": within_400, "within_800m": within_800, "average_distance_km": sum(distances) / len(distances)}


def solar_guidance(latitude: float, orientation_deg: float) -> dict[str, str]:
    latitude_value = _finite_number(latitude)
    orientation = _finite_number(orientation_deg) % 360
    preferred = (
        "South / southeast façades generally provide strong winter solar access; control summer gains with shading."
        if latitude_value >= 0 else
        "North / northeast façades generally provide strong winter solar access; control summer gains with shading."
    )
    if 135 <= orientation <= 225:
        note = "Primary orientation is broadly toward the south. Evaluate glazing, shading and daylight carefully."
    elif 315 <= orientation or orientation <= 45:
        note = "Primary orientation is broadly toward the north. Consider daylight distribution and solar access to outdoor spaces."
    else:
        note = "East/west exposure can create significant low-angle solar gain. External shading may be valuable."
    return {"guidance": preferred, "orientation_note": note}


def design_recommendations(metrics: dict[str, float], scores: dict[str, float]) -> list[str]:
    recommendations: list[str] = []
    if metrics["setback_reduction_pct"] > 20:
        recommendations.append("Review the setback envelope: the square-equivalent test materially constrains the requested footprint.")
    if metrics["green_ratio_pct"] < 20:
        recommendations.append("Consider increasing green/open space for landscape, heat-island and outdoor amenity performance.")
    if metrics["parking_area_ratio_pct"] > 25:
        recommendations.append("Parking demand is spatially intensive. Test shared parking, transit access and structured parking alternatives.")
    if scores["open_space"] < 60:
        recommendations.append("Increase permeable or usable open space where planning and site conditions allow.")
    if scores["density"] > 90:
        recommendations.append("High development intensity warrants early checks for massing, daylight, servicing, fire access and infrastructure capacity.")
    if not recommendations:
        recommendations.append("Concept parameters are internally coherent. Proceed to site-specific code, access, servicing and environmental checks.")
    return recommendations


def build_analysis(params: SiteParameters, places: list[dict[str, Any]] | None, center: tuple[float, float] | None = None) -> dict[str, Any]:
    p = _normalise_params(params)
    result = urban_indicators(p)
    result["land_use"] = classify_land_use(places)
    if center and len(center) == 2:
        result["walkability"] = walkability_score(places, center[0], center[1])
    else:
        result["walkability"] = walkability_score([])
    result["solar"] = solar_guidance(0.0, p.orientation_deg)
    result["recommendations"] = design_recommendations(result["metrics"], result["scores"])
    result["parameters"] = asdict(p)
    # Backward-compatible aliases for earlier consumers.
    result["site_metrics"] = result["metrics"]
    result["urban_indicators"] = {"scores": result["scores"], "green_ratio": result["metrics"]["green_ratio_pct"] / 100.0}
    return result
