"""Centralized CityScout configuration."""
from __future__ import annotations
import os

AUTH_URL = os.getenv("AUTH_URL", "http://localhost:8000")
AUTH_VERIFY_TIMEOUT = int(os.getenv("AUTH_VERIFY_TIMEOUT", "6"))
USER_DATA_DIR = os.getenv("USER_DATA_DIR", "./user_data")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
MEDIA_DIR_NAME = "media"
BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
OSRM_ROUTE_TTL = int(os.getenv("OSRM_ROUTE_TTL", "3600"))
APP_BG = "#000000"
APP_PRIMARY = "#0b6efd"
APP_FONT = "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial"
DEFAULT_CATEGORIES = ["Food", "Nightlife", "Shopping", "Attractions", "Parks", "Transit", "Other"]
PAGES = [
    "Trip Planner",
    "City Explorer",
    "Spatial Intelligence",
    "City Intelligence",
    "Architecture & Urban Design",
    "Building Design Cockpit",
    "AI CityScout",
    "Dashboard",
    "Explore",
    "Add Place",
    "Places",
    "Share",
    "Categories",
    "Settings",
]
