"""City Explorer page for CityScout."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from .gis import build_city_map, city_metrics


def render_city_explorer() -> None:
    """Render the interactive GIS explorer with stable controls and clear states."""
    st.markdown("<div class='card'><h3 style='margin:0'>City Explorer & GIS</h3></div>", unsafe_allow_html=True)
    st.caption("Explore saved places spatially, compare categories, and inspect place density.")

    places = st.session_state.get("places", [])
    if not isinstance(places, list):
        places = []
    metrics = city_metrics(places)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mapped Places", metrics["places"])
    c2.metric("Favorites", metrics["favorites"])
    c3.metric("Categories", metrics["categories"])
    c4.metric("Estimated Footprint", f"{metrics['footprint_km2']:.1f} km²")

    if not places:
        st.info("City Explorer is ready. Add your first place from **Add Place** to start building the GIS dataset.")
        return

    categories = ["All"] + sorted(metrics["category_counts"].keys())
    left, right = st.columns([1, 1])
    with left:
        selected_category = st.selectbox("Category layer", categories, key="city_explorer_category")
    with right:
        show_heatmap = st.checkbox("Show density heatmap", value=False, key="city_explorer_heatmap")
        cluster_markers = st.checkbox("Cluster markers", value=True, key="city_explorer_clusters")

    filtered_count = metrics["places"] if selected_category == "All" else metrics["category_counts"].get(selected_category, 0)
    st.caption(f"Showing {filtered_count} mapped place{'s' if filtered_count != 1 else ''} in the selected layer.")

    fmap = build_city_map(
        places,
        selected_category=selected_category,
        show_heatmap=show_heatmap,
        cluster_markers=cluster_markers,
    )
    st_folium(fmap, width=1100, height=560, key="city_explorer_map")

    if metrics["category_counts"]:
        st.markdown("### City composition")
        data = pd.DataFrame(
            sorted(metrics["category_counts"].items(), key=lambda item: (-item[1], item[0])),
            columns=["Category", "Places"],
        )
        st.bar_chart(data.set_index("Category"), use_container_width=True)

        with st.expander("GIS dataset", expanded=False):
            columns = ["name", "category", "favorite", "latitude", "longitude", "address"]
            rows = [
                {column: place.get(column, "") for column in columns}
                for place in places
                if isinstance(place, dict)
            ]
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
