"""File-backed user storage used by the Streamlit deployment."""
from __future__ import annotations
import json
import os
import re
from typing import Any
from .config import USER_DATA_DIR, MEDIA_DIR_NAME

USERS_FILE = os.path.join(USER_DATA_DIR, "users.json")


def user_media_dir(username: str) -> str:
    path = os.path.join(USER_DATA_DIR, f"{username}_{MEDIA_DIR_NAME}")
    os.makedirs(path, exist_ok=True)
    return path


def user_places_path(username: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", username)
    return os.path.join(USER_DATA_DIR, f"{safe}_places.json")


def load_json(path: str, default: Any):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def save_json(path: str, value: Any) -> bool:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
        return True
    except (OSError, TypeError, ValueError):
        return False


def load_user_places(username: str):
    return load_json(user_places_path(username), [])


def save_user_places(username: str, places) -> bool:
    return save_json(user_places_path(username), places)


def load_local_users():
    return load_json(USERS_FILE, {})


def save_local_users(users: dict) -> bool:
    return save_json(USERS_FILE, users)


def share_path(token: str) -> str:
    return os.path.join(USER_DATA_DIR, f"share_{token}.json")
