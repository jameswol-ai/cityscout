# streamlit_app.py
"""
CityScout - Streamlit app (OpenStreetMap + OSRM)
Features:
- Login / Sign up (file-backed, hashed passwords)
- Single SVG logo on login screen
- Add places by name + latitude + longitude
- Modern / Classic UI toggle
- Explore tab (calls backend /explore if available)
- Favorites tab with OSRM routing (driving/walking/cycling), distance/duration, pairwise matrix
- Folium maps with clustering, heatmap, and route polylines
- Lightweight caching (in-memory + optional file cache)
"""

import os
import json
import time
import hashlib
import streamlit as st
import requests
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import pandas as pd
import math

# -------------------------
# Configuration
# -------------------------
BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")  # optional backend for /explore
USERS_FILE = os.getenv("USERS_FILE", "users.json")
USE_FILE_CACHE = os.getenv("USE_FILE_CACHE", "false").lower() == "true"
CACHE_DIR = os.getenv("CACHE_DIR", "./.cache")
OSRM_ROUTE_TTL = int(os.getenv("OSRM_ROUTE_TTL", "3600"))  # seconds
PAIRWISE_TTL = int(os.getenv("PAIRWISE_TTL", "3600"))  # seconds

st.set_page_config(page_title="CityScout", page_icon="🌆", layout="wide")

# -------------------------
# Ensure cache dir
# -------------------------
if USE_FILE_CACHE and not os.path.exists(CACHE_DIR):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except Exception:
        USE_FILE_CACHE = False

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
# Session state defaults
# -------------------------
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = None
if "favorites" not in st.session_state:
    st.session_state["favorites"] = []
if "ui_theme" not in st.session_state:
    st.session_state["ui_theme"] = "modern"  # or "classic"

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
# File cache helpers
# -------------------------
def _file_cache_path(key):
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.json")

def file_cache_get(key):
    if not USE_FILE_CACHE:
        return None
    path = _file_cache_path(key)
    try:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if int(time.time()) > payload.get("expires_at", 0):
            try:
                os.remove(path)
            except Exception:
                pass
            return None
        return payload.get("value")
    except Exception:
        return None

def file_cache_set(key, value, ttl):
    if not USE_FILE_CACHE:
        return
    path = _file_cache_path(key)
    payload = {"value": value, "expires_at": int(time.time()) + ttl}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        pass

def cache_get(key):
    v = mem_cache.get(key)
    if v is not None:
        return v
    v = file_cache_get(key)
    if v is not None:
        mem_cache.set(key, v, OSRM_ROUTE_TTL)
        return v
    return None

def cache_set(key, value, ttl):
    mem_cache.set(key, value, ttl)
    file_cache_set(key, value, ttl)

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
    cached = cache_get(key)
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
            cache_set(key, payload, OSRM_ROUTE_TTL)
            return coords, distance_km, duration_min
    except Exception:
        pass
    return [], None, None

# -------------------------
# Pairwise matrix caching
# -------------------------
def _pairwise_cache_key(favorites, mode):
    coords = []
    for f in favorites:
        if "latitude" in f and "longitude" in f:
            coords.append(f"{f['latitude']:.6f},{f['longitude']:.6f}")
        else:
            coords.append("na")
    key_raw = f"pairwise:{mode}:" + "|".join(coords)
    return hashlib.sha256(key_raw.encode("utf-8")).hexdigest()

def compute_pairwise_matrix(favorites, mode="driving"):
    cache_key = _pairwise_cache_key(favorites, mode)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    matrix = []
    n = len(favorites)
    for i in range(n):
        a = favorites[i]
        if "latitude" not in a or "longitude" not in a:
            continue
        for j in range(n):
            if i == j:
                continue
            b = favorites[j]
            if "latitude" not in b or "longitude" not in b:
                continue
            coords, dist, dur = get_osrm_route(a["latitude"], a["longitude"], b["latitude"], b["longitude"], mode=mode)
            matrix.append({
                "origin_idx": i,
                "dest_idx": j,
                "origin_name": a.get("name", f"Fav {i}"),
                "dest_name": b.get("name", f"Fav {j}"),
                "distance_km": dist,
                "duration_min": dur
            })
    cache_set(cache_key, matrix, PAIRWISE_TTL)
    return matrix

