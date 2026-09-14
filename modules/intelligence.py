"""City intelligence analytics for CityScout."""
from __future__ import annotations

from math import cos, radians
from statistics import mean

import pandas as pd
import streamlit as st

from .architecture import SiteParameters, build_analysis
from .gis import valid_places, city_metrics


def _distance_km(a: dict, b: dict) -> float:
    lat1, lon1 = float(a["latitude"]), float(a["longitude"])
    lat2, lon2 = float(b["latitude"]), float(b["longitude"])
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    x = dlon * cos(radians((lat1 + lat2) / 2.0))
    return 111.32 * (x * x + dlat * dlat) ** 0.5


def city_intelligence(places: list[dict]) -> dict:
    """Build deterministic, data-only city intelligence metrics."""
    items = valid_places(places)
    metrics = city_metrics(items)
    if len(items) < 2:
        return {**metrics, "nearest_pair_km": None, "average_nearest_km": None}

    nearest = []
    minimum_pair = float("inf")
    for index, place in enumerate(items):
        distances = [_distance_km(place, other) for j, other in enumerate(items) if j != index]
        if distances:
            nearest.append(min(distances))
        for other in items[index + 1 :]:
            minimum_pair = min(minimum_pair, _distance_km(place, other))

    return {
        **metrics,
        "nearest_pair_km": minimum_pair if minimum_pair != float("inf") else None,
        "average_nearest_km": mean(nearest) if nearest else None,
    }


def category_table(places: list[dict]) -> pd.DataFrame:
    items = valid_places(places)
    rows = []
    counts: dict[str, int] = {}
    favorites: dict[str, int] = {}
    for place in items:
        category = str(place.get("category") or "Other").strip() or "Other"
        counts[category] = counts.get(category, 0) + 1
        favorites[category] = favorites.get(category, 0) + int(bool(place.get("favorite")))
    for category in sorted(counts):
        rows.append({"Category": category, "Places": counts[category], "Favorites": favorites[category], "Share": counts[category] / len(items)})
    return pd.DataFrame(rows)


def render_city_intelligence(places: list[dict]) -> None:
    """Render the City Intelligence dashboard."""
    st.markdown("<div class='card'><h3 style='margin:0'>City Intelligence Dashboard</h3></div>", unsafe_allow_html=True)
    st.caption("Deterministic analytics from your saved GIS dataset. Recommendations are kept separate from observed data.")

    intelligence = city_intelligence(places)
    a, b, c, d = st.columns(4)
    a.metric("Mapped Places", intelligence["places"])
    b.metric("Favorites", intelligence["favorites"])
    c.metric("Categories", intelligence["categories"])
    d.metric("Footprint", f"{intelligence['footprint_km2']:.1f} km²")

    if not places:
        st.info("Add places to build the city intelligence dataset.")
        return

    e, f = st.columns(2)
    e.metric("Nearest Place Pair", "N/A" if intelligence["nearest_pair_km"] is None else f"{intelligence['nearest_pair_km']:.2f} km")
    f.metric("Average Nearest Distance", "N/A" if intelligence["average_nearest_km"] is None else f"{intelligence['average_nearest_km']:.2f} km")

    table = category_table(places)
    if not table.empty:
        st.markdown("### Category intelligence")
        st.bar_chart(table.set_index("Category")["Places"], use_container_width=True)
        display = table.copy()
        display["Share"] = (display["Share"] * 100).round(1).astype(str) + "%"
        st.dataframe(display, use_container_width=True, hide_index=True)

    with st.expander("Concept site intelligence", expanded=False):
        st.caption("Use this as an early-stage planning aid, not as a statutory or engineering determination.")
        p1, p2, p3 = st.columns(3)
        with p1:
            area = st.number_input("Site area (m²)", min_value=1.0, value=1000.0, key="intel_site_area")
            coverage = st.slider("Site coverage (%)", 1, 100, 40, key="intel_coverage")
        with p2:
            floors = st.number_input("Floors", min_value=1, max_value=100, value=4, key="intel_floors")
            height = st.number_input("Floor height (m)", min_value=2.0, max_value=10.0, value=3.2, key="intel_height")
        with p3:
            green = st.slider("Green ratio (%)", 0, 100, 25, key="intel_green")
            parking = st.number_input("Parking / 100 m²", min_value=0.0, value=1.0, key="intel_parking")
        analysis = build_analysis(SiteParameters(site_area_m2=area, site_coverage_pct=coverage, floors=int(floors), floor_height_m=height, green_ratio_pct=green, parking_per_100m2=parking), places)
        site_metrics = analysis.get("site_metrics", {})
        u1, u2, u3 = st.columns(3)
        u1.metric("Developable Footprint", f"{site_metrics.get('buildable_footprint_m2', 0):,.0f} m²")
        u2.metric("Gross Floor Area", f"{site_metrics.get('gross_floor_area_m2', 0):,.0f} m²")
        u3.metric("Estimated Parking", f"{site_metrics.get('parking_spaces', 0):,.0f}")
