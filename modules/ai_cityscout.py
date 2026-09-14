"""Conversational and actionable AI CityScout with Gemini, local tools, and agent orchestration."""
from __future__ import annotations

import json
import math
import os
import re
from typing import Any

import pandas as pd
import requests
import streamlit as st

from .architecture import SiteParameters, build_analysis
from .gis import map_center
from .intelligence import city_intelligence, category_table
from .trip import estimate_trip_costs
from .ui import page_header


def _env_int(name: str, default: int, minimum: int = 1, maximum: int = 300) -> int:
    try:
        return max(minimum, min(maximum, int(os.getenv(name, str(default)))))
    except (TypeError, ValueError):
        return default


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"
GEMINI_TIMEOUT = _env_int("GEMINI_TIMEOUT", 30, 3, 120)
MAX_CONTEXT_PLACES = 100
MAX_HISTORY_TURNS = 8
MAX_PROMPT_CHARS = 30000

MODES = ["Agent Mode", "City Summary", "Site Analysis", "Urban Design Review", "Trip Advisor", "Place Recommendations"]
TOOLS = ["Find Nearest Places", "Rank Saved Places", "Build Quick Itinerary", "Analyze Selected Site", "City Intelligence Report"]


def _mapped_places(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for place in places or []:
        if not isinstance(place, dict):
            continue
        try:
            lat, lon = float(place.get("latitude")), float(place.get("longitude"))
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        result.append({**place, "latitude": lat, "longitude": lon})
    return result


def _place_context(places):
    return [{"name": p.get("name", "Unnamed"), "category": p.get("category", "Other"), "latitude": p.get("latitude"), "longitude": p.get("longitude"), "favorite": bool(p.get("favorite")), "cost_tier": p.get("cost_tier", "$$"), "address": p.get("address", ""), "description": p.get("description", "")} for p in places[:MAX_CONTEXT_PLACES] if isinstance(p, dict)]


def _distance_km(a, b):
    lat1, lon1, lat2, lon2 = float(a["latitude"]), float(a["longitude"]), float(b["latitude"]), float(b["longitude"])
    r = 6371.0088; p1, p2 = math.radians(lat1), math.radians(lat2); dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(max(0.0, min(1.0, h))))


def spatial_summary(places):
    valid = _mapped_places(places)
    if len(valid) < 2: return {"mapped_places": len(valid), "nearest_pair_km": None, "furthest_pair_km": None}
    pairs = [(_distance_km(a, b), a.get("name", "Unnamed"), b.get("name", "Unnamed")) for i, a in enumerate(valid) for b in valid[i + 1:]]
    nearest, furthest = min(pairs), max(pairs)
    return {"mapped_places": len(valid), "nearest_pair_km": round(nearest[0], 3), "nearest_pair": [nearest[1], nearest[2]], "furthest_pair_km": round(furthest[0], 3), "furthest_pair": [furthest[1], furthest[2]]}


def build_ai_context(places, params):
    safe_places = _mapped_places(places)
    center = map_center(safe_places) if safe_places else None
    analysis = build_analysis(params, safe_places, center=center)
    intelligence = city_intelligence(safe_places)
    counts = pd.Series([p.get("category", "Other") or "Other" for p in safe_places]).value_counts().to_dict() if safe_places else {}
    return {"places": _place_context(safe_places), "place_count": len(safe_places), "favorite_count": sum(bool(p.get("favorite")) for p in safe_places), "category_counts": counts, "spatial_summary": spatial_summary(safe_places), "city_intelligence": intelligence, "category_intelligence": category_table(safe_places).to_dict(orient="records"), "site_analysis": analysis}


