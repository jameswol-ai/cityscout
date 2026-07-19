# streamlit_app.py
"""
CityScout - Streamlit app (OpenStreetMap + OSRM)
Features:
- Login / Sign up (file-backed, hashed passwords)
- Add places by name + latitude/longitude OR paste a map link OR click on interactive map
- Modern / Classic UI toggle
- Single SVG logo on login screen
- Animated buttons via CSS
- Interactive Folium maps (st_folium) with clustering, heatmap, OSRM routing (driving/walking/cycling)
- Lightweight in-memory cache for OSRM calls
"""

import os
import json
import time
import hashlib
import re
import streamlit as st
import requests
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import pandas as pd

# -------------------------
# Configuration
# -------------------------
BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")  # optional backend for /explore
USERS_FILE = os.getenv("USERS_FILE", "users.json")
OSRM_ROUTE_TTL = 3600  # seconds

st.set_page_config(page_title="CityScout", page_icon="🌆", layout="wide")

# -------------------------
# Session state defaults
# -------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = None
if "favorites" not in st.session_state:
    st.session_state["favorites"] = []
if "ui_theme" not in st.session_state:
    st.session_state["ui_theme"] = "modern"

# -------------------------
# Simple user store (file-backed)
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
# Polyline decoder (self-contained)
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
# Map link parsing (Google Maps and OpenStreetMap)
# -------------------------
def parse_map_link(url: str):
    """
    Extract (lat, lon) from common Google Maps and OpenStreetMap link formats.
    Returns (lat, lon) or (None, None) if not found.
    """
    if not url or not isinstance(url, str):
        return None, None
    url = url.strip()
    # Google Maps @lat,lon,zoom pattern
    m = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Google Maps q=lat,lon
    m = re.search(r'[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    # OpenStreetMap mlat/mlon
    m = re.search(r'[?&]mlat=(-?\d+\.\d+)&mlon=(-?\d+\.\d+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    # OSM #map=zoom/lat/lon
    m = re.search(r'#map=\d+\/(-?\d+\.\d+)\/(-?\d+\.\d+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    # fallback: look for two floats separated by comma anywhere
    m = re.search(r'(-?\d+\.\d+)[, ]+(-?\d+\.\d+)', url)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None

# -------------------------
# SVG logo (single)
# -------------------------
APP_SVG_LOGO = """
<svg width="120" height="120" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect rx="16" width="100" height="100" fill="#0b6efd"/>
  <g transform="translate(18,18)" fill="#fff">
    <path d="M12 2c-5.5 0-10 4.5-10 10 0 7.5 10 18 10 18s10-10.5 10-18c0-5.5-4.5-10-10-10z"/>
    <circle cx="12" cy="12" r="3"/>
  </g>
</svg>
"""

# -------------------------
# CSS: modern/classic + animated buttons
# -------------------------
MODERN_CSS = """
<style>
.card { background: linear-gradient(180deg,#ffffff 0%,#f7fbff 100%); border-radius:12px; padding:14px; box-shadow:0 6px 18px rgba(11,110,253,0.08); margin-bottom:12px; }
.header-row {display:flex; align-items:center; gap:12px;}
.logo {width:64px; height:64px;}
.small-muted {color:#6b7280; font-size:0.9rem;}
.btn-animated {
  background:#0b6efd; color:white; padding:10px 14px; border-radius:10px; border:none; cursor:pointer;
  box-shadow: 0 6px 18px rgba(11,110,253,0.12);
  transform: translateY(0);
  animation: float 3s ease-in-out infinite;
}
@keyframes float {
  0% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
  100% { transform: translateY(0); }
}
.small-ghost { background:transparent; border:1px solid #0b6efd; color:#0b6efd; padding:8px 12px; border-radius:8px; cursor:pointer; }
</style>
"""

CLASSIC_CSS = """
<style>
.card { background:#fff; border-radius:6px; padding:10px; border:1px solid #e6e6e6; margin-bottom:10px; }
.header-row {display:flex; align-items:center; gap:10px;}
.logo {width:56px; height:56px;}
.btn-animated { background:#0b6efd; color:white; padding:8px 12px; border-radius:6px; border:none; cursor:pointer; animation: pulse 2.5s infinite; }
@keyframes pulse { 0% { box-shadow: 0 0 0 rgba(11,110,253,0.2);} 70% { box-shadow: 0 0 20px rgba(11,110,253,0);} 100% { box-shadow: 0 0 0 rgba(11,110,253,0);} }
</style>
"""

# -------------------------
# Authentication UI (file-backed)
# -------------------------
def show_login_signup():
    st.markdown("<div style='display:flex;align-items:center;gap:16px'>", unsafe_allow_html=True)
    st.markdown(f"<div class='logo'>{APP_SVG_LOGO}</div>", unsafe_allow_html=True)
    st.markdown("<div><h2 style='margin:0'>CityScout</h2><div class='small-muted'>Open maps, routes, favorites</div></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.write("---")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Login")
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login", key="btn_login"):
            users = load_users()
            if username in users and users[username]["password_hash"] == _hash_password(password):
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
                st.success("Logged in")
                st.experimental_rerun()
            else:
                st.error("Invalid username or password")
    with col2:
        st.subheader("Sign up")
        new_user = st.text_input("Choose username", key="signup_user")
        new_pass = st.text_input("Choose password", type="password", key="signup_pass")
        confirm_pass = st.text_input("Confirm password", type="password", key="signup_confirm")
        if st.button("Sign up", key="btn_signup"):
            if not new_user or not new_pass:
                st.error("Provide username and password")
            elif new_pass != confirm_pass:
                st.error("Passwords do not match")
            else:
                users = load_users()
                if new_user in users:
                    st.error("Username already exists")
                else:
                    users[new_user] = {"password_hash": _hash_password(new_pass)}
                    save_users(users)
                    st.success("Account created. You can now log in.")

# -------------------------
# Top bar and main app
# -------------------------
def top_bar():
    cols = st.columns([1, 3, 1])
    with cols[0]:
        st.markdown(APP_SVG_LOGO, unsafe_allow_html=True)
    with cols[1]:
        st.markdown("<h3 style='margin:0'>CityScout</h3>", unsafe_allow_html=True)
    with cols[2]:
        if st.session_state["logged_in"]:
            if st.button("Logout", key="btn_logout"):
                st.session_state["logged_in"] = False
                st.session_state["username"] = None
                st.experimental_rerun()

def main_app():
    # inject CSS
    if st.session_state["ui_theme"] == "modern":
        st.markdown(MODERN_CSS, unsafe_allow_html=True)
    else:
        st.markdown(CLASSIC_CSS, unsafe_allow_html=True)

    top_bar()
    theme_col1, theme_col2 = st.columns([1, 3])
    with theme_col1:
        theme_choice = st.radio("UI style", ["modern", "classic"], index=0 if st.session_state["ui_theme"] == "modern" else 1, horizontal=True, key="ui_style_radio")
        st.session_state["ui_theme"] = theme_choice

    tab1, tab2, tab3 = st.tabs(["🔍 Explore", "➕ Add Place", "⭐ Favorites"])

    # Explore tab (basic backend call optional)
    with tab1:
        st.markdown("<div class='card'><h4 style='margin:0'>Explore</h4></div>", unsafe_allow_html=True)
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
                        item.setdefault("tag", "None")
                        st.session_state["favorites"].append(item)
                        st.success("Added to favorites")

    # Add Place tab
    with tab2:
        st.markdown("<div class='card'><h4 style='margin:0'>Add a Place</h4></div>", unsafe_allow_html=True)
        st.write("You can add a place by **name + coordinates**, **paste a map link**, or **click on the interactive map** below.")
        with st.form("add_place_form"):
            name = st.text_input("Place name", "")
            lat = st.text_input("Latitude (decimal) — leave blank if using link or map click", "")
            lon = st.text_input("Longitude (decimal) — leave blank if using link or map click", "")
            map_link = st.text_input("Or paste a Google Maps / OpenStreetMap link (optional)", "")
            description = st.text_area("Short description (optional)", "")
            tag = st.selectbox("Tag", ["None", "Food", "Nightlife", "Shopping", "Attractions", "Custom"])
            if tag == "Custom":
                tag = st.text_input("Custom tag name", key="custom_tag_input")
            submitted = st.form_submit_button("Add place", help="Add the place to your favorites")
            # animated button style via markdown (visual only)
            if submitted:
                lat_f = None
                lon_f = None
                # try parse link first
                if map_link:
                    lat_f, lon_f = parse_map_link(map_link)
                # then try direct inputs
                if (lat and lon) and (lat_f is None or lon_f is None):
                    try:
                        lat_f = float(lat)
                        lon_f = float(lon)
                    except Exception:
                        lat_f, lon_f = None, None
                if lat_f is None or lon_f is None:
                    st.error("Could not determine coordinates. Provide valid lat/lon or a map link or click on the map below.")
                else:
                    place = {
                        "name": name or f"Place {len(st.session_state['favorites'])+1}",
                        "latitude": float(lat_f),
                        "longitude": float(lon_f),
                        "description": description,
                        "tag": tag or "None"
                    }
                    st.session_state["favorites"].append(place)
                    st.success("Place added to favorites")

        st.markdown("**Interactive map** — click to pick coordinates (click once to set).")
        # show an interactive map centered on last favorite or default
        if st.session_state["favorites"]:
            center = st.session_state["favorites"][-1]
            center_lat, center_lon = center.get("latitude", 0), center.get("longitude", 0)
        else:
            center_lat, center_lon = 0.3476, 32.5825  # Kampala default
        m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
        folium.TileLayer('OpenStreetMap').add_to(m)
        folium.TileLayer('Stamen Terrain').add_to(m)
        folium.LayerControl().add_to(m)
        map_result = st_folium(m, width=700, height=450)
        # st_folium returns last_clicked
        last_click = map_result.get("last_clicked")
        if last_click:
            st.info(f"Map clicked at: {last_click['lat']:.6f}, {last_click['lng']:.6f}")
            if st.button("Use clicked coordinates to add a new place", key="use_click_add"):
                name_click = st.text_input("Name for clicked place", value=f"Place {len(st.session_state['favorites'])+1}", key="name_click")
                place = {
                    "name": name_click or f"Place {len(st.session_state['favorites'])+1}",
                    "latitude": float(last_click["lat"]),
                    "longitude": float(last_click["lng"]),
                    "description": "",
                    "tag": "None"
                }
                st.session_state["favorites"].append(place)
                st.success("Place added from map click")

    # Favorites tab
    with tab3:
        st.markdown("<div class='card'><h4 style='margin:0'>Your Favorites</h4></div>", unsafe_allow_html=True)
        if not st.session_state["favorites"]:
            st.info("No favorites yet. Add places from Add Place or Explore.")
        else:
            search_query = st.text_input("Search favorites by name", key="fav_search")
            tags = sorted({fav.get("tag", "None") for fav in st.session_state["favorites"]})
            tag_options = ["All"] + [t for t in tags if t]
            tag_filter = st.selectbox("Filter by tag", tag_options, index=0, key="fav_tag_filter")

            favorites_to_show = st.session_state["favorites"]
            if search_query:
                favorites_to_show = [f for f in favorites_to_show if search_query.lower() in f.get("name","").lower()]
            if tag_filter != "All":
                favorites_to_show = [f for f in favorites_to_show if f.get("tag","None") == tag_filter]

            for idx, fav in enumerate(favorites_to_show):
                st.markdown(f"**{fav.get('name','Unknown')}**")
                if fav.get("description"):
                    st.write(fav.get("description"))
                if "latitude" in fav and "longitude" in fav:
                    st.write(f"📍 {fav['latitude']:.6f}, {fav['longitude']:.6f}")
                # Tagging
                current_tag = fav.get("tag", "None")
                tag_choices = ["None", "Food", "Nightlife", "Shopping", "Attractions", "Custom"]
                if current_tag not in tag_choices:
                    tag_choices.append(current_tag)
                new_tag = st.selectbox(f"Tag for {fav.get('name','')}", tag_choices, index=tag_choices.index(current_tag), key=f"tag_{idx}")
                if new_tag == "Custom":
                    custom_tag = st.text_input(f"Custom tag for {fav.get('name','')}", key=f"custom_tag_{idx}")
                    if custom_tag:
                        fav["tag"] = custom_tag
                else:
                    fav["tag"] = new_tag

                # OSRM directions
                if "latitude" in fav and "longitude" in fav and len(st.session_state["favorites"]) > 1:
                    other_favs = [f for f in st.session_state["favorites"] if f is not fav and "latitude" in f and "longitude" in f]
                    if other_favs:
                        dest_names = [o.get("name","Unknown") for o in other_favs]
                        dest_choice = st.selectbox(f"Get directions from {fav.get('name','')}", ["Select destination"] + dest_names, key=f"osrm_dest_{idx}")
                        if dest_choice and dest_choice != "Select destination":
                            chosen = other_favs[dest_names.index(dest_choice)]
                            mode = st.radio("Mode", ["driving", "walking", "cycling"], key=f"osrm_mode_{idx}")
                            coords, distance_km, duration_min = get_osrm_route(
                                fav["latitude"], fav["longitude"], chosen["latitude"], chosen["longitude"], mode=mode
                            )
                            if coords:
                                mid_lat, mid_lon = coords[len(coords)//2]
                                route_map = folium.Map(location=[mid_lat, mid_lon], zoom_start=13)
                                folium.PolyLine(coords, color="blue", weight=5, opacity=0.7).add_to(route_map)
                                folium.Marker([fav["latitude"], fav["longitude"]], tooltip="Origin", icon=folium.Icon(color="green")).add_to(route_map)
                                folium.Marker([chosen["latitude"], chosen["longitude"]], tooltip="Destination", icon=folium.Icon(color="red")).add_to(route_map)
                                folium.TileLayer('OpenStreetMap').add_to(route_map)
                                folium.TileLayer('Stamen Terrain').add_to(route_map)
                                folium.LayerControl().add_to(route_map)
                                st.write(f"**Mode:** {mode.capitalize()}")
                                if distance_km is not None:
                                    st.write(f"📏 Distance: {distance_km:.2f} km")
                                if duration_min is not None:
                                    if duration_min >= 60:
                                        hours = int(duration_min // 60)
                                        mins = int(duration_min % 60)
                                        st.write(f"⏱️ Estimated time: {hours}h {mins}m")
                                    else:
                                        st.write(f"⏱️ Estimated time: {duration_min:.1f} minutes")
                                st_folium(route_map, width=700, height=400)
                            else:
                                st.info("Could not fetch route from OSRM.")

                st.write("---")

            # Favorites map (all)
            coords = [f for f in st.session_state["favorites"] if "latitude" in f and "longitude" in f]
            if coords:
                first = coords[0]
                fav_map = folium.Map(location=[first["latitude"], first["longitude"]], zoom_start=12)
                marker_cluster = MarkerCluster().add_to(fav_map)
                heat_points = []
                for fav in coords:
                    folium.Marker(
                        [fav["latitude"], fav["longitude"]],
                        popup=f"{fav.get('name','')}<br>🏷️ {fav.get('tag','None')}",
                        tooltip=fav.get('name','')
                    ).add_to(marker_cluster)
                    heat_points.append([fav["latitude"], fav["longitude"]])
                if st.checkbox("Show heatmap of favorites", value=False):
                    HeatMap(heat_points, radius=15).add_to(fav_map)
                folium.TileLayer('OpenStreetMap').add_to(fav_map)
                folium.TileLayer('Stamen Terrain').add_to(fav_map)
                folium.LayerControl().add_to(fav_map)
                st.subheader("Favorites Map (interactive)")
                map_out = st_folium(fav_map, width=900, height=500)
                # show last clicked on favorites map
                last = map_out.get("last_clicked")
                if last:
                    st.info(f"Map clicked at: {last['lat']:.6f}, {last['lng']:.6f}")

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
                        rec.setdefault("tag", rec.get("tag", "None"))
                    st.session_state["favorites"].extend(imported_records)
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
        # show login/signup
        st.markdown("<div style='max-width:900px;margin:auto'>", unsafe_allow_html=True)
        show_login_signup()
        st.markdown("</div>", unsafe_allow_html=True)
        return
    main_app()

if __name__ == "__main__":
    run()
