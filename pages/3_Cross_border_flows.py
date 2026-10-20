"""MongoDB-backed ENTSO-E cross-border transfer charts."""

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

st.title("Cross-border physical flows")
st.caption("Daily transferred energy from ENTSO-E data prepared by the local notebook.")


def mongo_uri() -> str | None:
    """Read a private Streamlit secret without putting credentials in GitHub."""
    try:
        return st.secrets["MONGODB_URI"]
    except (KeyError, FileNotFoundError):
        return None


@st.cache_data(ttl=3600, show_spinner="Reading MongoDB…")
def load_flows(uri: str) -> pd.DataFrame:
    """Read only curated daily rows; no Cassandra or ENTSO-E token in this app."""
    from pymongo import MongoClient

    client = MongoClient(uri, serverSelectionTimeoutMS=10000, tz_aware=True)
    try:
        client.admin.command("ping")
        docs = list(client["ind320"]["flows_daily"].find(
            {}, {"_id": 0, "connection": 1, "direction": 1,
                 "date_utc": 1, "energy_mwh": 1}))
    finally:
        client.close()
    data = pd.DataFrame(docs)
    if not data.empty:
        data["date_utc"] = pd.to_datetime(data["date_utc"], utc=True)
        data["year"] = data["date_utc"].dt.year
        data["month"] = data["date_utc"].dt.month
    return data


uri = mongo_uri()
if not uri:
    st.warning("Set MONGODB_URI in Streamlit Secrets to show the curated flow data.")
    st.stop()
try:
    data = load_flows(uri)
except Exception:
    st.error("Could not connect to MongoDB. Check the private URI and network access.")
    st.stop()
if data.empty:
    st.info("No daily flow data in MongoDB yet. Run all notebook cells locally first.")
    st.stop()

left, right = st.columns(2, gap="large")
with left:
    st.subheader("Annual import and export")
    connection = st.radio("Connection", sorted(data["connection"].unique()))
    year = st.selectbox("Year", sorted(data["year"].unique(), reverse=True))
    annual = data[(data["connection"] == connection) & (data["year"] == year)]
    totals = annual.groupby("direction")["energy_mwh"].sum()
    values = [float(totals.get("Into Norway", 0)), float(totals.get("Out of Norway", 0))]
    if sum(values) > 0:
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.pie(values, labels=["Into Norway", "Out of Norway"], autopct="%1.1f%%",
               colors=["#0f766e", "#e69f38"], startangle=90)
        ax.set_title(f"{connection}, {year} (MWh transferred)")
        st.pyplot(fig, use_container_width=True)
        st.caption(f"Into Norway: {values[0]:,.0f} MWh · Out of Norway: {values[1]:,.0f} MWh")
    else:
        st.warning("No positive transferred energy for this connection/year.")

with right:
    st.subheader("Daily flow by connection and direction")
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    selected_months = st.pills("Months to include", month_names, selection_mode="multi",
                              default=["Jan"])
    month_numbers = [month_names.index(name) + 1 for name in selected_months]
    subset = data[(data["year"] == year) & data["month"].isin(month_numbers)]
    if subset.empty:
        st.info("Select a month that has data for this year.")
    else:
        lines = subset.pivot_table(index="date_utc", columns=["connection", "direction"],
                                   values="energy_mwh", aggfunc="sum").sort_index()
        lines.columns = [f"{link} · {direction}" for link, direction in lines.columns]
        st.line_chart(lines, y_label="Transferred energy (MWh/day)")

with st.expander("Source and calculation"):
    st.markdown(
        "Source: [ENTSO-E Transparency Platform, Physical Flows (12.1.G)]"
        "(https://transparencyplatform.zendesk.com/hc/en-us/articles/16583889683476-Physical-Flows-12-1-G). "
        "The notebook requests both directions for NO1–SE3 and NO2–DK1. "
        "ENTSO-E reports average MW for each market interval. We multiply MW by "
        "its duration in hours and sum those MWh by UTC date in Spark. The "
        "curated daily totals are stored in MongoDB and read by this page. "
        "These flows are transfers, not generation or total production."
    )
