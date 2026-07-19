# streamlit_app.py
import os
import time
import json
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
BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
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
# Simple in-memory TTL cache
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
# Simple file cache (optional)
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

# -------------------------
# Cache helpers
# -------------------------
def cache_get(key):
    # check memory first
    v = mem_cache.get(key)
    if v is not None:
        return v
    # then file cache
    v = file_cache_get(key)
    if v is not None:
        # populate memory for faster subsequent reads
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
    """
    Fetch route from OSRM public API for driving, walking, or cycling.
    Uses caching to reduce repeated calls.
    Returns (coords_list, distance_km, duration_min).
    """
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
# Pairwise matrix with caching
# -------------------------
def _pairwise_cache_key(favorites, mode):
    # build a stable key from favorite coordinates and mode
    coords = []
    for f in favorites:
        if "latitude" in f and "longitude" in f:
            coords.append(f"{f['latitude']:.6f},{f['longitude']:.6f}")
        else:
            coords.append("na")
    key_raw = f"pairwise:{mode}:" + "|".join(coords)
    return hashlib.sha256(key_raw.encode("utf-8")).hexdigest()

def compute_pairwise_matrix(favorites, mode="driving"):
    """
    Compute pairwise distances and durations between favorites using OSRM.
    Uses caching for the whole matrix.
    """
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
# UI (unchanged behavior)
# -------------------------
if "favorites" not in st.session_state:
    st.session_state["favorites"] = []

st.title("🌆 CityScout")
st.markdown("Explore cities, save favorites, and plot OSRM routes (driving, walking, cycling). Caching is enabled.")

tab1, tab2 = st.tabs(["🔍 Explore", "⭐ Favorites"])

# Explore tab (same as before)
with tab1:
    st.sidebar.header("Search Options")
    city = st.sidebar.text_input("Enter a city name", "Kampala")
    category = st.sidebar.selectbox("Choose category", ["restaurants", "attractions", "events", "nightlife", "shopping"])
    min_rating = st.sidebar.slider("Minimum rating", 0.0, 5.0, 0.0, 0.5)
    price_range = st.sidebar.selectbox("Price range", ["Any", "$", "$$", "$$$", "$$$$"])
    show_heatmap = st.sidebar.checkbox("Show heatmap of results", value=False)

    if st.sidebar.button("Explore"):
        try:
            resp = requests.get(f"{BASE_URL}/explore", params={"city": city, "category": category}, timeout=10)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as e:
            st.error(f"Failed to fetch explore results: {e}")
            results = []

        filtered = [
            item for item in results
            if item.get("rating", 0) >= min_rating and (price_range == "Any" or item.get("price") == price_range)
        ]

        st.subheader(f"Results for {city} - {category.capitalize()}")

        if not filtered:
            st.info("No results match your filters.")
        else:
            for item in filtered:
                st.markdown(f"**{item.get('name','Unknown')}**")
                st.write(item.get("description", "No description available"))
                if "rating" in item:
                    st.write(f"⭐ Rating: {item['rating']}")
                if "price" in item:
                    st.write(f"💲 Price: {item['price']}")
                if "address" in item:
                    st.write(f"📍 {item['address']}")

                add_key = f"addfav_{item.get('id', item.get('name'))}"
                if st.button(f"Add to Favorites: {item.get('name','Unknown')}", key=add_key):
                    item.setdefault("tag", "None")
                    st.session_state["favorites"].append(item)
                    st.success(f"Added {item.get('name','Unknown')} to Favorites")

                st.write("---")

            # Folium map
            first = filtered[0]
            lat, lon = first.get("latitude", 0), first.get("longitude", 0)
            m = folium.Map(location=[lat, lon], zoom_start=13)
            marker_cluster = MarkerCluster().add_to(m)
            heatmap_points = []

            for item in filtered:
                if "latitude" in item and "longitude" in item:
                    folium.Marker(
                        [item["latitude"], item["longitude"]],
                        popup=f"{item.get('name','')}<br>{item.get('address','')}",
                        tooltip=item.get("name","")
                    ).add_to(marker_cluster)
                    heatmap_points.append([item["latitude"], item["longitude"]])

            if show_heatmap and heatmap_points:
                HeatMap(heatmap_points, radius=15).add_to(m)

            folium.TileLayer('OpenStreetMap').add_to(m)
            folium.TileLayer('Stamen Terrain').add_to(m)
            folium.TileLayer('CartoDB positron').add_to(m)
            folium.LayerControl().add_to(m)

            st_folium(m, width=700, height=500)

