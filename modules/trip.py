"""Trip optimization and budget calculations."""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from typing import List, Tuple

from .maps import get_osrm_route

COST_TIER_ESTIMATES = {"$": 10.0, "$$": 35.0, "$$$": 80.0, "$$$$": 180.0}
MODE_COST_PER_KM = {"driving": 0.35, "cycling": 0.0, "walking": 0.0}
VALID_MODES = set(MODE_COST_PER_KM)


def _valid_coordinate_pair(place: dict) -> bool:
    try:
        lat = float(place["latitude"])
        lon = float(place["longitude"])
    except (KeyError, TypeError, ValueError):
        return False
    return math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180


def estimate_trip_costs(ordered_places: List[dict], total_km: float, mode: str) -> dict:
    safe_km = max(0.0, float(total_km or 0.0))
    activity = sum(COST_TIER_ESTIMATES.get(p.get("cost_tier", "$$"), 35.0) for p in ordered_places)
    travel = safe_km * MODE_COST_PER_KM.get(mode, 0.35)
    return {"activity_cost": activity, "travel_cost": travel, "total_cost": activity + travel}


def compute_distance_matrix(places: List[dict], mode: str = "driving"):
    if mode not in VALID_MODES:
        mode = "driving"
    n = len(places)
    dist = [[float("inf")] * n for _ in range(n)]
    dur = [[float("inf")] * n for _ in range(n)]
    for i in range(n):
        dist[i][i] = dur[i][i] = 0.0
        if not _valid_coordinate_pair(places[i]):
            continue
        for j in range(i + 1, n):
            if not _valid_coordinate_pair(places[j]):
                continue
            _, d_km, d_min = get_osrm_route(
                float(places[i]["latitude"]), float(places[i]["longitude"]),
                float(places[j]["latitude"]), float(places[j]["longitude"]), mode,
            )
            if d_km is not None and math.isfinite(float(d_km)):
                dist[i][j] = dist[j][i] = float(d_km)
            if d_min is not None and math.isfinite(float(d_min)):
                dur[i][j] = dur[j][i] = float(d_min)
    return dist, dur


def nearest_neighbor_order(dist_matrix, start_index: int = 0):
    if not dist_matrix or start_index < 0 or start_index >= len(dist_matrix):
        return []
    unvisited = set(range(len(dist_matrix)))
    order = [start_index]
    unvisited.discard(start_index)
    current = start_index
    while unvisited:
        reachable = [i for i in unvisited if math.isfinite(dist_matrix[current][i])]
        if not reachable:
            break
        nxt = min(reachable, key=lambda i: dist_matrix[current][i])
        order.append(nxt)
        unvisited.remove(nxt)
        current = nxt
    return order


def two_opt_improve(order: List[int], dist_matrix):
    if len(order) <= 3:
        return order
    improved = True
    while improved:
        improved = False
        for i in range(1, len(order) - 2):
            for j in range(i + 1, len(order) - 1):
                a, b, c, d = order[i - 1], order[i], order[j], order[j + 1]
                current = dist_matrix[a][b] + dist_matrix[c][d]
                candidate = dist_matrix[a][c] + dist_matrix[b][d]
                if not all(math.isfinite(value) for value in (current, candidate)):
                    continue
                if candidate + 1e-6 < current:
                    order[i:j + 1] = reversed(order[i:j + 1])
                    improved = True
    return order


def build_route_polyline_coords(order, places, mode="driving"):
    if mode not in VALID_MODES:
        mode = "driving"
    coords, total_km, total_min = [], 0.0, 0.0
    for left, right in zip(order, order[1:]):
        if left < 0 or right < 0 or left >= len(places) or right >= len(places):
            continue
        if not (_valid_coordinate_pair(places[left]) and _valid_coordinate_pair(places[right])):
            continue
        segment, km, minutes = get_osrm_route(
            float(places[left]["latitude"]), float(places[left]["longitude"]),
            float(places[right]["latitude"]), float(places[right]["longitude"]), mode,
        )
        if segment:
            coords.extend(segment[1:] if coords and segment[0] == coords[-1] else segment)
        if km is not None and math.isfinite(float(km)):
            total_km += float(km)
        if minutes is not None and math.isfinite(float(minutes)):
            total_min += float(minutes)
    return coords, total_km, total_min


def export_gpx(coords: List[Tuple[float, float]], name: str = "route"):
    gpx = ET.Element("gpx", version="1.1", creator="CityScout")
    track = ET.SubElement(gpx, "trk")
    ET.SubElement(track, "name").text = name
    segment = ET.SubElement(track, "trkseg")
    for lat, lon in coords:
        ET.SubElement(segment, "trkpt", lat=f"{float(lat):.6f}", lon=f"{float(lon):.6f}")
    return ET.tostring(gpx, encoding="utf-8", method="xml")
