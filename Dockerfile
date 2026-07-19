version: "3.9"
services:
  auth:
    build: ./auth_server
    environment:
      - JWT_SECRET=change_this_secret
      - AUTH_DB=/data/auth.db
    volumes:
      - ./auth_data:/data
    ports:
      - "8000:8000"

  frontend:
    build: .
    environment:
      - AUTH_URL=http://auth:8000
      - USER_DATA_DIR=/data/user_data
    volumes:
      - ./user_data:/data/user_data
    ports:
      - "8501:8501"
    depends_on:
      - auth
