"""City Explorer page for CityScout."""
from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from modules.gis import build_city_map, city_metrics


def render_city_explorer() -> None:
    st.markdown("<div class='card'><h3 style='margin:0'>City Explorer & GIS</h3></div>", unsafe_allow_html=True)
    places = st.session_state.get("places", [])
    metrics = city_metrics(places)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mapped Places", metrics["places"])
    c2.metric("Favorites", metrics["favorites"])
    c3.metric("Categories", metrics["categories"])
    c4.metric("Estimated Footprint", f"{metrics['footprint_km2']:.1f} km²")

    categories = ["All"] + sorted(metrics["category_counts"].keys())
    left, right = st.columns([1, 1])
    with left:
        selected_category = st.selectbox("Category layer", categories)
    with right:
        show_heatmap = st.checkbox("Show density heatmap", value=False)
        cluster_markers = st.checkbox("Cluster markers", value=True)

    fmap = build_city_map(
        places,
        selected_category=selected_category,
        show_heatmap=show_heatmap,
        cluster_markers=cluster_markers,
    )
    st_folium(fmap, width=None, height=560, key="city_explorer_map")

    if metrics["category_counts"]:
        st.markdown("### City composition")
        data = pd.DataFrame(
            sorted(metrics["category_counts"].items(), key=lambda item: (-item[1], item[0])),
            columns=["Category", "Places"],
        )
        st.bar_chart(data.set_index("Category"))
    else:
        st.info("Add places to begin building your city intelligence map.")
