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
    "This app explores Norwegian reservoir measurements from the IND320 course "
    "dataset. Use the pages in the sidebar to inspect the imported data and "
    "visualise monthly developments."
)

st.info(
    "Start with **Data table** to see the imported columns and the first-month "
    "sparkline. Then open **Plots** to choose a variable and a time period."
)

st.sidebar.header("Navigation")
st.sidebar.write("Use the page links below or Streamlit's page menu.")
st.sidebar.page_link("app.py", label="Home", icon="🏠")
st.sidebar.page_link("pages/1_Data_table.py", label="Data table", icon="📋")
st.sidebar.page_link("pages/2_Plots.py", label="Plots", icon="📈")
st.sidebar.page_link("pages/3_About.py", label="About", icon="ℹ️")
  

st.markdown("### Project overview")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Data source", "reservoirs.csv")
with col2:
    st.metric("Analysis level", "Monthly means")
with col3:
    st.metric("Measurements", "5")

