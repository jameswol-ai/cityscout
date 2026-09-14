"""Building design cockpit combining program, core, circulation and structure."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .building_program import ProgramParameters, core_geometry, program_allocation, circulation_assessment
from .building_systems import system_summary
from .parametric_design import floor_plate_dimensions
from .structural_grid import structural_summary
from .ui import page_header


def render_building_design() -> None:
    page_header("Building Design Cockpit")
    st.caption("Early-stage building program, floor-plate, core, circulation, vertical-systems and structural-grid study. Outputs are conceptual planning proxies and require project-specific professional verification.")

    with st.expander("01 · Building program inputs", expanded=True):
        c1, c2, c3 = st.columns(3)
        gfa = c1.number_input("Gross floor area (m²)", min_value=1.0, value=4000.0, step=100.0, key="bd_gfa")
        floors = c2.number_input("Floors", min_value=1, max_value=200, value=4, step=1, key="bd_floors")
        efficiency = c3.slider("Net efficiency (%)", 40.0, 95.0, 82.0, 1.0, key="bd_efficiency")
        c4, c5, c6 = st.columns(3)
        core_ratio = c4.slider("Core ratio (%)", 5.0, 30.0, 12.0, 0.5, key="bd_core")
        circulation_ratio = c5.slider("Circulation ratio (%)", 0.0, 30.0, 8.0, 0.5, key="bd_circ")
        service_ratio = c6.slider("Service/support ratio (%)", 0.0, 25.0, 5.0, 0.5, key="bd_service")
        c7, c8, c9 = st.columns(3)
        public = c7.slider("Public (%)", 0.0, 100.0, 20.0, 5.0, key="bd_public")
        commercial = c8.slider("Commercial (%)", 0.0, 100.0, 55.0, 5.0, key="bd_commercial")
        office = c9.slider("Office (%)", 0.0, 100.0, 25.0, 5.0, key="bd_office")
        c10, c11, c12 = st.columns(3)
        residential = c10.slider("Residential (%)", 0.0, 100.0, 0.0, 5.0, key="bd_residential")
        amenity = c11.slider("Amenity (%)", 0.0, 100.0, 20.0, 5.0, key="bd_amenity")
        location = c12.selectbox("Core location", ["Central", "North", "South", "East", "West"], key="bd_core_location")
        structural_system = st.selectbox("Structural system", ["Reinforced concrete frame", "Steel frame", "Mass timber frame", "Hybrid frame"], key="bd_structural_system")
        target_span = st.slider("Target structural span (m)", 3.0, 15.0, 7.5, 0.5, key="bd_structural_span")
        floor_load = st.number_input("Conceptual floor load (kPa)", min_value=1.0, max_value=20.0, value=5.0, step=0.5, key="bd_floor_load")

    params = ProgramParameters(gfa, int(floors), efficiency, core_ratio, circulation_ratio, service_ratio, public, residential, commercial, office, amenity, location)
    allocation = program_allocation(params)
    geometry = core_geometry(allocation["floor_plate_m2"], allocation["core_area_per_floor_m2"], location)
    circulation = circulation_assessment(params)
    systems = system_summary(allocation["floor_plate_m2"], allocation["core_area_per_floor_m2"], int(floors), gfa)
    plate = floor_plate_dimensions(allocation["floor_plate_m2"], 1.4)
    structural = structural_summary(plate["width_m"], plate["depth_m"], target_span, floor_load, structural_system)

    st.subheader("02 · Floor plate & area balance")
    k = st.columns(6)
    metrics = [("GFA", allocation["gfa_m2"], "{:,.0f} m²"), ("Net area", allocation["net_area_m2"], "{:,.0f} m²"), ("Floor plate", allocation["floor_plate_m2"], "{:,.0f} m²"), ("Core / floor", allocation["core_area_per_floor_m2"], "{:,.0f} m²"), ("Circulation", allocation["circulation_area_m2"], "{:,.0f} m²"), ("Service", allocation["service_area_m2"], "{:,.0f} m²")]
    for col, (label, value, fmt) in zip(k, metrics):
        col.metric(label, fmt.format(value))
    area_df = pd.DataFrame([["Net area", allocation["net_area_m2"]], ["Core", allocation["core_area_m2"]], ["Circulation", allocation["circulation_area_m2"]], ["Service / support", allocation["service_area_m2"]], ["Functional program", allocation["functional_area_m2"]]], columns=["Component", "Area m²"])
    st.bar_chart(area_df.set_index("Component"), use_container_width=True)
    st.dataframe(area_df.round(1), use_container_width=True, hide_index=True)

    st.subheader("03 · Program allocation")
    program_rows = [[name, value, allocation["program_balance_pct"].get(name, 0.0)] for name, value in allocation["program_area_m2"].items()]
    program_df = pd.DataFrame(program_rows, columns=["Program", "Area m²", "Share %"])
    st.dataframe(program_df.round(1), use_container_width=True, hide_index=True)
    if not program_df.empty:
        st.bar_chart(program_df.set_index("Program")[["Area m²"]], use_container_width=True)

    st.subheader("04 · Core geometry")
    g = st.columns(5)
    g[0].metric("Core location", geometry["location"])
    g[1].metric("Core area", f"{geometry['core_area_m2']:,.1f} m²")
    g[2].metric("Core width", f"{geometry['core_side_m']:.1f} m")
    g[3].metric("Floor plate side", f"{geometry['floor_plate_side_m']:.1f} m")
    g[4].metric("Core position", f"{geometry['center_x_fraction']:.2f}, {geometry['center_y_fraction']:.2f}")

    st.subheader("05 · Circulation & vertical systems")
    a, b, c, d = st.columns(4)
    a.metric("Circulation score", f"{circulation['score']:.0f}/100")
    b.metric("Conceptual lifts", str(systems["vertical"]["lifts"]))
    c.metric("Conceptual stairs", str(systems["vertical"]["stairs"]))
    d.metric("Service shafts", str(systems["vertical"]["service_shafts"]))
    st.write(f"Assessment: **{circulation['assessment']}**")
    st.info(str(systems["vertical"]["note"]))

    st.subheader("06 · Generative structural grid")
    s = st.columns(6)
    s[0].metric("Structural system", structural["members"]["system"])
    s[1].metric("X bays", structural["grid"]["bays_x"])
    s[2].metric("Y bays", structural["grid"]["bays_y"])
    s[3].metric("X spacing", f"{structural['grid']['x_spacing_m']:.2f} m")
    s[4].metric("Y spacing", f"{structural['grid']['y_spacing_m']:.2f} m")
    s[5].metric("Columns", structural["grid"]["column_count"])
    st.write(f"The structural grid is regenerated from the current floor plate: **{plate['width_m']:.1f} × {plate['depth_m']:.1f} m**.")
    grid_rows = [["X", i + 1, value] for i, value in enumerate(structural["grid"]["grid_lines_x"])] + [["Y", i + 1, value] for i, value in enumerate(structural["grid"]["grid_lines_y"])]
    st.dataframe(pd.DataFrame(grid_rows, columns=["Axis", "Grid line", "Coordinate m"]).round(3), use_container_width=True, hide_index=True)
    sm = st.columns(4)
    sm[0].metric("Beam", f"{structural['members']['conceptual_beam_width_mm']} × {structural['members']['conceptual_beam_depth_mm']} mm")
    sm[1].metric("Column", f"{structural['members']['conceptual_column_width_mm']} mm concept")
    sm[2].metric("Slab", f"{structural['members']['conceptual_slab_thickness_mm']} mm concept")
    sm[3].metric("Tributary area", f"{structural['grid']['tributary_area_m2']:.1f} m²")
    st.warning(structural["members"]["warning"])
    st.caption("Changing GFA, floor count, core ratio, or structural span changes the generated floor plate and structural grid. This is a generative coordination aid, not a final structural model.")

    st.subheader("07 · Structural scheme comparison")
    schemes = pd.DataFrame(structural["schemes"])
    display = schemes[["system", "governing_span_m", "bays_x", "bays_y", "column_count", "grid_efficiency_score"]].copy()
    display.columns = ["System", "Governing span m", "X bays", "Y bays", "Columns", "Grid efficiency score"]
    st.dataframe(display.round(2), use_container_width=True, hide_index=True)
    st.bar_chart(schemes.set_index("system")[["grid_efficiency_score"]], use_container_width=True)

    st.subheader("08 · Design coordination checks")
    checks = [("Net efficiency", allocation["parameters"]["efficiency_pct"] >= 70, "Review if below 70%"), ("Core ratio", 8 <= allocation["parameters"]["core_ratio_pct"] <= 20, "Check vertical transport, shafts and egress strategy"), ("Circulation", 5 <= allocation["parameters"]["circulation_ratio_pct"] <= 20, "Confirm actual planning and egress geometry"), ("Structural span", float(target_span) <= 12, "Longer spans require detailed structural analysis"), ("Grid regularity", abs(structural["grid"]["x_spacing_m"] - structural["grid"]["y_spacing_m"]) / max(structural["grid"]["x_spacing_m"], structural["grid"]["y_spacing_m"], 1.0) <= 0.35, "Consider rationalising bay spacing")]
    check_df = pd.DataFrame([[name, "Pass" if ok else "Review", note] for name, ok, note in checks], columns=["Check", "Status", "Action"])
    st.dataframe(check_df, use_container_width=True, hide_index=True)
    st.caption("All structural quantities are conceptual starting points. Final design requires full load combinations, material properties, lateral stability, foundations, geotechnical data, fire strategy, seismic/wind assessment and applicable codes.")
