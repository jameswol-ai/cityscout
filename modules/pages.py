"""Streamlit page renderers for CityScout."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from html import escape

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from .config import APP_PRIMARY
from .maps import parse_map_link, fetch_explore_from_backend
from .places import add_place, update_place, delete_place, create_share_token, public_share_url
from .storage import user_media_dir
from .trip import (
    estimate_trip_costs,
    compute_distance_matrix,
    nearest_neighbor_order,
    two_opt_improve,
    build_route_polyline_coords,
    export_gpx,
)
from .ui import page_header
from .urban_design import page_architecture
from .ai_cityscout import page_ai_cityscout
from .intelligence import render_city_intelligence


def _places() -> list[dict]:
    """Return only dictionary records from session state."""
    value = st.session_state.get("places", [])
    if not isinstance(value, list):
        return []
    return [place for place in value if isinstance(place, dict)]


def _label(place: dict, fallback: str = "Unnamed place") -> str:
    return str(place.get("name") or fallback).strip() or fallback


def page_share() -> None:
    page_header("Share")
    places = _places()
    if not places:
        st.info("Add places or build a route before sharing.")
        return
    share_kind = st.radio("Share", ["Last route", "Selected places"], key="share_kind")
    password = st.text_input("Optional password", type="password", key="share_password")
    expiry = st.number_input("Expiry (hours)", min_value=1, max_value=8760, value=24, key="share_expiry")
    payload = st.session_state.get("last_route") if share_kind == "Last route" else {"places": places}
    if not payload:
        st.warning("No route is available yet. Build one in Trip Planner or share selected places.")
        return
    if st.button("Create share link", key="create_share_link"):
        token = create_share_token(payload, password=password, expiry_hours=int(expiry))
        if token:
            st.session_state.share_tokens[token] = payload
            st.success("Share link created")
            st.code(public_share_url(token))
        else:
            st.error("Could not create the share link.")


def _valid_coord(place: dict) -> tuple[float, float] | None:
    try:
        lat, lon = float(place.get("latitude")), float(place.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def _show_route(route_places: list[dict], coords: list[list[float]] | None = None) -> None:
    valid = [(p, _valid_coord(p)) for p in route_places if isinstance(p, dict)]
    valid = [(p, coord) for p, coord in valid if coord is not None]
    if not valid:
        st.warning("No valid coordinates are available for this route.")
        return
    fmap = folium.Map(location=valid[0][1], zoom_start=12, control_scale=True)
    for index, (place, coord) in enumerate(valid, start=1):
        folium.Marker(coord, tooltip=f"{index}. {_label(place)}", popup=_label(place)).add_to(fmap)
    if coords:
        clean_coords = []
        for point in coords:
            try:
                lat, lon = float(point[0]), float(point[1])
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    clean_coords.append([lat, lon])
            except (TypeError, ValueError, IndexError):
                continue
        if len(clean_coords) >= 2:
            folium.PolyLine(clean_coords, weight=5).add_to(fmap)
    st_folium(fmap, width=1000, height=520, key="trip_route_map")


def page_trip_planner() -> None:
    page_header("Trip Planner")
    places = _places()
    if len(places) < 2:
        st.info("Save at least two places to build a route.")
        return
    labels = [_label(place, f"Place {i + 1}") for i, place in enumerate(places)]
    selected = st.multiselect("Places to visit", labels, default=labels[:2], key="trip_selected_places")
    selected_indices = [labels.index(label) for label in selected]
    if len(selected_indices) < 2:
        st.warning("Select at least two places.")
        return
    start_label = st.selectbox("Starting place", selected, key="trip_start")
    mode = st.selectbox("Travel mode", ["driving", "walking", "cycling"], key="trip_mode")
    round_trip = st.checkbox("Return to start", key="trip_round_trip")
    visit_minutes = st.number_input("Visit duration (minutes)", min_value=0, max_value=1440, value=60, key="trip_visit_minutes")
    chosen = [places[i] for i in selected_indices]
    start = selected.index(start_label)
    matrix = compute_distance_matrix(chosen, mode=mode)
    if not matrix:
        st.error("Unable to calculate distances for the selected places.")
        return
    order = nearest_neighbor_order(matrix, start=start)
    if not order:
        st.error("No reachable route was found for the selected places.")
        return
    order = two_opt_improve(order, matrix, round_trip=round_trip)
    route_places = [chosen[i] for i in order if 0 <= i < len(chosen)]
    if len(route_places) < 2:
        st.error("The generated route is incomplete.")
        return
    coords = build_route_polyline_coords(route_places, mode=mode)
    _show_route(route_places, coords)
    costs = estimate_trip_costs(matrix, order, round_trip=round_trip, visit_minutes=int(visit_minutes))
    st.subheader("Trip estimate")
    st.dataframe(pd.DataFrame([costs]), use_container_width=True, hide_index=True)
    st.session_state.last_route = {"places": route_places, "mode": mode, "round_trip": round_trip, "costs": costs, "created_at": datetime.now(timezone.utc).isoformat()}
    gpx = export_gpx(route_places, coords or [])
    if gpx:
        st.download_button("Download GPX", gpx, file_name="cityscout-trip.gpx", mime="application/gpx+xml", key="trip_gpx_download")


def page_add_place() -> None:
    page_header("Add Place")
    categories = list(dict.fromkeys([str(x) for x in st.session_state.get("categories", []) if str(x).strip()])) or ["Other"]
    with st.form("add_place_form"):
        name = st.text_input("Name", key="add_name")
        link = st.text_input("Map link (optional)", key="add_link")
        description = st.text_area("Description", key="add_description")
        category = st.selectbox("Category", categories, key="add_category")
        cost = st.selectbox("Cost Tier", ["$", "$$", "$$$", "$$$$"], index=1, key="add_cost")
        favorite = st.checkbox("Favorite", key="add_favorite")
        tags = st.text_input("Tags (comma separated)", key="add_tags")
        submitted = st.form_submit_button("Add place")
    if submitted:
        coords = parse_map_link(link) if link.strip() else None
        if not coords:
            st.error("Enter a valid map link with coordinates.")
        elif not name.strip():
            st.error("Enter a place name.")
        else:
            add_place(name.strip(), coords[0], coords[1], description.strip(), category, favorite, tags=[x.strip() for x in tags.split(",") if x.strip()], cost_tier=cost, source_link=link.strip())
            st.success("Place added.")


def page_places() -> None:
    page_header("Places")
    search = st.text_input("Search places by name or description", key="search_places")
    categories = list(dict.fromkeys([str(x) for x in st.session_state.get("categories", [])]))
    category = st.selectbox("Filter category", ["All"] + categories, key="places_category_filter")
    favorites = st.checkbox("Show favorites only", key="places_favorites_only")
    items = _places()
    query = search.strip().lower()
    if query:
        items = [p for p in items if query in (str(p.get("name", "")) + " " + str(p.get("description", ""))).lower()]
    if category != "All":
        items = [p for p in items if p.get("category") == category]
    if favorites:
        items = [p for p in items if bool(p.get("favorite"))]
    if not items:
        st.info("No places match the filters.")
        return
    for index, place in enumerate(items):
        name = _label(place)
        category_name = str(place.get("category") or "Other")
        cost = str(place.get("cost_tier") or "$$")
        st.markdown(f"**{escape(name)}** | *{escape(category_name)}* | Cost: `{escape(cost)}`")
        if place.get("address"): st.caption(str(place["address"]))
        if place.get("description"): st.write(str(place["description"]))
        coord = _valid_coord(place)
        st.write(f"📍 {coord[0]:.6f}, {coord[1]:.6f}" if coord else "📍 Coordinates unavailable")
        place_id = str(place.get("id") or f"index_{index}")
        a, b = st.columns(2)
        if a.button("Delete", key=f"del_{place_id}"):
            if place.get("id") is not None: delete_place(place["id"])
            st.rerun()
        label = "Unfavorite" if place.get("favorite") else "Mark Favorite"
        if b.button(label, key=f"fav_{place_id}"):
            if place.get("id") is not None: update_place(place["id"], favorite=not bool(place.get("favorite", False)))
            st.rerun()
        st.divider()


def page_categories() -> None:
    page_header("Categories")
    if not isinstance(st.session_state.get("categories"), list): st.session_state.categories = []
    new_category = st.text_input("New category name", key="new_cat")
    if st.button("Add category", key="add_category"):
        category = new_category.strip()
        if not category: st.warning("Enter a category name.")
        elif category in st.session_state.categories: st.info("That category already exists.")
        else:
            st.session_state.categories.append(category)
            st.success("Category added")
    st.write(", ".join(st.session_state.categories))


def page_dashboard() -> None:
    render_city_intelligence(_places())


def page_explore() -> None:
    page_header("Explore")
    city = st.text_input("City (optional)", key="explore_city")
    category = st.selectbox("Category (optional)", ["any", "restaurants", "attractions", "events", "nightlife", "shopping"], key="explore_cat")
    if st.button("Fetch Explore", key="fetch_explore"):
        result = fetch_explore_from_backend(city, category)
        st.session_state.explore_results = result if isinstance(result, list) else []
    results = st.session_state.get("explore_results", [])
    if not isinstance(results, list): results = []
    for index, result in enumerate(results):
        if not isinstance(result, dict): continue
        name = _label(result)
        st.markdown(f"**{escape(name)}**")
        if result.get("description"): st.caption(str(result["description"]))
        if st.button(f"Add {name} to my places", key=f"add_explore_{index}"):
            add_place(name, result.get("latitude", 0), result.get("longitude", 0), result.get("description", ""), result.get("category", "Other"), cost_tier="$$")
            st.success("Added")


def page_settings() -> None:
    page_header("Settings")
    st.write(f"Logged in as: **{escape(str(st.session_state.get('username') or 'guest'))}**")
    st.write(f"Authentication: **{escape(str(st.session_state.get('auth_mode') or 'unknown'))}**")