def find_nearest_places(places, origin, limit=5):
    mapped, origins = _mapped_places(places), _mapped_places([origin])
    if not origins: return []
    origin_safe = origins[0]
    try: count = max(1, min(50, int(limit)))
    except (TypeError, ValueError): count = 5
    ranked = []
    for place in mapped:
        if place.get("name") == origin_safe.get("name") and place.get("latitude") == origin_safe.get("latitude") and place.get("longitude") == origin_safe.get("longitude"): continue
        ranked.append((_distance_km(origin_safe, place), place))
    ranked.sort(key=lambda item: item[0])
    return [{"name": p.get("name", "Unnamed"), "category": p.get("category", "Other"), "distance_km": round(d, 2), "favorite": bool(p.get("favorite"))} for d, p in ranked[:count]]


def rank_saved_places(places, category="All", favorites_first=True):
    candidates = [p for p in places if isinstance(p, dict) and (category == "All" or p.get("category", "Other") == category)]
    def score(p):
        return (40 if p.get("favorite") and favorites_first else 0) + min(len(str(p.get("description", ""))) / 10, 10) + {"$": 10, "$$": 7, "$$$": 4, "$$$$": 1}.get(p.get("cost_tier", "$$"), 5)
    ranked = sorted(candidates, key=score, reverse=True)
    return [{"rank": i + 1, "name": p.get("name", "Unnamed"), "category": p.get("category", "Other"), "score": round(score(p), 1), "favorite": bool(p.get("favorite")), "cost_tier": p.get("cost_tier", "$$")} for i, p in enumerate(ranked)]


def build_quick_itinerary(places, start_name=None, limit=6):
    mapped = _mapped_places(places)
    if not mapped: return {"stops": [], "total_km": 0.0, "estimated_activity_cost": 0.0}
    try: stop_limit = max(2, min(20, int(limit)))
    except (TypeError, ValueError): stop_limit = 6
    start = next((p for p in mapped if p.get("name") == start_name), None) if start_name else None
    start = start or next((p for p in mapped if p.get("favorite")), mapped[0])
    remaining = [p for p in mapped if p is not start]; order = [start]
    while remaining and len(order) < stop_limit:
        nxt = min(remaining, key=lambda p: _distance_km(order[-1], p)); order.append(nxt); remaining.remove(nxt)
    total_km = sum(_distance_km(a, b) for a, b in zip(order, order[1:]))
    costs = estimate_trip_costs(order, total_km, "walking")
    return {"stops": [{"order": i + 1, "name": p.get("name", "Unnamed"), "category": p.get("category", "Other"), "cost_tier": p.get("cost_tier", "$$")} for i, p in enumerate(order)], "total_km": round(total_km, 2), "estimated_activity_cost": round(costs.get("activity_cost", 0.0), 2)}


def _intent(text):
    value = str(text or "").lower()
    if re.search(r"\b(near|nearest|closest|close to|around)\b", value): return "nearest"
    if re.search(r"\b(itinerary|tour|day trip|route|visit|stops)\b", value): return "itinerary"
    if re.search(r"\b(site|massing|development|building|plot|floor area|green area)\b", value): return "site"
    if re.search(r"\b(rank|best|recommend|favorite|top|priorit)\b", value): return "rank"
    if re.search(r"\b(report|intelligence|overview|summary|dashboard|coverage|catchment|gap)\b", value): return "report"
    return "summary"


def run_agent_task(question, places, context):
    intent = _intent(question)
    if intent == "nearest":
        mapped = _mapped_places(places)
        if not mapped: return {"intent": intent, "title": "Nearest Places", "message": "No mapped places are available yet.", "data": []}
        origin = next((p for p in mapped if p.get("favorite")), mapped[0])
        return {"intent": intent, "title": f"Places nearest to {origin.get('name', 'your starting place')}", "message": "Ranked by straight-line geographic distance.", "origin": origin.get("name"), "data": find_nearest_places(mapped, origin, 8)}
    if intent == "itinerary": return {"intent": intent, "title": "AI Quick Itinerary", "message": "Built from saved mapped places, favoring a favorite as the starting point when available.", "data": build_quick_itinerary(places, limit=min(8, max(2, len(_mapped_places(places)))))}
    if intent == "site": return {"intent": intent, "title": "AI Site Analysis", "message": "Concept-stage development indicators from the current site parameters.", "data": context["site_analysis"]}
    if intent == "rank": return {"intent": intent, "title": "Top Saved Places", "message": "Ranked using favorites, description richness, and cost accessibility.", "data": rank_saved_places(places)[:10]}
    if intent == "report": return {"intent": intent, "title": "City Intelligence Report", "message": "Combined city, spatial, category, coverage, and site intelligence.", "data": {"summary": {"places": len(places), "favorites": context["favorite_count"], "categories": context["category_counts"]}, "spatial": context["spatial_summary"], "intelligence": context["city_intelligence"], "category_intelligence": context["category_intelligence"], "site": context["site_analysis"], "top_places": rank_saved_places(places)[:10]}}
    return {"intent": intent, "title": "CityScout Summary", "message": "I can search nearby places, rank saved places, build an itinerary, analyze the site, or generate a city intelligence report.", "data": context["spatial_summary"]}


