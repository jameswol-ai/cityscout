"""Streamlit Architecture & Urban Design workspace."""
from __future__ import annotations

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from .architecture import SiteParameters, build_analysis
from .ui import page_header


def _center_from_places(places: list[dict]) -> tuple[float, float] | None:
    coords = []
    for place in places:
        try:
            coords.append((float(place["latitude"]), float(place["longitude"])))
        except (KeyError, TypeError, ValueError):
            pass
    if not coords:
        return None
    return sum(x[0] for x in coords) / len(coords), sum(x[1] for x in coords) / len(coords)


def page_architecture():
    page_header("Architecture & Urban Design")
    st.caption("Concept-stage urban analysis using explicit assumptions. Verify all planning and engineering requirements with the relevant authorities and consultants.")

    places = st.session_state.get("places", [])
    with st.expander("Site & development parameters", expanded=True):
        a, b, c = st.columns(3)
        area = a.number_input("Site area (m²)", min_value=1.0, value=1000.0, step=50.0)
        coverage = b.slider("Site coverage (%)", 0.0, 100.0, 40.0)
        floors = c.number_input("Number of floors", min_value=1, max_value=200, value=4, step=1)
        d, e, f = st.columns(3)
        floor_height = d.number_input("Floor-to-floor height (m)", min_value=2.0, max_value=10.0, value=3.2, step=0.1)
        green = e.slider("Green/open-space ratio (%)", 0.0, 100.0, 20.0)
        parking = f.number_input("Parking spaces / 100 m² GFA", min_value=0.0, value=1.0, step=0.1)
        g, h, i = st.columns(3)
        front = g.number_input("Front setback (m)", min_value=0.0, value=5.0, step=0.5)
        side = h.number_input("Side setback (m)", min_value=0.0, value=3.0, step=0.5)
        rear = i.number_input("Rear setback (m)", min_value=0.0, value=5.0, step=0.5)
        orientation = st.slider("Primary site/building orientation (°)", 0, 359, 0)

    params = SiteParameters(
        site_area_m2=area,
        site_coverage_pct=coverage,
        floors=int(floors),
        floor_height_m=floor_height,
        setback_front_m=front,
        setback_side_m=side,
        setback_rear_m=rear,
        green_ratio_pct=green,
        parking_per_100m2=parking,
        orientation_deg=orientation,
    )
    center = _center_from_places(places)
    analysis = build_analysis(params, places, center)
    metrics = analysis["metrics"]
    scores = analysis["scores"]

    st.subheader("Development metrics")
    cols = st.columns(4)
    cols[0].metric("Building footprint", f"{metrics['building_footprint_m2']:,.0f} m²")
    cols[1].metric("Gross floor area", f"{metrics['gross_floor_area_m2']:,.0f} m²")
    cols[2].metric("FAR", f"{metrics['floor_area_ratio']:.2f}")
    cols[3].metric("Building height", f"{metrics['building_height_m']:.1f} m")

    st.subheader("Urban performance indicators")
    score_df = pd.DataFrame({"Indicator": [k.replace("_", " ").title() for k in scores], "Score": list(scores.values())})
    st.bar_chart(score_df.set_index("Indicator"))

    left, right = st.columns(2)
    with left:
        st.subheader("Land-use context")
        land_use = analysis["land_use"]
        if land_use:
            st.dataframe(pd.DataFrame(list(land_use.items()), columns=["Context", "Places"]), use_container_width=True, hide_index=True)
        else:
            st.info("Add saved places to populate contextual land-use indicators.")
    with right:
        st.subheader("Walkability")
        walk = analysis["walkability"]
        st.metric("Walkability index", f"{walk['score']:.0f}/100")
        st.write(f"Within 400 m: **{walk['within_400m']}** places")
        st.write(f"Within 800 m: **{walk['within_800m']}** places")
        st.write(f"Average distance: **{walk['average_distance_km']:.2f} km**")

    st.subheader("Site context map")
    if center:
        map_center = center
    else:
        map_center = (0.0, 0.0)
        st.info("No saved coordinates are available. Add places or use Add Place to establish a site context.")
    zoom = 14 if center else 2
    m = folium.Map(location=map_center, zoom_start=zoom, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="Street Map").add_to(m)
    folium.TileLayer("CartoDB positron", name="Light Map").add_to(m)
    for place in places:
        try:
            folium.CircleMarker(
                [float(place["latitude"]), float(place["longitude"])],
                radius=5,
                tooltip=place.get("name", "Place"),
                popup=place.get("category", "Other"),
            ).add_to(m)
        except (KeyError, TypeError, ValueError):
            continue
    if center:
        folium.Marker(center, tooltip="Context centroid", icon=folium.Icon(icon="building", prefix="fa")).add_to(m)
        folium.Circle(center, radius=400, tooltip="400 m walkability study radius", fill=False).add_to(m)
        folium.Circle(center, radius=800, tooltip="800 m walkability study radius", fill=False).add_to(m)
    folium.LayerControl().add_to(m)
    st_folium(m, width=1000, height=500, key="architecture_context_map")

    st.subheader("Solar and orientation guidance")
    st.info(analysis["solar"]["guidance"])
    st.caption(analysis["solar"]["orientation_note"])

    report = pd.DataFrame([
        ["Site area", metrics["site_area_m2"], "m²"],
        ["Building footprint", metrics["building_footprint_m2"], "m²"],
        ["Gross floor area", metrics["gross_floor_area_m2"], "m²"],
        ["Floor area ratio", metrics["floor_area_ratio"], "ratio"],
        ["Green/open space", metrics["green_area_m2"], "m²"],
        ["Building height", metrics["building_height_m"], "m"],
        ["Estimated parking", metrics["estimated_parking_spaces"], "spaces"],
    ], columns=["Parameter", "Value", "Unit"])
    st.download_button("Download analysis CSV", report.to_csv(index=False).encode("utf-8"), "cityscout_architecture_analysis.csv", "text/csv")
