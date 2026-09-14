"""Conversational AI CityScout with Gemini support and a deterministic local fallback."""
from __future__ import annotations

import json
import math
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
MAX_CONTEXT_PLACES = 100
MAX_HISTORY_TURNS = 8

MODES = [
    "City Summary",
    "Site Analysis",
    "Urban Design Review",
    "Trip Advisor",
    "Place Recommendations",
]


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
        for p in places[:MAX_CONTEXT_PLACES]
    ]


def _distance_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat1, lon1 = float(a.get("latitude", 0)), float(a.get("longitude", 0))
    lat2, lon2 = float(b.get("latitude", 0)), float(b.get("longitude", 0))
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def spatial_summary(places: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [p for p in places if p.get("latitude") is not None and p.get("longitude") is not None]
    if len(valid) < 2:
        return {"mapped_places": len(valid), "nearest_pair_km": None, "furthest_pair_km": None}
    pairs = []
    for i, first in enumerate(valid):
        for second in valid[i + 1 :]:
            pairs.append((_distance_km(first, second), first["name"], second["name"]))
    nearest = min(pairs)
    furthest = max(pairs)
    return {
        "mapped_places": len(valid),
        "nearest_pair_km": round(nearest[0], 3),
        "nearest_pair": [nearest[1], nearest[2]],
        "furthest_pair_km": round(furthest[0], 3),
        "furthest_pair": [furthest[1], furthest[2]],
    }


def build_ai_context(places: list[dict[str, Any]], params: SiteParameters) -> dict[str, Any]:
    analysis = build_analysis(params)
    category_counts = pd.Series([p.get("category", "Other") for p in places]).value_counts().to_dict() if places else {}
    return {
        "places": _place_context(places),
        "place_count": len(places),
        "favorite_count": sum(bool(p.get("favorite")) for p in places),
        "category_counts": category_counts,
        "spatial_summary": spatial_summary(places),
        "site_analysis": analysis,
    }


def _local_response(mode: str, question: str, context: dict[str, Any]) -> str:
    places = context["places"]
    analysis = context["site_analysis"]
    counts = context["category_counts"]
    top_category = max(counts, key=counts.get) if counts else "No category yet"
    walk = analysis["walkability"]
    performance = analysis["urban_performance"]

    if mode == "Place Recommendations":
        if not places:
            return "Add a few places first. CityScout can then rank them by category, favorites, cost tier, and geographic context."
        favorites = [p["name"] for p in places if p["favorite"]]
        return (
            f"### Recommendation snapshot\n\n"
            f"You have **{len(places)}** saved places across **{len(counts)}** categories. "
            f"The strongest category is **{top_category}**. Favorites: **{', '.join(favorites[:5]) if favorites else 'none yet'}**.\n\n"
            "For a balanced itinerary, combine a high-priority attraction with food and a public-space or park stop, then cluster nearby destinations to reduce backtracking."
        )
    if mode == "Trip Advisor":
        spatial = context["spatial_summary"]
        nearest = spatial.get("nearest_pair_km")
        return (
            f"### Trip strategy\n\nYou have **{len(places)}** saved places. "
            + (f"The closest mapped pair is about **{nearest:.2f} km** apart. " if nearest is not None else "Add at least two mapped places for spatial advice. ")
            + "Start with a favorite or high-value stop, group destinations geographically, and use Trip Planner for actual route optimization and budget estimation."
        )
    if mode == "Site Analysis":
        return (
            f"### Concept site analysis\n\n"
            f"Gross floor area: **{analysis['site_metrics']['gross_floor_area_m2']:,.0f} m²**. "
            f"Estimated green area: **{analysis['site_metrics']['green_area_m2']:,.0f} m²**. "
            f"Walkability: **{walk['score']:.0f}/100**.\n\n"
            "The strongest next step is to test massing, access, servicing, open-space quality, and pedestrian connections against the intended program. "
            "These are concept-stage indicators, not statutory approvals."
        )
    if mode == "Urban Design Review":
        return (
            f"### Urban design review\n\n"
            f"Pedestrian access: **{performance['walkability']:.0f}/100**  \n"
            f"Green infrastructure: **{performance['green_infrastructure']:.0f}/100**  \n"
            f"Development intensity: **{performance['development_intensity']:.0f}/100**\n\n"
            "Prioritize active edges, shade, safe crossings, connected paths, clear entrances, and a legible public-to-private transition."
        )
    return (
        f"### City summary\n\nCityScout currently understands **{len(places)}** saved places, "
        f"**{context['favorite_count']}** favorites, and **{len(counts)}** categories. "
        f"The concept site has a walkability score of **{walk['score']:.0f}/100**.\n\n"
        "The current dataset supports a connected public realm, clear movement hierarchy, and a compact mix of destinations as useful design priorities."
    )


def _gemini_response(mode: str, question: str, context: dict[str, Any], history: list[dict[str, str]]) -> str | None:
    if not GEMINI_API_KEY:
        return None
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    history_text = "\n".join(
        f"{turn['role'].upper()}: {turn['content']}" for turn in history[-MAX_HISTORY_TURNS:]
    ) or "No previous conversation."
    prompt = f"""You are AI CityScout, a practical city-intelligence, urban-design and trip-planning assistant.
Mode: {mode}
Current user request: {question or 'Provide the most useful analysis for this mode.'}
Previous conversation:
{history_text}

Current structured CityScout context:
{json.dumps(context, ensure_ascii=False, default=str)}

Rules:
- Answer from the supplied context first.
- Clearly distinguish observed data from recommendations.
- Never invent missing places, regulations, measurements, prices, or transport facts.
- For architecture and urban design, provide conceptual planning support only, not statutory, legal, surveying, traffic, or engineering advice.
- Be concise but useful, using headings and bullets when appropriate.
"""
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


def generate_cityscout_response(
    mode: str, question: str, context: dict[str, Any], history: list[dict[str, str]] | None = None
) -> tuple[str, str]:
    generated = _gemini_response(mode, question, context, history or [])
    if generated:
        return generated, f"Gemini ({GEMINI_MODEL})"
    return _local_response(mode, question, context), "Local CityScout Insights"


def _init_ai_state() -> None:
    if "ai_cityscout_history" not in st.session_state:
        st.session_state.ai_cityscout_history = []


def page_ai_cityscout() -> None:
    _init_ai_state()
    page_header("AI CityScout")
    st.caption("Conversational city intelligence for places, GIS context, trips, architecture, and urban design.")

    places = st.session_state.get("places", [])
    st.info(f"Context loaded: {len(places)} saved places • {sum(bool(p.get('favorite')) for p in places)} favorites")

    mode = st.selectbox("Analysis mode", MODES)
    question = st.text_area(
        "Ask CityScout",
        placeholder="Which saved places are closest together?\nHow should I improve this site?\nCreate a one-day itinerary.",
        height=100,
    )

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

    ask_col, clear_col = st.columns([4, 1])
    if ask_col.button("Ask AI CityScout", type="primary", use_container_width=True):
        if not question.strip():
            st.warning("Enter a question for CityScout.")
        else:
            with st.spinner("Analyzing CityScout context..."):
                answer, source = generate_cityscout_response(
                    mode, question.strip(), context, st.session_state.ai_cityscout_history
                )
            st.session_state.ai_cityscout_history.append({"role": "user", "content": question.strip()})
            st.session_state.ai_cityscout_history.append({"role": "assistant", "content": answer})
            st.session_state.ai_cityscout_source = source

    if clear_col.button("Clear chat", use_container_width=True):
        st.session_state.ai_cityscout_history = []
        st.session_state.pop("ai_cityscout_source", None)
        st.rerun()

    if st.session_state.ai_cityscout_history:
        st.markdown("### CityScout Conversation")
        for turn in st.session_state.ai_cityscout_history:
            with st.chat_message("user" if turn["role"] == "user" else "assistant"):
                st.markdown(turn["content"])
        st.caption(f"Source: {st.session_state.get('ai_cityscout_source', 'CityScout')}")

        transcript = "# AI CityScout Conversation\n\n" + "\n\n".join(
            f"**{t['role'].title()}:**\n\n{t['content']}" for t in st.session_state.ai_cityscout_history
        )
        st.download_button("Download conversation", transcript, "cityscout_ai_conversation.md", "text/markdown")

    with st.expander("Structured context", expanded=False):
        st.json(context)
