"""Architecture & Urban Design workspace for CityScout."""
from __future__ import annotations

from html import escape
from math import cos, isfinite, radians

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from .architecture import SiteParameters, build_analysis
from .massing import build_massing_options
from .parametric_design import floor_plate_polygon, generate_design_options
from .site_planning import site_plan_summary
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
    result = []
    for place in places:
        if not isinstance(place, dict):
            continue
        lat = _valid_coordinate(place.get("latitude"), -90, 90)
        lon = _valid_coordinate(place.get("longitude"), -180, 180)
        if lat is not None and lon is not None:
            result.append({**place, "latitude": lat, "longitude": lon})
    return result


def _center_from_places(places: list[dict]) -> tuple[float, float] | None:
    if not places:
        return None
    return (sum(p["latitude"] for p in places) / len(places), sum(p["longitude"] for p in places) / len(places))


def _status(score: float) -> str:
    return "Strong" if score >= 80 else "Good" if score >= 60 else "Moderate" if score >= 40 else "Needs review"


def _massing_map(center: tuple[float, float], option: dict, orientation_deg: float = 0.0) -> folium.Map:
    fmap = folium.Map(location=center, zoom_start=16, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="Street Map").add_to(fmap)
    folium.TileLayer("CartoDB positron", name="Light Map").add_to(fmap)
    polygon = floor_plate_polygon(option, orientation_deg)
    cos_lat = max(0.2, abs(cos(radians(center[0]))))
    coords = []
    for x, y in polygon:
        lat = center[0] + y / 111_320.0
        lon = center[1] + x / (111_320.0 * cos_lat)
        coords.append((lat, lon))
    folium.Polygon(coords, tooltip=f"{option['option']} floor-plate concept", fill=True).add_to(fmap)
    folium.Marker(center, tooltip=f"{option['option']} centroid").add_to(fmap)
    return fmap


