# streamlit_app.py
"""
CityScout — Enhanced
- Resolves short map links (maps.app.goo.gl etc.)
- Parses Google, OSM, PetalMaps, Apple Maps, Bing Maps links
- Categories for places; favorites-only view
- External links for OSM, Google, PetalMaps, Apple Maps, Bing
- Edit / Delete places
- Black background, fixed font, no appearance controls
- Interactive Folium maps (st_folium)
- OSRM routing with in-memory caching
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
BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
USERS_FILE = os.getenv("USERS_FILE", "users.json")
OSRM_ROUTE_TTL = 3600  # seconds

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
if "favorites" not in st.session_state:
    st.session_state["favorites"] = []
if "categories" not in st.session_state:
    # default categories
    st.session_state["categories"] = ["Food", "Nightlife", "Shopping", "Attractions", "Parks", "Transit", "Other"]
if "dark_mode" not in st.session_state:
    st.session_state["dark_mode"] = True

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
        # Use HEAD first to follow redirects without downloading body
        resp = requests.head(url, allow_redirects=True, timeout=timeout)
        final = resp.url
        # If HEAD returned same or no location, try GET (some shorteners require GET)
        if not final or final == url:
            resp = requests.get(url, allow_redirects=True, timeout=timeout)
            final = resp.url
        return final
    except Exception:
        # fallback: return original
        return url

# -------------------------
# Map link parsing (Google, OSM, PetalMaps, Apple, Bing)
# -------------------------
def parse_map_link(url: str):
    """
    Resolve short links and extract (lat, lon) from common map link formats.
    Returns (lat, lon) or (None, None).
    """
    if not url or not isinstance(url, str):
        return None, None
    url = url.strip()
    # Resolve short links (maps.app.goo.gl, goo.gl, bit.ly, etc.)
    resolved = resolve_short_url(url)
    s = resolved

    # Patterns
    # Google Maps @lat,lon
    m = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Google Maps q=lat,lon or query=lat,lon
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
    # PetalMaps /place/lat,lon or @lat,lon
    m = re.search(r'/place/(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Apple Maps q=lat,lon or ll=lat,lon
    m = re.search(r'[?&](?:q|ll)=(-?\d+\.\d+),(-?\d+\.\d+)', s)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Bing maps cp=lat~lon
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
    # OpenStreetMap link with mlat/mlon and #map
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}"

def petal_maps_link(lat, lon):
    # Petal Maps often supports query param q=lat,lon or /place/lat,lon
    return f"https://map.petalmaps.com/?q={lat},{lon}"

def apple_maps_link(lat, lon):
    return f"https://maps.apple.com/?q={lat},{lon}"

def bing_maps_link(lat, lon):
    return f"https://www.bing.com/maps?cp={lat}~{lon}"

# -------------------------
# SVG logo
# -------------------------
APP_SVG_LOGO = """
<svg width="160" height="160" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
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
    .logo-center {{ display:flex; align-items:center; justify-content:center; padding:40px 0; }}
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
# Authentication UI (logo-only)
# -------------------------
def show_logo_only_login():
    inject_css()
    svg = APP_SVG_LOGO.format(color=APP_PRIMARY)
    st.markdown("<div class='logo-center'>", unsafe_allow_html=True)
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
# Place helpers: add/edit/delete
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
    st.session_state["favorites"].append(place)
    return place

def update_place(place_id, **fields):
    for p in st.session_state["favorites"]:
        if p.get("id") == place_id:
            p.update(fields)
            return p
    return None

def delete_place(place_id):
    st.session_state["favorites"] = [p for p in st.session_state["favorites"] if p.get("id") != place_id]

# -------------------------
# Top bar and main app
# -------------------------
def top_bar():
    cols = st.columns([1, 3, 1])
    with cols[0]:
        svg = APP_SVG_LOGO.format(color=APP_PRIMARY)
        st.markdown(svg, unsafe_allow_html=True)
    with cols[1]:
        st.markdown(f"<h3 style='margin:0;color:#e6e6e6'>CityScout</h3>", unsafe_allow_html=True)
    with cols[2]:
        if st.session_state["logged_in"]:
            if st.button("Logout", key="btn_logout"):
                st.session_state["logged_in"] = False
                st.session_state["username"] = None
                # safe rerun
                st.experimental_rerun()

