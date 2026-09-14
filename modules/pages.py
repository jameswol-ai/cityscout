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


def _places() -> list[dict]:
    """Return only dictionary records from session state."""
    value = st.session_state.get("places", [])
    if not isinstance(value, list):
        return []
    return [place for place in value if isinstance(place, dict)]


def _label(place: dict, index: int | None = None) -> str:
    name = str(place.get("name") or (f"Place {index + 1}" if index is not None else "Unnamed place"))
    category = str(place.get("category") or "Other")
    cost = str(place.get("cost_tier") or "$$")
    return f"{name} ({cost}) — {category}"


def page_share() -> None:
    page_header("Share")
    st.write("Create a public share token for a trip or a list of places.")
    choice = st.selectbox("Share payload", ["Last computed route", "Selected saved places"], key="share_payload")

    if choice == "Selected saved places":
        places = _places()
        if not places:
            st.info("No saved places to share.")
            return
        labels = [_label(place, i) for i, place in enumerate(places)]
        selected = st.multiselect("Select places to share", range(len(labels)), format_func=lambda i: labels[i], key="share_places")
        if not selected:
            st.write("Select at least one place to share.")
            return
        payload = {"type": "places", "places": [places[i] for i in selected], "owner": st.session_state.get("username")}
    else:
        route = st.session_state.get("last_route")
        if not isinstance(route, dict):
            st.info("No last route computed yet.")
            return
        payload = {"type": "route", "route": route, "owner": st.session_state.get("username")}

    password = st.text_input("Optional password to protect the share (leave blank for none)", type="password", key="share_password")
    expires = st.number_input("Expires in (hours, 0 = never)", min_value=0, max_value=8760, value=0, step=1, key="share_expiry")
    if st.button("Create share token", key="create_share_token"):
        token = create_share_token(payload, password or None, expires or None)
        st.success("Share token created")
        st.code(str(token), language=None)
        url = public_share_url(token)
        if url:
            st.markdown(f"Public URL: {escape(str(url))}")


