"""Interactive GIS helpers for CityScout.

The GIS layer is deliberately UI-light: it prepares map layers from the
existing saved-place model and keeps geographic calculations reusable by
future city intelligence features.
"""
from __future__ import annotations

from math import cos, radians
from typing import Iterable, Sequence

import folium
from folium.plugins import HeatMap, MarkerCluster


DEFAULT_CENTER = (0.3476, 32.5825)


def valid_places(places: Iterable[dict]) -> list[dict]:
    """Return places with usable latitude/longitude values."""
    result = []
    for place in places:
        try:
            lat = float(place.get("latitude"))
            lon = float(place.get("longitude"))
        except (TypeError, ValueError):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            result.append({**place, "latitude": lat, "longitude": lon})
    return result


def map_center(places: Sequence[dict]) -> tuple[float, float]:
    items = valid_places(places)
    if not items:
        return DEFAULT_CENTER
    return (
        sum(p["latitude"] for p in items) / len(items),
        sum(p["longitude"] for p in items) / len(items),
    )


def build_city_map(
    places: Sequence[dict],
    *,
    show_heatmap: bool = False,
    cluster_markers: bool = True,
    selected_category: str = "All",
    zoom_start: int = 12,
) -> folium.Map:
    """Build a layered Folium map from saved CityScout places."""
    items = valid_places(places)
    if selected_category != "All":
        items = [p for p in items if p.get("category", "Other") == selected_category]

    fmap = folium.Map(location=map_center(items), zoom_start=zoom_start, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="Street Map").add_to(fmap)
    folium.TileLayer("CartoDB positron", name="Light Map").add_to(fmap)

    target = MarkerCluster(name="Places") if cluster_markers else folium.FeatureGroup(name="Places")
    for place in items:
        favorite = " ⭐" if place.get("favorite") else ""
        popup = (
            f"<b>{place.get('name', 'Unnamed place')}</b>{favorite}<br>"
            f"{place.get('category', 'Other')}<br>"
            f"{place.get('address', '')}"
        )
        folium.Marker(
            [place["latitude"], place["longitude"]],
            tooltip=place.get("name", "Place"),
            popup=folium.Popup(popup, max_width=300),
        ).add_to(target)
    target.add_to(fmap)

    if show_heatmap and items:
        heat_points = [[p["latitude"], p["longitude"], 1.0] for p in items]
        HeatMap(heat_points, name="Place Density", radius=22, blur=18).add_to(fmap)

    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap


def city_metrics(places: Sequence[dict]) -> dict:
    """Calculate compact GIS metrics for the dashboard."""
    items = valid_places(places)
    categories: dict[str, int] = {}
    for place in items:
        category = place.get("category") or "Other"
        categories[category] = categories.get(category, 0) + 1

    if len(items) >= 2:
        latitudes = [p["latitude"] for p in items]
        longitudes = [p["longitude"] for p in items]
        lat_span_km = (max(latitudes) - min(latitudes)) * 111.32
        mean_lat = radians(sum(latitudes) / len(latitudes))
        lon_span_km = (max(longitudes) - min(longitudes)) * 111.32 * cos(mean_lat)
        footprint_km2 = max(0.0, lat_span_km * lon_span_km)
    else:
        footprint_km2 = 0.0

    return {
        "places": len(items),
        "favorites": sum(bool(p.get("favorite")) for p in items),
        "categories": len(categories),
        "category_counts": categories,
        "footprint_km2": footprint_km2,
    }
