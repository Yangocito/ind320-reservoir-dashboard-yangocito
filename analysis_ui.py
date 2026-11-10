"""Shared Streamlit controls for the reservoir and weather analyses."""

import matplotlib.pyplot as plt
import streamlit as st

from utils import fetch_reservoirs
from weather import download_weather

AREAS = {
    **{f"NO{i}": ("EL", i, f"NO{i} (price area)") for i in range(1, 6)},
    "VASS1": ("VASS", 1, "VASS1 (RS + RØ)"),
    "VASS2": ("VASS", 2, "VASS2 (RV)"),
    "VASS3": ("VASS", 3, "VASS3 (RM)"),
    "VASS4": ("VASS", 4, "VASS4 (RN)"),
    "NORWAY": ("NO", 0, "Norway"),
}


def select_analysis_area(page):
    """Keep the selected reservoir area when switching between analysis pages."""
    # Streamlit removes page widgets on navigation. Save the value separately.
    if st.session_state.get("_analysis_area_page") != page or "_analysis_area" not in st.session_state:
        st.session_state["_analysis_area"] = st.session_state.get("analysis_area", "NO3")
        st.session_state["_analysis_area_page"] = page

    selected = st.sidebar.selectbox("Reservoir area", list(AREAS), key="_analysis_area",
                                    format_func=lambda code: AREAS[code][2])
    st.session_state["analysis_area"] = selected
    return selected


@st.cache_data(ttl=3600, show_spinner="Fetching NVE reservoir data…")
def reservoir_data():
    return fetch_reservoirs()


@st.cache_data(ttl=86400, max_entries=24, show_spinner="Fetching hourly ERA5 data…")
def weather_data(region, start, end):
    return download_weather(region, start, end)


def show_figure(figure):
    st.pyplot(figure)
    plt.close(figure)
