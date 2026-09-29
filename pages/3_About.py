"""About page, included as the fourth page required by the assignment."""

import streamlit as st


st.title("About this project")
st.write(
    "This is the first IND320 project hand-in. The app reads the local "
    "reservoirs.csv file, caches the data, renames the original Norwegian "
    "headers in Python, and presents monthly measurement plots."
)
st.markdown(
    """
    **Planned extension:** In a later project part, the local CSV can be replaced
    by an online database without changing the user interface.
    """


