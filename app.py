"""Home page for the IND320 reservoir dashboard."""

import streamlit as st


st.set_page_config(
    page_title="IND320 Reservoir Dashboard",
    page_icon="💧",
    layout="wide",
)

st.title("IND320: Reservoir data dashboard")
st.subheader("Data to decision – compulsory project work")
st.write(
    "Explore Norwegian reservoir statistics from NVE's public API and "
    "cross-border electricity flows from ENTSO-E through MongoDB."
)

st.info(
    "Start with **Data table** or **Plots** to explore NVE's areas. "
    "Open **Cross-border flows** to compare imports and exports."
)



  
st.markdown("### Project overview")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Reservoir source", "NVE API")
with col2:
    st.metric("Flow source", "ENTSO-E")
with col3:
    st.metric("Stored flow data", "MongoDB")

