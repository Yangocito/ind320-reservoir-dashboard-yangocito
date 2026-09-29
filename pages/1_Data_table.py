"""Data table page: one row per imported data column plus a first-month sparkline."""

import pandas as pd
import streamlit as st

from utils import DISPLAY_NAMES, MEASUREMENT_COLUMNS, _prepare_data
from utils import monthly_measurements


st.title("Imported data")
st.caption("Each row represents one column from reservoirs.csv.")


@st.cache_data
def load_data() -> pd.DataFrame:
    """Cache the local CSV read so the app does not reload it on every interaction."""
    return _prepare_data()


data = load_data()
monthly = monthly_measurements(data)
first_month = data["date"].min().to_period("M")
first_month_data = data[data["date"].dt.to_period("M") == first_month]

summary_rows = []
for column in data.columns:
    if column in MEASUREMENT_COLUMNS:
        values = first_month_data[column].dropna().round(4).tolist()
        first_month_average = first_month_data[column].mean()
        description = DISPLAY_NAMES[column]
    else:
        values = []
        first_month_average = None
        description = "Metadata / calendar field"

    summary_rows.append(
        {
            "Column": column,
            "Description": description,
            "Data type": str(data[column].dtype),
            "Non-null values": int(data[column].notna().sum()),
            f"Average in {first_month}": first_month_average,
            "First month trend": values,
        }
    )

summary = pd.DataFrame(summary_rows)
st.dataframe(
    summary,
    use_container_width=True,
    hide_index=True,
    column_config={
        "First month trend": st.column_config.LineChartColumn(
            "First month trend",
            help="Weekly observations in the first calendar month for measurement columns.",
        ),
        f"Average in {first_month}": st.column_config.NumberColumn(format="%.4f"),
    },
)

st.write(
    f"The raw dataset contains **{len(data):,} rows** from "
    f"**{data['date'].min().date()}** to **{data['date'].max().date()}**."
)

with st.expander("Preview of the raw imported rows"):
    st.dataframe(data.head(20), use_container_width=True, hide_index=True)