def _local_response(mode, question, context):
    places, analysis, counts = context["places"], context["site_analysis"], context["category_counts"]
    top_category = max(counts, key=counts.get) if counts else "No category yet"; walk = analysis["walkability"]; performance = analysis["urban_performance"]
    if mode == "Agent Mode":
        result = run_agent_task(question, places, context); return f"### {result['title']}\n\n{result['message']}\n\n" + json.dumps(result["data"], indent=2, default=str)
    if mode == "Place Recommendations": return f"### Recommendation snapshot\n\nYou have **{len(places)}** mapped places across **{len(counts)}** categories. The strongest category is **{top_category}**. Use the AI tools to rank places or build a quick itinerary."
    if mode == "Trip Advisor":
        nearest = context["spatial_summary"].get("nearest_pair_km"); return f"### Trip strategy\n\nYou have **{len(places)}** mapped places. " + (f"The closest mapped pair is about **{nearest:.2f} km** apart. " if nearest is not None else "Add at least two mapped places for spatial advice. ") + "Use Quick Itinerary for a deterministic first pass, then Trip Planner for actual route optimization."
    if mode == "Site Analysis": return f"### Concept site analysis\n\nGross floor area: **{analysis['site_metrics']['gross_floor_area_m2']:,.0f} m²**. Estimated green area: **{analysis['site_metrics']['green_area_m2']:,.0f} m²**. Walkability: **{walk['score']:.0f}/100**.\n\nThese are concept-stage indicators, not statutory approvals."
    if mode == "Urban Design Review": return f"### Urban design review\n\nPedestrian access: **{performance['walkability']:.0f}/100**  \nGreen infrastructure: **{performance['green_infrastructure']:.0f}/100**  \nDevelopment intensity: **{performance['development_intensity']:.0f}/100**\n\nPrioritize active edges, shade, safe crossings, connected paths, clear entrances, and a legible public-to-private transition."
    return f"### City summary\n\nCityScout currently understands **{len(places)}** mapped places, **{context['favorite_count']}** favorites, and **{len(counts)}** categories. The concept site has a walkability score of **{walk['score']:.0f}/100**."


def _gemini_response(mode, question, context, history):
    if not GEMINI_API_KEY: return None
    history_text = "\n".join(f"{t.get('role', 'user').upper()}: {str(t.get('content', ''))[:4000]}" for t in history[-MAX_HISTORY_TURNS:] if isinstance(t, dict)) or "No previous conversation."
    context_text = json.dumps(context, ensure_ascii=False, default=str)
    prompt = f"""You are AI CityScout, a practical city-intelligence, urban-design and trip-planning assistant.
Mode: {mode}
Current user request: {str(question)[:5000]}
Previous conversation:\n{history_text}\n
Current structured CityScout context:\n{context_text[:MAX_PROMPT_CHARS]}\n
Rules: Answer from supplied context first. Distinguish observed data from recommendations. Never invent missing places, regulations, measurements, prices, or transport facts. Architecture and urban design advice is conceptual only, not statutory or engineering advice. Be concise and useful."""
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    try:
        response = requests.post(endpoint, params={"key": GEMINI_API_KEY}, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=GEMINI_TIMEOUT); response.raise_for_status(); payload = response.json(); candidates = payload.get("candidates") or []
        if not candidates: return None
        parts = (candidates[0].get("content") or {}).get("parts") or []; text = "\n".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip(); return text or None
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError): return None


