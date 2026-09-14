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
    return number if isfinite(number) and minimum <= number <= maximum else None


def _clean_places(places: object) -> list[dict]:
    if not isinstance(places, list):
        return []
    result: list[dict] = []
    for place in places:
        if not isinstance(place, dict):
            continue
        lat = _valid_coordinate(place.get("latitude"), -90.0, 90.0)
        lon = _valid_coordinate(place.get("longitude"), -180.0, 180.0)
        if lat is not None and lon is not None:
            result.append({**place, "latitude": lat, "longitude": lon})
    return result


def _center_from_places(places: list[dict]) -> tuple[float, float] | None:
    if not places:
        return None
    return sum(p["latitude"] for p in places) / len(places), sum(p["longitude"] for p in places) / len(places)


def _status(score: float) -> str:
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Moderate"
    return "Needs review"


def page_architecture() -> None:
    page_header("Architecture & Urban Design")
    st.caption("A concept design cockpit for site planning, development intensity, urban context, walkability, solar orientation and early design decisions. All indicators are assumption-driven and require project-specific professional verification.")

    places = _clean_places(st.session_state.get("places", []))

    with st.expander("01 · Site & development parameters", expanded=True):
        a, b, c = st.columns(3)
        area = a.number_input("Site area (m²)", min_value=1.0, value=1000.0, step=50.0, key="arch_site_area")
        coverage = b.slider("Maximum site coverage (%)", 0.0, 100.0, 40.0, key="arch_coverage")
        floors = c.number_input("Number of floors", min_value=1, max_value=200, value=4, step=1, key="arch_floors")
        d, e, f = st.columns(3)
        floor_height = d.number_input("Floor-to-floor height (m)", min_value=2.0, max_value=10.0, value=3.2, step=0.1, key="arch_floor_height")
        green = e.slider("Green / open-space ratio (%)", 0.0, 100.0, 20.0, key="arch_green")
        parking = f.number_input("Parking spaces / 100 m² GFA", min_value=0.0, value=1.0, step=0.1, key="arch_parking")
        g, h, i = st.columns(3)
        front = g.number_input("Front setback (m)", min_value=0.0, value=5.0, step=0.5, key="arch_front")
        side = h.number_input("Side setback (m)", min_value=0.0, value=3.0, step=0.5, key="arch_side")
        rear = i.number_input("Rear setback (m)", min_value=0.0, value=5.0, step=0.5, key="arch_rear")
        orientation = st.slider("Primary building orientation (°)", 0, 359, 0, key="arch_orientation")

    params = SiteParameters(float(area), float(coverage), int(floors), float(floor_height), float(front), float(side), float(rear), float(green), float(parking), float(orientation))
    center = _center_from_places(places)
    analysis = build_analysis(params, places, center)
    metrics = analysis["metrics"]
    scores = analysis["scores"]

    st.subheader("02 · Development envelope")
    cols = st.columns(5)
    cols[0].metric("Footprint", f"{metrics['building_footprint_m2']:,.0f} m²")
    cols[1].metric("GFA", f"{metrics['gross_floor_area_m2']:,.0f} m²")
    cols[2].metric("FAR", f"{metrics['floor_area_ratio']:.2f}")
    cols[3].metric("Height", f"{metrics['building_height_m']:.1f} m")
    cols[4].metric("Parking", f"{metrics['estimated_parking_spaces']:.0f}")

    env1, env2, env3 = st.columns(3)
    env1.metric("Setback envelope", f"{metrics['setback_envelope_m2']:,.0f} m²")
    env2.metric("Setback-limited footprint", f"{metrics['setback_limited_footprint_m2']:,.0f} m²")
    env3.metric("Setback reduction", f"{metrics['setback_reduction_pct']:.1f}%")
    if metrics["setback_reduction_pct"] > 20:
        st.warning("The conceptual setback envelope materially constrains the requested footprint. Test the actual parcel geometry before advancing the massing.")

    st.subheader("03 · Urban performance dashboard")
    score_rows = [{"Indicator": str(k).replace("_", " ").title(), "Score": float(v), "Assessment": _status(float(v))} for k, v in scores.items() if isinstance(v, (int, float)) and isfinite(float(v))]
    score_df = pd.DataFrame(score_rows)
    chart_df = score_df.set_index("Indicator")[["Score"]]
    st.bar_chart(chart_df, use_container_width=True)
    st.dataframe(score_df, use_container_width=True, hide_index=True)

    st.subheader("04 · Sustainability & site efficiency")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Green area", f"{metrics['green_area_m2']:,.0f} m²")
    s2.metric("Open space", f"{metrics['open_space_pct']:.1f}%")
    s3.metric("Parking area proxy", f"{metrics['parking_area_ratio_pct']:.1f}%")
    s4.metric("Site efficiency", f"{metrics['site_efficiency_pct']:.0f}%")
    st.caption("Parking area proxy assumes 30 m² per parking space for early land-use testing. It is not a parking design standard.")

    left, right = st.columns(2)
    with left:
        st.subheader("05 · Urban context")
        land_use = analysis.get("land_use", {})
        if land_use:
            st.dataframe(pd.DataFrame(list(land_use.items()), columns=["Context", "Places"]), use_container_width=True, hide_index=True)
        else:
            st.info("Add saved places to populate contextual land-use indicators.")
    with right:
        st.subheader("06 · Walkability")
        walk = analysis.get("walkability", {})
        st.metric("Walkability index", f"{float(walk.get('score', 0.0)):.0f}/100")
        st.write(f"400 m catchment: **{int(walk.get('within_400m', 0))}** places")
        st.write(f"800 m catchment: **{int(walk.get('within_800m', 0))}** places")
        st.write(f"Average distance: **{float(walk.get('average_distance_km', 0.0)):.2f} km**")
        st.caption("Walkability is a saved-place proximity proxy, not a pedestrian level-of-service calculation.")

    st.subheader("07 · Site context & study radii")
    map_center = center or (0.0, 0.0)
    if not center:
        st.info("No valid saved coordinates are available. Add places to establish a spatial design context.")
    context_map = folium.Map(location=map_center, zoom_start=14 if center else 2, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="Street Map").add_to(context_map)
    folium.TileLayer("CartoDB positron", name="Light Map").add_to(context_map)
    for place in places:
        name = escape(str(place.get("name") or "Place"))
        category = escape(str(place.get("category") or "Other"))
        folium.CircleMarker([place["latitude"], place["longitude"]], radius=5, tooltip=name, popup=folium.Popup(category, max_width=240)).add_to(context_map)
    if center:
        folium.Marker(center, tooltip="Context centroid", icon=folium.Icon(icon="building", prefix="fa")).add_to(context_map)
        folium.Circle(center, radius=400, tooltip="400 m study radius", fill=False).add_to(context_map)
        folium.Circle(center, radius=800, tooltip="800 m study radius", fill=False).add_to(context_map)
    folium.LayerControl(collapsed=False).add_to(context_map)
    st_folium(context_map, width=1000, height=500, key="architecture_context_map")

    st.subheader("08 · Solar & orientation")
    solar = analysis.get("solar", {})
    st.info(str(solar.get("guidance", "No solar guidance is available.")))
    st.caption(str(solar.get("orientation_note", "")))

    st.subheader("09 · Design review priorities")
    for recommendation in analysis.get("recommendations", []):
        st.write(f"• {recommendation}")

    st.subheader("10 · Concept analysis report")
    report_rows = [
        ["Site area", metrics["site_area_m2"], "m²"], ["Building footprint", metrics["building_footprint_m2"], "m²"],
        ["Gross floor area", metrics["gross_floor_area_m2"], "m²"], ["Floor area ratio", metrics["floor_area_ratio"], "ratio"],
        ["Green/open space", metrics["green_area_m2"], "m²"], ["Other open area", metrics["other_open_area_m2"], "m²"],
        ["Building height", metrics["building_height_m"], "m"], ["Estimated parking", metrics["estimated_parking_spaces"], "spaces"],
        ["Setback envelope", metrics["setback_envelope_m2"], "m²"], ["Setback-limited footprint", metrics["setback_limited_footprint_m2"], "m²"],
        ["Setback reduction", metrics["setback_reduction_pct"], "%"], ["Open space", metrics["open_space_pct"], "%"],
    ]
    report = pd.DataFrame(report_rows, columns=["Parameter", "Value", "Unit"])
    st.dataframe(report, use_container_width=True, hide_index=True)
    st.download_button("Download architecture analysis CSV", report.to_csv(index=False).encode("utf-8"), "cityscout_architecture_analysis.csv", "text/csv", key="architecture_analysis_download")