def page_architecture() -> None:
    page_header("Architecture & Urban Design")
    st.caption("Concept design cockpit for site planning, development intensity, massing, floor plates, cores, urban context, walkability and solar orientation. Outputs are assumption-driven and require project-specific professional verification.")
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
    metrics, scores = analysis["metrics"], analysis["scores"]

    st.subheader("02 · Development envelope")
    cols = st.columns(5)
    for col, label, key, fmt in [
        (cols[0], "Footprint", "building_footprint_m2", ",.0f"), (cols[1], "GFA", "gross_floor_area_m2", ",.0f"),
        (cols[2], "FAR", "floor_area_ratio", ".2f"), (cols[3], "Height", "building_height_m", ".1f"),
        (cols[4], "Parking", "estimated_parking_spaces", ".0f"),
    ]:
        suffix = " m²" if "m2" in key else ""
        col.metric(label, format(metrics[key], fmt) + suffix)

    env = st.columns(3)
    env[0].metric("Setback envelope", f"{metrics['setback_envelope_m2']:,.0f} m²")
    env[1].metric("Setback-limited footprint", f"{metrics['setback_limited_footprint_m2']:,.0f} m²")
    env[2].metric("Setback reduction", f"{metrics['setback_reduction_pct']:.1f}%")
    if metrics["setback_reduction_pct"] > 20:
        st.warning("The conceptual setback envelope materially constrains the requested footprint. Test the actual parcel geometry before advancing the massing.")

    st.subheader("03 · Massing & site-planning alternatives")
    options = build_massing_options(params)
    selected = st.selectbox("Massing scenario", [o["option"] for o in options], key="arch_massing_option")
    option = next((o for o in options if o["option"] == selected), options[0])
    comparison = pd.DataFrame(options)[["option", "strategy", "floors", "coverage_pct", "footprint_m2", "gfa_m2", "height_m", "far", "open_ground_m2", "gfa_delta_m2"]]
    comparison.columns = ["Option", "Strategy", "Floors", "Coverage %", "Footprint m²", "GFA m²", "Height m", "FAR", "Ground Open m²", "GFA Δ m²"]
    st.dataframe(comparison, use_container_width=True, hide_index=True)
    mc = st.columns(4)
    mc[0].metric("Scenario GFA", f"{option['gfa_m2']:,.0f} m²")
    mc[1].metric("Scenario footprint", f"{option['footprint_m2']:,.0f} m²")
    mc[2].metric("Scenario height", f"{option['height_m']:.1f} m")
    mc[3].metric("Ground open area", f"{option['open_ground_m2']:,.0f} m²")
    plan = site_plan_summary(params)
    st.caption(f"Open-ground-biased concept selection: **{plan['recommended_concept']}**. This is a design heuristic, not a regulatory recommendation.")
    if center:
        st_folium(_massing_map(center, option, float(orientation)), width=1000, height=430, key="architecture_massing_map")
    else:
        st.info("Add a saved place with valid coordinates to visualize the conceptual massing on the map.")

    st.subheader("04 · Parametric building design")
    p1, p2, p3 = st.columns(3)
    preferred = p1.selectbox("Preferred design option", [o["option"] for o in options], index=[o["option"] for o in options].index(selected), key="arch_design_option")
    core_ratio = p2.slider("Core ratio (% of floor plate)", 5.0, 30.0, 12.0, 0.5, key="arch_core_ratio")
    aspect = p3.slider("Floor-plate aspect ratio", 0.5, 3.0, 1.4, 0.1, key="arch_aspect_ratio")
    designs = generate_design_options(params, preferred, core_ratio, aspect)
    design_df = pd.DataFrame(designs)[["option", "form", "floors", "plate_width_m", "plate_depth_m", "core_area_m2", "net_floor_area_m2", "net_to_gross_pct", "daylight_perimeter_proxy", "design_score"]]
    design_df.columns = ["Option", "Form", "Floors", "Plate width m", "Plate depth m", "Core m²", "Net floor m²", "Net/Gross %", "Daylight proxy", "Design score"]
    st.dataframe(design_df.round(2), use_container_width=True, hide_index=True)
    selected_design = next((d for d in designs if d["option"] == preferred), designs[0])
    dc = st.columns(4)
    dc[0].metric("Net floor / level", f"{selected_design['net_floor_area_m2']:,.0f} m²")
    dc[1].metric("Core area", f"{selected_design['core_area_m2']:,.0f} m²")
    dc[2].metric("Net/Gross", f"{selected_design['net_to_gross_pct']:.1f}%")
    dc[3].metric("Concept score", f"{selected_design['design_score']:.0f}/100")
    st.caption("Core, circulation and daylight values are conceptual planning proxies. Confirm egress, accessibility, structure, shafts, fire separation and MEP requirements during detailed design.")
    st.markdown("**Conceptual program allocation per level**")
    program = pd.DataFrame(list(selected_design["program"].items()), columns=["Program", "Area m²"])
    st.dataframe(program.round(1), use_container_width=True, hide_index=True)
    if center:
        st_folium(_massing_map(center, selected_design, float(orientation)), width=1000, height=430, key="architecture_floor_plate_map")
    else:
        st.info("Add a saved place with valid coordinates to visualize the rotated conceptual floor plate.")

    st.subheader("05 · Urban performance dashboard")
    score_df = pd.DataFrame([{ "Indicator": str(k).replace("_", " ").title(), "Score": float(v), "Assessment": _status(float(v)) } for k, v in scores.items() if isinstance(v, (int, float)) and isfinite(float(v))])
    st.bar_chart(score_df.set_index("Indicator")[["Score"]], use_container_width=True)
    st.dataframe(score_df, use_container_width=True, hide_index=True)

    st.subheader("06 · Sustainability & site efficiency")
    s = st.columns(4)
    s[0].metric("Green area", f"{metrics['green_area_m2']:,.0f} m²")
    s[1].metric("Open space", f"{metrics['open_space_pct']:.1f}%")
    s[2].metric("Parking area proxy", f"{metrics['parking_area_ratio_pct']:.1f}%")
    s[3].metric("Site efficiency", f"{metrics['site_efficiency_pct']:.0f}%")
    st.caption("Parking area proxy uses 30 m² per space for early land-use testing. It is not a parking design standard.")

    left, right = st.columns(2)
    with left:
        st.subheader("07 · Urban context")
        land_use = analysis.get("land_use", {})
        st.dataframe(pd.DataFrame(list(land_use.items()), columns=["Context", "Places"]), use_container_width=True, hide_index=True) if land_use else st.info("Add saved places to populate contextual land-use indicators.")
    with right:
        st.subheader("08 · Walkability")
        walk = analysis.get("walkability", {})
        st.metric("Walkability index", f"{float(walk.get('score', 0.0)):.0f}/100")
        st.write(f"400 m catchment: **{int(walk.get('within_400m', 0))}** places")
        st.write(f"800 m catchment: **{int(walk.get('within_800m', 0))}** places")
        st.write(f"Average distance: **{float(walk.get('average_distance_km', 0.0)):.2f} km**")
        st.caption("Saved-place proximity proxy, not pedestrian level-of-service.")

    st.subheader("09 · Site context & study radii")
    fmap = folium.Map(location=center or (0, 0), zoom_start=14 if center else 2, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="Street Map").add_to(fmap)
    folium.TileLayer("CartoDB positron", name="Light Map").add_to(fmap)
    for place in places:
        folium.CircleMarker([place["latitude"], place["longitude"]], radius=5, tooltip=escape(str(place.get("name") or "Place")), popup=folium.Popup(escape(str(place.get("category") or "Other")), max_width=240)).add_to(fmap)
    if center:
        folium.Marker(center, tooltip="Context centroid").add_to(fmap)
        folium.Circle(center, radius=400, tooltip="400 m study radius", fill=False).add_to(fmap)
        folium.Circle(center, radius=800, tooltip="800 m study radius", fill=False).add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)
    st_folium(fmap, width=1000, height=480, key="architecture_context_map")

    st.subheader("10 · Solar & orientation")
    solar = analysis.get("solar", {})
    st.info(str(solar.get("guidance", "No solar guidance is available.")))
    st.caption(str(solar.get("orientation_note", "")))

    st.subheader("11 · Design review priorities")
    for recommendation in analysis.get("recommendations", []):
        st.write(f"• {recommendation}")

    st.subheader("12 · Concept analysis report")
    report = pd.DataFrame([
        ["Site area", metrics["site_area_m2"], "m²"], ["Building footprint", metrics["building_footprint_m2"], "m²"],
        ["Gross floor area", metrics["gross_floor_area_m2"], "m²"], ["Floor area ratio", metrics["floor_area_ratio"], "ratio"],
        ["Green/open space", metrics["green_area_m2"], "m²"], ["Other open area", metrics["other_open_area_m2"], "m²"],
        ["Building height", metrics["building_height_m"], "m"], ["Estimated parking", metrics["estimated_parking_spaces"], "spaces"],
        ["Setback envelope", metrics["setback_envelope_m2"], "m²"], ["Setback-limited footprint", metrics["setback_limited_footprint_m2"], "m²"],
        ["Setback reduction", metrics["setback_reduction_pct"], "%"], ["Open space", metrics["open_space_pct"], "%"],
        ["Selected net floor / level", selected_design["net_floor_area_m2"], "m²"], ["Selected core", selected_design["core_area_m2"], "m²"],
        ["Selected design score", selected_design["design_score"], "/100"],
    ], columns=["Parameter", "Value", "Unit"])
    st.dataframe(report, use_container_width=True, hide_index=True)
    st.download_button("Download architecture analysis CSV", report.to_csv(index=False).encode("utf-8"), "cityscout_architecture_analysis.csv", "text/csv", key="architecture_analysis_download")
