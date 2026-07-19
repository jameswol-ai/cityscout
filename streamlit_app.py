# streamlit_app.py
"""
CityScout - Updated
- Fixes fetch/explore flow
- Logo centered at top
- Categories management (create, assign, filter)
- More tabs/panels (Dashboard, Explore, Add Place, Favorites, Settings)
- Only one image (SVG logo) used; all other images removed
- Places provide external links for Apple Maps, Google, PetalMaps, Bing, OpenStreetMap
- Map display uses CartoDB / Stamen tiles (legal attributions included)
- For "open in Apple Maps" the app provides maps.apple.com links (cannot embed Apple tiles)
- Robust parsing for short links (maps.app.goo.gl etc.)
- Black theme, fixed font, no appearance controls
- OSRM routing (driving/walking/cycling) with in-memory caching
- Edit / delete places, mark favorites, categories per place
"""

import os
import re
import json
import time
import hashlib
import urllib.parse
import streamlit as st
import requests
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import pandas as pd

# -------------------------
# Configuration
# -------------------------
BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")  # backend /explore
USERS_FILE = os.getenv("USERS_FILE", "users.json")
OSRM_ROUTE_TTL = 3600  # seconds

# Visual constants (fixed)
APP_BG = "#000000"
APP_PRIMARY = "#0b6efd"
APP_FONT = "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial"

st.set_page_config(page_title="CityScout", page_icon="🌆", layout="wide")

# -------------------------
# Session defaults
# -------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = None
if "places" not in st.session_state:
    st.session_state["places"] = []  # list of place dicts
if "categories" not in st.session_state:
    st.session_state["categories"] = ["Food", "Nightlife", "Shopping", "Attractions", "Parks", "Transit", "Other"]

# -------------------------
# Utilities: users
# -------------------------
def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_users(users):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
    except Exception:
        pass

# -------------------------
# In-memory TTL cache
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

# -------------------------
# Polyline decoder
# -------------------------
def decode_polyline(polyline_str):
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
# OSRM helper with caching
# -------------------------
def _osrm_cache_key(lat1, lon1, lat2, lon2, mode):
    return f"osrm:{mode}:{lat1:.6f},{lon1:.6f}:{lat2:.6f},{lon2:.6f}"

def get_osrm_route(lat1, lon1, lat2, lon2, mode="driving"):
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
# Resolve short URLs (follow redirects)
# -------------------------
def resolve_short_url(url: str, timeout=8):
    try:
        resp = requests.head(url, allow_redirects=True, timeout=timeout)
        final = resp.url
        if not final or final == url:
            resp = requests.get(url, allow_redirects=True, timeout=timeout)
            final = resp.url
        return final
    except Exception:
        return url

