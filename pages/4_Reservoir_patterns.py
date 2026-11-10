"""STL and spectrogram views of weekly NVE reservoir filling."""

import streamlit as st

from analyses import filling_spectrogram, filling_stl, weekly_filling
from analysis_ui import AREAS, reservoir_data, select_analysis_area, show_figure

st.title("Reservoir patterns")
code = select_analysis_area("reservoir")
area_type, area_number, label = AREAS[code]
try:
    series = weekly_filling(reservoir_data(), area_type, area_number)
except Exception as exc:
    st.error(f"Could not prepare weekly filling: {exc}")
    st.stop()

st.caption(f"{label} · {len(series)} weeks · {series.attrs['interpolated_weeks']} interpolated weeks")
stl, spectral = st.tabs(["STL", "Spectrogram"])
with stl:
    st.write("Separate observed filling into a trend, a 52-week seasonal pattern and residuals.")
    left, center, right = st.columns(3)
    seasonal = left.number_input("Seasonal smoother", 7, 51, 13, step=2)
    trend = center.number_input("Trend smoother", 53, 301, 79, step=2)
    robust = right.checkbox("Robust fit", value=True)
    try:
        show_figure(filling_stl(series, seasonal=seasonal, trend=trend, robust=robust))
    except ValueError as exc:
        st.warning(str(exc))

with spectral:
    st.write("See when seasonal and shorter cycles contribute to variation in filling.")
    if len(series) < 53:
        st.info("At least 53 weekly observations are needed for this view.")
    else:
        maximum = min(len(series) - 1, 520)
        window = st.slider("Window length (weeks)", 52, maximum, min(156, maximum))
        overlap = st.slider("Window overlap (weeks)", 0, window - 1, (3 * window) // 4)
        show_figure(filling_spectrogram(series, window=window, overlap=overlap))
