# streamlit_app.py
"""
CityScout - Streamlit app with public share hosting and reverted logo

Changes in this version:
- Adds simple public share hosting support (local token files + optional password protection)
  - Generates share tokens and saves them as JSON files in USER_DATA_DIR
  - If PUBLIC_BASE_URL env var is set, the app will display a public URL for the token
  - Password protection supported (stored as SHA256 hash)
  - Loading a share token requires the password if one was set
- Reverted to the older compact SVG logo (single image asset)
- Keeps previously implemented features: sidebar navigation, Trip Planner, per-user persistence,
  photos, reviews, tags, proximity search, GPX export, templates, OSRM routing, explore fallback
- Uses local file-based share hosting; for true public hosting you must serve USER_DATA_DIR/share_*.json
  from a public endpoint (see PUBLIC_BASE_URL env var)
"""

from __future__ import annotations
import os
import re
import json
import time
import hashlib
import requests
import streamlit as st
import folium
import pandas as pd
import xml.etree.ElementTree as ET
from typing import Optional, Tuple, List, Dict
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from datetime import datetime
from math import radians, cos, sin, asin, sqrt

# rbac.py
import hashlib
from database import get_db_connection

ROLES = {
    "viewer": ["read", "review"],
    "planner": ["read", "review", "create_place", "plan_trip"],
    "approver": ["read", "review", "create_place", "plan_trip", "approve_itinerary", "manage_categories"],
    "admin": ["read", "review", "create_place", "plan_trip", "approve_itinerary", "manage_categories", "admin_panel"]
}

def get_user_role(username: str) -> str:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE username = %s", (username,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row["role"] if row else "viewer"

def check_permission(username: str, action: str) -> bool:
    role = get_user_role(username)
    allowed_actions = ROLES.get(role, [])
    return action in allowed_actions



# -------------------------
# Configuration
# -------------------------
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000")
AUTH_VERIFY_TIMEOUT = int(os.getenv("AUTH_VERIFY_TIMEOUT", "6"))
USER_DATA_DIR = os.getenv("USER_DATA_DIR", "./user_data")
os.makedirs(USER_DATA_DIR, exist_ok=True)

# PUBLIC_BASE_URL: if set, used to build public share URLs:
# e.g., https://cityscout.example.com/share/<token>.json
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
MEDIA_DIR_NAME = "media"
BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
OSRM_ROUTE_TTL = int(os.getenv("OSRM_ROUTE_TTL", "3600"))

# Visual constants
APP_BG = "#000000"
APP_PRIMARY = "#0b6efd"
APP_FONT = "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial"

st.set_page_config(page_title="CityScout", page_icon="🌆", layout="wide")

# -------------------------
# Session defaults
# -------------------------
if "access_token" not in st.session_state:
    st.session_state["access_token"] = None
if "username" not in st.session_state:
    st.session_state["username"] = None
if "places" not in st.session_state:
    st.session_state["places"] = []
if "categories" not in st.session_state:
    st.session_state["categories"] = ["Food", "Nightlife", "Shopping", "Attractions", "Parks", "Transit", "Other"]
if "auth_mode" not in st.session_state:
    st.session_state["auth_mode"] = None
if "page" not in st.session_state:
    st.session_state["page"] = "Trip Planner"
if "last_route" not in st.session_state:
    st.session_state["last_route"] = None
if "trip_templates" not in st.session_state:
    st.session_state["trip_templates"] = {}
if "share_tokens" not in st.session_state:
    st.session_state["share_tokens"] = {}  # token -> metadata

USERS_FILE = os.path.join(USER_DATA_DIR, "users.json")

# -------------------------
# Reverted compact SVG logo (single)
# -------------------------
APP_SVG_LOGO = """
<svg width="120" height="120" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect rx="18" width="100" height="100" fill="{color}"/>
  <g transform="translate(18,18)" fill="#fff">
    <path d="M12 2c-5.5 0-10 4.5-10 10 0 7.5 10 18 10 18s10-10.5 10-18c0-5.5-4.5-10-10-10z"/>
    <circle cx="12" cy="12" r="3"/>
  </g>
</svg>
"""

