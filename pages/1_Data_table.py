"""Area-aware NVE data overview with a sparkline per area number."""

import pandas as pd
import streamlit as st

from utils import DISPLAY_NAMES, area_series, fetch_area_names, fetch_reservoirs

st.title("NVE reservoir data")
st.caption("Weekly observations fetched from the live Magasinstatistikk API.")


@st.cache_data(ttl=3600, show_spinner="Fetching NVE reservoir data…")
def load_data() -> pd.DataFrame:
    return fetch_reservoirs()


@st.cache_data(ttl=86400)
def load_names() -> dict:
    return fetch_area_names()


try:
    data = load_data()
except Exception as exc:
    st.error(f"Could not read NVE data: {exc}")
    st.stop()
try:
    names = load_names()
except Exception:
    names = {}

area_type = st.radio("Area type", ["EL", "NO", "VASS"], horizontal=True)
measurement = st.selectbox("Measurement for mini charts", list(DISPLAY_NAMES),
                           format_func=lambda value: DISPLAY_NAMES[value])
series = area_series(data, area_type, measurement, names)
if series.empty:
    st.warning("No observations found for this area type.")
    st.stop()

# One table row (and LineChartColumn) per associated NVE area number.
rows = []
for column in series:
    values = series[column].dropna()
    rows.append({
        "Area": column,
        "Weekly observations": len(values),
        "Latest observation": values.index[-1].date() if not values.empty else None,
        "Latest value": float(values.iloc[-1]) if not values.empty else None,
        "Trend": values.tail(16).round(4).tolist(),
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
             column_config={"Trend": st.column_config.LineChartColumn(
                 "Last 16 observations", help=f"Weekly {DISPLAY_NAMES[measurement]} for each area number"
             )})
st.caption(f"{len(data):,} rows across all area types, {data['date'].min().date()}–{data['date'].max().date()}.")
with st.expander("Inspect API rows for the selected area type"):
    st.dataframe(data[data["area_type"] == area_type].tail(100), use_container_width=True)
