"""Streamlit Architecture & Urban Design workspace."""
from __future__ import annotations

from html import escape
from math import isfinite

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from .architecture import SiteParameters, build_analysis
from .ui import page_header


def _valid_coordinate(value: object, minimum: float, maximum: float) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number) or not (minimum <= number <= maximum):
        return None
    return number


def _clean_places(places: object) -> list[dict]:
    if not isinstance(places, list):
        return []
    result: list[dict] = []
    for place in places:
        if not isinstance(place, dict):
            continue
        lat = _valid_coordinate(place.get("latitude"), -90.0, 90.0)
        lon = _valid_coordinate(place.get("longitude"), -180.0, 180.0)
        if lat is None or lon is None:
            continue
        result.append({**place, "latitude": lat, "longitude": lon})
    return result


def _center_from_places(places: list[dict]) -> tuple[float, float] | None:
    if not places:
        return None
    return (
        sum(place["latitude"] for place in places) / len(places),
        sum(place["longitude"] for place in places) / len(places),
    )


def page_architecture() -> None:
    page_header("Architecture & Urban Design")
    st.caption(
        "Concept-stage urban analysis using explicit assumptions. "
        "Verify planning, surveying, engineering, environmental, accessibility, and fire-safety requirements with the relevant authorities and consultants."
    )

    places = _clean_places(st.session_state.get("places", []))

    with st.expander("Site & development parameters", expanded=True):
        a, b, c = st.columns(3)
        area = a.number_input("Site area (m²)", min_value=1.0, value=1000.0, step=50.0, key="arch_site_area")
        coverage = b.slider("Site coverage (%)", 0.0, 100.0, 40.0, key="arch_coverage")
        floors = c.number_input("Number of floors", min_value=1, max_value=200, value=4, step=1, key="arch_floors")

        d, e, f = st.columns(3)
        floor_height = d.number_input("Floor-to-floor height (m)", min_value=2.0, max_value=10.0, value=3.2, step=0.1, key="arch_floor_height")
        green = e.slider("Green/open-space ratio (%)", 0.0, 100.0, 20.0, key="arch_green")
        parking = f.number_input("Parking spaces / 100 m² GFA", min_value=0.0, value=1.0, step=0.1, key="arch_parking")

        g, h, i = st.columns(3)
        front = g.number_input("Front setback (m)", min_value=0.0, value=5.0, step=0.5, key="arch_front")
        side = h.number_input("Side setback (m)", min_value=0.0, value=3.0, step=0.5, key="arch_side")
        rear = i.number_input("Rear setback (m)", min_value=0.0, value=5.0, step=0.5, key="arch_rear")
        orientation = st.slider("Primary site/building orientation (°)", 0, 359, 0, key="arch_orientation")

    params = SiteParameters(
        site_area_m2=float(area),
        site_coverage_pct=float(coverage),
        floors=int(floors),
        floor_height_m=float(floor_height),
        setback_front_m=float(front),
        setback_side_m=float(side),
        setback_rear_m=float(rear),
        green_ratio_pct=float(green),
        parking_per_100m2=float(parking),
        orientation_deg=float(orientation),
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
    score_rows = [
        {"Indicator": str(name).replace("_", " ").title(), "Score": float(value)}
        for name, value in scores.items()
        if isinstance(value, (int, float)) and isfinite(float(value))
    ]
    if score_rows:
        score_df = pd.DataFrame(score_rows).set_index("Indicator")
        st.bar_chart(score_df, use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Land-use context")
        land_use = analysis.get("land_use", {})
        if isinstance(land_use, dict) and land_use:
            st.dataframe(
                pd.DataFrame(list(land_use.items()), columns=["Context", "Places"]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Add saved places to populate contextual land-use indicators.")

    with right:
        st.subheader("Walkability")
        walk = analysis.get("walkability", {})
        score = float(walk.get("score", 0.0) or 0.0)
        within_400 = int(walk.get("within_400m", 0) or 0)
        within_800 = int(walk.get("within_800m", 0) or 0)
        average_distance = float(walk.get("average_distance_km", 0.0) or 0.0)
        st.metric("Walkability index", f"{score:.0f}/100")
        st.write(f"Within 400 m: **{within_400}** places")
        st.write(f"Within 800 m: **{within_800}** places")
        st.write(f"Average distance: **{average_distance:.2f} km**")

    st.subheader("Site context map")
    if center:
        map_center = center
        zoom = 14
    else:
        map_center = (0.0, 0.0)
        zoom = 2
        st.info("No valid saved coordinates are available. Add places or use Add Place to establish a site context.")

    context_map = folium.Map(location=map_center, zoom_start=zoom, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="Street Map").add_to(context_map)
    folium.TileLayer("CartoDB positron", name="Light Map").add_to(context_map)

    for place in places:
        name = escape(str(place.get("name") or "Place"))
        category = escape(str(place.get("category") or "Other"))
        folium.CircleMarker(
            [place["latitude"], place["longitude"]],
            radius=5,
            tooltip=name,
            popup=folium.Popup(category, max_width=240),
        ).add_to(context_map)

    if center:
        folium.Marker(
            center,
            tooltip="Context centroid",
            icon=folium.Icon(icon="building", prefix="fa"),
        ).add_to(context_map)
        folium.Circle(center, radius=400, tooltip="400 m study radius", fill=False).add_to(context_map)
        folium.Circle(center, radius=800, tooltip="800 m study radius", fill=False).add_to(context_map)

    folium.LayerControl(collapsed=False).add_to(context_map)
    st_folium(context_map, width=1000, height=500, key="architecture_context_map")

    st.subheader("Solar and orientation guidance")
    solar = analysis.get("solar", {})
    st.info(str(solar.get("guidance", "No solar guidance is available.")))
    st.caption(str(solar.get("orientation_note", "")))

    st.subheader("Analysis report")
    report = pd.DataFrame(
        [
            ["Site area", metrics["site_area_m2"], "m²"],
            ["Building footprint", metrics["building_footprint_m2"], "m²"],
            ["Gross floor area", metrics["gross_floor_area_m2"], "m²"],
            ["Floor area ratio", metrics["floor_area_ratio"], "ratio"],
            ["Green/open space", metrics["green_area_m2"], "m²"],
            ["Other open area", metrics["other_open_area_m2"], "m²"],
            ["Building height", metrics["building_height_m"], "m"],
            ["Estimated parking", metrics["estimated_parking_spaces"], "spaces"],
        ],
        columns=["Parameter", "Value", "Unit"],
    )
    st.dataframe(report, use_container_width=True, hide_index=True)
    st.download_button(
        "Download analysis CSV",
        report.to_csv(index=False).encode("utf-8"),
        "cityscout_architecture_analysis.csv",
        "text/csv",
        key="architecture_analysis_download",
    )
