"""Part 3 analyses shared by the notebook and Streamlit."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.fft import dct, idct
from scipy.signal import spectrogram
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler


def _weather_series(series):
    """Require evenly spaced weather observations before analysing them."""
    series = series.astype(float).sort_index()
    if (len(series) < 24 or not np.isfinite(series).all()
            or not (series.index.to_series().diff().dropna() == pd.Timedelta(hours=1)).all()):
        raise ValueError("At least 24 consecutive hourly observations without gaps are required.")
    return series


def precipitation_spc(precipitation, cutoff_days=30, deviations=4.0):
    """Plot raw precipitation with time-varying limits estimated from DCT residuals."""
    series = _weather_series(precipitation)
    if cutoff_days <= 0 or deviations <= 0:
        raise ValueError("The cutoff period and number of deviations must be positive.")

    # Keep frequencies corresponding to periods shorter than cutoff_days.
    # DCT-II bin k has frequency k / (2 N) cycles per hourly observation.
    coefficients = dct(series.to_numpy(), norm="ortho")
    slow = np.arange(len(series)) / (2 * len(series)) <= 1 / (24 * cutoff_days)
    coefficients[slow] = 0
    residual = idct(coefficients, norm="ortho")
    center = np.median(residual)
    sigma = 1.4826 * np.median(np.abs(residual - center))
    # A fallback avoids classifying any tiny numerical difference in constant data.
    if sigma < 1e-10:
        sigma = (np.percentile(residual, 75) - np.percentile(residual, 25)) / 1.349
    if sigma < 1e-10:
        sigma = 0.0
    flagged = np.abs(residual - center) > max(deviations * sigma, 1e-10)
    baseline = series.to_numpy() - residual
    lower, upper = baseline + center - deviations * sigma, baseline + center + deviations * sigma

    details = pd.DataFrame({"precipitation_mm": series, "lower_limit": lower, "upper_limit": upper})
    details = details.loc[flagged]
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(series.index, series, lw=0.8, label="Mean precipitation")
    ax.plot(series.index, upper, color="#9a5800", lw=0.9, label="Robust SPC limits")
    ax.plot(series.index, lower, color="#9a5800", lw=0.9)
    ax.scatter(details.index, details["precipitation_mm"], s=11, color="#c62828",
               label="Outlier", zorder=3)
    ax.set(title="Hourly precipitation and DCT-based control limits", ylabel="Precipitation (mm)")
    ax.legend(loc="upper right")
    fig.tight_layout()
    summary = {"observations": len(series), "outliers": len(details),
               "outlier_percent": 100 * len(details) / len(series), "robust_sigma_mm": sigma}
    return fig, summary, details


def temperature_lof(temperature, proportion=0.01):
    """Find unusual temperatures relative to nearby observations in season and hour."""
    series = _weather_series(temperature)
    if not 0 < proportion <= 0.5:
        raise ValueError("The outlier proportion must be above zero and at most 0.5.")
    index = series.index
    year_angle = 2 * np.pi * (index.dayofyear - 1) / np.where(index.is_leap_year, 366, 365)
    hour_angle = 2 * np.pi * index.hour / 24
    # Cyclic features keep December close to January and 23:00 close to 00:00.
    features = np.column_stack([series, np.sin(year_angle), np.cos(year_angle),
                                np.sin(hour_angle), np.cos(hour_angle)])
    features = StandardScaler().fit_transform(features)
    lof = LocalOutlierFactor(n_neighbors=min(40, len(series) - 1), contamination=proportion)
    flagged = lof.fit_predict(features) == -1
    details = pd.DataFrame({"temperature_c": series, "lof_score": -lof.negative_outlier_factor_})
    details = details.loc[flagged].sort_values("lof_score", ascending=False)

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(index, series, lw=0.8, label="Mean temperature")
    ax.scatter(details.index, details["temperature_c"], s=15, color="#c62828",
               label="LOF anomaly", zorder=3)
    ax.set(title="Hourly temperature and LOF anomalies", ylabel="Temperature (°C)")
    ax.legend(loc="upper right")
    fig.tight_layout()
    summary = {"observations": len(series), "anomalies": len(details),
               "anomaly_percent": 100 * len(details) / len(series)}
    return fig, summary, details


def weekly_filling(data, area_type, area_number):
    """Use one percentage per ISO week and interpolate short internal gaps."""
    rows = data.loc[(data["area_type"] == area_type) & (data["area_number"] == area_number),
                    ["date", "iso_year", "iso_week", "reservoir_filling_fraction"]].dropna()
    rows = rows.sort_values("date").drop_duplicates(["iso_year", "iso_week"], keep="last")
    weeks = (rows["iso_year"].astype(int).astype(str) + "-W"
             + rows["iso_week"].astype(int).astype(str).str.zfill(2) + "-1")
    index = pd.to_datetime(weeks, format="%G-W%V-%u")
    series = pd.Series(100 * rows["reservoir_filling_fraction"].to_numpy(),
                       index=pd.DatetimeIndex(index), name="Filling (%)").sort_index()
    if series.empty:
        raise ValueError("No filling data for this reservoir area.")
    series = series.asfreq("W-MON")
    if series.isna().sum() > 0.05 * len(series):
        raise ValueError("More than 5% of weekly filling observations are missing.")
    gaps = series.isna()
    if (gaps.groupby((~gaps).cumsum()).sum() > 3).any():
        raise ValueError("The weekly series has a gap longer than three weeks.")
    series = series.interpolate(method="time", limit_area="inside")
    series.attrs["interpolated_weeks"] = int(gaps.sum())
    return series


def filling_stl(series, seasonal=13, trend=79, robust=True):
    """Decompose weekly filling using an approximately annual 52-week cycle."""
    from statsmodels.tsa.seasonal import STL

    if len(series) < 104:
        raise ValueError("STL needs at least two years of weekly filling data here.")
    result = STL(series, period=52, seasonal=seasonal, trend=trend, robust=robust).fit()
    fig, axes = plt.subplots(4, 1, figsize=(11, 7), sharex=True)
    for ax, label, values in zip(axes, ("Observed", "Trend", "Seasonal", "Residual"),
                                 (series, result.trend, result.seasonal, result.resid)):
        ax.plot(series.index, values, lw=1)
        ax.set_ylabel(label + " (%)")
        ax.grid(alpha=0.2)
    axes[0].set_title("STL decomposition of weekly reservoir filling")
    fig.tight_layout()
    return fig


def filling_spectrogram(series, window=156, overlap=117):
    """Plot nonzero frequencies of the weekly filling series over time."""
    if not 2 <= window <= len(series) or not 0 <= overlap < window:
        raise ValueError("The window must fit the series and overlap must be shorter than the window.")
    frequency, offset, power = spectrogram(series.to_numpy(), fs=1, window="hann",
                                           nperseg=window, noverlap=overlap, detrend="linear")
    centers = series.index[0] + pd.to_timedelta(offset * 7, unit="D")
    power_db = 10 * np.log10(np.maximum(power[1:], 1e-12))
    fig, ax = plt.subplots(figsize=(11, 4.5))
    image = ax.pcolormesh(centers, frequency[1:] * 52, power_db, shading="auto")
    ax.set(title="Spectrogram of weekly reservoir filling", ylabel="Cycles per year", yscale="log")
    fig.colorbar(image, ax=ax, label="Power spectral density (dB re 1 percentage point² per cycle/week)")
    fig.tight_layout()
    return fig
