<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://ai.google.dev/static/site-assets/images/share-ais-513315318.png" />
</div>

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/a60daf2d-dda8-4965-b9b9-63b147a976b3

or 
https://cityscout.ai.studio

or 
https://cityscout.streamlit.app/

## Run Locally

**Prerequisites:**  Node.js


1. Install dependencies:
   `npm install`
2. Set the `GEMINI_API_KEY` in [.env.local](.env.local) to your Gemini API key
3. Run the app:
   `npm run dev`

# CityScout (Streamlit)

CityScout is a Streamlit frontend that explores places, saves favorites, and integrates Google Maps features:
- Google Places enrichment (ratings, address, photos)
- Google Places Photo fetching (embedded in the UI)
- Google Directions (routes and polylines drawn on Folium maps)
- Folium clustering and heatmaps
- Favorites: search, tags, import/export, map

## Setup

1. Clone the repo and place `streamlit_app.py`, `requirements.txt`, and this README in the project root.

2. Install Python dependencies:
```bash
pip install -r requirements.txt
