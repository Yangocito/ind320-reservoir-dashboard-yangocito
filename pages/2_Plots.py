"""Download-window selection and one reservoir plot line per NVE area number."""

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from utils import DISPLAY_NAMES, area_series, fetch_area_names, fetch_reservoirs

st.title("Reservoir measurements")
st.write("Select a date window, area type and variable. Each area number has its own line.")


@st.cache_data(ttl=3600, show_spinner="Fetching NVE reservoir data…")
def load_data() -> pd.DataFrame:
    return fetch_reservoirs()


@st.cache_data(ttl=86400)
def load_names() -> dict:
    return fetch_area_names()


try:
    all_data = load_data()
except Exception as exc:
    st.error(f"Could not read NVE data: {exc}")
    st.stop()
try:
    names = load_names()
except Exception:
    names = {}

# NVE's endpoint has no date query parameters. The slider controls rows in
# the plot and the user's CSV download, not the server's API transfer.
available_months = pd.date_range(all_data["date"].min().to_period("M").to_timestamp(),
                                 all_data["date"].max().to_period("M").to_timestamp(), freq="MS")
options = [month.strftime("%Y-%m") for month in available_months]
start_label, end_label = st.select_slider(
    "Download interval (inclusive months)", options=options,
    value=(options[max(0, len(options) - 24)], options[-1]),
)
start = pd.Timestamp(f"{start_label}-01")
end = pd.Timestamp(f"{end_label}-01") + pd.offsets.MonthEnd(1)
filtered = all_data[all_data["date"].between(start, end)]
area_type = st.radio("Area type", ["EL", "NO", "VASS"], horizontal=True)
measurement = st.selectbox("Measurement", list(DISPLAY_NAMES),
                           format_func=lambda value: DISPLAY_NAMES[value])
subset = filtered[filtered["area_type"] == area_type]
monthly = area_series(subset, area_type, measurement, names, monthly=True)
if monthly.empty:
    st.warning("No data for this selection.")
    st.stop()

fig, ax = plt.subplots(figsize=(11, 5))
for column in monthly:
    ax.plot(monthly.index, monthly[column], label=column, linewidth=1.8)
ax.set(title=f"{DISPLAY_NAMES[measurement]} by {area_type} area",
       xlabel="Month", ylabel=DISPLAY_NAMES[measurement])
ax.grid(alpha=0.25)
ax.legend(loc="best", fontsize=8, ncol=2)
fig.autofmt_xdate()
fig.tight_layout()
st.pyplot(fig, use_container_width=True)
st.caption(f"{len(subset):,} weekly rows in the selected download interval.")
st.download_button("Download selected NVE rows (CSV)",
                   subset.to_csv(index=False).encode("utf-8"),
                   file_name=f"nve_{area_type}_{start_label}_{end_label}.csv",
                   mime="text/csv")
st.caption("The public NVE endpoint returns the complete dataset; this control filters the "
           "rows used for the chart and CSV download after the API response.")
