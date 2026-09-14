"""Trip optimization and budget calculations."""
from __future__ import annotations
import xml.etree.ElementTree as ET
from typing import List, Tuple
from .maps import get_osrm_route

COST_TIER_ESTIMATES = {"$": 10.0, "$$": 35.0, "$$$": 80.0, "$$$$": 180.0}
MODE_COST_PER_KM = {"driving": 0.35, "cycling": 0.0, "walking": 0.0}


def estimate_trip_costs(ordered_places: List[dict], total_km: float, mode: str) -> dict:
    activity = sum(COST_TIER_ESTIMATES.get(p.get("cost_tier", "$$"), 35.0) for p in ordered_places)
    travel = total_km * MODE_COST_PER_KM.get(mode, 0.35)
    return {"activity_cost": activity, "travel_cost": travel, "total_cost": activity + travel}


def compute_distance_matrix(places: List[dict], mode: str = "driving"):
    n = len(places)
    dist = [[float("inf")] * n for _ in range(n)]
    dur = [[float("inf")] * n for _ in range(n)]
    for i in range(n):
        dist[i][i] = dur[i][i] = 0.0
        for j in range(i + 1, n):
            _, d_km, d_min = get_osrm_route(places[i]["latitude"], places[i]["longitude"], places[j]["latitude"], places[j]["longitude"], mode)
            d_km = d_km if d_km is not None else float("inf")
            d_min = d_min if d_min is not None else float("inf")
            dist[i][j] = dist[j][i] = d_km
            dur[i][j] = dur[j][i] = d_min
    return dist, dur


def nearest_neighbor_order(dist_matrix, start_index: int = 0):
    if not dist_matrix:
        return []
    unvisited = set(range(len(dist_matrix)))
    order = [start_index]
    unvisited.discard(start_index)
    current = start_index
    while unvisited:
        nxt = min(unvisited, key=lambda i: dist_matrix[current][i])
        order.append(nxt)
        unvisited.remove(nxt)
        current = nxt
    return order


def two_opt_improve(order: List[int], dist_matrix):
    if len(order) <= 2:
        return order
    improved = True
    while improved:
        improved = False
        for i in range(1, len(order) - 2):
            for j in range(i + 1, len(order) - 1):
                a, b, c, d = order[i-1], order[i], order[j], order[j+1]
                current = dist_matrix[a][b] + dist_matrix[c][d]
                candidate = dist_matrix[a][c] + dist_matrix[b][d]
                if candidate + 1e-6 < current:
                    order[i:j+1] = reversed(order[i:j+1])
                    improved = True
    return order


def build_route_polyline_coords(order, places, mode="driving"):
    coords, total_km, total_min = [], 0.0, 0.0
    for left, right in zip(order, order[1:]):
        segment, km, minutes = get_osrm_route(places[left]["latitude"], places[left]["longitude"], places[right]["latitude"], places[right]["longitude"], mode)
        if segment:
            coords.extend(segment[1:] if coords and segment[0] == coords[-1] else segment)
        if km:
            total_km += km
        if minutes:
            total_min += minutes
    return coords, total_km, total_min


def export_gpx(coords: List[Tuple[float, float]], name: str = "route"):
    gpx = ET.Element("gpx", version="1.1", creator="CityScout")
    track = ET.SubElement(gpx, "trk")
    ET.SubElement(track, "name").text = name
    segment = ET.SubElement(track, "trkseg")
    for lat, lon in coords:
        ET.SubElement(segment, "trkpt", lat=f"{lat:.6f}", lon=f"{lon:.6f}")
    return ET.tostring(gpx, encoding="utf-8", method="xml")
