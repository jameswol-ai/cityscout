import streamlit as st
import requests
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import pandas as pd

# 🔑 Replace with your Google Maps API key
GOOGLE_API_KEY = "YOUR_API_KEY"

BASE_URL = "http://localhost:8000"  # Your backend

st.set_page_config(page_title="CityScout", page_icon="🌆", layout="wide")

if "favorites" not in st.session_state:
    st.session_state["favorites"] = []

st.title("🌆 CityScout")
st.markdown("Explore cities with AI-powered insights, maps, clustering, heatmaps, filters, sorting, and Google Maps integration.")

# --- Google Maps helpers ---
def enrich_place(name, city):
    """Fetch extra details from Google Places API"""
    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={name}+in+{city}&key={GOOGLE_API_KEY}"
    resp = requests.get(url).json()
    if resp.get("results"):
        place = resp["results"][0]
        return {
            "google_rating": place.get("rating"),
            "address": place.get("formatted_address"),
            "photo_ref": place.get("photos", [{}])[0].get("photo_reference")
        }
    return {}

def embed_google_map(lat, lon):
    """Embed Google Map iframe"""
    st.components.v1.html(
        f'<iframe src="https://www.google.com/maps/embed/v1/view?key={GOOGLE_API_KEY}&center={lat},{lon}&zoom=14" width="700" height="500"></iframe>',
        height=500
    )

def google_maps_link(lat, lon):
    """Generate Google Maps link"""
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"

# --- Tabs ---
tab1, tab2 = st.tabs(["🔍 Explore", "⭐ Favorites"])

with tab1:
    st.sidebar.header("Search Options")
    city = st.sidebar.text_input("Enter a city name", "Kampala")
    category = st.sidebar.selectbox("Choose category", ["restaurants", "attractions", "events", "nightlife", "shopping"])
    min_rating = st.sidebar.slider("Minimum rating", 0.0, 5.0, 0.0, 0.5)
    price_range = st.sidebar.selectbox("Price range", ["Any", "$", "$$", "$$$", "$$$$"])
    show_heatmap = st.sidebar.checkbox("Show heatmap of results", value=False)
    sort_option = st.sidebar.selectbox("Sort results by", ["None", "Rating (High → Low)", "Price (Low → High)", "Price (High → Low)", "Distance (Near → Far)"])

    if st.sidebar.button("Explore"):
        try:
            response = requests.get(f"{BASE_URL}/explore", params={"city": city, "category": category})
            if response.status_code == 200:
                results = response.json().get("results", [])

                # Apply filters
                filtered = [item for item in results if item.get("rating", 0) >= min_rating and (price_range == "Any" or item.get("price") == price_range)]

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

                        # Google Maps enrichment
                        extra = enrich_place(item.get("name",""), city)
                        if extra.get("google_rating"):
                            st.write(f"🌍 Google Rating: {extra['google_rating']}")
                        if extra.get("address"):
                            st.write(f"📍 Google Address: {extra['address']}")

                        if st.button(f"Add to Favorites: {item.get('name','Unknown')}", key=item.get("id", item.get("name"))):
                            item["tag"] = "None"
                            st.session_state["favorites"].append(item)
                            st.success(f"Added {item.get('name','Unknown')} to Favorites")

                        if "latitude" in item and "longitude" in item:
                            maps_url = google_maps_link(item["latitude"], item["longitude"])
                            st.markdown(f"[🌍 View on Google Maps]({maps_url})")

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

                    st_folium(m, width=700, height=500)

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

                # Google Maps link
                if "latitude" in fav and "longitude" in fav:
                    maps_url = google_maps_link(fav["latitude"], fav["longitude"])
                    st.markdown(f"[🌍 View on Google Maps]({maps_url})")
                    embed_google_map(fav["latitude"], fav["longitude"])

                st.write("---")

            # Export favorites
            df = pd.DataFrame(favorites_to_show)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("📥 Export Favorites to CSV", data=csv, file_name="cityscout_favorites.csv", mime="text/csv")

            if st.button("🗑️ Clear Favorites"):
                st.session_state["favorites"] = []
                st.success("Favorites cleared successfully!")

            # Favorites Map
            first = favorites_to_show[0]
            lat, lon = first.get("