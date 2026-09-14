"""Deterministic urban and spatial intelligence for CityScout."""
from __future__ import annotations

from math import cos, radians, sqrt
from statistics import mean

import pandas as pd
import streamlit as st

from .architecture import SiteParameters, build_analysis
from .gis import city_metrics, valid_places


def _distance_km(a: dict, b: dict) -> float:
    """Approximate distance between two valid geographic records."""
    lat1, lon1 = float(a["latitude"]), float(a["longitude"])
    lat2, lon2 = float(b["latitude"]), float(b["longitude"])
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    x = dlon * cos(radians((lat1 + lat2) / 2.0))
    return 111.32 * sqrt(x * x + dlat * dlat)


def _category_counts(items: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for place in items:
        category = str(place.get("category") or "Other").strip() or "Other"
        counts[category] = counts.get(category, 0) + 1
    return counts


def city_intelligence(places: list[dict]) -> dict:
    """Build deterministic, data-only city intelligence metrics."""
    items = valid_places(places)
    metrics = city_metrics(items)
    if len(items) < 2:
        return {
            **metrics,
            "nearest_pair_km": None,
            "average_nearest_km": None,
            "walkability_proxy": None,
            "land_use_mix": None,
            "coverage_400m_proxy": None,
        }

    nearest: list[float] = []
    minimum_pair = float("inf")
    for index, place in enumerate(items):
        distances = [_distance_km(place, other) for j, other in enumerate(items) if j != index]
        if distances:
            nearest.append(min(distances))
        for other in items[index + 1 :]:
            minimum_pair = min(minimum_pair, _distance_km(place, other))

    average_nearest = mean(nearest) if nearest else None
    # A transparent proxy based only on observed saved-place spacing. It is not
    # a statutory walkability or transport-accessibility score.
    walkability_proxy = None if average_nearest is None else max(0.0, min(100.0, 100.0 * (1.0 - average_nearest / 2.0)))

    counts = _category_counts(items)
    total = len(items)
    shares = [count / total for count in counts.values()]
    herfindahl = sum(share * share for share in shares)
    land_use_mix = max(0.0, min(100.0, 100.0 * (1.0 - herfindahl)))

    # Count places within 400 m of another saved place. This is a dataset
    # coverage proxy, not a claim about actual population or service catchment.
    covered = sum(any(_distance_km(place, other) <= 0.4 for other in items if other is not place) for place in items)
    coverage_400m_proxy = 100.0 * covered / total

    return {
        **metrics,
        "nearest_pair_km": minimum_pair if minimum_pair != float("inf") else None,
        "average_nearest_km": average_nearest,
        "walkability_proxy": walkability_proxy,
        "land_use_mix": land_use_mix,
        "coverage_400m_proxy": coverage_400m_proxy,
    }


def category_table(places: list[dict]) -> pd.DataFrame:
    """Return category composition and favorite counts."""
    items = valid_places(places)
    rows = []
    counts = _category_counts(items)
    favorites: dict[str, int] = {}
    for place in items:
        category = str(place.get("category") or "Other").strip() or "Other"
        favorites[category] = favorites.get(category, 0) + int(bool(place.get("favorite")))
    total = len(items)
    for category in sorted(counts):
        rows.append({
            "Category": category,
            "Places": counts[category],
            "Favorites": favorites[category],
            "Share": counts[category] / total if total else 0.0,
        })
    return pd.DataFrame(rows)


def category_gaps(places: list[dict], expected_categories: list[str] | None = None) -> list[str]:
    """Identify configured categories with no saved places."""
    items = valid_places(places)
    observed = {str(p.get("category") or "Other").strip() for p in items}
    expected = expected_categories or ["Food", "Nightlife", "Shopping", "Attractions", "Parks", "Transit", "Other"]
    return [category for category in expected if category not in observed]


def site_suitability_score(places: list[dict], *, site_area_m2: float = 1000.0, coverage_pct: float = 40.0, green_pct: float = 25.0) -> dict:
    """Produce a transparent concept-stage site score from configurable inputs."""
    try:
        area = max(1.0, float(site_area_m2))
        coverage = max(0.0, min(100.0, float(coverage_pct)))
        green = max(0.0, min(100.0, float(green_pct)))
    except (TypeError, ValueError):
        area, coverage, green = 1000.0, 40.0, 25.0

    mapped = len(valid_places(places))
    density_component = min(40.0, mapped * 4.0)
    green_component = min(30.0, green * 0.3)
    coverage_component = max(0.0, 30.0 - abs(coverage - 40.0) * 0.5)
    score = round(min(100.0, density_component + green_component + coverage_component), 1)
    return {
        "score": score,
        "rating": "High" if score >= 70 else "Moderate" if score >= 45 else "Low",
        "basis": "Conceptual heuristic using saved-place count, green ratio, and site coverage only.",
        "site_area_m2": area,
    }


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

    e, f, g = st.columns(3)
    e.metric("Nearest Place Pair", "N/A" if intelligence["nearest_pair_km"] is None else f"{intelligence['nearest_pair_km']:.2f} km")
    f.metric("Average Nearest Distance", "N/A" if intelligence["average_nearest_km"] is None else f"{intelligence['average_nearest_km']:.2f} km")
    g.metric("400 m Coverage Proxy", "N/A" if intelligence["coverage_400m_proxy"] is None else f"{intelligence['coverage_400m_proxy']:.0f}%")

    h, i = st.columns(2)
    h.metric("Spacing / Walkability Proxy", "N/A" if intelligence["walkability_proxy"] is None else f"{intelligence['walkability_proxy']:.0f}/100")
    i.metric("Land-use Mix", "N/A" if intelligence["land_use_mix"] is None else f"{intelligence['land_use_mix']:.0f}/100")

    table = category_table(places)
    if not table.empty:
        st.markdown("### Category intelligence")
        st.bar_chart(table.set_index("Category")["Places"], use_container_width=True)
        display = table.copy()
        display["Share"] = (display["Share"] * 100).round(1).astype(str) + "%"
        st.dataframe(display, use_container_width=True, hide_index=True)

    gaps = category_gaps(places, st.session_state.get("categories"))
    if gaps:
        st.warning("Category gaps in the current saved dataset: " + ", ".join(gaps))

    with st.expander("Site suitability screening", expanded=False):
        st.caption("Conceptual screening only. It does not determine planning permission, engineering feasibility, or statutory compliance.")
        s1, s2, s3 = st.columns(3)
        with s1:
            area = st.number_input("Site area (m²)", min_value=1.0, value=1000.0, key="intel_site_area")
        with s2:
            coverage = st.slider("Site coverage (%)", 1, 100, 40, key="intel_coverage")
        with s3:
            green = st.slider("Green ratio (%)", 0, 100, 25, key="intel_green")
        suitability = site_suitability_score(places, site_area_m2=area, coverage_pct=coverage, green_pct=green)
        x, y = st.columns(2)
        x.metric("Concept Suitability", f"{suitability['score']:.1f}/100")
        y.metric("Screening Rating", suitability["rating"])
        st.caption(suitability["basis"])

    with st.expander("Concept site intelligence", expanded=False):
        st.caption("Use this as an early-stage planning aid, not as a statutory or engineering determination.")
        p1, p2, p3 = st.columns(3)
        with p1:
            area = st.number_input("Development site area (m²)", min_value=1.0, value=1000.0, key="intel_dev_area")
            coverage = st.slider("Development coverage (%)", 1, 100, 40, key="intel_dev_coverage")
        with p2:
            floors = st.number_input("Floors", min_value=1, max_value=100, value=4, key="intel_floors")
            height = st.number_input("Floor height (m)", min_value=2.0, max_value=10.0, value=3.2, key="intel_height")
        with p3:
            green = st.slider("Green ratio (%)", 0, 100, 25, key="intel_dev_green")
            parking = st.number_input("Parking / 100 m²", min_value=0.0, value=1.0, key="intel_parking")
        analysis = build_analysis(
            SiteParameters(
                site_area_m2=area,
                site_coverage_pct=coverage,
                floors=int(floors),
                floor_height_m=height,
                green_ratio_pct=green,
                parking_per_100m2=parking,
            ),
            places,
        )
        site_metrics = analysis.get("site_metrics", {})
        u1, u2, u3 = st.columns(3)
        u1.metric("Developable Footprint", f"{site_metrics.get('buildable_footprint_m2', 0):,.0f} m²")
        u2.metric("Gross Floor Area", f"{site_metrics.get('gross_floor_area_m2', 0):,.0f} m²")
        u3.metric("Estimated Parking", f"{site_metrics.get('parking_spaces', 0):,.0f}")
