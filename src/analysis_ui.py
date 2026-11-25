"""Cached data access, shared selections and consistent Plotly styling."""

from contextlib import contextmanager

import pandas as pd
import plotly.express as px
import streamlit as st

from src.forecast import exchange_rates
from src.utils import fetch_reservoirs
from src.weather import daily_weather, download_weather, sample_locations

AREAS = {"Norway": ("NO", 0, "NORWAY")}
AREAS.update({f"NO{i}": ("EL", i, f"NO{i}") for i in range(1, 6)})
AREAS.update({f"Water area {i}": ("VASS", i, f"VASS{i}") for i in range(1, 4)})
REGION_LABELS = {value[2]: key for key, value in AREAS.items()}
COLORS = ["#087e86", "#df8e33", "#5864b3", "#ca536f", "#3570a0", "#60843a"]


@st.cache_data(ttl=1800, show_spinner="Getting reservoir observations from NVE…")
def reservoir_data():
    data = fetch_reservoirs()
    if data.empty:
        raise ValueError("NVE returned no reservoir observations.")
    return data


@st.cache_data(ttl=21600, show_spinner="Getting exchange rates from Norges Bank…")
def fx_data(start, end):
    return exchange_rates(start, end)


@st.cache_data(ttl=21600, show_spinner="Getting regional ERA5 daily weather…", max_entries=48)
def weather_daily(region, start, end):
    return daily_weather(region, start, end)


@st.cache_data(ttl=21600, show_spinner="Getting hourly ERA5 weather…", max_entries=24)
def weather_hourly(region, start, end):
    sample = sample_locations(count=24, regions=[region])
    return download_weather(region, start, end, sample)


@contextmanager
def display_data_errors(source):
    """Report network, numerical and missing-data errors without tracebacks."""
    try:
        yield
    except (OSError, ValueError, RuntimeError, KeyError, TimeoutError) as exc:
        if getattr(exc, "code", None) == 429:
            message = "The provider is limiting requests. Try again later or select a shorter interval."
        elif getattr(exc, "code", None) == 404:
            message = "The provider returned no observations for this date range."
        elif isinstance(exc, (ValueError, RuntimeError)):
            message = str(exc)
        else:
            message = "The provider could not be reached or its response changed. Try again later."
        st.warning(f"{source}: {message}")


def shared_controls():
    today = pd.Timestamp.now(tz="Europe/Oslo").date()
    st.session_state.setdefault("chosen_area", "NO3")
    with st.sidebar:
        st.header("Shared selections")
        st.selectbox("Reservoir region", tuple(AREAS), key="chosen_area")
        st.date_input("Analysis / forecast date", value=today, max_value=today,
                      min_value=pd.Timestamp("2005-01-01").date(), key="as_of")
        st.slider("Forecast horizon (months)", 1, 12, 3, key="horizon")
    return AREAS[st.session_state.chosen_area], pd.Timestamp(st.session_state.as_of)


def area_context():
    return AREAS[st.session_state.chosen_area], pd.Timestamp(st.session_state.as_of)


def archive_end(as_of):
    """ERA5 observations are usually published several days after observation."""
    today = pd.Timestamp.now(tz="Europe/Oslo").tz_localize(None).normalize()
    return min(as_of, today - pd.Timedelta(days=7))


def show_plot(fig):
    fig.update_layout(template="plotly_white", colorway=COLORS, hovermode="x unified",
                      margin=dict(l=20, r=15, t=48, b=72 if fig.frames else 24),
                      legend=dict(orientation="h", y=1.04, x=0))
    st.plotly_chart(fig, width="stretch")


def lines(data, label, **kwargs):
    return px.line(data, labels={"value": label, "variable": "", "index": "Date"}, **kwargs)
