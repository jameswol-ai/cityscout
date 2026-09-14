"""AI CityScout assistant with Gemini support and deterministic local fallback."""
from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd
import requests
import streamlit as st

from .architecture import SiteParameters, build_analysis
from .ui import page_header

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "30"))


def _place_context(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": p.get("name", "Unnamed"),
            "category": p.get("category", "Other"),
            "latitude": p.get("latitude"),
            "longitude": p.get("longitude"),
            "favorite": bool(p.get("favorite")),
            "cost_tier": p.get("cost_tier", "$$"),
            "address": p.get("address", ""),
            "description": p.get("description", ""),
        }
        for p in places[:100]
    ]


def build_ai_context(places: list[dict[str, Any]], params: SiteParameters) -> dict[str, Any]:
    analysis = build_analysis(params)
    return {
        "places": _place_context(places),
        "place_count": len(places),
        "favorite_count": sum(bool(p.get("favorite")) for p in places),
        "categories": sorted({p.get("category", "Other") for p in places}),
        "site_analysis": analysis,
    }


def _local_response(mode: str, context: dict[str, Any]) -> str:
    places = context["places"]
    analysis = context["site_analysis"]
    category_counts = pd.Series([p["category"] for p in places]).value_counts().to_dict() if places else {}
    top_category = max(category_counts, key=category_counts.get) if category_counts else "No category yet"
    walk = analysis["walkability"]
    performance = analysis["urban_performance"]

    if mode == "Place Recommendations":
        if not places:
            return "Add a few places first. CityScout can then rank them by category, favorites, cost tier, and geographic context."
        favorites = [p["name"] for p in places if p["favorite"]]
        return (f"Your current place set contains {len(places)} places across {len(category_counts)} categories. "
                f"The strongest category is {top_category}. "
                f"Favorites include {', '.join(favorites[:5]) if favorites else 'none yet'}. "
                "For a balanced city itinerary, combine one attraction, one food destination, one public-space or park stop, and a nearby optional stop.")
    if mode == "Trip Advisor":
        return (f"You have {len(places)} saved places. A practical planning strategy is to cluster stops geographically, "
                "start with a high-priority favorite, and avoid unnecessary backtracking. Use Trip Planner for route optimization and budget estimation.")
    if mode == "Site Analysis":
        return (f"The concept site supports approximately {analysis['site_metrics']['gross_floor_area_m2']:,.0f} m² of gross floor area "
                f"under the supplied assumptions. Estimated green area is {analysis['site_metrics']['green_area_m2']:,.0f} m². "
                f"The walkability score is {walk['score']:.0f}/100. Treat these as concept-stage indicators, not statutory approvals.")
    if mode == "Urban Design Review":
        return (f"Urban performance is led by pedestrian access at {performance['walkability']:.0f}/100, "
                f"with green infrastructure at {performance['green_infrastructure']:.0f}/100 and development intensity at "
                f"{performance['development_intensity']:.0f}/100. Consider active edges, shade, safe crossings, connected paths, "
                "and a legible public-to-private transition as the next design moves.")
    return (f"CityScout currently understands {len(places)} saved places, {context['favorite_count']} favorites, and "
            f"{len(category_counts)} place categories. The concept site has a walkability score of {walk['score']:.0f}/100. "
            "The data suggests starting with a connected public realm, clear movement hierarchy, and a compact mix of destinations.")


def _gemini_response(mode: str, question: str, context: dict[str, Any]) -> str | None:
    if not GEMINI_API_KEY:
        return None
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    prompt = f"""You are AI CityScout, a planning and city-exploration assistant.
Mode: {mode}
User request: {question or 'Provide the most useful analysis for this mode.'}
Context JSON:
{json.dumps(context, ensure_ascii=False, default=str)}

Give a concise, practical response with headings and bullets where useful. Distinguish observed data from recommendations. Do not invent missing facts. Architecture and urban-design observations are conceptual planning support only and are not statutory, legal, surveying, traffic, or engineering advice."""
    try:
        response = requests.post(
            endpoint,
            params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=GEMINI_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "\n".join(part.get("text", "") for part in parts).strip()
        return text or None
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None


def generate_cityscout_response(mode: str, question: str, context: dict[str, Any]) -> tuple[str, str]:
    generated = _gemini_response(mode, question, context)
    if generated:
        return generated, f"Gemini ({GEMINI_MODEL})"
    return _local_response(mode, context), "Local CityScout Insights"


def page_ai_cityscout() -> None:
    page_header("AI CityScout")
    st.caption("City intelligence, planning observations, recommendations, and trip guidance.")

    places = st.session_state.get("places", [])
    st.info(f"Context loaded: {len(places)} saved places • {sum(bool(p.get('favorite')) for p in places)} favorites")

    mode = st.selectbox(
        "Analysis mode",
        ["City Summary", "Site Analysis", "Urban Design Review", "Trip Advisor", "Place Recommendations"],
    )
    question = st.text_area("Ask CityScout", placeholder="What should I improve about this site or itinerary?")

    with st.expander("Concept site parameters", expanded=False):
        a, b, c = st.columns(3)
        site_area = a.number_input("Site area (m²)", min_value=100.0, value=1000.0, step=50.0)
        coverage = b.slider("Site coverage (%)", 5, 95, 40)
        floors = c.number_input("Floors", min_value=1, max_value=100, value=4, step=1)
        d, e, f = st.columns(3)
        floor_height = d.number_input("Floor height (m)", min_value=2.2, max_value=8.0, value=3.2, step=0.1)
        green_ratio = e.slider("Green ratio (%)", 0, 90, 25)
        parking = f.number_input("Parking / 100 m²", min_value=0.0, value=1.0, step=0.1)

    params = SiteParameters(
        site_area_m2=site_area,
        site_coverage_pct=coverage,
        floors=int(floors),
        floor_height_m=floor_height,
        green_ratio_pct=green_ratio,
        parking_per_100m2=parking,
    )
    context = build_ai_context(places, params)

    if st.button("Ask AI CityScout", type="primary", use_container_width=True):
        with st.spinner("Analyzing city context..."):
            answer, source = generate_cityscout_response(mode, question, context)
        st.session_state.ai_cityscout_answer = answer
        st.session_state.ai_cityscout_source = source

    answer = st.session_state.get("ai_cityscout_answer")
    if answer:
        st.markdown("### CityScout Analysis")
        st.caption(f"Source: {st.session_state.get('ai_cityscout_source', 'CityScout')}")
        st.markdown(answer)
        report = f"# AI CityScout Report\n\nMode: {mode}\n\n{answer}\n\n## Context\n\n{json.dumps(context, indent=2, ensure_ascii=False, default=str)}"
        st.download_button("Download report", report, "cityscout_ai_report.md", "text/markdown")

    with st.expander("Structured context", expanded=False):
        st.json(context)
