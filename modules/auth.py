"""Remote authentication with a local JSON fallback for simple deployments."""
from __future__ import annotations
import hashlib
import requests
import streamlit as st
from .config import AUTH_URL, AUTH_VERIFY_TIMEOUT
from .storage import load_local_users, save_local_users


def create_local_user(username: str, password: str) -> bool:
    users = load_local_users()
    if not username or username in users:
        return False
    users[username] = {"password_hash": hashlib.sha256(password.encode()).hexdigest()}
    return save_local_users(users)


def verify_local_user(username: str, password: str) -> bool:
    user = load_local_users().get(username)
    if not user:
        return False
    return user.get("password_hash") == hashlib.sha256(password.encode()).hexdigest()


def ensure_demo_local_user() -> None:
    users = load_local_users()
    if "demo" not in users:
        users["demo"] = {"password_hash": hashlib.sha256("demo123".encode()).hexdigest()}
        save_local_users(users)


def _auth_request(method: str, path: str, **kwargs):
    try:
        response = requests.request(method, f"{AUTH_URL}{path}", timeout=AUTH_VERIFY_TIMEOUT, **kwargs)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError, TypeError):
        return None


def call_auth_signup(username: str, password: str):
    data = _auth_request("POST", "/signup", json={"username": username, "password": password})
    return data.get("access_token") if isinstance(data, dict) else None


def call_auth_login(username: str, password: str):
    data = _auth_request("POST", "/login", json={"username": username, "password": password})
    return data.get("access_token") if isinstance(data, dict) else None


def verify_token(token: str):
    if not token:
        return None
    return _auth_request("GET", "/me", headers={"Authorization": f"Bearer {token}"})


def logout_user() -> None:
    for key, value in {
        "access_token": None,
        "username": None,
        "places": [],
        "auth_mode": None,
        "trip_templates": {},
        "last_route": None,
    }.items():
        st.session_state[key] = value
