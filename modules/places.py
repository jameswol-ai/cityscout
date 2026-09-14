"""Place, favorite, review and share domain operations."""
from __future__ import annotations
import hashlib
import json
import os
import time
from datetime import datetime
from typing import List, Optional
import streamlit as st
from .config import PUBLIC_BASE_URL
from .maps import reverse_geocode
from .storage import save_user_places, share_path, load_json, save_json, user_media_dir


def add_place(name: str, lat: float, lon: float, description: str = "", category: str = "Other",
              favorite: bool = False, source_link: str = "", tags: List[str] | None = None,
              photos: List[str] | None = None, cost_tier: str = "$$"):
    place = {
        "id": hashlib.sha1(f"{name}{lat}{lon}{time.time()}".encode()).hexdigest()[:12],
        "name": name,
        "latitude": float(lat), "longitude": float(lon),
        "address": reverse_geocode(lat, lon),
        "description": description or "", "category": category or "Other",
        "favorite": bool(favorite), "source_link": source_link or "",
        "tags": tags or [], "photos": photos or [], "reviews": [],
        "cost_tier": cost_tier or "$$",
    }
    st.session_state.places.append(place)
    _persist_places()
    return place


def _persist_places():
    username = st.session_state.get("username")
    if username:
        save_user_places(username, st.session_state.get("places", []))


def update_place(place_id: str, **fields):
    for place in st.session_state.get("places", []):
        if place.get("id") == place_id:
            place.update(fields)
            if "latitude" in fields or "longitude" in fields:
                place["address"] = reverse_geocode(place.get("latitude"), place.get("longitude"))
            _persist_places()
            return place
    return None


def delete_place(place_id: str):
    username = st.session_state.get("username")
    if username:
        for place in st.session_state.get("places", []):
            if place.get("id") == place_id:
                for filename in place.get("photos", []):
                    try:
                        os.remove(os.path.join(user_media_dir(username), filename))
                    except OSError:
                        pass
    st.session_state.places = [p for p in st.session_state.get("places", []) if p.get("id") != place_id]
    _persist_places()


def add_review(place_id: str, user: str, rating: int, text: str):
    for place in st.session_state.get("places", []):
        if place.get("id") == place_id:
            place.setdefault("reviews", []).append({"user": user, "rating": int(rating), "text": text, "ts": datetime.utcnow().isoformat()})
            _persist_places()
            return place
    return None


def average_rating(place: dict) -> Optional[float]:
    reviews = place.get("reviews", [])
    return sum(r.get("rating", 0) for r in reviews) / len(reviews) if reviews else None


def create_share_token(payload: dict, password: Optional[str] = None, expires_hours: Optional[int] = None) -> str:
    token = hashlib.sha1(json.dumps(payload, default=str).encode()).hexdigest()[:12]
    now = datetime.utcnow()
    meta = {
        "payload": payload, "created_at": now.isoformat(),
        "password_hash": hashlib.sha256(password.encode()).hexdigest() if password else None,
        "expires_at": now.timestamp() + expires_hours * 3600 if expires_hours else None,
    }
    if not save_json(share_path(token), meta):
        raise OSError("Unable to save share token")
    st.session_state.share_tokens[token] = meta
    return token


def load_share_token(token: str, password: Optional[str] = None):
    meta = load_json(share_path(token), None)
    if not isinstance(meta, dict):
        return None
    if meta.get("expires_at") and time.time() > meta["expires_at"]:
        return None
    password_hash = meta.get("password_hash")
    if password_hash:
        if not password:
            return {"requires_password": True}
        if hashlib.sha256(password.encode()).hexdigest() != password_hash:
            return {"invalid_password": True}
    return meta.get("payload")


def public_share_url(token: str):
    return f"{PUBLIC_BASE_URL}/share_{token}.json" if PUBLIC_BASE_URL else None
