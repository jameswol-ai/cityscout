import streamlit as st
import requests
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import pandas as pd
import polyline  # pip install polyline

BASE_URL = "http://localhost:8000"  # Your backend

st.set_page_config(page_title="CityScout", page_icon="🌆", layout="wide")

if "favorites" not in st.session_state:
    st.session_state["favorites"] = []

# -------------------------
# OSRM helper
# -------------------------
def get_osrm_route(lat1, lon1, lat2, lon2, mode="driving"):
    """Fetch route from OSRM public API for driving, walking, or cycling."""
    url = f"http://router.project-osrm.org/route/v1/{mode}/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=polyline"
    resp = requests.get(url).json()
    if resp.get("routes"):
        route = resp["routes"][0]
        coords = polyline.decode(route["geometry"])
        distance_km = route["distance"] / 1000.0
        duration_min = route["duration"] / 60.0
        return coords, distance_km, duration_min
    return [], None, None

# -------------------------
# UI
# -------------------------
st.title("🌆 CityScout")
st.markdown("Explore cities with AI-powered insights, maps, clustering, heatmaps, and OSRM routing.")

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

    if st.sidebar.button("Explore"):
        try:
            resp = requests.get(f"{BASE_URL}/explore", params={"city": city, "category": category}, timeout=10)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as e:
            st.error(f"Failed to fetch explore results: {e}")
            results = []

        filtered = [item for item in results if item.get("rating", 0) >= min_rating and (price_range == "Any" or item.get("price") == price_range)]

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

                if st.button(f"Add to Favorites: {item.get('name','Unknown')}", key=item.get("id", item.get("name"))):
                    item["tag"] = "None"
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
                    folium.Marker([item["latitude"], item["longitude"]],
                                  popup=f"{item['name']}<br>{item.get('address','')}",
                                  tooltip=item["name"]).add_to(marker_cluster)
                    heatmap_points.append([item["latitude"], item["longitude"]])

            if show_heatmap and heatmap_points:
                HeatMap(heatmap_points, radius=15).add_to(m)

            folium.TileLayer('OpenStreetMap').add_to(m)
            folium.TileLayer('Stamen Terrain').add_to(m)
            folium.TileLayer('CartoDB positron').add_to(m)
            folium.LayerControl().add_to(m)

            st_folium(m, width=700, height=500)

# -------------------------
# Favorites tab
# -------------------------
with tab2:
    st.subheader("⭐ Your Favorites")
    if not st.session_state["favorites"]:
        st.info("No favorites saved yet.")
    else:
        search_query = st.text_input("🔎 Search favorites by name")
        tag_filter = st.selectbox("🏷️ Filter by tag", ["All", "Food", "Nightlife", "Shopping", "Attractions", "Custom"])

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
                if "rating" in fav:
                    st.write(f"⭐ Rating: {fav['rating']}")
                if "address" in fav:
                    st.write(f"📍 {fav['address']}")

                # Tagging
                current_tag = fav.get("tag", "None")
                new_tag = st.selectbox(f"Assign a tag to {fav.get('name','Unknown')}",
                                       ["None", "Food", "Nightlife", "Shopping", "Attractions", "Custom"],
                                       index=["None","Food","Nightlife","Shopping","Attractions","Custom"].index(current_tag)
                                       if current_tag in ["None","Food","Nightlife","Shopping","Attractions","Custom"] else 0,
                                       key=f"tag_{idx}")
                if new_tag == "Custom":
                    custom_tag = st.text_input(f"Enter custom tag for {fav.get('name','Unknown')}", key=f"custom_tag_{idx}")
                    if custom_tag:
                        fav["tag"] = custom_tag
                else:
                    fav["tag"] = new_tag

                st.write(f"🏷️ Current Tag: {fav['tag']}")

                # OSRM directions
                if "latitude" in fav and "longitude" in fav and len(st.session_state["favorites"]) > 1:
                    other_favs = [f for f in st.session_state["favorites"] if f is not fav and "latitude" in f and "longitude" in f]
                    if other_favs:
                        dest_names = [o.get("name","Unknown") for o in other_favs]
                        dest_choice = st.selectbox(f"Get OSRM directions from {fav.get('name','Unknown')} to:", ["Select destination"] + dest_names, key=f"osrm_dir_{idx}")
                        if dest_choice and dest_choice != "Select destination":
                            chosen = other_favs[dest_names.index(dest_choice)]
                            mode = st.radio("Travel mode", ["driving", "walking", "cycling"], key=f"osrm_mode_{idx}")
                            coords, distance_km, duration_min = get_osrm_route(fav["latitude"], fav["longitude"], chosen["latitude"], chosen["longitude"], mode=mode)
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

                                st.subheader(f"🛣️ OSRM Route