# -------------------------
# SVG logo (single logo used at login)
# -------------------------
APP_SVG_LOGO = """
<svg width="160" height="160" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect rx="16" width="100" height="100" fill="#0b6efd"/>
  <g transform="translate(18,18)" fill="#fff">
    <path d="M12 2c-5.5 0-10 4.5-10 10 0 7.5 10 18 10 18s10-10.5 10-18c0-5.5-4.5-10-10-10z"/>
    <circle cx="12" cy="12" r="3"/>
  </g>
</svg>
"""

# -------------------------
# UI theme CSS
# -------------------------
MODERN_CSS = """
<style>
/* Modern card style */
.css-1d391kg {padding: 0.5rem;} /* small tweak for Streamlit container */
.card {
  background: linear-gradient(180deg, #ffffff 0%, #f7fbff 100%);
  border-radius: 12px;
  padding: 14px;
  box-shadow: 0 6px 18px rgba(11,110,253,0.08);
  margin-bottom: 12px;
}
.header-row {display:flex; align-items:center; gap:12px;}
.logo {width:64px; height:64px;}
.small-muted {color:#6b7280; font-size:0.9rem;}
.btn-primary {background:#0b6efd; color:white; padding:8px 12px; border-radius:8px; border:none;}
</style>
"""

CLASSIC_CSS = """
<style>
/* Classic minimal style */
.card {
  background: #fff;
  border-radius: 6px;
  padding: 10px;
  border: 1px solid #e6e6e6;
  margin-bottom: 10px;
}
.header-row {display:flex; align-items:center; gap:10px;}
.logo {width:56px; height:56px;}
.small-muted {color:#333; font-size:0.9rem;}
</style>
"""

# -------------------------
# Authentication UI
# -------------------------
def show_login_signup():
    st.markdown("<div style='display:flex;align-items:center;gap:16px'>", unsafe_allow_html=True)
    st.markdown(f"<div class='logo'>{APP_SVG_LOGO}</div>", unsafe_allow_html=True)
    st.markdown("<div><h2 style='margin:0'>CityScout</h2><div class='small-muted'>Open maps, routes, favorites</div></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    st.write("---")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Login")
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login"):
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
        if st.button("Sign up"):
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
# Top bar: theme toggle and logout
# -------------------------
def top_bar():
    cols = st.columns([1, 3, 1])
    with cols[0]:
        # small logo
        st.markdown(APP_SVG_LOGO, unsafe_allow_html=True)
    with cols[1]:
        st.markdown("<h3 style='margin:0'>CityScout</h3>", unsafe_allow_html=True)
    with cols[2]:
        if st.session_state["logged_in"]:
            if st.button("Logout"):
                st.session_state["logged_in"] = False
                st.session_state["username"] = None
                st.experimental_rerun()

