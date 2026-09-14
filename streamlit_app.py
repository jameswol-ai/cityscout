"""CityScout Streamlit application entry point.

The entry point intentionally contains only application wiring. Domain logic,
services and page renderers live in ``modules/`` so CityScout can grow without
turning this file into another monolith.
"""
from __future__ import annotations

import streamlit as st

from modules.auth import (
    call_auth_login,
    create_local_user,
    ensure_demo_local_user,
    logout_user,
    verify_local_user,
    verify_token,
)
from modules.config import DEFAULT_CATEGORIES
from modules.storage import load_user_places
from modules.ui import inject_css, render_logo, sidebar_navigation
from modules.pages import (
    page_add_place,
    page_categories,
    page_dashboard,
    page_explore,
    page_places,
    page_settings,
    page_share,
    page_trip_planner,
)

st.set_page_config(page_title="CityScout", page_icon="🌆", layout="wide")


def initialize_session() -> None:
    defaults = {
        "access_token": None,
        "username": None,
        "places": [],
        "categories": list(DEFAULT_CATEGORIES),
        "auth_mode": None,
        "page": "Trip Planner",
        "last_route": None,
        "trip_templates": {},
        "share_tokens": {},
        "explore_results": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_login() -> None:
    inject_css()
    render_logo()
    st.markdown("<div class='small-muted'>Sign in or create an account to continue</div>", unsafe_allow_html=True)
    ensure_demo_local_user()

    username = st.text_input("Username", key="login_user", placeholder="username")
    password = st.text_input("Password", type="password", key="login_pass", placeholder="password")
    login_col, signup_col = st.columns(2)

    with login_col:
        if st.button("Login", use_container_width=True):
            if not username or not password:
                st.error("Enter a username and password.")
                return
            token = call_auth_login(username, password)
            if token:
                info = verify_token(token)
                if info and info.get("username") == username:
                    st.session_state.access_token = token
                    st.session_state.username = username
                    st.session_state.auth_mode = "remote"
                    st.session_state.places = load_user_places(username)
                    st.rerun()
            if verify_local_user(username, password):
                st.session_state.access_token = None
                st.session_state.username = username
                st.session_state.auth_mode = "local"
                st.session_state.places = load_user_places(username)
                st.rerun()
            st.error("Login failed. Check credentials.")

    with signup_col:
        if st.button("Sign up", use_container_width=True):
            if not username or not password:
                st.error("Enter a username and password.")
                return
            if create_local_user(username, password):
                st.session_state.username = username
                st.session_state.auth_mode = "local"
                st.session_state.places = []
                st.rerun()
            st.error("Sign up failed. Username may already exist.")

    st.caption("Demo account: demo / demo123")


def validate_session() -> bool:
    token = st.session_state.get("access_token")
    username = st.session_state.get("username")
    if token and username:
        info = verify_token(token)
        if not info or info.get("username") != username:
            logout_user()
            return False
    return bool(st.session_state.get("username"))


def render_app() -> None:
    inject_css()
    sidebar_navigation()
    if st.sidebar.button("Logout"):
        logout_user()
        st.rerun()

    if not st.session_state.get("places") and st.session_state.get("username"):
        st.session_state.places = load_user_places(st.session_state.username)

    pages = {
        "Trip Planner": page_trip_planner,
        "Dashboard": page_dashboard,
        "Explore": page_explore,
        "Add Place": page_add_place,
        "Places": page_places,
        "Share": page_share,
        "Categories": page_categories,
        "Settings": page_settings,
    }
    pages.get(st.session_state.get("page"), page_trip_planner)()


def run() -> None:
    initialize_session()
    if not validate_session():
        render_login()
        return
    render_app()


if __name__ == "__main__":
    run()
