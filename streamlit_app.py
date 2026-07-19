# streamlit_app.py
import os
import streamlit as st
import requests
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import pandas as pd
import urllib.parse
import base64
import math
import requests
import polyline  # pip install polyline

def get_osrm_route(lat1, lon1, lat2, lon2):
    """Fetch route from OSRM public API and return decoded coordinates."""
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=polyline"
    resp = requests.get(url).json()
    if resp.get("routes"):
        return polyline.decode(resp["routes"][0]["geometry"])
    return []



# -------------------------
# Configuration
# -------------------------
# Prefer environment variable for security
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "YOUR_API_KEY")
BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="CityScout", page_icon="🌆", layout="wide")

# -------------------------
# Session state
# -------------------------
if "favorites" not in st.session_state:
    st.session_state["favorites"] = []

# -------------------------
# Utility: decode Google polyline
# -------------------------
def decode_polyline(polyline_str):
    """Decodes a polyline that was encoded using the Google Encoded Polyline Algorithm Format.
    Returns list of (lat, lon) tuples.
    """
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
# Google Places & Directions helpers
# -------------------------
def enrich_place_with_google(name: str, city: str):
    """Use Google Places Text Search to fetch basic enrichment (rating, formatted address, place_id, photo ref)."""
    if not GOOGLE_API_KEY or not name:
        return {}
    try:
        query = urllib.parse.quote_plus(f"{name} in {city}")
        url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={query}&key={GOOGLE_API_KEY}"
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if data.get("results"):
            place = data["results"][0]
            return {
                "google_rating": place.get("rating"),
                "google_address": place.get("formatted_address"),
                "google_place_id": place.get("place_id"),
                "google_photo_ref": (place.get("photos") or [{}])[0].get("photo_reference")
            }
    except Exception:
        return {}
    return {}

def fetch_place_photo(photo_ref: str, maxwidth: int = 400):
    """Fetch a photo from Google Places Photo API and return a data URI (base64) for embedding in Streamlit."""
    if not GOOGLE_API_KEY or not photo_ref:
        return None
    try:
        url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth={maxwidth}&photoreference={photo_ref}&key={GOOGLE_API_KEY}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        # The Places Photo endpoint returns a redirect to the actual image; requests follows it and returns image bytes.
        img_bytes = resp.content
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        mime = "image/jpeg"
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None

def google_maps_link(lat: float, lon: float):
    """Return a Google Maps search link for coordinates."""
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

def google_directions_link(origin_lat, origin_lon, dest_lat, dest_lon):
    """Return a Google Maps directions link between two coordinates."""
    origin = f"{origin_lat},{origin_lon}"
    dest = f"{dest_lat},{dest_lon}"
    return f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={dest}"

def get_directions_polyline(origin_lat, origin_lon, dest_lat, dest_lon):
    """Call Google Directions API and return overview_polyline string (if available)."""
    if not GOOGLE_API_KEY:
        return None
    try:
        origin = f"{origin_lat},{origin_lon}"
        dest = f"{dest_lat},{dest_lon}"
        url = f"https://maps.googleapis.com/maps/api/directions/json?origin={origin}&destination={dest}&key={GOOGLE_API_KEY}"
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if data.get("routes"):
            return data["routes"][0]["overview_polyline"]["points"]
    except Exception:
        return None
    return None

def embed_google_map_iframe(lat: float, lon: float, zoom: int = 14, width: int = 700, height: int = 500):
    """Embed a Google Maps iframe centered on lat/lon. Requires GOOGLE_API_KEY."""
    if not GOOGLE_API_KEY:
        st.info("Set GOOGLE_API_KEY to enable embedded Google Maps.")
        return
    src = f"https://www.google.com/maps/embed/v1/view?key={GOOGLE_API_KEY}&center={lat},{lon}&zoom={zoom}"
    iframe = f'<iframe src="{src}" width="{width}" height="{height}" style="border:0;" allowfullscreen="" loading="lazy"></iframe>'
    st.components.v1.html(iframe, height=height)

# -------------------------
# UI
# -------------------------
st.title("🌆 CityScout")
st.markdown("Explore cities with AI-powered insights, maps, clustering, heatmaps, Google Places photos, and Directions polylines.")

tab1, tab2 = st.tabs(["🔍 Explore", "⭐ Favorites"])

