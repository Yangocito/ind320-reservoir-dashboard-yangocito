"""Time alignment, River forecasts and date-ordered evaluation for Part 4."""

from io import BytesIO
from time import perf_counter
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd
from river import linear_model, optim

FX_URL = "https://data.norges-bank.no/api/data/EXR/B.EUR+USD.NOK.SP"
WEATHER_LABELS = {
    "temperature_2m": "Temperature (°C)",
    "precipitation": "Precipitation (mm)",
    "relative_humidity_2m": "Relative humidity (%)",
}
PERIODS = {"Weekly": ("W-SUN", 52), "Monthly": ("ME", 12)}
DEFAULT = {"resolution": "Weekly", "history_years": 8, "lags": 4, "rate": 0.005,
           "sources": ()}


def exchange_rates(start, end):
    """Get business-day NOK per euro and dollar; weekends stay absent."""
    query = urlencode({"format": "csv", "startPeriod": str(pd.Timestamp(start).date()),
                       "endPeriod": str(pd.Timestamp(end).date())})
    with urlopen(f"{FX_URL}?{query}", timeout=30) as response:
        raw = pd.read_csv(BytesIO(response.read()), sep=";")
    rates = raw.pivot(index="TIME_PERIOD", columns="BASE_CUR", values="OBS_VALUE")
    rates.index = pd.to_datetime(rates.index)
    rates.index.name = "date"
    return rates.sort_index().reindex(columns=["EUR", "USD"])


def reservoir_observations(data, area):
    """Get percentages labelled by NVE's Sunday date, verified by ISO week."""
    kind, number = area
    rows = data.loc[data.area_type.eq(kind) & data.area_number.eq(number)].copy()
    iso = rows.iso_year.astype(int).astype(str) + "-W" + rows.iso_week.astype(int).astype(str).str.zfill(2)
    rows["week_end"] = pd.to_datetime(iso + "-7", format="%G-W%V-%u")
    return (rows.sort_values("date").drop_duplicates("week_end", keep="last")
            .set_index("week_end")["reservoir_filling_fraction"].mul(100).sort_index()
            .rename("Filling (%)"))


def period_weather(weather, freq, local=True, hourly=True):
    """Aggregate UTC hours by Oslo calendar day, then by reporting period."""
    frame = weather.copy()
    if frame.index.tz is not None:
        if local:
            frame.index = frame.index.tz_convert("Europe/Oslo")
        frame.index = frame.index.tz_localize(None)
    results = {}
    for name in frame:
        grouped = frame[name].resample(freq)
        minimum = (7 if freq == "W-SUN" else 27) * (24 if hourly else 1)
        aggregate = grouped.sum(min_count=1) if name == "precipitation" else grouped.mean()
        # A weekly weather total needs nearly all samples; tolerate one DST hour.
        results[name] = aggregate.where(grouped.count() >= minimum - int(hourly))
    return pd.DataFrame(results)


def rolling_correlation(filling, weather, window, lag, target="change"):
    """Positive lag means weather leads the change or level in reservoir filling."""
    weekly = filling.asfreq("W-SUN")
    if target == "change":
        weekly = weekly.diff()
    joined = pd.concat({"Filling": weekly, "Weather": weather.asfreq("W-SUN").shift(lag)}, axis=1)
    return joined.Filling.rolling(window, min_periods=window).corr(joined.Weather).rename("Correlation")


def model_frame(filling, drivers, resolution):
    """Keep empty periods explicit. Use the last weekly level within each month."""
    freq, _ = PERIODS[resolution]
    target = filling.resample(freq).last().rename("filling")
    if drivers.empty:
        return target.to_frame()
    aggregated = {}
    for name in drivers:
        period = drivers[name].resample(freq)
        aggregated[name] = period.sum(min_count=1) if name == "precipitation" else period.mean()
    return target.to_frame().join(pd.DataFrame(aggregated))


