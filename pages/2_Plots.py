"""Plot page with a column selector and a month selection slider."""

import pandas as pd
import streamlit as st

from utils import DISPLAY_NAMES, MEASUREMENT_COLUMNS, _prepare_data
from utils import make_measurement_plot, monthly_measurements


st.title("Reservoir measurements")
st.write(
    "The chart uses monthly means. When all measurements are selected, values "
    "are min–max scaled to 0–1 because the variables use different units."
)


@st.cache_data
def load_data() -> pd.DataFrame:
    """Cache the local CSV read for faster app interaction."""
    return _prepare_data()


data = load_data()
monthly = monthly_measurements(data)
month_options = list(monthly.index)
month_labels = [month.strftime("%Y-%m") for month in month_options]

selected_label = st.selectbox(
    "Which column should be plotted?",
    options=["All measurement columns", *MEASUREMENT_COLUMNS],
    format_func=lambda value: value
    if value == "All measurement columns"
    else DISPLAY_NAMES[value],
)

selected_end_label = st.select_slider(
    "Show data from the first month up to:",
    options=month_labels,
    value=month_labels[0],
)
selected_end = pd.Timestamp(selected_end_label + "-01")

st.caption(f"Selected period: {month_labels[0]} to {selected_end_label}")
figure = make_measurement_plot(
    monthly,
    selected_label,
    start_month=month_options[0],
    end_month=selected_end,
)
st.pyplot(figure, use_container_width=True)

