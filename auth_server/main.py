# auth_server/main.py
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from passlib.context import CryptContext
from datetime import datetime, timedelta
import sqlite3
import os
import jwt
from typing import Optional

# Configuration from environment
JWT_SECRET = os.getenv("JWT_SECRET", "change_this_secret")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # default 24h
DB_PATH = os.getenv("AUTH_DB", "auth.db")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI(title="CityScout Auth")

# --- Database helpers
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

def get_user(username: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, created_at FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "password_hash": row[2], "created_at": row[3]}

def create_user(username: str, password_hash: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    try:
        cur.execute("INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, password_hash, now))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return None
    user_id = cur.lastrowid
    conn.close()
    return {"id": user_id, "username": username, "created_at": now}

# --- Pydantic models
class SignupIn(BaseModel):
    username: str
    password: str

class LoginIn(BaseModel):
    username: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

# --- Utilities
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

# --- Startup
@app.on_event("startup")
def startup():
    init_db()

# --- Endpoints
@app.post("/signup", response_model=dict)
def signup(payload: SignupIn):
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail="username and password required")
    if get_user(payload.username):
        raise HTTPException(status_code=400, detail="username already exists")
    hashed = hash_password(payload.password)
    user = create_user(payload.username, hashed)
    if not user:
        raise HTTPException(status_code=500, detail="failed to create user")
    token = create_access_token({"sub": payload.username})
    return {"username": payload.username, "access_token": token}

@app.post("/login", response_model=TokenOut)
def login(payload: LoginIn):
    user = get_user(payload.username)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = create_access_token({"sub": payload.username})
    return {"access_token": token}

@app.get("/me", response_model=dict)
def me(authorization: Optional[str] = Header(None)):
    """
    Verify token and return basic user info.
    Provide header: Authorization: Bearer <token>
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="missing authorization header")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="invalid token")
    username = payload["sub"]
    user = get_user(username)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return {"username": username, "created_at": user["created_at"]}