def main_app():
    inject_css()
    top_bar()

    # Sidebar: categories and favorites-only toggle
    st.sidebar.header("Filters")
    cat_options = ["All"] + st.session_state["categories"]
    selected_cat = st.sidebar.selectbox("Category", cat_options, index=0)
    favorites_only = st.sidebar.checkbox("Favorites only", value=False)
    show_fullscreen_favs = st.sidebar.button("Open Favorites Map (full)")

    tab1, tab2, tab3 = st.tabs(["🔍 Explore", "➕ Add Place (link or map click)", "⭐ Favorites"])

    # Explore tab (optional backend)
    with tab1:
        st.markdown("<div class='card'><h4 style='margin:0;color:#e6e6e6'>Explore</h4></div>", unsafe_allow_html=True)
        st.sidebar.header("Search Options")
        city = st.sidebar.text_input("City (optional)", "")
        category = st.sidebar.selectbox("Category (optional)", ["any", "restaurants", "attractions", "events", "nightlife", "shopping"])
        if st.button("Fetch Explore (backend)", key="btn_fetch_explore"):
            try:
                resp = requests.get(f"{BASE_URL}/explore", params={"city": city, "category": category}, timeout=10)
                resp.raise_for_status()
                results = resp.json().get("results", [])
            except Exception as e:
                st.error(f"Failed to fetch explore results: {e}")
                results = []
            if not results:
                st.info("No results from backend or backend not running.")
            else:
                for item in results:
                    st.markdown(f"**{item.get('name','Unknown')}**")
                    st.write(item.get("description", ""))
                    if st.button("Add to Favorites", key=f"explore_add_{hash(item.get('name',''))}"):
                        item.setdefault("category", "Other")
                        item.setdefault("favorite", True)
                        st.session_state["favorites"].append(item)
                        st.success("Added to favorites")

    # Add Place tab
    with tab2:
        st.markdown("<div class='card'><h4 style='margin:0;color:#e6e6e6'>Add a Place</h4></div>", unsafe_allow_html=True)
        st.write("Provide a **map link** (Google Maps, OpenStreetMap, PetalMaps, Apple Maps, Bing Maps) or click on the interactive map below to pick a location.")
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
                    place = add_place(name or f"Place {len(st.session_state['favorites'])+1}", lat_f, lon_f, description, category, favorite_flag, source_link=map_link)
                    st.success("Place added to favorites")
                    st.write("External links:")
                    st.markdown(f"- [OpenStreetMap]({osm_link(lat_f, lon_f)})")
                    st.markdown(f"- [Google Maps]({google_maps_link(lat_f, lon_f)})")
                    st.markdown(f"- [PetalMaps]({petal_maps_link(lat_f, lon_f)})")
                    st.markdown(f"- [Apple Maps]({apple_maps_link(lat_f, lon_f)})")
                    st.markdown(f"- [Bing Maps]({bing_maps_link(lat_f, lon_f)})")

        st.markdown("**Interactive map** — click to pick coordinates (last click shown below).")
        if st.session_state["favorites"]:
            center = st.session_state["favorites"][-1]
            center_lat, center_lon = center.get("latitude", 0), center.get("longitude", 0)
        else:
            center_lat, center_lon = 0.3476, 32.5825  # Kampala default

        m = folium.Map(location=[center_lat, center_lon], zoom_start=12, control_scale=True)
        folium.TileLayer('OpenStreetMap', attr='© OpenStreetMap contributors').add_to(m)
        folium.TileLayer('Stamen Terrain', attr='Map tiles by Stamen Design, CC BY 3.0 — Map data © OpenStreetMap contributors').add_to(m)
        folium.TileLayer('CartoDB positron', attr='© CartoDB').add_to(m)
        folium.TileLayer(
            tiles='https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
            name='Dark',
            attr='© CartoDB',
            overlay=False,
            control=True
        ).add_to(m)
        folium.LayerControl().add_to(m)

        map_result = st_folium(m, width=800, height=450)
        last_click = map_result.get("last_clicked")
        if last_click:
            st.info(f"Map clicked at: {last_click['lat']:.6f}, {last_click['lng']:.6f}")
            with st.form("add_from_click_form"):
                place_name = st.text_input("Name for clicked place", value=f"Place {len(st.session_state['favorites'])+1}", key="name_click")
                place_desc = st.text_area("Description (optional)", key="desc_click")
                place_cat = st.selectbox("Category", st.session_state["categories"] + ["Other"], key="cat_click")
                fav_flag = st.checkbox("Mark as favorite", value=False, key="fav_click")
                add_clicked = st.form_submit_button("Add place at clicked location")
                if add_clicked:
                    place = add_place(place_name or f"Place {len(st.session_state['favorites'])+1}", last_click["lat"], last_click["lng"], place_desc, place_cat, fav_flag, source_link="")
                    st.success("Place added from map click")
                    st.markdown(f"- [OpenStreetMap]({osm_link(place['latitude'], place['longitude'])})")
                    st.markdown(f"- [Google Maps]({google_maps_link(place['latitude'], place['longitude'])})")
                    st.markdown(f"- [PetalMaps]({petal_maps_link(place['latitude'], place['longitude'])})")
                    st.markdown(f"- [Apple Maps]({apple_maps_link(place['latitude'], place['longitude'])})")
                    st.markdown(f"- [Bing Maps]({bing_maps_link(place['latitude'], place['longitude'])})")

    # Favorites tab
    with tab3:
        st.markdown("<div class='card'><h4 style='margin:0;color:#e6e6e6'>Your Favorites</h4></div>", unsafe_allow_html=True)
        # Build filtered list
        items = st.session_state["favorites"]
        if selected_cat != "All":
            items = [p for p in items if p.get("category") == selected_cat]
        if favorites_only:
            items = [p for p in items if p.get("favorite")]

        if not items:
            st.info("No places match the current filters.")
        else:
            # List with edit/delete and external links
            for p in items:
                st.markdown(f"**{p.get('name','Unknown')}**  —  *{p.get('category','None')}*")
                if p.get("description"):
                    st.write(p.get("description"))
                lat, lon = p.get("latitude"), p.get("longitude")
                if lat is not None and lon is not None:
                    st.write(f"📍 {lat:.6f}, {lon:.6f}")
                    # external links
                    st.markdown(f"[OpenStreetMap]({osm_link(lat, lon)})  |  [Google]({google_maps_link(lat, lon)})  |  [PetalMaps]({petal_maps_link(lat, lon)})  |  [Apple]({apple_maps_link(lat, lon)})  |  [Bing]({bing_maps_link(lat, lon)})", unsafe_allow_html=True)
                # Edit / Delete / Favorite toggle
                col_a, col_b, col_c = st.columns([1,1,1])
                with col_a:
                    if st.button("Edit", key=f"edit_{p['id']}"):
                        # show edit form in modal-like area
                        with st.form(f"edit_form_{p['id']}"):
                            new_name = st.text_input("Name", value=p.get("name",""))
                            new_desc = st.text_area("Description", value=p.get("description",""))
                            new_cat = st.selectbox("Category", st.session_state["categories"] + ["Other"], index=(st.session_state["categories"] + ["Other"]).index(p.get("category","Other")))
                            new_fav = st.checkbox("Favorite", value=bool(p.get("favorite", False)))
                            save = st.form_submit_button("Save changes")
                            if save:
                                update_place(p["id"], name=new_name, description=new_desc, category=new_cat, favorite=new_fav)
                                st.success("Saved")
                with col_b:
                    if st.button("Delete", key=f"del_{p['id']}"):
                        delete_place(p["id"])
                        st.success("Deleted")
                with col_c:
                    fav_label = "Unfavorite" if p.get("favorite") else "Mark Favorite"
                    if st.button(fav_label, key=f"fav_{p['id']}"):
                        update_place(p["id"], favorite=not p.get("favorite", False))
                        st.success("Updated favorite status")
                st.write("---")

            # Favorites-only full map
            if show_fullscreen_favs:
                coords = [f for f in items if "latitude" in f and "longitude" in f]
                if coords:
                    first = coords[0]
                    fav_map = folium.Map(location=[first["latitude"], first["longitude"]], zoom_start=12)
                    marker_cluster = MarkerCluster().add_to(fav_map)
                    for fav in coords:
                        folium.Marker(
                            [fav["latitude"], fav["longitude"]],
                            popup=f"{fav.get('name','')}<br>🏷️ {fav.get('category','None')}",
                            tooltip=fav.get('name','')
                        ).add_to(marker_cluster)
                    folium.TileLayer('OpenStreetMap', attr='© OpenStreetMap contributors').add_to(fav_map)
                    folium.TileLayer('Stamen Terrain', attr='Map tiles by Stamen Design, CC BY 3.0 — Map data © OpenStreetMap contributors').add_to(fav_map)
                    folium.TileLayer('CartoDB positron', attr='© CartoDB').add_to(fav_map)
                    folium.TileLayer(
                        tiles='https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
                        name='Dark',
                        attr='© CartoDB',
                        overlay=False,
                        control=True
                    ).add_to(fav_map)
                    folium.LayerControl().add_to(fav_map)
                    st.subheader("Favorites Map (full)")
                    st_folium(fav_map, width=1200, height=800)

            # Export / Import / Clear
            df = pd.DataFrame(st.session_state["favorites"])
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Export favorites (CSV)", data=csv, file_name="cityscout_favorites.csv", mime="text/csv")
            uploaded = st.file_uploader("Import favorites CSV", type=["csv"], key="import_csv")
            if uploaded is not None:
                try:
                    imported_df = pd.read_csv(uploaded)
                    imported_records = imported_df.to_dict(orient="records")
                    for rec in imported_records:
                        rec.setdefault("category", rec.get("category", "Other"))
                        rec.setdefault("favorite", rec.get("favorite", False))
                        st.session_state["favorites"].append(rec)
                    st.success("Imported favorites")
                except Exception as e:
                    st.error(f"Import failed: {e}")

            if st.button("Clear all favorites"):
                st.session_state["favorites"] = []
                st.success("Favorites cleared")

            # Pairwise matrix
            st.subheader("Pairwise distances & times")
            mode_for_matrix = st.selectbox("Mode for matrix", ["driving", "walking", "cycling"], index=0, key="matrix_mode")
            if st.button("Compute pairwise matrix"):
                with st.spinner("Computing pairwise matrix..."):
                    matrix = []
                    n = len(st.session_state["favorites"])
                    for i in range(n):
                        a = st.session_state["favorites"][i]
                        if "latitude" not in a or "longitude" not in a:
                            continue
                        for j in range(n):
                            if i == j:
                                continue
                            b = st.session_state["favorites"][j]
                            if "latitude" not in b or "longitude" not in b:
                                continue
                            _, dist, dur = get_osrm_route(a["latitude"], a["longitude"], b["latitude"], b["longitude"], mode=mode_for_matrix)
                            matrix.append({
                                "Origin": a.get("name", f"Fav {i}"),
                                "Destination": b.get("name", f"Fav {j}"),
                                "Distance": f"{dist:.2f} km" if dist is not None else "N/A",
                                "Duration": (f"{int(dur//60)}h {int(dur%60)}m" if dur and dur>=60 else (f"{dur:.1f} min" if dur else "N/A"))
                            })
                    if not matrix:
                        st.info("No pairwise data available")
                    else:
                        df_matrix = pd.DataFrame(matrix)
                        st.dataframe(df_matrix, use_container_width=True)

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