# -------------------------
# Main app UI
# -------------------------
def main_app():
    # inject CSS based on theme
    if st.session_state["ui_theme"] == "modern":
        st.markdown(MODERN_CSS, unsafe_allow_html=True)
    else:
        st.markdown(CLASSIC_CSS, unsafe_allow_html=True)

    top_bar()

    # Theme toggle
    theme_col1, theme_col2 = st.columns([1, 3])
    with theme_col1:
        theme_choice = st.radio("UI style", ["modern", "classic"], index=0 if st.session_state["ui_theme"] == "modern" else 1, horizontal=True, key="ui_style_radio")
        st.session_state["ui_theme"] = theme_choice

    # Tabs
    tab1, tab2, tab3 = st.tabs(["🔍 Explore", "➕ Add Place", "⭐ Favorites"])

    # Explore tab
    with tab1:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<h4 style='margin:0'>Explore</h4>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.sidebar.header("Search Options")
        city = st.sidebar.text_input("Enter a city name (optional)", "")
        category = st.sidebar.selectbox("Category (optional)", ["any", "restaurants", "attractions", "events", "nightlife", "shopping"])
        min_rating = st.sidebar.slider("Minimum rating (if backend provides)", 0.0, 5.0, 0.0, 0.5)
        show_heatmap = st.sidebar.checkbox("Show heatmap", value=False)

        if st.button("Fetch Explore (backend)"):
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
                st.write(f"Found {len(results)} results")
                # display and allow add to favorites
                for item in results:
                    st.markdown(f"**{item.get('name','Unknown')}**")
                    st.write(item.get("description", ""))
                    if st.button(f"Add to Favorites: {item.get('name','Unknown')}", key=f"explore_add_{item.get('name','')}_{hash(item.get('name',''))}"):
                        item.setdefault("tag", "None")
                        st.session_state["favorites"].append(item)
                        st.success("Added to favorites")

    # Add Place tab
    with tab2:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<h4 style='margin:0'>Add a Place</h4>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        with st.form("add_place_form"):
            name = st.text_input("Place name", "")
            lat = st.text_input("Latitude (decimal)", "")
            lon = st.text_input("Longitude (decimal)", "")
            description = st.text_area("Short description (optional)", "")
            tag = st.selectbox("Tag", ["None", "Food", "Nightlife", "Shopping", "Attractions", "Custom"])
            if tag == "Custom":
                tag = st.text_input("Custom tag name", key="custom_tag_input")
            submitted = st.form_submit_button("Add place")
            if submitted:
                try:
                    lat_f = float(lat)
                    lon_f = float(lon)
                    place = {
                        "name": name or f"Place {len(st.session_state['favorites'])+1}",
                        "latitude": lat_f,
                        "longitude": lon_f,
                        "description": description,
                        "tag": tag or "None"
                    }
                    st.session_state["favorites"].append(place)
                    st.success("Place added to favorites")
                except Exception:
                    st.error("Invalid latitude or longitude. Use decimal degrees (e.g., 0.3476, 32.5825).")

    # Favorites tab
    with tab3:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown("<h4 style='margin:0'>Your Favorites</h4>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if not st.session_state["favorites"]:
            st.info("No favorites yet. Add places from Explore or Add Place.")
        else:
            # Search and tag filter
            search_query = st.text_input("Search favorites by name", key="fav_search")
            tags = sorted({fav.get("tag", "None") for fav in st.session_state["favorites"]})
            tag_options = ["All"] + [t for t in tags if t]
            tag_filter = st.selectbox("Filter by tag", tag_options, index=0, key="fav_tag_filter")

            favorites_to_show = st.session_state["favorites"]
            if search_query:
                favorites_to_show = [f for f in favorites_to_show if search_query.lower() in f.get("name","").lower()]
            if tag_filter != "All":
                favorites_to_show = [f for f in favorites_to_show if f.get("tag","None") == tag_filter]

            # List favorites with small controls
            for idx, fav in enumerate(favorites_to_show):
                st.markdown(f"**{fav.get('name','Unknown')}**")
                if fav.get("description"):
                    st.write(fav.get("description"))
                if fav.get("latitude") and fav.get("longitude"):
                    st.write(f"📍 {fav.get('latitude'):.6f}, {fav.get('longitude'):.6f}")
                # Tagging UI
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

                # OSRM directions selector
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
                                folium.TileLayer('CartoDB positron').add_to(route_map)
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
                for fav in coords:
                    folium.Marker(
                        [fav["latitude"], fav["longitude"]],
                        popup=f"{fav.get('name','')}<br>{fav.get('address','')}<br>🏷️ {fav.get('tag','None')}",
                        tooltip=fav.get('name','')
                    ).add_to(marker_cluster)
                st.subheader("Favorites Map")
                st_folium(fav_map, width=700, height=500)

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
                    matrix = compute_pairwise_matrix(st.session_state["favorites"], mode=mode_for_matrix)
                if not matrix:
                    st.info("No pairwise data available")
                else:
                    rows = []
                    for r in matrix:
                        dist = f"{r['distance_km']:.2f} km" if r['distance_km'] is not None else "N/A"
                        if r['duration_min'] is not None:
                            if r['duration_min'] >= 60:
                                hrs = int(r['duration_min'] // 60)
                                mins = int(r['duration_min'] % 60)
                                dur = f"{hrs}h {mins}m"
                            else:
                                dur = f"{r['duration_min']:.1f} min"
                        else:
                            dur = "N/A"
                        rows.append({"Origin": r["origin_name"], "Destination": r["dest_name"], "Distance": dist, "Duration": dur})
                    df_matrix = pd.DataFrame(rows)
                    st.dataframe(df_matrix, use_container_width=True)

# -------------------------
# App entry
# -------------------------
def run():
    # If not logged in, show login/signup
    if not st.session_state["logged_in"]:
        # show login/signup with logo
        st.markdown("<div style='max-width:900px;margin:auto'>", unsafe_allow_html=True)
        show_login_signup()
        st.markdown("</div>", unsafe_allow_html=True)
        return
    # else show main app
    main_app()

if __name__ == "__main__":
    run()
