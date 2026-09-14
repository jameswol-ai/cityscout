# CityScout

CityScout is a city exploration and trip-planning workspace with a Streamlit application and an existing AI Studio web application.

Live applications:
- Streamlit: https://cityscout.streamlit.app/
- AI Studio: https://ai.studio/apps/a60daf2d-dda8-4965-b9b9-63b147a976b3

## Streamlit capabilities

- Places and favorites with categories, tags, descriptions and cost tiers
- Map-link coordinate extraction and OpenStreetMap reverse geocoding
- Interactive Folium maps
- OSRM route calculation with in-memory route caching
- Trip optimization using nearest-neighbor routing and 2-opt improvement
- Driving, walking and cycling modes
- Trip expense estimation
- GPX route export
- Explore endpoint integration with a safe sample fallback
- Public share tokens with optional password and expiry
- CSV export of saved places
- Local JSON authentication fallback plus optional remote authentication service
- Dashboard metrics and category chart

## Modular Streamlit architecture

The Streamlit entry point is intentionally thin. Domain logic and UI pages are separated into the `modules/` package:

```text
modules/
├── __init__.py
├── config.py       # configuration and navigation constants
├── auth.py         # remote/local authentication
├── storage.py      # JSON user, place and share storage
├── maps.py         # map links, geocoding and OSRM routing
├── places.py       # places, favorites, reviews and sharing
├── trip.py         # optimization, budgets and GPX export
├── ui.py           # styling, logo and sidebar navigation
└── pages.py        # Streamlit page renderers
```

`streamlit_app.py` handles only application bootstrap, session initialization, authentication flow and page dispatch. This structure is designed to make the next CityScout layers easier to add without returning to a monolithic application file.

## Local Streamlit setup

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
streamlit run streamlit_app.py
```

### Optional environment variables

```text
AUTH_URL=http://localhost:8000
BACKEND_URL=http://localhost:8000
AUTH_VERIFY_TIMEOUT=6
USER_DATA_DIR=./user_data
PUBLIC_BASE_URL=
OSRM_ROUTE_TTL=3600
```

If the remote authentication service is unavailable, the Streamlit application uses the local JSON authentication fallback. A demo account is created automatically:

```text
username: demo
password: demo123
```

## AI Studio application

The repository also contains the existing Node/Vite application. Its development setup remains separate from the Streamlit application:

```bash
npm install
```

Set `GEMINI_API_KEY` in `.env.local`, then run:

```bash
npm run dev
```

## Roadmap

The modular foundation enables the next CityScout evolution:

1. City Explorer
2. Interactive GIS and city layers
3. Architecture and urban-design intelligence
4. Places and city amenities intelligence
5. Advanced trip planning
6. Personal city dashboard
7. AI CityScout assistant
8. City analytics and comparison dashboards
9. Cloud-backed user data and accounts

CityScout is intended to evolve from a place-saving and trip-planning app into a broader **City Intelligence & Exploration Platform**.
