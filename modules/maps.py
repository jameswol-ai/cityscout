"""Mapping, geocoding and routing services for CityScout."""
from __future__ import annotations

import re
import time
from math import radians, cos, sin, asin, sqrt
from typing import Optional, Tuple

import requests

from .config import BASE_URL, OSRM_ROUTE_TTL


OSRM_PROFILES = {"driving", "cycling", "walking"}


def resolve_short_url(url: str, timeout: int = 8) -> str:
    try:
        response = requests.head(url, allow_redirects=True, timeout=timeout)
        final = response.url or url
        if final == url:
            response = requests.get(url, allow_redirects=True, timeout=timeout)
            final = response.url or url
        return final
    except requests.RequestException:
        return url


def parse_map_link(url: str) -> Tuple[Optional[float], Optional[float]]:
    if not isinstance(url, str) or not url.strip():
        return None, None
    value = resolve_short_url(url.strip())
    patterns = [
        r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
        r"[?&](?:q|query)=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
        r"[?&]mlat=(-?\d+(?:\.\d+)?)&mlon=(-?\d+(?:\.\d+)?)",
        r"#map=\d+\/(-?\d+(?:\.\d+)?)\/(-?\d+(?:\.\d+)?)",
        r"/place/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
        r"[?&](?:q|ll)=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)",
        r"[?&]cp=(-?\d+(?:\.\d+)?)~(-?\d+(?:\.\d+)?)",
        r"(-?\d+(?:\.\d+)?)[, ]+(-?\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            lat, lon = float(match.group(1)), float(match.group(2))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon
    return None, None


def reverse_geocode(lat: float, lon: float) -> str:
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1},
            headers={"User-Agent": "CityScout/1.1"},
            timeout=6,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("display_name", "") if isinstance(data, dict) else ""
    except (requests.RequestException, ValueError, TypeError):
        return ""


def decode_polyline(value: str):
    """Decode a Google/OSRM encoded polyline without leaking malformed input errors."""
    if not isinstance(value, str) or not value:
        return []
    index = lat = lng = 0
    coordinates = []
    try:
        while index < len(value):
            shift = result = 0
            while True:
                if index >= len(value):
                    return []
                b = ord(value[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            lat += ~(result >> 1) if result & 1 else result >> 1

            shift = result = 0
            while True:
                if index >= len(value):
                    return []
                b = ord(value[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            lng += ~(result >> 1) if result & 1 else result >> 1
            coordinates.append((lat / 1e5, lng / 1e5))
    except (IndexError, TypeError, ValueError):
        return []
    return coordinates


class InMemoryCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        entry = self.store.get(key)
        if not entry:
            return None
        value, expires_at = entry
        if time.time() > expires_at:
            self.store.pop(key, None)
            return None
        return value

    def set(self, key, value, ttl):
        self.store[key] = (value, time.time() + max(0, ttl))


_route_cache = InMemoryCache()


def get_osrm_route(lat1: float, lon1: float, lat2: float, lon2: float, mode: str = "driving"):
    """Return route coordinates, distance and duration with graceful API failure handling."""
    try:
        lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return [], None, None
    if not all((-90 <= lat <= 90 for lat in (lat1, lat2))) or not all((-180 <= lon <= 180 for lon in (lon1, lon2))):
        return [], None, None

    profile = mode if mode in OSRM_PROFILES else "driving"
    key = f"osrm:{profile}:{lat1:.6f},{lon1:.6f}:{lat2:.6f},{lon2:.6f}"
    cached = _route_cache.get(key)
    if cached is not None:
        return cached["coords"], cached["distance_km"], cached["duration_min"]

    try:
        url = f"https://router.project-osrm.org/route/v1/{profile}/{lon1},{lat1};{lon2},{lat2}"
        response = requests.get(
            url,
            params={"overview": "full", "geometries": "polyline", "steps": "false"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        routes = data.get("routes", []) if isinstance(data, dict) else []
        if routes and isinstance(routes[0], dict):
            route = routes[0]
            distance = route.get("distance")
            duration = route.get("duration")
            if distance is None or duration is None:
                return [], None, None
            payload = {
                "coords": decode_polyline(route.get("geometry", "")),
                "distance_km": float(distance) / 1000.0,
                "duration_min": float(duration) / 60.0,
            }
            _route_cache.set(key, payload, OSRM_ROUTE_TTL)
            return payload["coords"], payload["distance_km"], payload["duration_min"]
    except (requests.RequestException, ValueError, TypeError, KeyError):
        pass
    return [], None, None


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def fetch_explore_from_backend(city: str, category: str):
    sample = [
        {"name": "Central Park Cafe", "description": "Sample cafe for testing", "latitude": 0.3476, "longitude": 32.5825, "category": "Food", "url": ""},
        {"name": "Riverside Park", "description": "Sample park", "latitude": 0.3490, "longitude": 32.5800, "category": "Parks", "url": ""},
    ]
    try:
        params = {"city": city} if city else {}
        if category and category != "any":
            params["category"] = category
        response = requests.get(f"{BASE_URL}/explore", params=params, timeout=8)
        response.raise_for_status()
        data = response.json()
        results = data.get("results") if isinstance(data, dict) else data
        if not isinstance(results, list):
            return sample
        normalized = []
        for item in results:
            if not isinstance(item, dict):
                continue
            lat = item.get("latitude") or item.get("lat")
            lon = item.get("longitude") or item.get("lon")
            if lat is None or lon is None:
                lat, lon = parse_map_link(item.get("url") or item.get("link") or item.get("maps_link") or "")
            if lat is not None and lon is not None:
                try:
                    lat, lon = float(lat), float(lon)
                except (TypeError, ValueError):
                    continue
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    item["latitude"], item["longitude"] = lat, lon
                    normalized.append(item)
        return normalized or sample
    except (requests.RequestException, ValueError, TypeError):
        return sample
