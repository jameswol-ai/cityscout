"""Interactive Spatial Intelligence 2.0 dashboard."""
from __future__ import annotations

import json

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from .gis import valid_places
from .spatial_intelligence import spatial_report


def _map(places: list[dict], radius_m: int, show_hotspots: bool) -> folium.Map:
    items = valid_places(places)
    if not items:
        center = (0.3476, 32.5825)
    else:
        center = (sum(p["latitude"] for p in items) / len(items), sum(p["longitude"] for p in items) / len(items))
    fmap = folium.Map(location=center, zoom_start=13, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="Street Map").add_to(fmap)
    folium.TileLayer("CartoDB positron", name="Light Map").add_to(fmap)
    for place in items:
        folium.Marker([place["latitude"], place["longitude"]], tooltip=str(place.get("name", "Unnamed")),
                      popup=f"{place.get('name', 'Unnamed')}<br>{place.get('category', 'Other')}").add_to(fmap)
        folium.Circle([place["latitude"], place["longitude"]], radius=radius_m,
                      fill=False, weight=1, tooltip=f"{radius_m} m catchment").add_to(fmap)
    if show_hotspots:
        report = spatial_report(items)
        for row in report["hotspots_400m"]:
            place = next((p for p in items if p.get("name") == row["name"]), None)
            if place and row["nearby_places"] > 0:
                folium.CircleMarker([place["latitude"], place["longitude"]], radius=5 + min(12, row["nearby_places"]),
                                    tooltip=f"Hotspot: {row['name']} ({row['nearby_places']} nearby)").add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap


def render_spatial_intelligence(places: list[dict]) -> None:
    st.markdown("<div class='card'><h3 style='margin:0'>Spatial Intelligence 2.0</h3></div>", unsafe_allow_html=True)
    st.caption("Catchments, service coverage, category gaps and density hotspots from saved places. These are GIS dataset proxies.")
    items = valid_places(places)
    report = spatial_report(items, st.session_state.get("categories"))
    a, b, c, d = st.columns(4)
    a.metric("Mapped Places", report["dataset_places"])
    b.metric("400 m Coverage", f"{report['catchment_400m']['coverage_pct']:.0f}%")
    c.metric("800 m Coverage", f"{report['catchment_800m']['coverage_pct']:.0f}%")
    d.metric("Category Gaps", len(report["category_gaps"]))
    if not items:
        st.info("Add mapped places to activate Spatial Intelligence 2.0.")
        return
    radius = st.select_slider("Catchment radius", options=[400, 800], value=400, format_func=lambda x: f"{x} m", key="spatial_radius")
    show_hotspots = st.checkbox("Show density hotspots", value=True, key="spatial_hotspots")
    st_folium(_map(items, radius, show_hotspots), width=1000, height=600, key="spatial_intelligence_map")
    tabs = st.tabs(["Catchments", "Service Coverage", "Hotspots", "Category Gaps", "Report"])
    with tabs[0]:
        data = report[f"catchment_{radius}m"]["rows"]
        st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True)
    with tabs[1]:
        st.dataframe(pd.DataFrame(report["service_coverage_400m"]), use_container_width=True, hide_index=True)
    with tabs[2]:
        st.dataframe(pd.DataFrame(report["hotspots_400m"]), use_container_width=True, hide_index=True)
    with tabs[3]:
        gaps = report["category_gaps"]
        if gaps:
            st.warning("Potential dataset gaps: " + ", ".join(row["category"] for row in gaps))
            st.dataframe(pd.DataFrame(gaps), use_container_width=True, hide_index=True)
        else:
            st.success("All configured categories have at least one saved place.")
    with tabs[4]:
        st.json(report)
        st.download_button("Download Spatial Intelligence JSON", json.dumps(report, indent=2, default=str),
                           "cityscout_spatial_intelligence.json", "application/json", key="spatial_download_report")
