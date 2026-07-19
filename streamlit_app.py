import streamlit as st
import requests
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import pandas as pd

BASE_URL = "http://localhost:8000"  # Adjust if your backend runs elsewhere

st.set_page_config(page_title="CityScout", page_icon="🌆", layout="wide")

# Initialize favorites in session state
if "favorites" not in st.session_state:
    st.session_state["favorites"] = []

st.title("🌆 CityScout")
st.markdown("Explore cities with AI-powered insights, maps, clustering, heatmaps, filters, sorting, and favorites.")

# Tabs for Explore and Favorites
tab1, tab2 = st.tabs(["🔍 Explore", "⭐ Favorites"])

with tab1:
    # Sidebar inputs
    st.sidebar.header("Search Options")
    city = st.sidebar.text_input("Enter a city name", "Kampala")
    category = st.sidebar.selectbox(
        "Choose category",
        ["restaurants", "attractions", "events", "nightlife", "shopping"]
    )

    # Filters
    min_rating = st.sidebar.slider("Minimum rating", 0.0, 5.0, 0.0, 0.5)
    price_range = st.sidebar.selectbox("Price range", ["Any", "$", "$$", "$$$", "$$$$"])
    show_heatmap = st.sidebar.checkbox("Show heatmap of results", value=False)

    # Sorting
    sort_option = st.sidebar.selectbox(
        "Sort results by",
        ["None", "Rating (High → Low)", "Price (Low → High)", "Price (High → Low)", "Distance (Near → Far)"]
    )

    if st.sidebar.button("Explore"):
        try:
            response = requests.get(
                f"{BASE_URL}/explore",
                params={"city": city, "category": category}
            )

            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])

                # Apply filters
                filtered = []
                for item in results:
                    rating_ok = item.get("rating", 0) >= min_rating
                    price_ok = (price_range == "Any" or item.get("price") == price_range)
                    if rating_ok and price_ok:
                        filtered.append(item)

                # Apply sorting
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
                    # Display list of results with "Add to Favorites"
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
                        if st.button(f"Add to Favorites: {item.get('name','Unknown')}", key=item.get("id", item.get("name"))):
                            st.session_state["favorites"].append(item)
                            st.success(f"Added {item.get('name','Unknown')} to Favorites")
                        st.write("---")

                    # Center map on first filtered result
                    first = filtered[0]
                    lat = first.get("latitude", 0)
                    lon = first.get("longitude", 0)
                    m = folium.Map(location=[lat, lon], zoom_start=13)

                    # Add clustered markers
                    marker_cluster = MarkerCluster().add_to(m)
                    heatmap_points = []

                    for item in filtered:
                        if "latitude" in item and "longitude" in item:
                            folium.Marker(
                                [item["latitude"], item["longitude"]],
                                popup=f"{item['name']}<br>{item.get('address','')}",
                                tooltip=item["name"]
                            ).add_to(marker_cluster)

                            # Collect points for heatmap
                            heatmap_points.append([item["latitude"], item["longitude"]])

                    # Optional heatmap layer
                    if show_heatmap and heatmap_points:
                        HeatMap(heatmap_points, radius=15).add_to(m)

                    st_folium(m, width=700, height=500)

            else:
                st.error(f"Error {response.status_code}: {response.text}")
        except Exception as e:
            st.error(f"Request failed: {e}")

with tab2:
    st.subheader("⭐ Your Favorites")
    if not st.session_state["favorites"]:
        st.info("No favorites saved yet.")
    else:
        for fav in st.session_state["favorites"]:
            st.markdown(f"**{fav.get('name','Unknown')}**")
            st.write(fav.get("description", "No description available"))
            if "rating" in fav:
                st.write(f"⭐ Rating: {fav['rating']}")
            if "price" in fav:
                st.write(f"💲 Price: {fav['price']}")
            if "address" in fav:
                st.write(f"📍 {fav['address']}")
            st.write("---")

        # Export favorites to CSV
        df = pd.DataFrame(st.session_state["favorites"])
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Export Favorites to CSV",
            data=csv,
            file_name="cityscout_favorites.csv",
            mime="text/csv"
        )

        # Clear favorites button
        if st.button("🗑️ Clear Favorites"):
            st.session_state["favorites"] = []
            st.success("Favorites cleared successfully!")

        # Favorites Map
        st.subheader("🗺️ Favorites Map")
        first = st.session_state["favorites"][0]
        lat = first.get("latitude", 0)
        lon = first.get("longitude", 0)
        fav_map = folium.Map(location=[lat, lon], zoom_start=13)
        marker_cluster = MarkerCluster().add_to(fav_map)

        for fav in st.session_state["favorites"]:
            if "latitude" in fav and "longitude" in fav:
                folium.Marker(
                    [fav["latitude"], fav["longitude"]],
                    popup=f"{fav['name']}<br>{fav.get('address','')}",
                    tooltip=fav["name"]
                ).add_to(marker_cluster)

        st_folium(fav_map, width=700, height=500)

    # Import favorites from CSV
    st.subheader("📤 Import Favorites from CSV")
    uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"])
    if uploaded_file is not None:
        try:
            imported_df = pd.read_csv(uploaded_file)
            imported_records = imported_df.to_dict(orient="records")
            st.session_state["favorites"].extend(imported_records)
            st.success("Favorites imported successfully!")
        except Exception as e:
            st.error(f"Failed to import CSV: {e}")
