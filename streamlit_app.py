import streamlit as st
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

BASE_URL = "https://cityscout.ai.studio/api"  # Replace with actual backend endpoint if available

st.set_page_config(page_title="CityScout", page_icon="🌆", layout="wide")

# App Header
st.title("🌆 CityScout")
st.markdown("Explore cities with AI-powered insights.")

# Sidebar for user input
st.sidebar.header("Search Options")
city = st.sidebar.text_input("Enter a city name", "Kampala")
category = st.sidebar.selectbox("Choose category", ["Restaurants", "Attractions", "Events", "Nightlife", "Shopping"])

# Search button
if st.sidebar.button("Explore"):
    if not API_KEY:
        st.error("Missing GEMINI_API_KEY. Please set it in your .env file.")
    else:
        try:
            # Example request payload
            payload = {
                "city": city,
                "category": category,
                "api_key": API_KEY
            }
            response = requests.post(f"{BASE_URL}/explore", json=payload)

            if response.status_code == 200:
                data = response.json()
                st.subheader(f"Results for {city} - {category}")
                for item in data.get("results", []):
                    st.markdown(f"**{item['name']}**")
                    st.write(item.get("description", "No description available"))
                    if "rating" in item:
                        st.write(f"⭐ Rating: {item['rating']}")
                    st.write("---")
            else:
                st.error(f"Error {response.status_code}: {response.text}")
        except Exception as e:
            st.error(f"Request failed: {e}")

# Footer
st.markdown("---")
st.caption("Powered by CityScout AI Studio · Built with Streamlit")
