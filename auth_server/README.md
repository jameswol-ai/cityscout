# CityScout Auth Server (FastAPI + JWT)

Simple authentication service for CityScout.

## Features
- Signup (`/signup`) — returns JWT access token
- Login (`/login`) — returns JWT access token
- Verify token (`/me`) — returns username and created_at

## Quick start (local)
1. Create a Python environment and install dependencies:
```bash
pip install -r requirements.txt
