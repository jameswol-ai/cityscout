"""Streamlit page renderers for CityScout."""
from __future__ import annotations
import os
import time
from datetime import datetime
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium
from .config import APP_PRIMARY
from .maps import parse_map_link, fetch_explore_from_backend
from .places import add_place, update_place, delete_place, create_share_token, public_share_url
from .storage import load_user_places, user_media_dir
from .trip import estimate_trip_costs, compute_distance_matrix, nearest_neighbor_order, two_opt_improve, build_route_polyline_coords, export_gpx
from .ui import page_header
from .urban_design import page_architecture
from .ai_cityscout import page_ai_cityscout


def page_share():
    page_header("Share")
    st.write("Create a public share token for a trip or a list of places.")
    choice = st.selectbox("Share payload", ["Last computed route", "Selected saved places"])
    if choice == "Selected saved places":
        places = st.session_state.get("places", [])
        if not places:
            st.info("No saved places to share."); return
        labels = [f"{p['name']} — {p.get('category','')}" for p in places]
        selected = st.multiselect("Select places to share", range(len(labels)), format_func=lambda i: labels[i])
        if not selected:
            st.write("Select at least one place to share."); return
        payload = {"type":"places", "places":[places[i] for i in selected], "owner":st.session_state.get("username")}
    else:
        route = st.session_state.get("last_route")
        if not route:
            st.info("No last route computed yet."); return
        payload = {"type":"route", "route":route, "owner":st.session_state.get("username")}
    password = st.text_input("Optional password to protect the share (leave blank for none)", type="password")
    expires = st.number_input("Expires in (hours, 0 = never)", min_value=0, value=0, step=1)
    if st.button("Create share token"):
        token = create_share_token(payload, password or None, expires or None)
        st.success("Share token created")
        st.write(f"Token: **{token}**")
        if (url := public_share_url(token)):
            st.markdown(f"Public URL: {url}")


