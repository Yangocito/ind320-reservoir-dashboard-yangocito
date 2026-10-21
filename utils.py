"""NVE API loading and reservoir plotting shared by notebook and Streamlit."""

import json
from datetime import date
from urllib.request import Request, urlopen

import matplotlib.pyplot as plt
import pandas as pd

NVE_BASE = "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk"
NVE_DATA_URL = f"{NVE_BASE}/HentOffentligData"
NVE_AREAS_URL = f"{NVE_BASE}/HentOmr%C3%A5der"
COLUMN_NAMES = {
    "dato_Id": "date", "omrType": "area_type", "omrnr": "area_number",
    "iso_aar": "iso_year", "iso_uke": "iso_week",
    "fyllingsgrad": "reservoir_filling_fraction",
    "kapasitet_TWh": "capacity_TWh", "fylling_TWh": "stored_energy_TWh",
    "neste_Publiseringsdato": "next_publication_date",
    "fyllingsgrad_forrige_uke": "filling_fraction_previous_week",
    "endring_fyllingsgrad": "change_in_filling_fraction",
}
MEASUREMENT_COLUMNS = [
    "reservoir_filling_fraction", "capacity_TWh", "stored_energy_TWh",
    "filling_fraction_previous_week", "change_in_filling_fraction",
]
DISPLAY_NAMES = {
    "reservoir_filling_fraction": "Reservoir filling fraction",
    "capacity_TWh": "Capacity (TWh)",
    "stored_energy_TWh": "Stored energy (TWh)",
    "filling_fraction_previous_week": "Filling fraction, previous week",
    "change_in_filling_fraction": "Change in filling fraction",
}


def _get_json(url: str):
    """Read a public JSON endpoint with an explicit timeout."""
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "IND320-course-project/2"})
    with urlopen(request, timeout=45) as response:
        return json.load(response)


def fetch_reservoirs(start_date: date | str | None = None,
                     end_date: date | str | None = None) -> pd.DataFrame:
    """Fetch NVE's full response and select observation dates locally.

    The HentOffentligData endpoint does not expose server-side date parameters.
    """
    payload = _get_json(NVE_DATA_URL)
    if isinstance(payload, dict):
        payload = payload.get("data", payload.get("value", payload))
    if not isinstance(payload, list) or not payload:
        raise ValueError("NVE returned no reservoir rows or changed its response format.")
    data = pd.DataFrame(payload).rename(columns=COLUMN_NAMES)
    required = {"date", "area_type", "area_number", *MEASUREMENT_COLUMNS}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Missing NVE columns: {', '.join(sorted(missing))}")
    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.normalize()
    data["area_number"] = pd.to_numeric(data["area_number"], errors="coerce")
    for column in MEASUREMENT_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if "next_publication_date" in data:
        data["next_publication_date"] = pd.to_datetime(
            data["next_publication_date"].replace("0001-01-01T00:00:00", pd.NA),
            errors="coerce", format="mixed",
        )
    data = data.dropna(subset=["date", "area_type", "area_number"])
    if start_date is not None:
        data = data[data["date"] >= pd.Timestamp(start_date)]
    if end_date is not None:
        data = data[data["date"] <= pd.Timestamp(end_date)]
    return data.sort_values(["date", "area_type", "area_number"]).reset_index(drop=True)


def fetch_area_names() -> dict[tuple[str, int], str]:
    """Read NVE's area names for EL, NO and VASS area numbers."""
    payload = _get_json(NVE_AREAS_URL)
    if isinstance(payload, dict):
        areas = sum((payload.get(key) or [] for key in ("land", "elspot", "vassdrag")), [])
    elif isinstance(payload, list):
        areas = payload
    else:
        raise ValueError("Unknown NVE area response format.")
    return {
        (str(row["omrType"]), int(row["omrnr"])):
        str(row.get("navn_langt") or row.get("navn") or row.get("beskrivelse") or row["omrnr"])
        for row in areas if row.get("omrType") is not None and row.get("omrnr") is not None
    }


def area_series(data: pd.DataFrame, area_type: str, measurement: str,
                area_names: dict | None = None, monthly: bool = False) -> pd.DataFrame:
    """Return a separate line for each area number within an area type."""
    if measurement not in MEASUREMENT_COLUMNS:
        raise ValueError(f"Unknown measurement: {measurement}")
    subset = data.loc[data["area_type"] == area_type, ["date", "area_number", measurement]]
    result = subset.pivot_table(index="date", columns="area_number", values=measurement, aggfunc="mean")
    if monthly:
        result = result.resample("MS").mean().dropna(how="all")
    names = area_names or {}
    result.columns = [
        f"{area_type} {int(number)} – {names.get((area_type, int(number)), 'Area ' + str(int(number)))}"
        for number in result.columns
    ]
    return result.sort_index()


def monthly_measurements(data: pd.DataFrame) -> pd.DataFrame:
    """Monthly means for Norway (NO 0), without averaging overlapping areas."""
    nationwide = data.loc[(data["area_type"] == "NO") & (data["area_number"] == 0)]
    return nationwide.set_index("date")[MEASUREMENT_COLUMNS].resample("MS").mean().dropna(how="all")


def min_max_scale(data: pd.DataFrame) -> pd.DataFrame:
    """Scale differently measured series to 0–1 for the combined chart."""
    result = data.copy()
    for column in result.columns:
        minimum, maximum = result[column].min(), result[column].max()
        result[column] = 0.0 if maximum == minimum else (result[column] - minimum) / (maximum - minimum)
    return result


def make_measurement_plot(monthly: pd.DataFrame, selected_column: str,
                          start_month: pd.Timestamp, end_month: pd.Timestamp):
    """Recreate the separate and combined plots from part 1 for NO 0."""
    selected = monthly.loc[start_month:end_month]
    fig, ax = plt.subplots(figsize=(11, 5.5))
    if selected_column == "All measurement columns":
        plot_data = min_max_scale(selected)
        for column in plot_data:
            ax.plot(plot_data.index, plot_data[column], linewidth=1.8, label=DISPLAY_NAMES[column])
        ax.set_ylabel("Scaled value (0–1)")
        ax.set_title("Monthly national reservoir measurements, min–max scaled")
        ax.legend(loc="upper left", fontsize=8, ncol=2)
    else:
        ax.plot(selected.index, selected[selected_column], linewidth=1.8, color="#0f766e")
        ax.set_ylabel(DISPLAY_NAMES[selected_column])
        ax.set_title(f"Monthly national development: {DISPLAY_NAMES[selected_column]}")
    ax.set_xlabel("Month")
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig
