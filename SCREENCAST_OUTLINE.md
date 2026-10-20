# Five-minute screencast outline

- **0:00–0:35** Open the deployed app. Explain the two public API sources
  and that the flow page reads curated rows from MongoDB.
- **0:35–1:30** Show NVE Data table. Select EL, NO, VASS. Point out one
  area-number sparkline per row and the API source.
- **1:30–2:20** Show Plots. Change measurement, area type and date interval.
  Download the selected CSV. Explain that NVE returns full history and the
  interval filters the displayed/exported rows.
- **2:20–3:20** Show Cross-border flows. Change connection/year, then choose
  multiple month pills. Explain that MW × hours gives transferred MWh, with
  separate import/export directions.
- **3:20–4:35** Show the executed notebook: NVE API call, Cassandra/Spark
  connection and write/read, January line plot, MongoDB readback. Explain
  the UTC timestamps and the daily Spark aggregation.
- **4:35–5:00** Show the source expander, GitHub feature branch and the
  notebook links. Summarise what you learned and one issue you resolved.

Record the running app and your own explanation. Check that the video link
is accessible to a peer reviewer before submitting.
