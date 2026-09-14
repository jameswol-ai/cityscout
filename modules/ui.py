"""Shared CityScout UI components and styling."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from .config import APP_BG, APP_PRIMARY, APP_FONT, PAGES
from .places import add_place

APP_SVG_LOGO = """
<svg width="120" height="120" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect rx="18" width="100" height="100" fill="{color}"/>
  <g transform="translate(18,18)" fill="#fff">
    <path d="M12 2c-5.5 0-10 4.5-10 10 0 7.5 10 18 10 18s10-10.5 10-18c0-5.5-4.5-10-10-10z"/>
    <circle cx="12" cy="12" r="3"/>
  </g>
</svg>
"""


def inject_css():
    st.markdown(f"""
    <style>
      html, body, .stApp {{ background:{APP_BG} !important; color:#e6e6e6 !important; font-family:{APP_FONT} !important; }}
      .card {{ background:rgba(255,255,255,.03); border-radius:10px; padding:12px; margin-bottom:12px; border:1px solid rgba(255,255,255,.06); }}
      .logo-top {{ display:flex; align-items:center; justify-content:center; padding:18px 0 6px; }}
      .logo-top svg {{ display:block; margin:0 auto; }}
      .small-muted {{ color:#9ca3af; font-size:.95rem; text-align:center; }}
      .sidebar-section {{ margin-bottom:12px; }}
      a.map-link {{ color:#9ad0ff; text-decoration:underline; }}
    </style>
    """, unsafe_allow_html=True)


def render_logo(container=None):
    target = container or st
    target.markdown("<div class='logo-top'>", unsafe_allow_html=True)
    target.markdown(APP_SVG_LOGO.format(color=APP_PRIMARY), unsafe_allow_html=True)
    target.markdown("</div>", unsafe_allow_html=True)


def page_header(title: str):
    st.markdown(f"<div class='card'><h3 style='margin:0;color:#e6e6e6'>{title}</h3></div>", unsafe_allow_html=True)


def sidebar_navigation():
    render_logo(st.sidebar)
    st.sidebar.markdown("<div class='sidebar-section small-muted'>Navigate</div>", unsafe_allow_html=True)
    current = st.session_state.get("page", "Trip Planner")
    if current not in PAGES:
        current = PAGES[0]
    choice = st.sidebar.radio("Pages", PAGES, index=PAGES.index(current))
    st.session_state.page = choice
    st.sidebar.markdown("---")
    if st.sidebar.button("Add sample place"):
        add_place("Sample Place", 0.3476, 32.5825, "Sample", category="Attractions", cost_tier="$$")
        st.sidebar.success("Sample place added")
    if st.sidebar.button("Export all places (CSV)"):
        csv = pd.DataFrame(st.session_state.get("places", [])).to_csv(index=False).encode("utf-8")
        st.sidebar.download_button("Download CSV", data=csv, file_name="places.csv", mime="text/csv")
    st.sidebar.markdown("---")
    if st.session_state.get("username"):
        st.sidebar.markdown(f"**User:** {st.session_state.username}")
        st.sidebar.markdown(f"**Auth:** {st.session_state.get('auth_mode') or 'unknown'}")