# -------------------------
# Map link parsing (Google, OSM, PetalMaps, Apple, Bing)
# -------------------------
def parse_map_link(url: str):
    if not url or not isinstance(url, str):
        return None, None
    url = url.strip()
    resolved = resolve_short_url(url)
    s = resolved

    # Google Maps @lat,lon
    m = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Google q=lat,lon or query
    m = re.search(r'[?&](?:q|query)=(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    # OSM mlat/mlon
    m = re.search(r'[?&]mlat=(-?\d+\.\d+)&mlon=(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    # OSM #map=zoom/lat/lon
    m = re.search(r'#map=\d+\/(-?\d+\.\d+)\/(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    # PetalMaps /place/lat,lon
    m = re.search(r'/place/(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Apple Maps q=lat,lon or ll=lat,lon
    m = re.search(r'[?&](?:q|ll)=(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Bing cp=lat~lon
    m = re.search(r'[?&]cp=(-?\d+\.\d+)~(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Generic fallback: first two floats separated by comma
    m = re.search(r'(-?\d+\.\d+)[, ]+(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None

# -------------------------
# External map link generators
# -------------------------
def google_maps_link(lat, lon):
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

def osm_link(lat, lon, zoom=16):
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}"

def petal_maps_link(lat, lon):
    return f"https://map.petalmaps.com/?q={lat},{lon}"

def apple_maps_link(lat, lon):
    # maps.apple.com link
    return f"https://maps.apple.com/?q={lat},{lon}"

def bing_maps_link(lat, lon):
    return f"https://www.bing.com/maps?cp={lat}~{lon}"

# -------------------------
# SVG logo (single)
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
# Minimal CSS (black background)
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
    .logo-top {{ display:flex; align-items:center; justify-content:center; padding:12px 0 6px 0; }}
    .small-muted {{ color: #9ca3af; font-size:0.95rem; }}
    .btn-animated {{
      background: {APP_PRIMARY};
      color: white;
      padding: 10px 14px;
      border-radius: 10px;
      border: none;
      cursor: pointer;
      box-shadow: 0 8px 24px rgba(11,110,253,0.12);
    }}
    a.map-link {{ color: #9ad0ff; text-decoration: underline; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# -------------------------
# Authentication UI (logo centered top)
# -------------------------
def show_logo_only_login():
    inject_css()
    svg = APP_SVG_LOGO.format(color=APP_PRIMARY)
    st.markdown("<div class='logo-top'>", unsafe_allow_html=True)
    st.markdown(svg, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div style='text-align:center; margin-bottom:8px;'><div class='small-muted'>Sign in to continue</div></div>", unsafe_allow_html=True)
    username = st.text_input("Username", key="login_user", placeholder="username")
    password = st.text_input("Password", type="password", key="login_pass", placeholder="password")
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("Login", key="btn_login"):
            users = load_users()
            if username in users and users[username]["password_hash"] == _hash_password(password):
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
            else:
                st.error("Invalid username or password")
    with col2:
        if st.button("Sign up", key="btn_signup"):
            if not username or not password:
                st.error("Provide username and password")
            else:
                users = load_users()
                if username in users:
                    st.error("Username exists")
                else:
                    users[username] = {"password_hash": _hash_password(password)}
                    save_users(users)
                    st.success("Account created. Log in now.")

# -------------------------
# Place helpers
# -------------------------
def add_place(name, lat, lon, description="", category="Other", favorite=False, source_link=None):
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
    return place

def update_place(place_id, **fields):
    for p in st.session_state["places"]:
        if p.get("id") == place_id:
            p.update(fields)
            return p
    return None

def delete_place(place_id):
    st.session_state["places"] = [p for p in st.session_state["places"] if p.get("id") != place_id]

# -------------------------
# Fetch explore (fixed)
# -------------------------
def fetch_explore_from_backend(city: str, category: str):
    """
    Calls backend /explore and returns list of results.
    Handles network errors gracefully.
    """
    try:
        resp = requests.get(f"{BASE_URL}/explore", params={"city": city, "category": category}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        # normalize: ensure lat/lon present
        normalized = []
        for r in results:
            if "latitude" in r and "longitude" in r:
                normalized.append(r)
            else:
                # try to parse a link field if present
                link = r.get("url") or r.get("link") or r.get("maps_link") or ""
                lat, lon = parse_map_link(link)
                if lat is not None and lon is not None:
                    r["latitude"] = lat
                    r["longitude"] = lon
                    normalized.append(r)
        return normalized
    except Exception as e:
        # return empty and log to console
        st.error("Explore fetch failed (backend unreachable or returned error).")
        return []

# -------------------------
# Top bar and main app
# -------------------------
def top_logo():
    svg = APP_SVG_LOGO.format(color=APP_PRIMARY)
    st.markdown("<div class='logo-top'>", unsafe_allow_html=True)
    st.markdown(svg, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

def main_app():
    inject_css()
    top_logo()

    # Main layout: tabs and panels
    tabs = st.tabs(["Dashboard", "Explore", "Add Place", "Favorites", "Categories", "Settings"])

    # Dashboard: summary and quick actions
    with tabs[0]:
        st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Dashboard</h3></div>", unsafe_allow_html=True)
        total = len(st.session_state["places"])
        favs = sum(1 for p in st.session_state["places"] if p.get("favorite"))
        st.markdown(f"**Total places:** {total}  •  **Favorites:** {favs}")
        st.write("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Add sample place (center)"):
                # add a sample place at Kampala center
                add_place("Sample Place", 0.3476, 32.5825, "Sample", category="Attractions", favorite=False)
                st.success("Sample place added")
        with col2:
            if st.button("Open Favorites Map (full)"):
                st.session_state["_open_full_favs"] = True
        with col3:
            if st.button("Clear all places"):
                st.session_state["places"] = []
                st.success("All places cleared")

    # Explore tab
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
                        if st.button(f"Add {name} to places", key=f"add_explore_{hash(name)}"):
                            add_place(name, lat, lon, desc, category=r.get("category","Other"), favorite=False, source_link=r.get("url",""))
                            st.success(f"Added {name}")
                    st.write("---")

    # Add Place tab
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
        # center map
        if st.session_state["places"]:
            center = st.session_state["places"][-1]
            center_lat, center_lon = center.get("latitude", 0), center.get("longitude", 0)
        else:
            center_lat, center_lon = 0.3476, 32.5825
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

    # Favorites tab
    with tabs[3]:
        st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Places & Favorites</h3></div>", unsafe_allow_html=True)
        # Filters
        colf1, colf2 = st.columns([2,1])
        with colf1:
            search = st.text_input("Search places by name or description", key="search_places")
        with colf2:
            cat_filter = st.selectbox("Filter category", ["All"] + st.session_state["categories"], index=0)
        fav_only = st.checkbox("Show favorites only", value=False)

        # Build list
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
            # Map preview and list
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
                # external links (Apple first)
                st.markdown(f"[Open in Apple Maps]({apple_maps_link(lat, lon)})  |  [Google]({google_maps_link(lat, lon)})  |  [PetalMaps]({petal_maps_link(lat, lon)})  |  [Bing]({bing_maps_link(lat, lon)})  |  [OSM]({osm_link(lat, lon)})", unsafe_allow_html=True)
                # actions
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

    # Categories tab: manage categories
    with tabs[4]:
        st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Categories</h3></div>", unsafe_allow_html=True)
        st.write("Create, rename, or delete categories. Deleting a category moves places to 'Other'.")
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
                    # move places to Other
                    for p in st.session_state["places"]:
                        if p.get("category") == sel:
                            p["category"] = "Other"
                    st.success("Category deleted and places moved to Other")

        st.write("Current categories:")
        st.write(", ".join(st.session_state["categories"]))

    # Settings tab: minimal (logout)
    with tabs[5]:
        st.markdown("<div class='card'><h3 style='margin:0;color:#e6e6e6'>Settings</h3></div>", unsafe_allow_html=True)
        st.write(f"Logged in as: **{st.session_state.get('username') or 'guest'}**")
        if st.button("Logout (end session)"):
            st.session_state["logged_in"] = False
            st.session_state["username"] = None
            st.experimental_rerun()

# -------------------------
# App entry
# -------------------------
def run():
    if not st.session_state["logged_in"]:
        show_logo_only_login()
        return
    main_app()

if __name__ == "__main__":
    run()