# Favorites tab (same as before, using cached get_osrm_route and compute_pairwise_matrix)
with tab2:
    st.subheader("⭐ Your Favorites")

    # CSV import
    st.subheader("📤 Import Favorites from CSV")
    uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"], key="import_csv")
    if uploaded_file is not None:
        try:
            imported_df = pd.read_csv(uploaded_file)
            imported_records = imported_df.to_dict(orient="records")
            for rec in imported_records:
                rec.setdefault("tag", rec.get("tag", "None"))
            st.session_state["favorites"].extend(imported_records)
            st.success("Favorites imported successfully!")
        except Exception as e:
            st.error(f"Failed to import CSV: {e}")

    if not st.session_state["favorites"]:
        st.info("No favorites saved yet.")
    else:
        search_query = st.text_input("🔎 Search favorites by name", key="fav_search")
        tags = sorted({fav.get("tag", "None") for fav in st.session_state["favorites"]})
        tag_options = ["All"] + [t for t in tags if t]
        tag_filter = st.selectbox("🏷️ Filter by tag", tag_options, index=0, key="fav_tag_filter")

        favorites_to_show = st.session_state["favorites"]
        if search_query:
            favorites_to_show = [fav for fav in favorites_to_show if search_query.lower() in fav.get("name", "").lower()]
        if tag_filter != "All":
            favorites_to_show = [fav for fav in favorites_to_show if fav.get("tag", "None") == tag_filter]

        if not favorites_to_show:
            st.warning("No favorites match your search or tag filter.")
        else:
            for idx, fav in enumerate(favorites_to_show):
                st.markdown(f"**{fav.get('name','Unknown')}**")
                if fav.get("description"):
                    st.write(fav.get("description"))
                if fav.get("rating"):
                    st.write(f"⭐ Rating: {fav.get('rating')}")
                if fav.get("address"):
                    st.write(f"📍 {fav.get('address')}")

                # Tagging UI
                current_tag = fav.get("tag", "None")
                tag_choices = ["None", "Food", "Nightlife", "Shopping", "Attractions", "Custom"]
                if current_tag not in tag_choices:
                    tag_choices.append(current_tag)
                new_tag = st.selectbox(
                    f"Assign a tag to {fav.get('name','Unknown')}",
                    tag_choices,
                    index=tag_choices.index(current_tag),
                    key=f"tag_{idx}"
                )
                if new_tag == "Custom":
                    custom_tag = st.text_input(f"Enter custom tag for {fav.get('name','Unknown')}", key=f"custom_tag_{idx}")
                    if custom_tag:
                        fav["tag"] = custom_tag
                else:
                    fav["tag"] = new_tag

                st.write(f"🏷️ Current Tag: {fav.get('tag','None')}")

                # OSRM directions
                if "latitude" in fav and "longitude" in fav and len(st.session_state["favorites"]) > 1:
                    other_favs = [f for f in st.session_state["favorites"] if f is not fav and "latitude" in f and "longitude" in f]
                    if other_favs:
                        dest_names = [o.get("name","Unknown") for o in other_favs]
                        dest_choice = st.selectbox(
                            f"Get OSRM directions from {fav.get('name','Unknown')} to:",
                            ["Select destination"] + dest_names,
                            key=f"osrm_dir_{idx}"
                        )
                        if dest_choice and dest_choice != "Select destination":
                            chosen = other_favs[dest_names.index(dest_choice)]
                            mode = st.radio("Travel mode", ["driving", "walking", "cycling"], key=f"osrm_mode_{idx}")
                            coords, distance_km, duration_min = get_osrm_route(
                                fav["latitude"], fav["longitude"],
                                chosen["latitude"], chosen["longitude"],
                                mode=mode
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

                                st.subheader("🛣️ OSRM Route")
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
                                st.info(f"Could not fetch {mode} route from OSRM.")

                st.write("---")

            # Export favorites to CSV
            df = pd.DataFrame(st.session_state["favorites"])
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Export Favorites to CSV", data=csv, file_name="cityscout_favorites.csv", mime="text/csv")

            # Clear favorites
            if st.button("🗑️ Clear Favorites"):
                st.session_state["favorites"] = []
                st.success("Favorites cleared successfully!")

            # Favorites Folium map (show all favorites with coordinates)
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
                st.subheader("🗺️ Favorites Map")
                st_folium(fav_map, width=700, height=500)

            # Pairwise summary table
            st.subheader("📊 Pairwise distances and times")
            mode_for_matrix = st.selectbox("Choose travel mode for pairwise matrix", ["driving", "walking", "cycling"], index=0, key="matrix_mode")
            if st.button("Compute pairwise matrix"):
                with st.spinner("Computing pairwise distances (this may take a moment)..."):
                    matrix = compute_pairwise_matrix(st.session_state["favorites"], mode=mode_for_matrix)
                if not matrix:
                    st.info("No pairwise data available (ensure favorites have coordinates).")
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
                        rows.append({
                            "Origin": r["origin_name"],
                            "Destination": r["dest_name"],
                            "Distance": dist,
                            "Duration": dur
                        })
                    df_matrix = pd.DataFrame(rows)
                    st.dataframe(df_matrix, use_container_width=True)

# Footer
st.markdown("---")
st.caption("Tip: OSRM public server is used for routing. For heavy usage or production, host your own OSRM instance or add Redis caching.")
