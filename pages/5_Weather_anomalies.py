"""ERA5 precipitation control chart and temperature anomaly detection."""

from datetime import date

import streamlit as st

from analyses import precipitation_spc, temperature_lof
from analysis_ui import AREAS, select_analysis_area, show_figure, weather_data
from weather import PRICE_AREAS

st.title("Weather outliers and anomalies")
region = select_analysis_area("weather")
st.caption(f"{AREAS[region][2]} · hourly ERA5 regional averages from Open-Meteo")
if region not in PRICE_AREAS:
    st.caption("Weather boundaries use NVE administrative regions as an approximation.")
with st.form("weather_download"):
    start = st.date_input("Start date (UTC)", date(2024, 1, 1), min_value=date(1940, 1, 1))
    end = st.date_input("End date (UTC)", date(2024, 1, 28), min_value=date(1940, 1, 1))
    st.caption("Choose up to 60 days. The notebook runs the full year 2024 for NO3.")
    submitted = st.form_submit_button("Download weather data")
if submitted:
    if not 2 <= (end - start).days + 1 <= 60:
        st.warning("Choose a date range of 2 to 60 days.")
    else:
        try:
            st.session_state["weather_result"] = (region, start, end, weather_data(region, start, end))
        except Exception as exc:
            st.error(f"Could not load ERA5 data: {exc}")
            st.stop()

selection = st.session_state.get("weather_result")
if selection is None or selection[:3] != (region, start, end):
    st.info("Download weather data for the selected reservoir area and date range.")
    st.stop()

weather = selection[3]
st.caption(f"{len(weather):,} hours · {weather.attrs['sampled_locations']:,} sampled points · "
           f"{weather.attrs['era5_cells']} unique ERA5 cells")
spc, lof = st.tabs(["Outliers / SPC", "Anomalies / LOF"])
with spc:
    left, right = st.columns(2)
    cutoff = left.number_input("DCT cutoff period (days)", 1, 120, 30)
    deviations = right.number_input("Robust deviations", 1.0, 10.0, 4.0, step=0.5)
    try:
        figure, summary, details = precipitation_spc(weather["precipitation"], cutoff, deviations)
        show_figure(figure)
        st.metric("Flagged hours", f"{summary['outliers']:,}", f"{summary['outlier_percent']:.2f}% of hours",
                  delta_color="off")
        st.caption(f"Robust scale: {summary['robust_sigma_mm']:.3f} mm")
        st.dataframe(details.head(100))
    except ValueError as exc:
        st.warning(str(exc))
with lof:
    percentage = st.slider("Expected anomaly share (%)", 0.1, 10.0, 1.0, step=0.1)
    try:
        figure, summary, details = temperature_lof(weather["temperature_2m"], percentage / 100)
        show_figure(figure)
        st.metric("Flagged hours", f"{summary['anomalies']:,}", f"{summary['anomaly_percent']:.2f}% of hours",
                  delta_color="off")
        st.dataframe(details.head(100))
    except ValueError as exc:
        st.warning(str(exc))
