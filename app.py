"""IND320 reservoir dashboard navigation and shared controls."""

import streamlit as st

from src.analysis_ui import shared_controls
from src.views import correlation_page, forecast_page, fx_page, overview
from src.views import patterns_page, reservoirs_page, weather_page

st.set_page_config(page_title="IND320 Reservoir Dashboard", page_icon="💧", layout="wide")
shared_controls()
navigation = st.navigation({
    "Project": [st.Page(overview, title="Overview and map", default=True)],
    "Explore": [
        st.Page(reservoirs_page, title="Reservoir data"),
        st.Page("pages/flows.py", title="Cross-border flows"),
        st.Page(fx_page, title="Exchange rates"),
    ],
    "Analyse": [
        st.Page(patterns_page, title="Reservoir patterns"),
        st.Page(weather_page, title="Weather anomalies"),
        st.Page(correlation_page, title="Weather and filling"),
    ],
    "Predict": [st.Page(forecast_page, title="Filling forecast")],
    "Information": [st.Page("pages/about.py", title="About the project")],
})
navigation.run()