def generate_cityscout_response(mode, question, context, history=None):
    generated = _gemini_response(mode, question, context, history or []); return (generated, f"Gemini ({GEMINI_MODEL})") if generated else (_local_response(mode, question, context), "Local CityScout Insights")


def _init_ai_state():
    if "ai_cityscout_history" not in st.session_state or not isinstance(st.session_state.ai_cityscout_history, list): st.session_state.ai_cityscout_history = []
    if len(st.session_state.ai_cityscout_history) > MAX_HISTORY_TURNS * 2: st.session_state.ai_cityscout_history = st.session_state.ai_cityscout_history[-MAX_HISTORY_TURNS * 2:]


def page_ai_cityscout():
    _init_ai_state(); page_header("AI CityScout"); st.caption("Conversational intelligence plus actionable tools for your CityScout dataset.")
    places = st.session_state.get("places", []); places = places if isinstance(places, list) else []
    st.info(f"Context loaded: {len(places)} saved places • {sum(bool(p.get('favorite')) for p in places if isinstance(p, dict))} favorites")
    mode = st.selectbox("Analysis mode", MODES, key="ai_mode")
    question = st.text_area("Ask CityScout", placeholder="What are the biggest category gaps and which areas need more services?", height=100, key="ai_question")
    with st.expander("Concept site parameters", expanded=False):
        a, b, c = st.columns(3); site_area = a.number_input("Site area (m²)", min_value=100.0, value=1000.0, step=50.0, key="ai_site_area"); coverage = b.slider("Site coverage (%)", 5, 95, 40, key="ai_coverage"); floors = c.number_input("Floors", min_value=1, max_value=100, value=4, step=1, key="ai_floors")
        d, e, f = st.columns(3); floor_height = d.number_input("Floor height (m)", min_value=2.2, max_value=8.0, value=3.2, step=0.1, key="ai_floor_height"); green_ratio = e.slider("Green ratio (%)", 0, 90, 25, key="ai_green_ratio"); parking = f.number_input("Parking / 100 m²", min_value=0.0, value=1.0, step=0.1, key="ai_parking")
    params = SiteParameters(site_area_m2=site_area, site_coverage_pct=coverage, floors=int(floors), floor_height_m=floor_height, green_ratio_pct=green_ratio, parking_per_100m2=parking)
    context = build_ai_context(places, params)
    if mode == "Agent Mode":
        st.markdown("### 🧠 CityScout Agent"); st.caption("Describe the outcome you want. CityScout will choose and run a local tool sequence.")
        if st.button("Run Agent", type="primary", use_container_width=True, key="ai_run_agent"):
            if not question.strip(): st.warning("Describe what you want CityScout to accomplish.")
            else: st.session_state.ai_agent_result = run_agent_task(question.strip(), places, context)
        result = st.session_state.get("ai_agent_result")
        if result:
            st.markdown(f"#### {result.get('title', 'Agent result')}"); st.caption(result.get("message", "")); data = result.get("data", {}); st.dataframe(pd.DataFrame(data), use_container_width=True, hide_index=True) if isinstance(data, list) else st.json(data)
            if result.get("intent") == "report": st.download_button("Download agent report", json.dumps(data, indent=2, default=str), "cityscout_agent_report.json", "application/json", key="ai_download_agent_report")
    st.markdown("### AI Tools"); tool = st.selectbox("Choose an action", TOOLS, key="ai_tool")
    if tool == "Find Nearest Places":
        names = [p.get("name", "Unnamed") for p in _mapped_places(places)]
        if names:
            origin_name = st.selectbox("From place", names, key="ai_nearest_origin"); origin = next(p for p in _mapped_places(places) if p.get("name") == origin_name)
            if st.button("Find nearest", key="ai_nearest"): st.dataframe(pd.DataFrame(find_nearest_places(places, origin, 8)), use_container_width=True, hide_index=True)
        else: st.warning("Add at least two mapped places first.")
    elif tool == "Rank Saved Places":
        categories = ["All"] + sorted({p.get("category", "Other") for p in places if isinstance(p, dict)}); category = st.selectbox("Category", categories, key="ai_rank_category")
        if st.button("Rank places", key="ai_rank"): st.dataframe(pd.DataFrame(rank_saved_places(places, category)), use_container_width=True, hide_index=True)
    elif tool == "Build Quick Itinerary":
        names = [p.get("name", "Unnamed") for p in _mapped_places(places)]; start = st.selectbox("Starting place", ["Automatic"] + names, key="ai_itinerary_start"); max_limit = min(10, max(2, len(names))); limit = st.slider("Maximum stops", 2, max_limit, min(6, max_limit), key="ai_itinerary_limit") if names else 2
        if st.button("Build itinerary", key="ai_itinerary"):
            result = build_quick_itinerary(places, None if start == "Automatic" else start, limit); st.dataframe(pd.DataFrame(result["stops"]), use_container_width=True, hide_index=True); c1, c2 = st.columns(2); c1.metric("Estimated distance", f"{result['total_km']:.2f} km"); c2.metric("Estimated activity cost", f"${result['estimated_activity_cost']:.2f}")
    elif tool == "Analyze Selected Site":
        analysis = context["site_analysis"]; c1, c2, c3 = st.columns(3); c1.metric("Gross floor area", f"{analysis['site_metrics']['gross_floor_area_m2']:,.0f} m²"); c2.metric("Green area", f"{analysis['site_metrics']['green_area_m2']:,.0f} m²"); c3.metric("Walkability", f"{analysis['walkability']['score']:.0f}/100"); st.json(analysis)
    else:
        report = run_agent_task("generate city intelligence report", places, context)["data"]; st.json(report); st.download_button("Download city intelligence report", json.dumps(report, indent=2, default=str), "cityscout_intelligence_report.json", "application/json", key="ai_download_report")
    ask_col, clear_col = st.columns([4, 1])
    if ask_col.button("Ask AI CityScout", type="primary", use_container_width=True, key="ai_ask"):
        if not question.strip(): st.warning("Enter a question for CityScout.")
        else:
            with st.spinner("Analyzing CityScout context..."):
                answer, source = generate_cityscout_response(mode, question.strip(), context, st.session_state.ai_cityscout_history)
            st.session_state.ai_cityscout_history.extend([{"role": "user", "content": question.strip()}, {"role": "assistant", "content": answer}]); st.session_state.ai_cityscout_history = st.session_state.ai_cityscout_history[-MAX_HISTORY_TURNS * 2:]; st.session_state.ai_cityscout_source = source
    if clear_col.button("Clear chat", use_container_width=True, key="ai_clear_chat"):
        st.session_state.ai_cityscout_history = []; st.session_state.pop("ai_cityscout_source", None); st.session_state.pop("ai_agent_result", None); st.rerun()
    if st.session_state.ai_cityscout_history:
        st.markdown("### CityScout Conversation")
        for turn in st.session_state.ai_cityscout_history:
            role = "user" if turn.get("role") == "user" else "assistant"
            with st.chat_message(role): st.markdown(turn.get("content", ""))
        st.caption(f"Source: {st.session_state.get('ai_cityscout_source', 'CityScout')}")
        transcript = "# AI CityScout Conversation\n\n" + "\n\n".join(f"**{t.get('role', 'user').title()}:**\n\n{t.get('content', '')}" for t in st.session_state.ai_cityscout_history)
        st.download_button("Download conversation", transcript, "cityscout_ai_conversation.md", "text/markdown", key="ai_download_conversation")
    with st.expander("Structured context", expanded=False): st.json(context)