# -------------------------
# Explore tab
# -------------------------
with tab1:
    st.sidebar.header("Search Options")
    city = st.sidebar.text_input("Enter a city name", "Kampala")
    category = st.sidebar.selectbox("Choose category", ["restaurants", "attractions", "events", "nightlife", "shopping"])
    min_rating = st.sidebar.slider("Minimum rating", 0.0, 5.0, 0.0, 0.5)
    price_range = st.sidebar.selectbox("Price range", ["Any", "$", "$$", "$$$", "$$$$"])
    show_heatmap = st.sidebar.checkbox("Show heatmap of results", value=False)
    sort_option = st.sidebar.selectbox("Sort results by", ["None", "Rating (High → Low)", "Price (Low → High)", "Price (High → Low)", "Distance (Near → Far)"])

    if st.sidebar.button("Explore"):
        # Check backend health
        try:
            health_resp = requests.get(f"{BASE_URL}/ping", timeout=3)
            if health_resp.status_code != 200:
                st.warning("Backend ping returned non-200. Proceeding to /explore may fail.")
        except Exception:
            st.error("Backend not reachable. Start the backend or update BACKEND_URL.")
            st.stop()

        try:
            resp = requests.get(f"{BASE_URL}/explore", params={"city": city, "category": category}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
        except Exception as e:
            st.error(f"Failed to fetch explore results: {e}")
            results = []

        # Apply filters
        filtered = []
        for item in results:
            rating_ok = item.get("rating", 0) >= min_rating
            price_ok = (price_range == "Any" or item.get("price") == price_range)
            if rating_ok and price_ok:
                filtered.append(item)

        # Sorting
        if sort_option == "Rating (High → Low)":
            filtered.sort(key=lambda x: x.get("rating", 0), reverse=True)
        elif sort_option == "Price (Low → High)":
            filtered.sort(key=lambda x: len(x.get("price", "")))
        elif sort_option == "Price (High → Low)":
            filtered.sort(key=lambda x: len(x.get("price", "")), reverse=True)
        elif sort_option == "Distance (Near → Far)":
            filtered.sort(key=lambda x: x.get("distance", float("inf")))

        st.subheader(f"Results for {city} - {category.capitalize()}")

        if not filtered:
            st.info("No results match your filters.")
        else:
            # Display results
            for item in filtered:
                st.markdown(f"**{item.get('name','Unknown')}**")
                st.write(item.get("description", "No description available"))
                if "rating" in item:
                    st.write(f"⭐ Rating: {item['rating']}")
                if "price" in item:
                    st.write(f"💲 Price: {item['price']}")
                if "distance" in item:
                    st.write(f"📏 Distance: {item['distance']} km")
                if "address" in item:
                    st.write(f"📍 {item['address']}")

                # Enrich with Google Places (non-blocking)
                try:
                    extra = enrich_place_with_google(item.get("name", ""), city)
                    if extra.get("google_rating"):
                        st.write(f"🌍 Google Rating: {extra['google_rating']}")
                    if extra.get("google_address"):
                        st.write(f"📍 Google Address: {extra['google_address']}")
                    if extra.get("google_photo_ref"):
                        photo_data_uri = fetch_place_photo(extra["google_photo_ref"], maxwidth=400)
                        if photo_data_uri:
                            st.image(photo_data_uri, width=300)
                except Exception:
                    pass

                # Add to favorites
                add_key = f"addfav_{item.get('id', item.get('name'))}"
                if st.button(f"Add to Favorites: {item.get('name','Unknown')}", key=add_key):
                    item.setdefault("tag", "None")
                    try:
                        enrichment = enrich_place_with_google(item.get("name", ""), city)
                        item.update({k: v for k, v in enrichment.items() if v})
                    except Exception:
                        pass
                    st.session_state["favorites"].append(item)
                    st.success(f"Added {item.get('name','Unknown')} to Favorites")

                # Google Maps link
                if "latitude" in item and "longitude" in item:
                    maps_url = google_maps_link(item["latitude"], item["longitude"])
                    st.markdown(f"[🌍 View on Google Maps]({maps_url})")

                st.write("---")

            # Folium map for filtered results
            first = filtered[0]
            lat = first.get("latitude", 0)
            lon = first.get("longitude", 0)
            m = folium.Map(location=[lat, lon], zoom_start=13)
            marker_cluster = MarkerCluster().add_to(m)
            heatmap_points = []

            for item in filtered:
                if "latitude" in item and "longitude" in item:
                    folium.Marker(
                        [item["latitude"], item["longitude"]],
                        popup=f"{item.get('name','')}<br>{item.get('address','')}",
                        tooltip=item.get('name','')
                    ).add_to(marker_cluster)
                    heatmap_points.append([item["latitude"], item["longitude"]])

            if show_heatmap and heatmap_points:
                HeatMap(heatmap_points, radius=15).add_to(m)

            st_folium(m, width=700, height=500)

# -------------------------
# Favorites tab
# -------------------------
with tab2:
    st.subheader("⭐ Your Favorites")

    # Import favorites CSV uploader
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
            # Display favorites list with tagging, photos, maps, and directions
            for idx, fav in enumerate(favorites_to_show):
                st.markdown(f"**{fav.get('name','Unknown')}**")
                if fav.get("description"):
                    st.write(fav.get("description"))
                if fav.get("rating"):
                    st.write(f"⭐ Rating: {fav.get('rating')}")
                if fav.get("google_rating"):
                    st.write(f"🌍 Google Rating: {fav.get('google_rating')}")
                if fav.get("address"):
                    st.write(f"📍 {fav.get('address')}")
                if fav.get("google_address"):
                    st.write(f"📍 {fav.get('google_address')}")

                # Photo (if available)
                photo_uri = None
                if fav.get("google_photo_ref"):
                    photo_uri = fetch_place_photo(fav["google_photo_ref"], maxwidth=600)
                if photo_uri:
                    st.image(photo_uri, width=400)

                # Tagging UI
                current_tag = fav.get("tag", "None")
                tag_choices = ["None", "Food", "Nightlife", "Shopping", "Attractions", "Custom"]
                if current_tag not in tag_choices:
                    tag_choices.append(current_tag)
                new_tag = st.selectbox(f"Assign a tag to {fav.get('name','Unknown')}", tag_choices, index=tag_choices.index(current_tag), key=f"tag_{idx}")
                if new_tag == "Custom":
                    custom_tag = st.text_input(f"Enter custom tag for {fav.get('name','Unknown')}", key=f"custom_tag_{idx}")
                    if custom_tag:
                        fav["tag"] = custom_tag
                else:
                    fav["tag"] = new_tag

                st.write(f"🏷️ Current Tag: {fav.get('tag','None')}")

                # Google Maps link and embed
                if "latitude" in fav and "longitude" in fav:
                    maps_url = google_maps_link(fav["latitude"], fav["longitude"])
                    st.markdown(f"[🌍 View on Google Maps]({maps_url})")
                    try:
                        embed_google_map_iframe(fav["latitude"], fav["longitude"])
                    except Exception:
                        pass

                # Directions: choose another favorite as destination and draw polyline on a small map
                if "latitude" in fav and "longitude" in fav and len(st.session_state["favorites"]) > 1:
                    other_favs = [f for f in st.session_state["favorites"] if f is not fav and "latitude" in f and "longitude" in f]
                    if other_favs:
                        dest_names = [f"{o.get('name','Unknown')} ({o.get('tag','')})" for o in other_favs]
                        dest_choice = st.selectbox(f"Get directions from {fav.get('name','Unknown')} to:", ["Select destination"] + dest_names, key=f"dir_select_{idx}")
                        if dest_choice and dest_choice != "Select destination":
                            chosen = other_favs[dest_names.index(dest_choice)]
                            # Get directions polyline
                            polyline_str = get_directions_polyline(fav["latitude"], fav["longitude"], chosen["latitude"], chosen["longitude"])
                            dir_link = google_directions_link(fav["latitude"], fav["longitude"], chosen["latitude"], chosen["longitude"])
                            st.markdown(f"[🧭 Open directions in Google Maps]({dir_link})")
                            if polyline_str:
                                coords = decode_polyline(polyline_str)
                                # Draw on a Folium map
                                mid_lat, mid_lon = coords[len(coords)//2] if coords else (fav["latitude"], fav["longitude"])
                                route_map = folium.Map(location=[mid_lat, mid_lon], zoom_start=13)
                                folium.PolyLine(locations=coords, color="blue", weight=5, opacity=0.7).add_to(route_map)
                                # Mark origin and destination
                                folium.Marker([fav["latitude"], fav["longitude"]], tooltip="Origin", icon=folium.Icon(color="green")).add_to(route_map)
                                folium.Marker([chosen["latitude"], chosen["longitude"]], tooltip="Destination", icon=folium.Icon(color="red")).add_to(route_map)
                                st_folium(route_map, width=700, height=400)
                            else:
                                st.info("Could not fetch route polyline from Google Directions API.")

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

# Directions: choose another favorite as destination and draw OSRM route
if "latitude" in fav and "longitude" in fav and len(st.session_state["favorites"]) > 1:
    other_favs = [f for f in st.session_state["favorites"] if f is not fav and "latitude" in f and "longitude" in f]
    if other_favs:
        dest_names = [o.get("name","Unknown") for o in other_favs]
        dest_choice = st.selectbox(f"Get OSRM directions from {fav.get('name','Unknown')} to:", ["Select destination"] + dest_names, key=f"osrm_dir_{idx}")
        if dest_choice and dest_choice != "Select destination":
            chosen = other_favs[dest_names.index(dest_choice)]
            coords = get_osrm_route(fav["latitude"], fav["longitude"], chosen["latitude"], chosen["longitude"])
            if coords:
                # Draw route on Folium map
                mid_lat, mid_lon = coords[len(coords)//2]
                route_map = folium.Map(location=[mid_lat, mid_lon], zoom_start=13)
                folium.PolyLine(coords, color="blue", weight=5, opacity=0.7).add_to(route_map)
                folium.Marker([fav["latitude"], fav["longitude"]], tooltip="Origin", icon=folium.Icon(color="green")).add_to(route_map)
                folium.Marker([chosen["latitude"], chosen["longitude"]], tooltip="Destination", icon=folium.Icon(color="red")).add_to(route_map)

                # Add multiple tile layers for style switching
                folium.TileLayer('OpenStreetMap').add_to(route_map)
                folium.TileLayer('Stamen Terrain').add_to(route_map)
                folium.TileLayer('CartoDB positron').add_to(route_map)
                folium.LayerControl().add_to(route_map)

                st.subheader("🛣️ OSRM Route")
                st_folium(route_map, width=700, height=400)
            else:
                st.info("Could not fetch route from OSRM.")


# -------------------------
# Footer / Notes
# -------------------------
st.markdown("---")
st.caption("Tip: Set your GOOGLE_API_KEY as an environment variable to enable Places enrichment, photos, Directions, and embedded Google Maps.")