def _show_route(route):
    costs = route.get("costs") or estimate_trip_costs(route.get("ordered_places", []), route.get("total_km", 0), route.get("mode", "driving"))
    st.markdown(f"**Estimated Trip Expenses:** 💵 ${costs['total_cost']:.2f} total *(Activities: ${costs['activity_cost']:.2f} | Travel: ${costs['travel_cost']:.2f})*")
    if route.get("coords"):
        m = folium.Map(location=route["coords"][len(route["coords"])//2], zoom_start=12)
        folium.PolyLine(route["coords"], color=APP_PRIMARY, weight=5, opacity=.85).add_to(m)
        for i, place in enumerate(route.get("ordered_places", [])):
            folium.Marker([place["latitude"], place["longitude"]], tooltip=f"{i+1}. {place['name']} ({place.get('cost_tier','$$')})").add_to(m)
        folium.TileLayer("CartoDB positron", attr="© CartoDB").add_to(m)
        st_folium(m, width=900, height=400)


def page_trip_planner():
    page_header("Trip Planner & Budget Calculator")
    last_route = st.session_state.get("last_route")
    if last_route:
        st.markdown("**Last computed route**")
        st.write(f"- Stops: {len(last_route.get('ordered_places', []))}")
        st.write(f"- Distance: {last_route.get('total_km', 0):.2f} km")
        st.write(f"- Duration: {last_route.get('total_min', 0):.1f} min")
        _show_route(last_route)
        st.write("---")
    places = st.session_state.get("places", [])
    if not places:
        st.info("No saved places yet. Add places first."); return
    labels = [f"{p['name']} ({p.get('cost_tier','$$')}) — {p.get('category','')}" for p in places]
    selected = st.multiselect("Select places to include (2+)", range(len(labels)), format_func=lambda i: labels[i])
    if len(selected) < 2:
        st.write("Select at least two places to plan a route."); return
    start = st.selectbox("Start from", selected, format_func=lambda i: labels[i])
    mode = st.selectbox("Mode", ["driving", "walking", "cycling"])
    round_trip = st.checkbox("Round trip (return to start)")
    visit_duration = st.number_input("Visit duration per stop (minutes)", min_value=0, value=0, step=5)
    if st.button("Compute optimized route & budget"):
        subset = [places[i] for i in selected]
        with st.spinner("Computing pairwise distances & estimating budget..."):
            dist, _ = compute_distance_matrix(subset, mode)
        order = nearest_neighbor_order(dist, selected.index(start))
        order = two_opt_improve(order, dist)
        if round_trip and order[-1] != order[0]:
            order.append(order[0])
        ordered = [subset[i] for i in order]
        coords, km, minutes = build_route_polyline_coords(order, subset, mode)
        minutes += visit_duration * max(0, len(ordered) - (1 if round_trip else 0))
        costs = estimate_trip_costs(ordered, km, mode)
        route = {"ordered_places":ordered,"coords":coords,"total_km":km,"total_min":minutes,"mode":mode,"costs":costs,"computed_at":datetime.utcnow().isoformat()}
        st.session_state.last_route = route
        st.success(f"Route computed — {len(ordered)} stops, {km:.2f} km, {minutes:.1f} min")
        st.info(f"💵 **Estimated Budget:** ${costs['total_cost']:.2f} (Activities: ${costs['activity_cost']:.2f} | Transit: ${costs['travel_cost']:.2f})")
        for i, place in enumerate(ordered, 1):
            st.markdown(f"{i}. **{place['name']}** — {place.get('category','')} | Cost Tier: `{place.get('cost_tier','$$')}`")
            if place.get("address"): st.caption(place["address"])
        _show_route(route)
        if coords:
            st.download_button("Export route (GPX)", data=export_gpx(coords, f"trip_{int(time.time())}"), file_name="trip_route.gpx", mime="application/gpx+xml")


def page_add_place():
    page_header("Add Place")
    with st.form("add_place_form"):
        name = st.text_input("Place name")
        link = st.text_input("Map link (paste here)")
        description = st.text_area("Short description (optional)")
        categories = st.session_state.get("categories", []) + ["Other"]
        category = st.selectbox("Category", categories)
        cost = st.selectbox("Cost Tier", ["$", "$$", "$$$", "$$$$"], index=1)
        favorite = st.checkbox("Mark as favorite")
        tags = st.text_input("Tags (comma separated)")
        uploads = st.file_uploader("Upload photos (optional)", accept_multiple_files=True, type=["png","jpg","jpeg"], key="upload_photos")
        submitted = st.form_submit_button("Add place from link")
        if submitted:
            lat, lon = parse_map_link(link) if link else (None, None)
            if lat is None or lon is None:
                st.error("Could not extract coordinates from the link. Click on the map below instead.")
            else:
                saved = []
                if uploads and st.session_state.get("username"):
                    directory = user_media_dir(st.session_state.username)
                    for upload in uploads:
                        filename = f"{int(time.time())}_{upload.name}"
                        with open(os.path.join(directory, filename), "wb") as handle:
                            handle.write(upload.getbuffer())
                        saved.append(filename)
                add_place(name or f"Place {len(st.session_state.places)+1}", lat, lon, description, category, favorite, link, [x.strip() for x in tags.split(",") if x.strip()], saved, cost)
                st.success("Place added successfully")
    st.markdown("**Interactive map** • click to pick coordinates.")
    center = st.session_state.places[-1] if st.session_state.places else {"latitude":0.3476,"longitude":32.5825}
    m = folium.Map(location=[center.get("latitude",0), center.get("longitude",0)], zoom_start=12, control_scale=True)
    folium.TileLayer("CartoDB positron", attr="© CartoDB").add_to(m)
    result = st_folium(m, width=900, height=450)
    click = result.get("last_clicked")
    if click:
        with st.form("add_from_click_form"):
            pname = st.text_input("Name for clicked place", value=f"Place {len(st.session_state.places)+1}")
            pdesc = st.text_area("Description (optional)")
            pcat = st.selectbox("Category", st.session_state.categories + ["Other"])
            pcost = st.selectbox("Cost Tier", ["$", "$$", "$$$", "$$$$"], index=1)
            pfav = st.checkbox("Mark as favorite")
            ptags = st.text_input("Tags (comma separated)")
            if st.form_submit_button("Add place at clicked location"):
                add_place(pname, click["lat"], click["lng"], pdesc, pcat, pfav, tags=[x.strip() for x in ptags.split(",") if x.strip()], cost_tier=pcost)
                st.success("Place added from map click")


def page_places():
    page_header("Places")
    search = st.text_input("Search places by name or description", key="search_places")
    category = st.selectbox("Filter category", ["All"] + st.session_state.categories)
    favorites = st.checkbox("Show favorites only")
    items = st.session_state.places
    if search: items = [p for p in items if search.lower() in (p.get("name","") + p.get("description","")).lower()]
    if category != "All": items = [p for p in items if p.get("category") == category]
    if favorites: items = [p for p in items if p.get("favorite")]
    if not items: st.info("No places match the filters."); return
    for place in items:
        st.markdown(f"**{place['name']}** — *{place.get('category','Other')}* | Cost: `{place.get('cost_tier','$$')}`")
        if place.get("address"): st.caption(place["address"])
        if place.get("description"): st.write(place["description"])
        st.write(f"📍 {place.get('latitude',0):.6f}, {place.get('longitude',0):.6f}")
        a, b = st.columns(2)
        if a.button("Delete", key=f"del_{place['id']}"):
            delete_place(place["id"]); st.rerun()
        label = "Unfavorite" if place.get("favorite") else "Mark Favorite"
        if b.button(label, key=f"fav_{place['id']}"):
            update_place(place["id"], favorite=not place.get("favorite", False)); st.rerun()
        st.write("---")


def page_categories():
    page_header("Categories")
    new_category = st.text_input("New category name", key="new_cat")
    if st.button("Add category") and new_category and new_category not in st.session_state.categories:
        st.session_state.categories.append(new_category); st.success("Category added")
    st.write(", ".join(st.session_state.categories))


def page_dashboard():
    page_header("Dashboard")
    places = st.session_state.places
    total, favorites = len(places), sum(bool(p.get("favorite")) for p in places)
    a, b, c = st.columns(3)
    a.metric("Places", total); b.metric("Favorites", favorites); c.metric("Categories", len(st.session_state.categories))
    if places:
        counts = pd.Series([p.get("category", "Other") for p in places]).value_counts()
        st.bar_chart(counts)


def page_explore():
    page_header("Explore")
    city = st.text_input("City (optional)", key="explore_city")
    category = st.selectbox("Category (optional)", ["any", "restaurants", "attractions", "events", "nightlife", "shopping"], key="explore_cat")
    if st.button("Fetch Explore"):
        st.session_state.explore_results = fetch_explore_from_backend(city, category)
    for result in st.session_state.get("explore_results", []):
        st.markdown(f"**{result.get('name','Unnamed place')}**")
        if result.get("description"): st.caption(result["description"])
        if st.button(f"Add {result.get('name','place')} to my places", key=f"add_explore_{hash(result.get('name'))}"):
            add_place(result.get("name","Place"), result.get("latitude",0), result.get("longitude",0), result.get("description", ""), result.get("category", "Other"), cost_tier="$$")
            st.success("Added")


def page_settings():
    page_header("Settings")
    st.write(f"Logged in as: **{st.session_state.get('username') or 'guest'}**")
    st.write(f"Authentication: **{st.session_state.get('auth_mode') or 'unknown'}**")
