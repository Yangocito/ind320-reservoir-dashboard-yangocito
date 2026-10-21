# IND320 Reservoir Dashboard – part 2

This project extends the existing Streamlit app and local notebook. The app
fetches current reservoir statistics from [NVE](https://biapi.nve.no/magasinstatistikk/swagger/index.html).
The locally run notebook fetches two years of [ENTSO-E physical flows](https://transparencyplatform.zendesk.com/hc/en-us/articles/16583889683476-Physical-Flows-12-1-G),
writes market periods to Cassandra using Spark, reads/aggregates them in
Spark, and writes daily MWh totals to MongoDB. The deployed app reads MongoDB.

## Run the notebook locally

Use **Python 3.11** for the local Spark 3.5 notebook. The user's Python 3.14
kernel cannot be assumed compatible with that Spark version. Install packages
once in a dedicated environment, then select that same Jupyter kernel for
every notebook. The default connector coordinate
`com.datastax.spark:spark-cassandra-connector_2.12:3.5.1` is for Spark 3.5
with Scala 2.12. If the installed Spark/Scala versions differ, set
`SPARK_CONNECTOR_PACKAGE` to a compatible coordinate.

    py -3.11 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements-notebook.txt
    .\.venv\Scripts\python.exe -m ipykernel install --user --name ind320-py311 --display-name "IND320 Python 3.11"

Open `IND320_reservoirs_analysis.ipynb` in your existing Jupyter/VS Code
installation and choose that kernel. PowerShell activation is not required.

In Jupyter, select **IND320 Python 3.11** as the kernel. You need Java and a
running local Cassandra service for the independent Spark/Cassandra checks.
In PowerShell, `Test-NetConnection 127.0.0.1 -Port 9042` should report a
successful TCP connection. If `py -3.11` is not found, install Python 3.11
before creating this environment. This one-time environment setup is not
repeated when opening another file.

The notebook checks NVE, Cassandra, Spark and MongoDB independently of the
ENTSO-E token. Enter the MongoDB URI when prompted (input is hidden); the
check writes, reads and removes a temporary document. Until the token is
granted, the ENTSO-E request and dependent flow charts print an explicit
"skipped" message instead of producing `NameError` tracebacks. Once the
token arrives, set `ENTSOE_TOKEN` in the process environment and rerun.
The notebook can read `MONGODB_URI` from the environment too. Never paste
secrets into a code cell, commit `.streamlit/secrets.toml`, or include
credentials in a screenshot. If Cassandra is on another local host/port, set
`CASSANDRA_HOST` and `CASSANDRA_PORT`.

Run **all** notebook cells and inspect the real response counts, checks and plots.
The notebook deliberately contains no invented execution output. Update the
300–500-word log to describe what actually happened, including any skipped
sections. Add the screencast URL,
then export the executed notebook:

    jupyter nbconvert --to html IND320_reservoirs_analysis.ipynb

For the PDF, use Jupyter's **Print → Save as PDF** on the HTML file, or
`jupyter nbconvert --to webpdf IND320_reservoirs_analysis.ipynb` if
Playwright/Chromium is installed. Check that code outputs and every plot are
visible in the PDF before uploading it to Canvas.

## Run and deploy Streamlit

For the local app, copy `.streamlit/secrets.example.toml` to
`.streamlit/secrets.toml` and replace its placeholder URI. For Streamlit
Community Cloud, paste just `MONGODB_URI = "..."` into **App settings →
Secrets**. The MongoDB user needs read access to `ind320.flows_daily`, and
the cluster's network access must permit the deployed app.

    python -m pip install -r requirements.txt
    streamlit run app.py

The reservoir endpoint returns all historical rows and exposes no date
parameters. The month slider controls the rows selected for plotting and
the CSV download **after** the API request. The CSV from part 1 is removed.
The app uses EL, NO and VASS independently and provides one line/sparkline
for each area number.

## Submission branch and screencast

Make a new branch in the original repository (for example
`part-2-apis-databases`), commit this code and the **one** notebook, and
push the branch. Keep `main` unchanged until the reviews are complete.
The app must be deployed from this branch for the reviewer to see the new
pages. The five-minute screencast should show the reservoir controls, the
MongoDB flow page, and the API → Cassandra → Spark → MongoDB code path.
Place its shareable URL in the notebook or in the Canvas submission comment.

In your local repository, create the branch **before** copying in the ZIP
contents:

    git switch -c part-2-apis-databases
    # Copy the ZIP's project contents over the corresponding repo files.
    git add -A
    git commit -m "Build IND320 part 2 API and database dashboard"
    git push -u origin part-2-apis-databases

Check that Streamlit is deploying this branch, rather than the old main
version, before recording the screencast.

## Project links

- [GitHub project branch](https://github.com/Yangocito/ind320-reservoir-dashboard-yangocito/tree/part-2-apis-databases)
- [Streamlit app](https://ind320-reservoir-dashboard-yangocito-jqlwog89hlllmliwtrhsmd.streamlit.app/)
