# streamlit_app.py
"""
CityScout - Single-file Streamlit app (updated)

Features:
- Centered SVG logo at the top of every page (only image asset)
- Login / Sign up via FastAPI JWT auth server (AUTH_URL env var) with local fallback
- Auto-creates a demo user (demo/demo123) in local fallback mode
- Per-user persistent places stored in USER_DATA_DIR as JSON
- Add places by map link (Google, Apple, PetalMaps, Bing, OSM short links supported)
- Click-to-add on interactive map (st_folium)
- Categories management, favorites flag, edit/delete places
- External links: maps.apple.com, Google Maps, PetalMaps, Bing, OpenStreetMap
- Interactive maps via folium + st_folium; tile layers include attribution
- OSRM routing (driving/walking/cycling) with in-memory caching
- Black theme, fixed font, no appearance controls
- CSV import/export and pairwise matrix
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
from typing import Optional, Tuple
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium

# -------------------------
# Configuration
# -------------------------
AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000")  # FastAPI auth server
AUTH_VERIFY_TIMEOUT = int(os.getenv("AUTH_VERIFY_TIMEOUT", "6"))
USER_DATA_DIR = os.getenv("USER_DATA_DIR", "./user_data")
os.makedirs(USER_DATA_DIR, exist_ok=True)

BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")  # optional explore backend
OSRM_ROUTE_TTL = int(os.getenv("OSRM_ROUTE_TTL", "3600"))

# Visual constants (fixed)
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
    # "remote" when auth server used successfully, "local" when fallback to users.json
    st.session_state["auth_mode"] = None

USERS_FILE = os.path.join(USER_DATA_DIR, "users.json")

# -------------------------
# SVG logo (single, centered)
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
# Minimal CSS (black background, centered logo)
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
    .btn-primary {{
      background: {APP_PRIMARY};
      color: white;
      padding: 8px 12px;
      border-radius: 8px;
      border: none;
      cursor: pointer;
    }}
    a.map-link {{ color: #9ad0ff; text-decoration: underline; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# -------------------------
# Per-user storage helpers
# -------------------------
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
# Local users.json helpers (fallback)
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
# Short URL resolution and map link parsing
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

# -------------------------
# External map link generators
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
# Polyline decoder (Google encoded polyline)
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

# -------------------------
# In-memory TTL cache for OSRM
# -------------------------
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
# Auth helpers (FastAPI remote + local fallback)
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

# -------------------------
# Place helpers
# -------------------------
def add_place(name: str, lat: float, lon: float, description: str = "", category: str = "Other", favorite: bool = False, source_link: str = "") -> dict:
    place = {
        "id": hashlib.sha1(f"{name}{lat}{lon}{time.time()}".encode()).hexdigest()[:12],
        "name": name,
        "latitude": float(lat),
        "longitude": float(lon),
        "description": description or "",
        "category": category or "Other",
        "favorite": bool(favorite),
        "source_link": source_link or ""
    }
    st.session_state["places"].append(place)
    if st.session_state.get("username"):
        save_user_places(st.session_state["username"], st.session_state["places"])
    return place

def update_place(place_id: str, **fields) -> Optional[dict]:
    for p in st.session_state["places"]:
        if p.get("id") == place_id:
            p.update(fields)
            if st.session_state.get("username"):
                save_user_places(st.session_state["username"], st.session_state["places"])
            return p
    return None

def delete_place(place_id: str):
    st.session_state["places"] = [p for p in st.session_state["places"] if p.get("id") != place_id]
    if st.session_state.get("username"):
        save_user_places(st.session_state["username"], st.session_state["places"])

# -------------------------
# Explore backend helper (safe)
# -------------------------
def fetch_explore_from_backend(city: str, category: str):
    try:
        resp = requests.get(f"{BASE_URL}/explore", params={"city": city, "category": category}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", []) if isinstance(data, dict) else []
        normalized = []
        for r in results:
            lat = r.get("latitude") or r.get("lat") or None
            lon = r.get("longitude") or r.get("lon") or None
            if lat is None or lon is None:
                link = r.get("url") or r.get("link") or r.get("maps_link") or r.get("map_url") or ""
                lat, lon = parse_map_link(link)
            if lat is not None and lon is not None:
                r["latitude"] = float(lat)
                r["longitude"] = float(lon)
                normalized.append(r)
        return normalized
    except Exception:
        st.error("Explore fetch failed: backend unreachable or returned unexpected data.")
        return []

# -------------------------
# UI: centered logo and login (with fallback)
# -------------------------
def top_logo():
    inject_css()
    svg = APP_SVG_LOGO.format(color=APP_PRIMARY)
    st.markdown("<div class='logo-top'>", unsafe_allow_html=True)
    st.markdown(svg, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

def show_login_page():
    inject_css()
    svg = APP_SVG_LOGO.format(color=APP_PRIMARY)
    st.markdown("<div class='logo-top'>", unsafe_allow_html=True)
    st.markdown(svg, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='small-muted'>Sign in or create an account to continue</div>", unsafe_allow_html=True)

    # Ensure demo local user exists for fallback testing
    ensure_demo_local_user()

    username = st.text_input("Username", key="login_user", placeholder="username")
    password = st.text_input("Password", type="password", key="login_pass", placeholder="password")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Login", key="btn_login"):
            # Try remote auth first
            token = call_auth_login(username, password)
            if token:
                info = verify_token(token)
                if info and info.get("username") == username:
                    st.session_state["access_token"] = token
                    st.session_state["username"] = username
                    st.session_state["auth_mode"] = "remote"
                    st.session_state["places"] = load_user_places(username)
                    st.success("Logged in (remote auth)")
                    return
                else:
                    st.error("Login succeeded but token verification failed.")
                    return
            # Remote failed -> try local fallback
            if verify_local_user(username, password):
                st.session_state["access_token"] = None
                st.session_state["username"] = username
                st.session_state["auth_mode"] = "local"
                st.session_state["places"] = load_user_places(username)
                st.success("Logged in (local fallback)")
            else:
                st.error("Login failed. Check credentials or auth server.")
    with col2:
        if st.button("Sign up", key="btn_signup"):
            # Try remote signup first
            token = call_auth_signup(username, password)
            if token:
                info = verify_token(token)
                if info and info.get("username") == username:
                    st.session_state["access_token"] = token
                    st.session_state["username"] = username
                    st.session_state["auth_mode"] = "remote"
                    st.session_state["places"] = load_user_places(username)
                    st.success("Account created and logged in (remote auth)")
                    return
                else:
                    st.error("Sign up succeeded but token verification failed.")
                    return
            # Remote signup failed -> create local user
            created = create_local_user(username, password)
            if created:
                st.session_state["access_token"] = None
                st.session_state["username"] = username
                st.session_state["auth_mode"] = "local"
                st.session_state["places"] = []
                save_user_places(username, st.session_state["places"])
                st.success("Account created and logged in (local fallback)")
            else:
                st.error("Sign up failed (username may already exist).")

# -------------------------
# Main application UI
# -------------------------
def main_app():
    inject_css()
    top_logo()

    # Top controls
    cols = st.columns([3, 1])
    with cols[0]:
        st.markdown(f"<h2 style='margin:0;color:#e6e6e6'>CityScout</h2>", unsafe_allow_html=True)
    with cols[1]:
        if st.button("Logout"):
            logout_user()
            st.experimental_rerun()

    tabs = st.tabs(["Dashboard", "Explore", "Add Place", "Places", "Categories", "Settings"])

    # Dashboard
    with tabs[0]:
        st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Dashboard</h3></div>", unsafe_allow_html=True)
        total = len(st.session_state["places"])
        favs = sum(1 for p in st.session_state["places"] if p.get("favorite"))
        st.markdown(f"**Total places:** {total}  •  **Favorites:** {favs}")
        st.write("---")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Add sample place"):
                add_place("Sample Place", 0.3476, 32.5825, "Sample", category="Attractions", favorite=False)
                st.success("Sample place added")
        with c2:
            df = pd.DataFrame(st.session_state["places"])
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Export places (CSV)", data=csv, file_name="places.csv", mime="text/csv")
        with c3:
            if st.button("Clear all places"):
                st.session_state["places"] = []
                if st.session_state.get("username"):
                    save_user_places(st.session_state["username"], st.session_state["places"])
                st.success("All places cleared")

    # Explore
    with tabs[1]:
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
                    st.write("---")

    # Add Place
    with tabs[2]:
        st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Add Place</h3></div>", unsafe_allow_html=True)
        st.write("Paste a map link (Google, Apple, PetalMaps, Bing, OpenStreetMap) or click on the interactive map below.")
        with st.form("add_place_form"):
            name = st.text_input("Place name", "")
            map_link = st.text_input("Map link (paste here)", "")
            description = st.text_area("Short description (optional)", "")
            category = st.selectbox("Category", st.session_state["categories"] + ["Other"])
            favorite_flag = st.checkbox("Mark as favorite", value=False)
            submitted = st.form_submit_button("Add place from link")
            if submitted:
                lat_f, lon_f = None, None
                if map_link:
                    lat_f, lon_f = parse_map_link(map_link)
                if lat_f is None or lon_f is None:
                    st.error("Could not extract coordinates from the link. Try a different link or click on the map below.")
                else:
                    p = add_place(name or f"Place {len(st.session_state['places'])+1}", lat_f, lon_f, description, category, favorite_flag, source_link=map_link)
                    st.success("Place added")
                    st.markdown(f"- [Open in Apple Maps]({apple_maps_link(lat_f, lon_f)})")
                    st.markdown(f"- [Open in Google Maps]({google_maps_link(lat_f, lon_f)})")
                    st.markdown(f"- [Open in PetalMaps]({petal_maps_link(lat_f, lon_f)})")
                    st.markdown(f"- [Open in Bing Maps]({bing_maps_link(lat_f, lon_f)})")
                    st.markdown(f"- [Open in OpenStreetMap]({osm_link(lat_f, lon_f)})")

        st.markdown("**Interactive map** — click to pick coordinates.")
        if st.session_state["places"]:
            center = st.session_state["places"][-1]
            center_lat, center_lon = center.get("latitude", 0), center.get("longitude", 0)
        else:
            center_lat, center_lon = 0.3476, 32.5825  # Kampala default

        m = folium.Map(location=[center_lat, center_lon], zoom_start=12, control_scale=True)
        folium.TileLayer('CartoDB positron', attr='© CartoDB').add_to(m)
        folium.TileLayer('Stamen Terrain', attr='Map tiles by Stamen Design, CC BY 3.0 — Map data © OpenStreetMap contributors').add_to(m)
        folium.TileLayer(
            tiles='https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
            name='Dark',
            attr='© CartoDB',
            overlay=False,
            control=True
        ).add_to(m)
        folium.LayerControl().add_to(m)

        map_result = st_folium(m, width=900, height=450)
        last_click = map_result.get("last_clicked")
        if last_click:
            st.info(f"Map clicked at: {last_click['lat']:.6f}, {last_click['lng']:.6f}")
            with st.form("add_from_click_form"):
                place_name = st.text_input("Name for clicked place", value=f"Place {len(st.session_state['places'])+1}", key="name_click")
                place_desc = st.text_area("Description (optional)", key="desc_click")
                place_cat = st.selectbox("Category", st.session_state["categories"] + ["Other"], key="cat_click")
                fav_flag = st.checkbox("Mark as favorite", value=False, key="fav_click")
                add_clicked = st.form_submit_button("Add place at clicked location")
                if add_clicked:
                    p = add_place(place_name or f"Place {len(st.session_state['places'])+1}", last_click["lat"], last_click["lng"], place_desc, place_cat, fav_flag, source_link="")
                    st.success("Place added from map click")
                    st.markdown(f"- [Open in Apple Maps]({apple_maps_link(p['latitude'], p['longitude'])})")

    # Places (list, edit, delete, map preview)
    with tabs[3]:
        st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Places</h3></div>", unsafe_allow_html=True)
        search = st.text_input("Search places by name or description", key="search_places")
        cat_filter = st.selectbox("Filter category", ["All"] + st.session_state["categories"], index=0)
        fav_only = st.checkbox("Show favorites only", value=False)

        items = st.session_state["places"]
        if search:
            items = [p for p in items if search.lower() in (p.get("name","").lower() + p.get("description","").lower())]
        if cat_filter != "All":
            items = [p for p in items if p.get("category") == cat_filter]
        if fav_only:
            items = [p for p in items if p.get("favorite")]

        if not items:
            st.info("No places match the filters.")
        else:
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
                if p.get("description"):
                    st.write(p.get("description"))
                lat, lon = p.get("latitude"), p.get("longitude")
                st.write(f"📍 {lat:.6f}, {lon:.6f}")
                st.markdown(f"[Apple Maps]({apple_maps_link(lat, lon)})  |  [Google]({google_maps_link(lat, lon)})  |  [PetalMaps]({petal_maps_link(lat, lon)})  |  [Bing]({bing_maps_link(lat, lon)})  |  [OSM]({osm_link(lat, lon)})", unsafe_allow_html=True)
                ca, cb, cc = st.columns([1,1,1])
                with ca:
                    if st.button("Edit", key=f"edit_{p['id']}"):
                        with st.form(f"edit_form_{p['id']}"):
                            new_name = st.text_input("Name", value=p.get("name",""))
                            new_desc = st.text_area("Description", value=p.get("description",""))
                            new_cat = st.selectbox("Category", st.session_state["categories"] + ["Other"], index=(st.session_state["categories"] + ["Other"]).index(p.get("category","Other")))
                            new_fav = st.checkbox("Favorite", value=bool(p.get("favorite", False)))
                            save = st.form_submit_button("Save")
                            if save:
                                update_place(p["id"], name=new_name, description=new_desc, category=new_cat, favorite=new_fav)
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
                st.write("---")

    # Categories
    with tabs[4]:
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

    # Settings
    with tabs[5]:
        st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Settings</h3></div>", unsafe_allow_html=True)
        st.write(f"Logged in as: **{st.session_state.get('username') or 'guest'}**")
        st.write(f"Auth mode: **{st.session_state.get('auth_mode') or 'unknown'}**")
        if st.button("Logout (end session)"):
            logout_user()
            st.experimental_rerun()

# -------------------------
# App entry
# -------------------------
def run():
    # If token exists, verify remote token; if invalid, clear
    token = st.session_state.get("access_token")
    username = st.session_state.get("username")
    if token and username:
        info = verify_token(token)
        if not info or info.get("username") != username:
            # remote token invalid -> clear
            st.session_state["access_token"] = None
            st.session_state["username"] = None
            st.session_state["auth_mode"] = None

    # If no username, show login
    if not st.session_state.get("username"):
        show_login_page()
        return

    # Ensure user's places loaded
    if st.session_state.get("username") and not st.session_state.get("places"):
        st.session_state["places"] = load_user_places(st.session_state["username"])

    main_app()

if __name__ == "__main__":
    run()