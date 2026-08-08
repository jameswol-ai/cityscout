# database.py
import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/cityscout")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Users table with roles
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username VARCHAR(150) PRIMARY KEY,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) DEFAULT 'viewer',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Places table for per-user or global data
    cur.execute("""
        CREATE TABLE IF NOT EXISTS places (
            id VARCHAR(64) PRIMARY KEY,
            username VARCHAR(150) REFERENCES users(username) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            latitude FLOAT NOT NULL,
            longitude FLOAT NOT NULL,
            address TEXT,
            description TEXT,
            category VARCHAR(100),
            favorite BOOLEAN DEFAULT FALSE,
            source_link TEXT,
            tags JSONB DEFAULT '[]',
            photos JSONB DEFAULT '[]',
            reviews JSONB DEFAULT '[]',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Templates table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trip_templates (
            id SERIAL PRIMARY KEY,
            username VARCHAR(150) REFERENCES users(username) ON DELETE CASCADE,
            template_name VARCHAR(150) NOT NULL,
            indices JSONB DEFAULT '[]',
            UNIQUE(username, template_name)
        );
    """)
    
    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    init_db()
