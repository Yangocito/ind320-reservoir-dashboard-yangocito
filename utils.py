"""Shared data-loading and plotting helpers for the IND320 Streamlit app."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


DATA_PATH = Path(__file__).parent / "data" / "reservoirs.csv"

COLUMN_NAMES = {
    "dato_Id": "date",
    "omrType": "area_type",
    "omrnr": "area_number",
    "iso_aar": "iso_year",
    "iso_uke": "iso_week",
    "fyllingsgrad": "reservoir_filling_fraction",
    "kapasitet_TWh": "capacity_TWh",
    "fylling_TWh": "stored_energy_TWh",
    "neste_Publiseringsdato": "next_publication_date",
    "fyllingsgrad_forrige_uke": "filling_fraction_previous_week",
    "endring_fyllingsgrad": "change_in_filling_fraction",
}

MEASUREMENT_COLUMNS = [
    "reservoir_filling_fraction",
    "capacity_TWh",
    "stored_energy_TWh",
    "filling_fraction_previous_week",
    "change_in_filling_fraction",
]

DISPLAY_NAMES = {
    "reservoir_filling_fraction": "Reservoir filling fraction",
    "capacity_TWh": "Capacity (TWh)",
    "stored_energy_TWh": "Stored energy (TWh)",
    "filling_fraction_previous_week": "Filling fraction, previous week",
    "change_in_filling_fraction": "Change in filling fraction",
}


def _prepare_data() -> pd.DataFrame:
    """Read the CSV, rename headers, and parse date fields."""
    data = pd.read_csv(DATA_PATH)
    data = data.rename(columns=COLUMN_NAMES)
    data["date"] = pd.to_datetime(data["date"])
    # The source uses year 0001 as a missing-date placeholder.
    next_publication = data["next_publication_date"].replace(
        "0001-01-01T00:00:00", pd.NA
    )
    data["next_publication_date"] = pd.to_datetime(
        next_publication, errors="coerce", format="mixed"
    )
    return data.sort_values("date").reset_index(drop=True)


def monthly_measurements(data: pd.DataFrame) -> pd.DataFrame:
    """Return monthly means for the measurement columns, indexed by month."""
    monthly = (
        data.set_index("date")[MEASUREMENT_COLUMNS]
        .resample("MS")
        .mean()
        .dropna(how="all")
    )
    monthly.index.name = "month"
    return monthly


def min_max_scale(data: pd.DataFrame) -> pd.DataFrame:
    """Scale columns to 0-1 so differently scaled measurements can share a plot."""
    result = data.copy()
    for column in result.columns:
        minimum = result[column].min()
        maximum = result[column].max()
        if maximum == minimum:
            result[column] = 0.0
        else:
            result[column] = (result[column] - minimum) / (maximum - minimum)
    return result


def make_measurement_plot(
    monthly: pd.DataFrame,
    selected_column: str,
    start_month: pd.Timestamp,
    end_month: pd.Timestamp,
):
    """Create a formatted matplotlib figure for one or all measurements."""
    selected = monthly.loc[start_month:end_month]
    fig, ax = plt.subplots(figsize=(11, 5.5))

    if selected_column == "All measurement columns":
        plot_data = min_max_scale(selected)
        for column in plot_data.columns:
            ax.plot(
                plot_data.index,
                plot_data[column],
                linewidth=1.8,
                label=DISPLAY_NAMES[column],
            )
        ax.set_ylabel("Scaled value (0–1)")
        ax.set_title("Monthly reservoir measurements, min–max scaled")
        ax.legend(loc="upper left", fontsize=8, ncol=2)
    else:
        column = selected_column
        ax.plot(
            selected.index,
            selected[column],
            marker="o",
            markersize=3,
            linewidth=1.8,
            color="#0f766e",
        )
        ax.set_ylabel(DISPLAY_NAMES[column])
        ax.set_title(f"Monthly development: {DISPLAY_NAMES[column]}")

    ax.set_xlabel("Month")
    ax.grid(True, alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig
