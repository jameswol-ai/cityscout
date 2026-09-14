"""Building design cockpit combining program, core and circulation studies."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .building_program import ProgramParameters, core_geometry, program_allocation, circulation_assessment
from .building_systems import system_summary
from .ui import page_header


def render_building_design() -> None:
    page_header("Building Design Cockpit")
    st.caption("Early-stage building program, floor-plate, core, circulation and vertical-systems study. All outputs are conceptual planning proxies and require project-specific professional verification.")

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

    params = ProgramParameters(gfa, int(floors), efficiency, core_ratio, circulation_ratio, service_ratio, public, residential, commercial, office, amenity, location)
    allocation = program_allocation(params)
    geometry = core_geometry(allocation["floor_plate_m2"], allocation["core_area_per_floor_m2"], location)
    circulation = circulation_assessment(params)
    systems = system_summary(allocation["floor_plate_m2"], allocation["core_area_per_floor_m2"], int(floors), gfa)

    st.subheader("02 · Floor plate & area balance")
    k = st.columns(6)
    metrics = [
        ("GFA", allocation["gfa_m2"], "{:,.0f} m²"),
        ("Net area", allocation["net_area_m2"], "{:,.0f} m²"),
        ("Floor plate", allocation["floor_plate_m2"], "{:,.0f} m²"),
        ("Core / floor", allocation["core_area_per_floor_m2"], "{:,.0f} m²"),
        ("Circulation", allocation["circulation_area_m2"], "{:,.0f} m²"),
        ("Service", allocation["service_area_m2"], "{:,.0f} m²"),
    ]
    for col, (label, value, fmt) in zip(k, metrics):
        col.metric(label, fmt.format(value))

    area_df = pd.DataFrame([
        ["Net area", allocation["net_area_m2"]], ["Core", allocation["core_area_m2"]],
        ["Circulation", allocation["circulation_area_m2"]], ["Service / support", allocation["service_area_m2"]],
        ["Functional program", allocation["functional_area_m2"]],
    ], columns=["Component", "Area m²"])
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
    system_df = pd.DataFrame([
        ["Conceptual population", systems["vertical"]["conceptual_population"], "persons"],
        ["Lifts", systems["vertical"]["lifts"], "count"],
        ["Stairs", systems["vertical"]["stairs"], "count"],
        ["Service shafts", systems["vertical"]["service_shafts"], "count"],
        ["Vertical cores", systems["vertical"]["vertical_core_count"], "count"],
        ["Usable program / floor", systems["circulation"]["usable_program_area_m2"], "m²"],
        ["Usable efficiency", systems["circulation"]["usable_efficiency_pct"], "%"],
    ], columns=["System metric", "Value", "Unit"])
    st.dataframe(system_df.round(2), use_container_width=True, hide_index=True)

    st.subheader("06 · Design coordination checks")
    checks = [
        ("Net efficiency", allocation["parameters"]["efficiency_pct"] >= 70, "Review if below 70%"),
        ("Core ratio", 8 <= allocation["parameters"]["core_ratio_pct"] <= 20, "Check vertical transport, shafts and egress strategy"),
        ("Circulation", 5 <= allocation["parameters"]["circulation_ratio_pct"] <= 20, "Confirm actual planning and egress geometry"),
        ("Program weights", sum([public, residential, commercial, office, amenity]) > 0, "At least one program category is required"),
    ]
    check_df = pd.DataFrame([[name, "Pass" if ok else "Review", note] for name, ok, note in checks], columns=["Check", "Status", "Action"])
    st.dataframe(check_df, use_container_width=True, hide_index=True)
    st.caption("These checks are design-coordination prompts only. They do not establish code compliance or minimum statutory requirements.")
