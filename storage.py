# storage.py
import json
from database import get_db_connection

def load_user_places_db(username: str) -> list:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM places WHERE username = %s", (username,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    places = []
    for row in rows:
        place = dict(row)
        place["tags"] = json.loads(json.dumps(place["tags"])) if place["tags"] else []
        place["photos"] = json.loads(json.dumps(place["photos"])) if place["photos"] else []
        place["reviews"] = json.loads(json.dumps(place["reviews"])) if place["reviews"] else []
        places.append(place)
    return places

def save_user_place_db(username: str, place: dict):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO places (id, username, name, latitude, longitude, address, description, category, favorite, source_link, tags, photos, reviews)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            address = EXCLUDED.address,
            description = EXCLUDED.description,
            category = EXCLUDED.category,
            favorite = EXCLUDED.favorite,
            source_link = EXCLUDED.source_link,
            tags = EXCLUDED.tags,
            photos = EXCLUDED.photos,
            reviews = EXCLUDED.reviews,
            updated_at = CURRENT_TIMESTAMP;
    """, (
        place["id"], username, place["name"], place["latitude"], place["longitude"],
        place.get("address", ""), place.get("description", ""), place.get("category", "Other"),
        place.get("favorite", False), place.get("source_link", ""),
        json.dumps(place.get("tags", [])), json.dumps(place.get("photos", [])),
        json.dumps(place.get("reviews", []))
    ))
    conn.commit()
    cur.close()
    conn.close()

def delete_user_place_db(place_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM places WHERE id = %s", (place_id,))
    conn.commit()
    cur.close()
    conn.close()
