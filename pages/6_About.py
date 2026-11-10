"""Source and method documentation, moved from the previous fourth page."""

import streamlit as st

st.title("About this project")
st.markdown(
    """
    This IND320 app uses the [NVE Magasinstatistikk API](https://biapi.nve.no/magasinstatistikk/swagger/index.html)
    for weekly reservoir observations. EL refers to electricity price areas,
    NO to Norway as a whole and VASS to watercourse areas. Each area number
    appears separately in the charts.

    Cross-border physical flows come from the
    [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/).
    The locally run notebook downloads the flow data, writes raw periods to
    Cassandra with Spark, extracts and sums energy in MWh by UTC date, then
    writes the resulting rows to MongoDB. This online app reads only those
    curated MongoDB rows; no ENTSO-E token is deployed with the app.

    A physical flow is measured transfer between bidding zones; it is not
    electricity generation. All dates on the flows page are UTC.
    """
)