def _show_route(route: dict) -> None:
    costs = route.get("costs")
    if not isinstance(costs, dict):
        costs = estimate_trip_costs(route.get("ordered_places", []), route.get("total_km", 0), route.get("mode", "driving"))
    total_cost = float(costs.get("total_cost", 0) or 0)
    activity_cost = float(costs.get("activity_cost", 0) or 0)
    travel_cost = float(costs.get("travel_cost", 0) or 0)
    st.markdown(f"**Estimated Trip Expenses:** 💵 ${total_cost:.2f} total *(Activities: ${activity_cost:.2f} | Travel: ${travel_cost:.2f})*")

    coords = route.get("coords")
    ordered = route.get("ordered_places", [])
    if not isinstance(coords, list) or not coords:
        return
    valid_coords = []
    for coord in coords:
        if isinstance(coord, (list, tuple)) and len(coord) >= 2:
            try:
                lat, lon = float(coord[0]), float(coord[1])
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    valid_coords.append([lat, lon])
            except (TypeError, ValueError):
                continue
    if not valid_coords:
        return

    m = folium.Map(location=valid_coords[len(valid_coords) // 2], zoom_start=12, control_scale=True)
    folium.PolyLine(valid_coords, color=APP_PRIMARY, weight=5, opacity=0.85).add_to(m)
    if isinstance(ordered, list):
        for i, place in enumerate(ordered):
            if not isinstance(place, dict):
                continue
            lat, lon = place.get("latitude"), place.get("longitude")
            try:
                lat, lon = float(lat), float(lon)
            except (TypeError, ValueError):
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            name = str(place.get("name") or "Unnamed place")
            cost = str(place.get("cost_tier") or "$$")
            folium.Marker([lat, lon], tooltip=f"{i + 1}. {name} ({cost})").add_to(m)
    folium.TileLayer("CartoDB positron", attr="© CartoDB").add_to(m)
    st_folium(m, width=900, height=400, key="trip_route_map")


def page_trip_planner() -> None:
    page_header("Trip Planner & Budget Calculator")
    last_route = st.session_state.get("last_route")
    if isinstance(last_route, dict):
        st.markdown("**Last computed route**")
        st.write(f"- Stops: {len(last_route.get('ordered_places', []))}")
        st.write(f"- Distance: {float(last_route.get('total_km', 0) or 0):.2f} km")
        st.write(f"- Duration: {float(last_route.get('total_min', 0) or 0):.1f} min")
        _show_route(last_route)
        st.divider()

    places = _places()
    if not places:
        st.info("No saved places yet. Add places first.")
        return

    labels = [_label(place, i) for i, place in enumerate(places)]
    selected = st.multiselect("Select places to include (2+)", range(len(labels)), format_func=lambda i: labels[i], key="trip_selected_places")
    if len(selected) < 2:
        st.write("Select at least two places to plan a route.")
        return

    start = st.selectbox("Start from", selected, format_func=lambda i: labels[i], key="trip_start")
    mode = st.selectbox("Mode", ["driving", "walking", "cycling"], key="trip_mode")
    round_trip = st.checkbox("Round trip (return to start)", key="trip_round_trip")
    visit_duration = st.number_input("Visit duration per stop (minutes)", min_value=0, max_value=1440, value=0, step=5, key="trip_visit_duration")

    if st.button("Compute optimized route & budget", key="compute_trip_route"):
        subset = [places[i] for i in selected]
        with st.spinner("Computing pairwise distances & estimating budget..."):
            dist, _ = compute_distance_matrix(subset, mode)
        start_position = selected.index(start)
        order = nearest_neighbor_order(dist, start_position)
        order = two_opt_improve(order, dist)
        if not order:
            st.error("No valid route could be constructed from the selected places.")
            return
        if round_trip and order[-1] != order[0]:
            order.append(order[0])
        ordered = [subset[i] for i in order if 0 <= i < len(subset)]
        coords, km, minutes = build_route_polyline_coords(order, subset, mode)
        minutes += float(visit_duration) * max(0, len(ordered) - (1 if round_trip else 0))
        costs = estimate_trip_costs(ordered, km, mode)
        route = {
            "ordered_places": ordered,
            "coords": coords,
            "total_km": km,
            "total_min": minutes,
            "mode": mode,
            "costs": costs,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
        st.session_state.last_route = route
        st.success(f"Route computed — {len(ordered)} stops, {km:.2f} km, {minutes:.1f} min")
        st.info(f"💵 **Estimated Budget:** ${costs['total_cost']:.2f} (Activities: ${costs['activity_cost']:.2f} | Transit: ${costs['travel_cost']:.2f})")
        for i, place in enumerate(ordered, 1):
            name = str(place.get("name") or "Unnamed place")
            category = str(place.get("category") or "Other")
            tier = str(place.get("cost_tier") or "$$")
            st.markdown(f"{i}. **{name}** — {category} | Cost Tier: `{tier}`")
            if place.get("address"):
                st.caption(str(place["address"]))
        _show_route(route)
        if coords:
            st.download_button(
                "Export route (GPX)",
                data=export_gpx(coords, f"trip_{int(time.time())}"),
                file_name="trip_route.gpx",
                mime="application/gpx+xml",
                key="trip_gpx_download",
            )


def page_add_place() -> None:
    page_header("Add Place")
    categories = list(dict.fromkeys([str(x) for x in st.session_state.get("categories", [])] + ["Other"]))
    with st.form("add_place_form"):
        name = st.text_input("Place name", key="add_place_name")
        link = st.text_input("Map link (paste here)", key="add_place_link")
        description = st.text_area("Short description (optional)", key="add_place_description")
        category = st.selectbox("Category", categories, key="add_place_category")
        cost = st.selectbox("Cost Tier", ["$", "$$", "$$$", "$$$$"], index=1, key="add_place_cost")
        favorite = st.checkbox("Mark as favorite", key="add_place_favorite")
        tags = st.text_input("Tags (comma separated)", key="add_place_tags")
        uploads = st.file_uploader("Upload photos (optional)", accept_multiple_files=True, type=["png", "jpg", "jpeg"], key="upload_photos")
        submitted = st.form_submit_button("Add place from link")
        if submitted:
            lat, lon = parse_map_link(link) if link else (None, None)
            if lat is None or lon is None:
                st.error("Could not extract coordinates from the link. Click on the map below instead.")
            else:
                saved = []
                username = st.session_state.get("username")
                if uploads and username:
                    directory = user_media_dir(str(username))
                    for upload in uploads:
                        safe_name = os.path.basename(upload.name).replace("..", "_")
                        filename = f"{int(time.time())}_{safe_name}"
                        with open(os.path.join(directory, filename), "wb") as handle:
                            handle.write(upload.getbuffer())
                        saved.append(filename)
                add_place(
                    name or f"Place {len(_places()) + 1}", lat, lon, description, category, favorite,
                    link, [x.strip() for x in tags.split(",") if x.strip()], saved, cost,
                )
                st.success("Place added successfully")

    st.markdown("**Interactive map** • click to pick coordinates.")
    places = _places()
    center = places[-1] if places else {"latitude": 0.3476, "longitude": 32.5825}
    try:
        map_lat = float(center.get("latitude", 0.3476))
        map_lon = float(center.get("longitude", 32.5825))
        if not (-90 <= map_lat <= 90 and -180 <= map_lon <= 180):
            raise ValueError
    except (TypeError, ValueError):
        map_lat, map_lon = 0.3476, 32.5825
    m = folium.Map(location=[map_lat, map_lon], zoom_start=12, control_scale=True)
    folium.TileLayer("CartoDB positron", attr="© CartoDB").add_to(m)
    result = st_folium(m, width=900, height=450, key="add_place_map")
    click = result.get("last_clicked") if isinstance(result, dict) else None
    if isinstance(click, dict) and "lat" in click and "lng" in click:
        with st.form("add_from_click_form"):
            pname = st.text_input("Name for clicked place", value=f"Place {len(places) + 1}", key="clicked_place_name")
            pdesc = st.text_area("Description (optional)", key="clicked_place_description")
            pcat = st.selectbox("Category", categories, key="clicked_place_category")
            pcost = st.selectbox("Cost Tier", ["$", "$$", "$$$", "$$$$"], index=1, key="clicked_place_cost")
            pfav = st.checkbox("Mark as favorite", key="clicked_place_favorite")
            ptags = st.text_input("Tags (comma separated)", key="clicked_place_tags")
            if st.form_submit_button("Add place at clicked location"):
                try:
                    lat, lon = float(click["lat"]), float(click["lng"])
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        raise ValueError
                except (TypeError, ValueError):
                    st.error("The selected map coordinates are invalid.")
                else:
                    add_place(pname, lat, lon, pdesc, pcat, pfav, tags=[x.strip() for x in ptags.split(",") if x.strip()], cost_tier=pcost)
                    st.success("Place added from map click")


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
        name = str(place.get("name") or "Unnamed place")
        category_name = str(place.get("category") or "Other")
        cost = str(place.get("cost_tier") or "$$")
        st.markdown(f"**{escape(name)}** — *{escape(category_name)}* | Cost: `{escape(cost)}`")
        if place.get("address"):
            st.caption(str(place["address"]))
        if place.get("description"):
            st.write(str(place["description"]))
        try:
            lat, lon = float(place.get("latitude")), float(place.get("longitude"))
            st.write(f"📍 {lat:.6f}, {lon:.6f}")
        except (TypeError, ValueError):
            st.write("📍 Coordinates unavailable")
        place_id = str(place.get("id") or f"index_{index}")
        a, b = st.columns(2)
        if a.button("Delete", key=f"del_{place_id}"):
            if place.get("id") is not None:
                delete_place(place["id"])
            st.rerun()
        label = "Unfavorite" if place.get("favorite") else "Mark Favorite"
        if b.button(label, key=f"fav_{place_id}"):
            if place.get("id") is not None:
                update_place(place["id"], favorite=not bool(place.get("favorite", False)))
            st.rerun()
        st.divider()


def page_categories() -> None:
    page_header("Categories")
    if not isinstance(st.session_state.get("categories"), list):
        st.session_state.categories = []
    new_category = st.text_input("New category name", key="new_cat")
    if st.button("Add category", key="add_category"):
        category = new_category.strip()
        if not category:
            st.warning("Enter a category name.")
        elif category in st.session_state.categories:
            st.info("That category already exists.")
        else:
            st.session_state.categories.append(category)
            st.success("Category added")
    st.write(", ".join(st.session_state.categories))


def page_dashboard() -> None:
    page_header("Dashboard")
    places = _places()
    categories = st.session_state.get("categories", [])
    if not isinstance(categories, list):
        categories = []
    total, favorites = len(places), sum(bool(p.get("favorite")) for p in places)
    a, b, c = st.columns(3)
    a.metric("Places", total)
    b.metric("Favorites", favorites)
    c.metric("Categories", len(categories))
    if places:
        counts = pd.Series([str(p.get("category") or "Other") for p in places]).value_counts()
        st.bar_chart(counts)


def page_explore() -> None:
    page_header("Explore")
    city = st.text_input("City (optional)", key="explore_city")
    category = st.selectbox("Category (optional)", ["any", "restaurants", "attractions", "events", "nightlife", "shopping"], key="explore_cat")
    if st.button("Fetch Explore", key="fetch_explore"):
        result = fetch_explore_from_backend(city, category)
        st.session_state.explore_results = result if isinstance(result, list) else []
    results = st.session_state.get("explore_results", [])
    if not isinstance(results, list):
        results = []
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            continue
        name = str(result.get("name") or "Unnamed place")
        st.markdown(f"**{escape(name)}**")
        if result.get("description"):
            st.caption(str(result["description"]))
        if st.button(f"Add {name} to my places", key=f"add_explore_{index}"):
            add_place(
                name,
                result.get("latitude", 0),
                result.get("longitude", 0),
                result.get("description", ""),
                result.get("category", "Other"),
                cost_tier="$$",
            )
            st.success("Added")


def page_settings() -> None:
    page_header("Settings")
    st.write(f"Logged in as: **{escape(str(st.session_state.get('username') or 'guest'))}**")
    st.write(f"Authentication: **{escape(str(st.session_state.get('auth_mode') or 'unknown'))}**")
