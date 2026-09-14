"""Streamlit cockpit for conceptual structural grid studies."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .structural_grid import structural_scheme_options, structural_summary
from .ui import page_header


def render_structural_design() -> None:
    page_header("Structural Design Cockpit")
    st.caption("Conceptual structural-grid, framing-system and preliminary member-sizing study. Results are planning proxies only and require project-specific structural analysis, geotechnical information and code verification.")

    with st.expander("01 · Structural inputs", expanded=True):
        c1, c2, c3 = st.columns(3)
        width = c1.number_input("Floor plate width (m)", min_value=3.0, max_value=300.0, value=30.0, step=1.0, key="str_width")
        depth = c2.number_input("Floor plate depth (m)", min_value=3.0, max_value=300.0, value=20.0, step=1.0, key="str_depth")
        span = c3.slider("Target structural span (m)", 3.0, 15.0, 7.5, 0.5, key="str_span")
        c4, c5 = st.columns(2)
        load = c4.number_input("Conceptual floor load (kPa)", min_value=1.0, max_value=20.0, value=5.0, step=0.5, key="str_load")
        system = c5.selectbox("Structural system", ["Reinforced concrete frame", "Steel frame", "Mass timber frame", "Hybrid frame"], key="str_system")

    result = structural_summary(width, depth, span, load, system)
    grid, members = result["grid"], result["members"]

    st.subheader("02 · Structural grid")
    k = st.columns(6)
    values = [
        ("X bays", grid["bays_x"]), ("Y bays", grid["bays_y"]),
        ("X spacing", f"{grid['x_spacing_m']:.2f} m"), ("Y spacing", f"{grid['y_spacing_m']:.2f} m"),
        ("Columns", grid["column_count"]), ("Tributary area", f"{grid['tributary_area_m2']:.1f} m²"),
    ]
    for col, (label, value) in zip(k, values):
        col.metric(label, value)

    rows = []
    for ix, x in enumerate(grid["grid_lines_x"]):
        rows.append(["X", ix + 1, x])
    for iy, y in enumerate(grid["grid_lines_y"]):
        rows.append(["Y", iy + 1, y])
    st.dataframe(pd.DataFrame(rows, columns=["Axis", "Grid line", "Coordinate m"]).round(3), use_container_width=True, hide_index=True)

    st.subheader("03 · Preliminary member sizing")
    m = st.columns(4)
    m[0].metric("Beam width", f"{members['conceptual_beam_width_mm']} mm")
    m[1].metric("Beam depth", f"{members['conceptual_beam_depth_mm']} mm")
    m[2].metric("Column width", f"{members['conceptual_column_width_mm']} mm")
    m[3].metric("Slab thickness", f"{members['conceptual_slab_thickness_mm']} mm")
    st.warning(members["warning"])

    st.subheader("04 · Structural system comparison")
    schemes = pd.DataFrame(result["schemes"])
    display = schemes[["system", "strategy", "governing_span_m", "bays_x", "bays_y", "column_count", "grid_efficiency_score", "conceptual_beam_depth_mm", "conceptual_column_width_mm", "conceptual_slab_thickness_mm"]].copy()
    display.columns = ["System", "Strategy", "Governing span m", "X bays", "Y bays", "Columns", "Grid score", "Beam depth mm", "Column width mm", "Slab mm"]
    st.dataframe(display.round(2), use_container_width=True, hide_index=True)
    st.bar_chart(schemes.set_index("system")[["grid_efficiency_score"]], use_container_width=True)

    st.subheader("05 · Structural coordination checks")
    checks = [
        ["Span", 3.0 <= float(span) <= 12.0, "Review long-span systems above 12 m"],
        ["Grid regularity", abs(grid["x_spacing_m"] - grid["y_spacing_m"]) / max(grid["x_spacing_m"], grid["y_spacing_m"], 1.0) <= 0.35, "Consider rationalising bay spacing"],
        ["Floor load", 1.0 <= float(load) <= 10.0, "Confirm occupancy, finishes, partitions and equipment loads"],
        ["Member sizing", members["conceptual_beam_depth_mm"] >= 250 and members["conceptual_column_width_mm"] >= 250, "Perform full member design"],
    ]
    check_df = pd.DataFrame([[name, "Pass" if ok else "Review", note] for name, ok, note in checks], columns=["Check", "Status", "Action"])
    st.dataframe(check_df, use_container_width=True, hide_index=True)
    st.download_button("Download structural study CSV", display.to_csv(index=False), "cityscout_structural_study.csv", "text/csv", key="structural_study_csv")