def forecast_filling(filling, drivers, *, as_of, horizon_months=3, resolution="Weekly",
                     history_years=8, lags=4, rate=0.005, sources=()):
    """Fit direct River regressions for future periods using origin data only.

    Each model learns the change from the last observed filling to one lead.
    A one-period driver lag leaves time for ERA5 and FX observations to arrive.
    Regional filling becomes available on Wednesday after the reporting week.
    """
    if not 1 <= horizon_months <= 12 or lags < 1 or rate <= 0 or history_years < 1:
        raise ValueError("Use 1–12 forecast months, positive lags, history and learning rate.")
    freq, annual = PERIODS[resolution]
    as_of = pd.Timestamp(as_of).normalize()
    cutoff = as_of - pd.Timedelta(days=3)
    start = as_of - pd.DateOffset(years=history_years)
    actual = filling.loc[start:cutoff].dropna()
    if actual.empty:
        raise ValueError("No published observations in this training range.")
    missing = set(sources).difference(drivers.columns)
    if missing:
        raise ValueError(f"Selected records are unavailable: {', '.join(sorted(missing))}.")
    frame = model_frame(actual, drivers.reindex(columns=list(sources)), resolution).loc[:cutoff]
    if frame.empty or len(frame) < max(24, lags + 3):
        raise ValueError("Increase the training timeframe or choose weekly resolution.")
    if pd.isna(frame.filling.iloc[-1]):
        raise ValueError("The most recent training period has no reservoir observation.")
    y = frame.filling.to_numpy()
    prior = frame[list(sources)].shift(1)
    # Fit scaling only on data available at this forecast origin.
    scaled = ((prior - prior.mean()) / prior.std().replace(0, 1)).to_numpy()
    dates = frame.index
    min_position = lags - 1
    future = pd.date_range(dates[-1], as_of + pd.DateOffset(months=horizon_months), freq=freq)[1:]

    def features(position, target_date):
        if not np.isfinite(y[position - lags + 1:position + 1]).all():
            return None
        if not np.isfinite(scaled[position]).all():
            return None
        x = {f"filling_lag_{lag}": (y[position - lag] - 50) / 50 for lag in range(lags)}
        angle = 2 * np.pi * (target_date.dayofyear - 1) / 365.25
        x.update(sin=float(np.sin(angle)), cos=float(np.cos(angle)))
        x.update({name: float(value) for name, value in zip(sources, scaled[position])})
        seasonal = position - annual
        if seasonal >= 0 and np.isfinite(y[seasonal]):
            x["last_year_filling"] = (y[seasonal] - 50) / 50
        return x

    rows = []
    for lead, target_date in enumerate(future, 1):
        model = linear_model.LinearRegression(optimizer=optim.SGD(rate), intercept_lr=rate, l2=0.01)
        # A training pair is usable only when the target is already published.
        count = 0
        for position in range(min_position, len(y) - lead):
            target = y[position + lead]
            x = features(position, dates[position + lead])
            if x is not None and np.isfinite(target):
                model.learn_one(x, (target - y[position]) / 100)
                count += 1
        x = features(len(y) - 1, target_date)
        if x is None or count < 15:
            raise ValueError("Not enough complete history for these lags and predictors. Choose fewer variables or a longer date range.")
        prediction = np.clip(y[-1] + model.predict_one(x) * 100, 0, 100)
        previous_year = y[len(y) - 1 + lead - annual] if lead <= annual and len(y) + lead > annual else np.nan
        rows.append((target_date, prediction, y[-1], previous_year, count))
    output = pd.DataFrame(rows, columns=["Date", "River", "Persistence", "Seasonal naive", "Training pairs"])
    output = output.set_index("Date")
    output.attrs["last_observed"] = dates[-1]
    return output


def backtest(filling, drivers, settings, origins, horizon_months=3, common_monthly=False):
    """Score each fixed origin without its future reservoir or driver records."""
    target = model_frame(filling, pd.DataFrame(), settings["resolution"]).filling
    records = []
    for origin in origins:
        started = perf_counter()
        predictions = forecast_filling(filling, drivers.loc[:origin], as_of=origin,
                                       horizon_months=horizon_months, **settings)
        elapsed = perf_counter() - started
        if common_monthly and settings["resolution"] == "Weekly":
            # Compare both resolutions on the same last observed Sunday per month.
            months = predictions.index + pd.offsets.MonthEnd(0)
            last_sundays = months - pd.to_timedelta((months.dayofweek + 1) % 7, unit="D")
            predictions = predictions.loc[(predictions.index == last_sundays) &
                                          (months <= origin + pd.DateOffset(months=horizon_months))]
        errors = predictions[["River", "Persistence", "Seasonal naive"]].sub(target, axis=0)
        errors = errors.reindex(predictions.index).dropna()
        if errors.empty:
            raise ValueError(f"No completed outcomes after {origin}.")
        record = errors.abs().mean().to_dict()
        record.update(origin=origin, seconds=elapsed, predictions=len(errors))
        records.append(record)
    return pd.DataFrame(records).set_index("origin")