# -------------------------
# CSS
# -------------------------
def inject_css():
    css = f"""
    <style>
    html, body, .stApp {{
      background: {APP_BG} !important;
      color: #e6e6e6 !important;
      font-family: {APP_FONT} !important;
    }}
    .card {{
      background: rgba(255,255,255,0.03);
      border-radius: 10px;
      padding: 12px;
      margin-bottom: 12px;
      border: 1px solid rgba(255,255,255,0.06);
    }}
    .logo-top {{
      display:flex;
      align-items:center;
      justify-content:center;
      padding:18px 0 6px 0;
    }}
    .logo-top svg {{ display:block; margin:0 auto; }}
    .small-muted {{ color: #9ca3af; font-size:0.95rem; text-align:center; }}
    .sidebar-section {{ margin-bottom: 12px; }}
    a.map-link {{ color: #9ad0ff; text-decoration: underline; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# -------------------------
# Helpers: per-user paths and media
# -------------------------
def user_media_dir(username: str) -> str:
    path = os.path.join(USER_DATA_DIR, f"{username}_{MEDIA_DIR_NAME}")
    os.makedirs(path, exist_ok=True)
    return path

def _user_places_path(username: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", username)
    return os.path.join(USER_DATA_DIR, f"{safe}_places.json")

def load_user_places(username: str):
    path = _user_places_path(username)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_user_places(username: str, places):
    path = _user_places_path(username)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(places, f, indent=2)
    except Exception:
        pass

# -------------------------
# Local users fallback
# -------------------------
def load_local_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_local_users(users: dict):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
    except Exception:
        pass

def create_local_user(username: str, password: str) -> bool:
    users = load_local_users()
    if username in users:
        return False
    users[username] = {"password_hash": hashlib.sha256(password.encode()).hexdigest()}
    save_local_users(users)
    return True

def verify_local_user(username: str, password: str) -> bool:
    users = load_local_users()
    if username not in users:
        return False
    return users[username].get("password_hash") == hashlib.sha256(password.encode()).hexdigest()

def ensure_demo_local_user():
    users = load_local_users()
    if "demo" not in users:
        users["demo"] = {"password_hash": hashlib.sha256("demo123".encode()).hexdigest()}
        save_local_users(users)

# -------------------------
# Map link parsing and reverse geocode
# -------------------------
def resolve_short_url(url: str, timeout: int = 8) -> str:
    try:
        resp = requests.head(url, allow_redirects=True, timeout=timeout)
        final = resp.url or url
        if final == url:
            resp = requests.get(url, allow_redirects=True, timeout=timeout)
            final = resp.url or url
        return final
    except Exception:
        return url

def parse_map_link(url: str) -> Tuple[Optional[float], Optional[float]]:
    if not url or not isinstance(url, str):
        return None, None
    s = url.strip()
    s = resolve_short_url(s)
    m = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'[?&](?:q|query)=(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'[?&]mlat=(-?\d+\.\d+)&mlon=(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'#map=\d+\/(-?\d+\.\d+)\/(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'/place/(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'[?&](?:q|ll)=(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'[?&]cp=(-?\d+\.\d+)~(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'(-?\d+\.\d+)[, ]+(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None

def reverse_geocode(lat: float, lon: float) -> str:
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1}
        headers = {"User-Agent": "CityScout/1.0 (+https://example.com)"}
        r = requests.get(url, params=params, headers=headers, timeout=6)
        r.raise_for_status()
        data = r.json()
        return data.get("display_name", "")
    except Exception:
        return ""

# -------------------------
# Polyline decoder and OSRM
# -------------------------
def decode_polyline(polyline_str: str):
    if not polyline_str:
        return []
    index, lat, lng = 0, 0, 0
    coordinates = []
    length = len(polyline_str)
    while index < length:
        shift, result = 0, 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat
        shift, result = 0, 0
        while True:
            b = ord(polyline_str[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng
        coordinates.append((lat / 1e5, lng / 1e5))
    return coordinates

class InMemoryCache:
    def __init__(self):
        self.store = {}
    def _now(self):
        return int(time.time())
    def get(self, key):
        entry = self.store.get(key)
        if not entry:
            return None
        value, expires_at = entry
        if self._now() > expires_at:
            del self.store[key]
            return None
        return value
    def set(self, key, value, ttl):
        self.store[key] = (value, self._now() + ttl)

mem_cache = InMemoryCache()

def _osrm_cache_key(lat1, lon1, lat2, lon2, mode):
    return f"osrm:{mode}:{lat1:.6f},{lon1:.6f}:{lat2:.6f},{lon2:.6f}"

def get_osrm_route(lat1: float, lon1: float, lat2: float, lon2: float, mode: str = "driving"):
    key = _osrm_cache_key(lat1, lon1, lat2, lon2, mode)
    cached = mem_cache.get(key)
    if cached is not None:
        return cached["coords"], cached["distance_km"], cached["duration_min"]
    try:
        url = (
            f"http://router.project-osrm.org/route/v1/{mode}/"
            f"{lon1},{lat1};{lon2},{lat2}"
            f"?overview=full&geometries=polyline"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("routes"):
            route = data["routes"][0]
            coords = decode_polyline(route.get("geometry", ""))
            distance_km = route.get("distance", 0) / 1000.0
            duration_min = route.get("duration", 0) / 60.0
            payload = {"coords": coords, "distance_km": distance_km, "duration_min": duration_min}
            mem_cache.set(key, payload, OSRM_ROUTE_TTL)
            return coords, distance_km, duration_min
    except Exception:
        pass
    return [], None, None

# -------------------------
# Auth helpers (remote + local fallback)
# -------------------------
def call_auth_signup(username: str, password: str) -> Optional[str]:
    try:
        r = requests.post(f"{AUTH_URL}/signup", json={"username": username, "password": password}, timeout=AUTH_VERIFY_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        return data.get("access_token")
    except Exception:
        return None

def call_auth_login(username: str, password: str) -> Optional[str]:
    try:
        r = requests.post(f"{AUTH_URL}/login", json={"username": username, "password": password}, timeout=AUTH_VERIFY_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        return data.get("access_token")
    except Exception:
        return None

def verify_token(token: str) -> Optional[dict]:
    if not token:
        return None
    try:
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{AUTH_URL}/me", headers=headers, timeout=AUTH_VERIFY_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def logout_user():
    st.session_state["access_token"] = None
    st.session_state["username"] = None
    st.session_state["places"] = []
    st.session_state["auth_mode"] = None
    st.session_state["trip_templates"] = {}
    st.session_state["last_route"] = None

# -------------------------
# Place helpers (photos, tags, reviews)
# -------------------------
def add_place(name: str, lat: float, lon: float, description: str = "", category: str = "Other",
              favorite: bool = False, source_link: str = "", tags: List[str] = None,
              photos: List[str] = None):
    address = reverse_geocode(lat, lon)
    place = {
        "id": hashlib.sha1(f"{name}{lat}{lon}{time.time()}".encode()).hexdigest()[:12],
        "name": name,
        "latitude": float(lat),
        "longitude": float(lon),
        "address": address,
        "description": description or "",
        "category": category or "Other",
        "favorite": bool(favorite),
        "source_link": source_link or "",
        "tags": tags or [],
        "photos": photos or [],
        "reviews": [],
    }
    st.session_state["places"].append(place)
    if st.session_state.get("username"):
        save_user_places(st.session_state["username"], st.session_state["places"])
    return place

def update_place(place_id: str, **fields):
    for p in st.session_state["places"]:
        if p.get("id") == place_id:
            p.update(fields)
            if "latitude" in fields or "longitude" in fields:
                p["address"] = reverse_geocode(p.get("latitude"), p.get("longitude"))
            if st.session_state.get("username"):
                save_user_places(st.session_state["username"], st.session_state["places"])
            return p
    return None

def delete_place(place_id: str):
    to_delete = [p for p in st.session_state["places"] if p.get("id") == place_id]
    for p in to_delete:
        for fn in p.get("photos", []):
            try:
                path = os.path.join(user_media_dir(st.session_state["username"]), fn)
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
    st.session_state["places"] = [p for p in st.session_state["places"] if p.get("id") != place_id]
    if st.session_state.get("username"):
        save_user_places(st.session_state["username"], st.session_state["places"])

def add_review(place_id: str, user: str, rating: int, text: str):
    for p in st.session_state["places"]:
        if p.get("id") == place_id:
            p.setdefault("reviews", []).append({"user": user, "rating": int(rating), "text": text, "ts": datetime.utcnow().isoformat()})
            if st.session_state.get("username"):
                save_user_places(st.session_state["username"], st.session_state["places"])
            return p
    return None

def average_rating(place: dict) -> Optional[float]:
    reviews = place.get("reviews", [])
    if not reviews:
        return None
    return sum(r.get("rating", 0) for r in reviews) / len(reviews)

# -------------------------
# Proximity helper (Haversine)
# -------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    km = 6371 * c
    return km

# -------------------------
# GPX export helper
# -------------------------
def export_gpx(coords: List[Tuple[float, float]], name: str = "route"):
    import xml.etree.ElementTree as ET
    gpx = ET.Element("gpx", version="1.1", creator="CityScout")
    trk = ET.SubElement(gpx, "trk")
    name_el = ET.SubElement(trk, "name")
    name_el.text = name
    trkseg = ET.SubElement(trk, "trkseg")
    for lat, lon in coords:
        ET.SubElement(trkseg, "trkpt", attrib={"lat": f"{lat:.6f}", "lon": f"{lon:.6f}"})
    xml_str = ET.tostring(gpx, encoding="utf-8", method="xml")
    return xml_str

# -------------------------
# Explore helper (safe)
# -------------------------
def fetch_explore_from_backend(city: str, category: str):
    sample = [
        {"name": "Central Park Cafe", "description": "Sample cafe for testing", "latitude": 0.3476, "longitude": 32.5825, "category": "Food", "url": ""},
        {"name": "Riverside Park", "description": "Sample park", "latitude": 0.3490, "longitude": 32.5800, "category": "Parks", "url": ""}
    ]
    try:
        params = {}
        if city:
            params["city"] = city
        if category and category != "any":
            params["category"] = category
        resp = requests.get(f"{BASE_URL}/explore", params=params, timeout=8)
        if resp.status_code < 200 or resp.status_code >= 300:
            st.warning(f"Explore backend returned status {resp.status_code}. Using sample results.")
            snippet = resp.text[:400].replace("\n", " ")
            st.caption(f"Backend response snippet: {snippet}")
            return sample
        data = resp.json()
        if isinstance(data, dict) and "results" in data and isinstance(data["results"], list):
            results = data["results"]
        elif isinstance(data, list):
            results = data
        else:
            st.warning("Explore backend returned unexpected JSON structure. Using sample results.")
            st.caption(f"Response type: {type(data)}")
            return sample

        normalized = []
        for r in results:
            lat = r.get("latitude") or r.get("lat") or None
            lon = r.get("longitude") or r.get("lon") or None
            if lat is None or lon is None:
                link = r.get("url") or r.get("link") or r.get("maps_link") or r.get("map_url") or ""
                lat, lon = parse_map_link(link)
            if lat is not None and lon is not None:
                try:
                    r["latitude"] = float(lat)
                    r["longitude"] = float(lon)
                    normalized.append(r)
                except Exception:
                    continue
        if not normalized:
            st.info("Explore backend returned no usable coordinates. Showing sample results.")
            return sample
        return normalized

    except Exception:
        st.warning("Explore fetch failed; using sample results.")
        return sample

# -------------------------
# Trip planner helpers (nearest neighbor + 2-opt)
# -------------------------
def compute_distance_matrix(places: List[dict], mode: str = "driving"):
    n = len(places)
    dist = [[float("inf")] * n for _ in range(n)]
    dur = [[float("inf")] * n for _ in range(n)]
    for i in range(n):
        dist[i][i] = 0.0
        dur[i][i] = 0.0
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            a = places[i]
            b = places[j]
            coords, d_km, d_min = get_osrm_route(a["latitude"], a["longitude"], b["latitude"], b["longitude"], mode=mode)
            dist[i][j] = d_km if d_km is not None else float("inf")
            dur[i][j] = d_min if d_min is not None else float("inf")
    return dist, dur

def nearest_neighbor_order(dist_matrix: List[List[float]], start_index: int = 0) -> List[int]:
    n = len(dist_matrix)
    unvisited = set(range(n))
    order = [start_index]
    unvisited.remove(start_index)
    current = start_index
    while unvisited:
        next_idx = min(unvisited, key=lambda x: dist_matrix[current][x] if dist_matrix[current][x] is not None else float("inf"))
        order.append(next_idx)
        unvisited.remove(next_idx)
        current = next_idx
    return order

def two_opt_improve(order: List[int], dist_matrix: List[List[float]]) -> List[int]:
    improved = True
    n = len(order)
    if n <= 2:
        return order
    while improved:
        improved = False
        for i in range(1, n - 2):
            for j in range(i + 1, n - 1):
                a, b = order[i - 1], order[i]
                c, d = order[j], order[j + 1]
                cur = (dist_matrix[a][b] or float("inf")) + (dist_matrix[c][d] or float("inf"))
                new = (dist_matrix[a][c] or float("inf")) + (dist_matrix[b][d] or float("inf"))
                if new + 1e-6 < cur:
                    order[i:j + 1] = list(reversed(order[i:j + 1]))
                    improved = True
        if improved:
            continue
    return order

def build_route_polyline_coords(order: List[int], places: List[dict], mode: str = "driving"):
    all_coords = []
    total_km = 0.0
    total_min = 0.0
    for idx in range(len(order) - 1):
        a = places[order[idx]]
        b = places[order[idx + 1]]
        coords, d_km, d_min = get_osrm_route(a["latitude"], a["longitude"], b["latitude"], b["longitude"], mode=mode)
        if coords:
            if all_coords and coords[0] == all_coords[-1]:
                all_coords.extend(coords[1:])
            else:
                all_coords.extend(coords)
        if d_km:
            total_km += d_km
        if d_min:
            total_min += d_min
    return all_coords, total_km, total_min

# -------------------------
# Share token helpers (public share hosting)
# -------------------------
def _share_path(token: str) -> str:
    return os.path.join(USER_DATA_DIR, f"share_{token}.json")

def create_share_token(payload: dict, password: Optional[str] = None, expires_hours: Optional[int] = None) -> str:
    """
    Create a share token file. Returns token string.
    - payload: arbitrary JSON-serializable data (e.g., last_route or list of places)
    - password: optional plaintext password; stored as SHA256 hash
    - expires_hours: optional TTL in hours
    """
    token = hashlib.sha1(json.dumps(payload, default=str).encode()).hexdigest()[:12]
    meta = {
        "payload": payload,
        "created_at": datetime.utcnow().isoformat(),
        "password_hash": hashlib.sha256(password.encode()).hexdigest() if password else None,
        "expires_at": (datetime.utcnow().timestamp() + expires_hours * 3600) if expires_hours else None
    }
    path = _share_path(token)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    # store in session for quick access
    st.session_state["share_tokens"][token] = meta
    return token

def load_share_token(token: str, password: Optional[str] = None) -> Optional[dict]:
    path = _share_path(token)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        # check expiry
        if meta.get("expires_at") and time.time() > meta["expires_at"]:
            return None
        ph = meta.get("password_hash")
        if ph:
            if not password:
                return {"requires_password": True}
            if hashlib.sha256(password.encode()).hexdigest() != ph:
                return {"invalid_password": True}
        return meta.get("payload")
    except Exception:
        return None

def public_share_url(token: str) -> Optional[str]:
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL}/share_{token}.json"
    return None

# -------------------------
# Sidebar navigation (tabs in sidebar)
# -------------------------
def sidebar_navigation():
    inject_css()
    st.sidebar.markdown("<div class='logo-top'>", unsafe_allow_html=True)
    st.sidebar.markdown(APP_SVG_LOGO.format(color=APP_PRIMARY), unsafe_allow_html=True)
    st.sidebar.markdown("</div>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='sidebar-section small-muted'>Navigate</div>", unsafe_allow_html=True)
    pages = ["Trip Planner", "Dashboard", "Explore", "Add Place", "Places", "Share", "Categories", "Settings"]
    choice = st.sidebar.radio("Pages", pages, index=pages.index(st.session_state.get("page", "Trip Planner")))
    st.session_state["page"] = choice
    st.sidebar.markdown("---")
    if st.sidebar.button("Add sample place"):
        add_place("Sample Place", 0.3476, 32.5825, "Sample", category="Attractions", favorite=False)
        st.sidebar.success("Sample place added")
    if st.sidebar.button("Export all places (CSV)"):
        df = pd.DataFrame(st.session_state["places"])
        csv = df.to_csv(index=False).encode("utf-8")
        st.sidebar.download_button("Download CSV", data=csv, file_name="places.csv", mime="text/csv")
    st.sidebar.markdown("---")
    if st.session_state.get("username"):
        st.sidebar.markdown(f"**User:** {st.session_state['username']}")
        st.sidebar.markdown(f"**Auth:** {st.session_state.get('auth_mode') or 'unknown'}")
        if st.sidebar.button("Logout"):
            logout_user()
            st.experimental_rerun()

# -------------------------
# Page renderers (Share page + others)
# -------------------------
def page_share():
    st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Share</h3></div>", unsafe_allow_html=True)
    st.write("Create a public share token for a trip or a list of places. Tokens are stored as files in the app instance.")
    st.write("If PUBLIC_BASE_URL is configured and you serve USER_DATA_DIR publicly at that base URL, the share will be accessible via the public URL.")
    st.write("---")

    # Choose payload: last route or selected places
    choice = st.selectbox("Share payload", ["Last computed route", "Selected saved places"])
    if choice == "Selected saved places":
        if not st.session_state.get("places"):
            st.info("No saved places to share.")
            return
        place_names = [f"{p['name']} — {p.get('category','')}" for p in st.session_state["places"]]
        selected = st.multiselect("Select places to share", options=list(range(len(place_names))), format_func=lambda i: place_names[i])
        if not selected:
            st.write("Select at least one place to share.")
            return
        payload = {"type": "places", "places": [st.session_state["places"][i] for i in selected], "owner": st.session_state.get("username")}
    else:
        if not st.session_state.get("last_route"):
            st.info("No last route computed yet.")
            return
        payload = {"type": "route", "route": st.session_state["last_route"], "owner": st.session_state.get("username")}

    password = st.text_input("Optional password to protect the share (leave blank for none)", type="password")
    expires = st.number_input("Expires in (hours, 0 = never)", min_value=0, value=0, step=1)
    if st.button("Create share token"):
        token = create_share_token(payload, password=password if password else None, expires_hours=(expires if expires > 0 else None))
        url = public_share_url(token)
        st.success("Share token created")
        st.write(f"Token: **{token}**")
        if url:
            st.markdown(f"Public URL (if you serve share files at PUBLIC_BASE_URL): {url}")
        else:
            st.info("PUBLIC_BASE_URL not configured. To make the share publicly accessible, set PUBLIC_BASE_URL to the base URL where share files will be served and ensure the files in USER_DATA_DIR are reachable there.")
        st.write("You can load this token on any instance of this app (Settings → Load shared token).")

    st.write("---")
    st.markdown("**Existing local share tokens**")
    files = [f for f in os.listdir(USER_DATA_DIR) if f.startswith("share_") and f.endswith(".json")]
    if not files:
        st.write("No local share tokens found.")
    else:
        for fn in sorted(files, reverse=True):
            token = fn.replace("share_", "").replace(".json", "")
            meta = None
            try:
                with open(os.path.join(USER_DATA_DIR, fn), "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                continue
            created = meta.get("created_at")
            expires_at = meta.get("expires_at")
            expires_str = datetime.utcfromtimestamp(expires_at).isoformat() if expires_at else "never"
            st.markdown(f"- **{token}** — created {created} — expires {expires_str}")
            url = public_share_url(token)
            if url:
                st.markdown(f"  - Public URL: {url}")
            if st.button(f"Delete token {token}", key=f"delshare_{token}"):
                try:
                    os.remove(os.path.join(USER_DATA_DIR, fn))
                    st.success("Deleted")
                except Exception:
                    st.error("Failed to delete token")

# The rest of the page renderers (Trip Planner, Add Place, Places, Categories, Settings)
# are similar to previous versions. For brevity they are included but unchanged in behavior.
# (They reuse helpers defined above: add_place, update_place, delete_place, compute_distance_matrix, etc.)

def page_trip_planner():
    st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Trip Planner</h3></div>", unsafe_allow_html=True)
    if st.session_state.get("last_route"):
        lr = st.session_state["last_route"]
        st.markdown("**Last computed route**")
        st.write(f"- Stops: {len(lr.get('ordered_places', []))}")
        st.write(f"- Distance: {lr.get('total_km', 0):.2f} km")
        st.write(f"- Duration: {lr.get('total_min', 0):.1f} min")
        if lr.get("coords"):
            route_map = folium.Map(location=lr["coords"][len(lr["coords"])//2], zoom_start=12)
            folium.PolyLine(lr["coords"], color=APP_PRIMARY, weight=5, opacity=0.85).add_to(route_map)
            for i, p in enumerate(lr["ordered_places"]):
                folium.Marker([p['latitude'], p['longitude']], tooltip=f"{i+1}. {p['name']}").add_to(route_map)
            folium.TileLayer('CartoDB positron', attr='© CartoDB').add_to(route_map)
            st_folium(route_map, width=900, height=350)
        st.write("---")

    if not st.session_state.get("places"):
        st.info("No saved places yet. Add places first.")
        return

    place_names = [f"{p['name']} — {p.get('category','')}" for p in st.session_state["places"]]
    selected_indices = st.multiselect("Select places to include (2+)", options=list(range(len(place_names))), format_func=lambda i: place_names[i])
    if len(selected_indices) < 2:
        st.write("Select at least two places to plan a route.")
        return

    templates = st.session_state.get("trip_templates", {})
    template_names = list(templates.keys())
    col_t1, col_t2 = st.columns([2,1])
    with col_t1:
        if template_names:
            chosen_template = st.selectbox("Load template", ["(none)"] + template_names)
        else:
            chosen_template = "(none)"
    with col_t2:
        new_template_name = st.text_input("Save as template (name)", key="new_template_name")
        if st.button("Save template"):
            if new_template_name:
                templates[new_template_name] = {"indices": selected_indices, "created_at": datetime.utcnow().isoformat()}
                st.session_state["trip_templates"] = templates
                if st.session_state.get("username"):
                    path = os.path.join(USER_DATA_DIR, f"{st.session_state['username']}_templates.json")
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(templates, f, indent=2)
                st.success("Template saved")
            else:
                st.error("Provide a template name")

    if chosen_template and chosen_template != "(none)":
        templ = templates.get(chosen_template)
        if templ:
            selected_indices = templ.get("indices", selected_indices)
            st.info(f"Loaded template '{chosen_template}'")

    start_choice = st.selectbox("Start from", options=selected_indices, format_func=lambda i: place_names[i])
    mode_choice = st.selectbox("Mode", ["driving", "walking", "cycling"], index=0)
    round_trip = st.checkbox("Round trip (return to start)", value=False)
    visit_duration = st.number_input("Visit duration per stop (minutes)", min_value=0, value=0, step=5)

    if st.button("Compute optimized route"):
        subset = [st.session_state["places"][i] for i in selected_indices]
        with st.spinner("Computing pairwise distances..."):
            dist_matrix, dur_matrix = compute_distance_matrix(subset, mode=mode_choice)
        start_idx_in_subset = selected_indices.index(start_choice)
        order = nearest_neighbor_order(dist_matrix, start_index=start_idx_in_subset)
        order = two_opt_improve(order, dist_matrix)
        if round_trip:
            if order[0] != order[-1]:
                order.append(order[0])
        ordered_places = [subset[i] for i in order]
        coords, total_km, total_min = build_route_polyline_coords(order, subset, mode=mode_choice)
        total_min += visit_duration * max(0, len(ordered_places) - (1 if round_trip else 0))
        st.session_state["last_route"] = {
            "ordered_places": ordered_places,
            "coords": coords,
            "total_km": total_km,
            "total_min": total_min,
            "mode": mode_choice,
            "computed_at": datetime.utcnow().isoformat()
        }
        st.success(f"Route computed — {len(ordered_places)} stops, {total_km:.2f} km, {total_min:.1f} min (approx)")
        st.markdown("**Ordered stops**")
        for idx, p in enumerate(ordered_places, start=1):
            st.markdown(f"{idx}. **{p['name']}** — {p.get('category','')}")
            if p.get("address"):
                st.caption(p.get("address"))
            st.markdown(f"- Apple: {apple_maps_link(p['latitude'], p['longitude'])}  |  Google: {google_maps_link(p['latitude'], p['longitude'])}", unsafe_allow_html=True)
        if coords:
            route_map = folium.Map(location=coords[len(coords)//2], zoom_start=12)
            folium.PolyLine(coords, color=APP_PRIMARY, weight=5, opacity=0.85).add_to(route_map)
            for i, p in enumerate(ordered_places):
                folium.Marker([p['latitude'], p['longitude']], tooltip=f"{i+1}. {p['name']}", popup=p.get('description','')).add_to(route_map)
            folium.TileLayer('CartoDB positron', attr='© CartoDB').add_to(route_map)
            folium.LayerControl().add_to(route_map)
            st_folium(route_map, width=900, height=500)
        if coords:
            gpx_bytes = export_gpx(coords, name=f"trip_{int(time.time())}")
            st.download_button("Export route (GPX)", data=gpx_bytes, file_name="trip_route.gpx", mime="application/gpx+xml")
        df_ordered = pd.DataFrame(ordered_places)
        csv = df_ordered.to_csv(index=False).encode("utf-8")
        st.download_button("Export ordered stops (CSV)", data=csv, file_name="trip_order.csv", mime="text/csv")

def page_add_place():
    st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Add Place</h3></div>", unsafe_allow_html=True)
    st.write("Paste a map link or click on the interactive map below. You can upload photos and add tags.")
    with st.form("add_place_form"):
        name = st.text_input("Place name", "")
        map_link = st.text_input("Map link (paste here)", "")
        description = st.text_area("Short description (optional)", "")
        category = st.selectbox("Category", st.session_state["categories"] + ["Other"])
        favorite_flag = st.checkbox("Mark as favorite", value=False)
        tags_input = st.text_input("Tags (comma separated)", "")
        uploaded_files = st.file_uploader("Upload photos (optional)", accept_multiple_files=True, type=["png","jpg","jpeg"], key="upload_photos")
        submitted = st.form_submit_button("Add place from link")
        if submitted:
            lat_f, lon_f = None, None
            if map_link:
                lat_f, lon_f = parse_map_link(map_link)
            if lat_f is None or lon_f is None:
                st.error("Could not extract coordinates from the link. Try a different link or click on the map below.")
            else:
                tags = [t.strip() for t in tags_input.split(",") if t.strip()]
                photos_saved = []
                if uploaded_files and st.session_state.get("username"):
                    media_dir = user_media_dir(st.session_state["username"])
                    for up in uploaded_files:
                        fname = f"{int(time.time())}_{up.name}"
                        path = os.path.join(media_dir, fname)
                        with open(path, "wb") as f:
                            f.write(up.getbuffer())
                        photos_saved.append(fname)
                p = add_place(name or f"Place {len(st.session_state['places'])+1}", lat_f, lon_f, description, category, favorite_flag, source_link=map_link, tags=tags, photos=photos_saved)
                st.success("Place added")
                st.markdown(f"- [Open in Apple Maps]({apple_maps_link(lat_f, lon_f)})")
                st.markdown(f"- [Open in Google Maps]({google_maps_link(lat_f, lon_f)})")
                st.markdown(f"- [Open in PetalMaps]({petal_maps_link(lat_f, lon_f)})")
                st.markdown(f"- [Open in Bing]({bing_maps_link(lat_f, lon_f)})")
                st.markdown(f"- [Open in OpenStreetMap]({osm_link(lat_f, lon_f)})")

    st.markdown("**Interactive map** — click to pick coordinates.")
    if st.session_state["places"]:
        center = st.session_state["places"][-1]
        center_lat, center_lon = center.get("latitude", 0), center.get("longitude", 0)
    else:
        center_lat, center_lon = 0.3476, 32.5825

    m = folium.Map(location=[center_lat, center_lon], zoom_start=12, control_scale=True)
    folium.TileLayer('CartoDB positron', attr='© CartoDB').add_to(m)
    folium.LayerControl().add_to(m)
    map_result = st_folium(m, width=900, height=450)
    last_click = map_result.get("last_clicked")
    if last_click:
        addr = reverse_geocode(last_click["lat"], last_click["lng"])
        st.info(f"Map clicked at: {last_click['lat']:.6f}, {last_click['lng']:.6f}")
        if addr:
            st.caption(f"Address: {addr}")
        with st.form("add_from_click_form"):
            place_name = st.text_input("Name for clicked place", value=f"Place {len(st.session_state['places'])+1}", key="name_click")
            place_desc = st.text_area("Description (optional)", key="desc_click")
            place_cat = st.selectbox("Category", st.session_state["categories"] + ["Other"], key="cat_click")
            fav_flag = st.checkbox("Mark as favorite", value=False, key="fav_click")
            tags_input2 = st.text_input("Tags (comma separated)", key="tags_click")
            uploaded_files2 = st.file_uploader("Upload photos (optional)", accept_multiple_files=True, type=["png","jpg","jpeg"], key="upload_photos_click")
            add_clicked = st.form_submit_button("Add place at clicked location")
            if add_clicked:
                tags = [t.strip() for t in tags_input2.split(",") if t.strip()]
                photos_saved = []
                if uploaded_files2 and st.session_state.get("username"):
                    media_dir = user_media_dir(st.session_state["username"])
                    for up in uploaded_files2:
                        fname = f"{int(time.time())}_{up.name}"
                        path = os.path.join(media_dir, fname)
                        with open(path, "wb") as f:
                            f.write(up.getbuffer())
                        photos_saved.append(fname)
                p = add_place(place_name or f"Place {len(st.session_state['places'])+1}", last_click["lat"], last_click["lng"], place_desc, place_cat, fav_flag, source_link="", tags=tags, photos=photos_saved)
                st.success("Place added from map click")
                st.markdown(f"- [Open in Apple Maps]({apple_maps_link(p['latitude'], p['longitude'])})")

def page_places():
    st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Places</h3></div>", unsafe_allow_html=True)
    search = st.text_input("Search places by name or description", key="search_places")
    cat_filter = st.selectbox("Filter category", ["All"] + st.session_state["categories"], index=0)
    tag_filter = st.text_input("Filter by tag (single)", key="tag_filter")
    fav_only = st.checkbox("Show favorites only", value=False)
    proximity_section = st.expander("Find nearby (proximity search)")
    with proximity_section:
        lat_q = st.number_input("Latitude", value=0.0, format="%.6f", key="prox_lat")
        lon_q = st.number_input("Longitude", value=0.0, format="%.6f", key="prox_lon")
        radius_km = st.number_input("Radius (km)", min_value=0.1, value=5.0, step=0.1, key="prox_radius")
        if st.button("Find nearby"):
            nearby = []
            for p in st.session_state["places"]:
                d = haversine_km(lat_q, lon_q, p["latitude"], p["longitude"])
                if d <= radius_km:
                    nearby.append((p, d))
            if not nearby:
                st.info("No saved places within radius.")
            else:
                st.success(f"Found {len(nearby)} places within {radius_km} km")
                nearby_sorted = sorted(nearby, key=lambda x: x[1])
                for p, d in nearby_sorted:
                    st.markdown(f"**{p['name']}** — {d:.2f} km")
                    if p.get("address"):
                        st.caption(p.get("address"))

    items = st.session_state["places"]
    if search:
        items = [p for p in items if search.lower() in (p.get("name","").lower() + p.get("description","").lower())]
    if cat_filter != "All":
        items = [p for p in items if p.get("category") == cat_filter]
    if tag_filter:
        items = [p for p in items if tag_filter in p.get("tags", [])]
    if fav_only:
        items = [p for p in items if p.get("favorite")]

    if not items:
        st.info("No places match the filters.")
        return

    first = items[0]
    preview_map = folium.Map(location=[first["latitude"], first["longitude"]], zoom_start=12)
    marker_cluster = MarkerCluster().add_to(preview_map)
    for p in items:
        folium.Marker([p["latitude"], p["longitude"]], popup=f"{p['name']} ({p['category']})").add_to(marker_cluster)
    folium.TileLayer('CartoDB positron', attr='© CartoDB').add_to(preview_map)
    folium.LayerControl().add_to(preview_map)
    st.subheader("Map preview")
    st_folium(preview_map, width=900, height=400)

    st.write("---")
    for p in items:
        st.markdown(f"**{p['name']}**  —  *{p.get('category','Other')}*")
        if p.get("address"):
            st.caption(p.get("address"))
        if p.get("description"):
            st.write(p.get("description"))
        lat, lon = p.get("latitude"), p.get("longitude")
        st.write(f"📍 {lat:.6f}, {lon:.6f}")
        if p.get("photos"):
            media_dir = user_media_dir(st.session_state.get("username") or "public")
            cols = st.columns(len(p["photos"]))
            for i, fn in enumerate(p["photos"]):
                path = os.path.join(media_dir, fn)
                try:
                    cols[i].image(path, width=160)
                except Exception:
                    cols[i].write("Image not found")
        avg = average_rating(p)
        if avg:
            st.markdown(f"**Rating:** {avg:.1f} / 5 ({len(p.get('reviews',[]))} reviews)")
        else:
            st.markdown("**Rating:** —")
        st.markdown(f"[Apple Maps]({apple_maps_link(lat, lon)})  |  [Google]({google_maps_link(lat, lon)})  |  [OSM]({osm_link(lat, lon)})", unsafe_allow_html=True)
        ca, cb, cc = st.columns([1,1,1])
        with ca:
            if st.button("Edit", key=f"edit_{p['id']}"):
                with st.form(f"edit_form_{p['id']}"):
                    new_name = st.text_input("Name", value=p.get("name",""))
                    new_desc = st.text_area("Description", value=p.get("description",""))
                    new_cat = st.selectbox("Category", st.session_state["categories"] + ["Other"], index=(st.session_state["categories"] + ["Other"]).index(p.get("category","Other")))
                    new_tags = st.text_input("Tags (comma separated)", value=",".join(p.get("tags", [])))
                    new_fav = st.checkbox("Favorite", value=bool(p.get("favorite", False)))
                    save = st.form_submit_button("Save")
                    if save:
                        tags = [t.strip() for t in new_tags.split(",") if t.strip()]
                        update_place(p["id"], name=new_name, description=new_desc, category=new_cat, favorite=new_fav, tags=tags)
                        st.success("Saved")
        with cb:
            if st.button("Delete", key=f"del_{p['id']}"):
                delete_place(p["id"])
                st.success("Deleted")
        with cc:
            fav_label = "Unfavorite" if p.get("favorite") else "Mark Favorite"
            if st.button(fav_label, key=f"fav_{p['id']}"):
                update_place(p["id"], favorite=not p.get("favorite", False))
                st.success("Updated favorite status")
        with st.expander("Add review"):
            r_user = st.text_input("Your name", value=st.session_state.get("username") or "guest", key=f"rev_user_{p['id']}")
            r_rating = st.slider("Rating", 1, 5, 5, key=f"rev_rating_{p['id']}")
            r_text = st.text_area("Review text", key=f"rev_text_{p['id']}")
            if st.button("Submit review", key=f"rev_submit_{p['id']}"):
                add_review(p["id"], r_user, r_rating, r_text)
                st.success("Review added")
        if p.get("reviews"):
            st.markdown("**Reviews**")
            for rev in sorted(p.get("reviews", []), key=lambda x: x.get("ts",""), reverse=True):
                st.markdown(f"- **{rev.get('user')}** — {rev.get('rating')}/5 — {rev.get('text')}")
        st.write("---")

def page_categories():
    st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Categories</h3></div>", unsafe_allow_html=True)
    st.write("Create, rename, or delete categories. Deleting moves places to 'Other'.")
    col1, col2 = st.columns([2,1])
    with col1:
        new_cat = st.text_input("New category name", key="new_cat")
        if st.button("Add category"):
            if new_cat and new_cat not in st.session_state["categories"]:
                st.session_state["categories"].append(new_cat)
                st.success("Category added")
            else:
                st.error("Invalid or duplicate category")
    with col2:
        sel = st.selectbox("Existing categories", st.session_state["categories"], key="sel_cat")
        if st.button("Delete selected category"):
            if sel in st.session_state["categories"]:
                st.session_state["categories"].remove(sel)
                for p in st.session_state["places"]:
                    if p.get("category") == sel:
                        p["category"] = "Other"
                if st.session_state.get("username"):
                    save_user_places(st.session_state["username"], st.session_state["places"])
                st.success("Category deleted and places moved to Other")
    st.write("Current categories:")
    st.write(", ".join(st.session_state["categories"]))

def page_settings():
    st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Settings</h3></div>", unsafe_allow_html=True)
    st.write(f"Logged in as: **{st.session_state.get('username') or 'guest'}**")
    st.write(f"Auth mode: **{st.session_state.get('auth_mode') or 'unknown'}**")
    st.write("---")
    st.markdown("**Load shared token** (local instance)")
    token_in = st.text_input("Share token", key="share_token_input")
    if st.button("Load share token"):
        if token_in:
            payload = load_share_token(token_in)
            if payload is None:
                st.error("Token not found or expired.")
            elif isinstance(payload, dict) and payload.get("requires_password"):
                pw = st.text_input("Enter share password", type="password", key="share_pw")
                if st.button("Submit share password"):
                    payload2 = load_share_token(token_in, password=pw)
                    if payload2 is None:
                        st.error("Invalid token or password.")
                    elif isinstance(payload2, dict) and payload2.get("invalid_password"):
                        st.error("Invalid password.")
                    else:
                        st.success("Share loaded")
                        st.write(json.dumps(payload2, indent=2))
            elif isinstance(payload, dict) and payload.get("invalid_password"):
                st.error("Invalid password.")
            else:
                st.success("Share loaded")
                st.write(json.dumps(payload, indent=2))
    st.write("---")
    if st.button("Logout (end session)"):
        logout_user()
        st.experimental_rerun()

# -------------------------
# Utility map link generators
# -------------------------
def google_maps_link(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

def apple_maps_link(lat: float, lon: float) -> str:
    return f"https://maps.apple.com/?q={lat},{lon}"

def petal_maps_link(lat: float, lon: float) -> str:
    return f"https://map.petalmaps.com/?q={lat},{lon}"

def bing_maps_link(lat: float, lon: float) -> str:
    return f"https://www.bing.com/maps?cp={lat}~{lon}"

def osm_link(lat: float, lon: float, zoom: int = 16) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}"

# -------------------------
# App entry
# -------------------------
def run():
    token = st.session_state.get("access_token")
    username = st.session_state.get("username")
    if token and username:
        info = verify_token(token)
        if not info or info.get("username") != username:
            st.session_state["access_token"] = None
            st.session_state["username"] = None
            st.session_state["auth_mode"] = None

    if not st.session_state.get("username"):
        inject_css()
        st.markdown("<div class='logo-top'>", unsafe_allow_html=True)
        st.markdown(APP_SVG_LOGO.format(color=APP_PRIMARY), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div class='small-muted'>Sign in or create an account to continue</div>", unsafe_allow_html=True)
        ensure_demo_local_user()
        username = st.text_input("Username", key="login_user", placeholder="username")
        password = st.text_input("Password", type="password", key="login_pass", placeholder="password")
        col1, col2 = st.columns([1,1])
        with col1:
            if st.button("Login"):
                token = call_auth_login(username, password)
                if token:
                    info = verify_token(token)
                    if info and info.get("username") == username:
                        st.session_state["access_token"] = token
                        st.session_state["username"] = username
                        st.session_state["auth_mode"] = "remote"
                        st.session_state["places"] = load_user_places(username)
                        templates_path = os.path.join(USER_DATA_DIR, f"{username}_templates.json")
                        if os.path.exists(templates_path):
                            try:
                                with open(templates_path, "r", encoding="utf-8") as f:
                                    st.session_state["trip_templates"] = json.load(f)
                            except Exception:
                                st.session_state["trip_templates"] = {}
                        st.experimental_rerun()
                    else:
                        st.error("Login succeeded but token verification failed.")
                else:
                    if verify_local_user(username, password):
                        st.session_state["access_token"] = None
                        st.session_state["username"] = username
                        st.session_state["auth_mode"] = "local"
                        st.session_state["places"] = load_user_places(username)
                        templates_path = os.path.join(USER_DATA_DIR, f"{username}_templates.json")
                        if os.path.exists(templates_path):
                            try:
                                with open(templates_path, "r", encoding="utf-8") as f:
                                    st.session_state["trip_templates"] = json.load(f)
                            except Exception:
                                st.session_state["trip_templates"] = {}
                        st.experimental_rerun()
                    else:
                        st.error("Login failed. Check credentials or auth server.")
        with col2:
            if st.button("Sign up"):
                token = call_auth_signup(username, password)
                if token:
                    info = verify_token(token)
                    if info and info.get("username") == username:
                        st.session_state["access_token"] = token
                        st.session_state["username"] = username
                        st.session_state["auth_mode"] = "remote"
                        st.session_state["places"] = load_user_places(username)
                        st.experimental_rerun()
                    else:
                        st.error("Sign up succeeded but token verification failed.")
                else:
                    created = create_local_user(username, password)
                    if created:
                        st.session_state["access_token"] = None
                        st.session_state["username"] = username
                        st.session_state["auth_mode"] = "local"
                        st.session_state["places"] = []
                        save_user_places(username, st.session_state["places"])
                        st.experimental_rerun()
                    else:
                        st.error("Sign up failed (username may already exist).")
        return

    if st.session_state.get("username") and not st.session_state.get("places"):
        st.session_state["places"] = load_user_places(st.session_state["username"])
    if st.session_state.get("username") and not st.session_state.get("trip_templates"):
        templates_path = os.path.join(USER_DATA_DIR, f"{st.session_state['username']}_templates.json")
        if os.path.exists(templates_path):
            try:
                with open(templates_path, "r", encoding="utf-8") as f:
                    st.session_state["trip_templates"] = json.load(f)
            except Exception:
                st.session_state["trip_templates"] = {}

    sidebar_navigation()
    page = st.session_state.get("page", "Trip Planner")
    if page == "Trip Planner":
        page_trip_planner()
    elif page == "Dashboard":
        # simple dashboard summary
        st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Dashboard</h3></div>", unsafe_allow_html=True)
        total = len(st.session_state["places"])
        favs = sum(1 for p in st.session_state["places"] if p.get("favorite"))
        st.markdown(f"**Total places:** {total}  •  **Favorites:** {favs}")
    elif page == "Explore":
        st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Explore</h3></div>", unsafe_allow_html=True)
        city = st.text_input("City (optional)", key="explore_city")
        category = st.selectbox("Category (optional)", ["any", "restaurants", "attractions", "events", "nightlife", "shopping"], key="explore_cat")
        if st.button("Fetch Explore"):
            results = fetch_explore_from_backend(city, category)
            if not results:
                st.info("No results found or backend not available.")
            else:
                st.success(f"Found {len(results)} results")
                for r in results:
                    name = r.get("name", "Unknown")
                    desc = r.get("description", "")
                    lat = r.get("latitude")
                    lon = r.get("longitude")
                    st.markdown(f"**{name}**")
                    if desc:
                        st.write(desc)
                    if lat and lon:
                        st.write(f"📍 {lat:.6f}, {lon:.6f}")
                        if st.button(f"Add {name} to my places", key=f"add_explore_{hash(name)}"):
                            add_place(name, lat, lon, desc, category=r.get("category", "Other"), favorite=False, source_link=r.get("url", ""))
                            st.success(f"Added {name}")
    elif page == "Add Place":
        page_add_place()
    elif page == "Places":
        page_places()
    elif page == "Share":
        page_share()
    elif page == "Categories":
        page_categories()
    elif page == "Settings":
        page_settings()
    else:
        st.info("Unknown page")

if __name__ == "__main__":
    run()
