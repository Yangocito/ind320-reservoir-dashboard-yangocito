"""Interactive dashboard pages for exploring and predicting reservoir filling."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st
from plotly.subplots import make_subplots
from scipy.signal import spectrogram
from statsmodels.tsa.seasonal import STL

from src.analyses import precipitation_control_data, sparse_tv, weather_lof, weekly_filling
from src.analysis_ui import (AREAS, COLORS, REGION_LABELS, archive_end, area_context,
                             display_data_errors, fx_data, lines, reservoir_data,
                             show_plot, weather_daily, weather_hourly)
from src.forecast import (DEFAULT, PERIODS, WEATHER_LABELS, forecast_filling,
                          period_weather, reservoir_observations, rolling_correlation)
from src.utils import DISPLAY_NAMES, area_series
from src.weather import REGION_DIR

DRIVER_LABELS = WEATHER_LABELS | {"EUR": "EUR to NOK", "USD": "USD to NOK"}


def heading(title):
    area, as_of = area_context()
    st.title(title)
    st.caption(f"{st.session_state.chosen_area} · As of {as_of:%d %b %Y}")
    return area, as_of


@st.cache_data
def map_shapes(layer):
    return json.loads((REGION_DIR / f"{layer}.geojson").read_text())


def overview():
    (_, _, current), as_of = heading("Norwegian reservoir dashboard")
    st.write("Click a region to use it across the analysis and forecast pages.")
    left, right = st.columns(2)
    layer = left.selectbox("Map boundaries", ("Price areas", "Water areas", "Norway"))
    filename = {"Price areas": "price", "Water areas": "water", "Norway": "national"}[layer]
    metric = right.selectbox("Colour areas by", ("Reservoir filling (%)", *WEATHER_LABELS),
                             format_func=lambda name: WEATHER_LABELS.get(name, name))
    geojson = map_shapes(filename)
    values = {}
    dates = {}
    if metric == "Reservoir filling (%)":
        with display_data_errors("NVE"):
            data = reservoir_data()
            for feature in geojson["features"]:
                region = feature["id"]
                area = AREAS[REGION_LABELS[region]][:2]
                series = reservoir_observations(data, area).loc[:as_of - pd.Timedelta(days=3)].dropna()
                if not series.empty:
                    values[region] = float(series.iloc[-1])
                    dates[region] = f"Week ending {series.index[-1]:%d %b %Y}"
    else:
        end = archive_end(as_of)
        start = end - pd.Timedelta(days=6)
        st.caption(f"Weather interval: {start:%d %b}–{end:%d %b %Y}. Precipitation is summed. Other properties are averaged.")
        for feature in geojson["features"]:
            region = feature["id"]
            with display_data_errors(REGION_LABELS[region]):
                weather = weather_daily(region, start.date(), end.date())[metric]
                if weather.count() == 7:
                    values[region] = float(weather.sum() if metric == "precipitation" else weather.mean())
                    dates[region] = f"{start:%d %b} to {end:%d %b %Y}"

    lower = 0 if metric == "Reservoir filling (%)" else min(values.values(), default=0)
    upper = 100 if metric == "Reservoir filling (%)" else max(values.values(), default=1)
    for feature in geojson["features"]:
        region = feature["id"]
        value = values.get(region)
        colour = [148, 163, 170, 92]
        if value is not None:
            ratio = (value - lower) / (upper - lower) if upper > lower else 0.5
            colour = [int(181 - ratio * 171), int(231 - ratio * 114), int(224 - ratio * 85), 160]
        feature["properties"].update(
            label=REGION_LABELS[region], fill=colour,
            outline=[208, 98, 27] if region == current else [16, 68, 76],
            width=4 if region == current else 1,
            observation=f"{value:.1f} · {dates[region]}" if value is not None else "No data for this period",
        )
    if values:
        st.caption(f"Colour scale: {lower:.1f} (light) to {upper:.1f} (dark). Orange outline marks the selected area.")
    # The named layer and single-object selection expose the clicked GeoJSON feature.
    deck = pdk.Deck(
        layers=[pdk.Layer("GeoJsonLayer", id="reservoir_regions", data=geojson,
                          get_fill_color="properties.fill", get_line_color="properties.outline",
                          get_line_width="properties.width", line_width_units=pdk.types.String("pixels"),
                          line_width_min_pixels=1, line_width_max_pixels=4,
                          line_joint_rounded=True, pickable=True)],
        initial_view_state=pdk.ViewState(latitude=64.7, longitude=14.5, zoom=3.6),
        map_style="light",
        tooltip={"text": "{properties.label}\n{properties.observation}"},
    )
    def select_region():
        state = st.session_state["region_map"]
        objects = state["selection"]["objects"].get("reservoir_regions", [])
        if objects:
            region = objects[0].get("properties", {}).get("region")
            if region in REGION_LABELS:
                st.session_state.chosen_area = REGION_LABELS[region]

    st.pydeck_chart(deck, key="region_map", on_select=select_region, height=610)
    if filename == "water":
        st.caption("Water boundaries approximate the three NVE reporting areas using the previous administrative shapefiles.")
    with st.expander("Map values"):
        st.dataframe(pd.DataFrame({"Area": [REGION_LABELS[key] for key in values],
                                  "Value": list(values.values()),
                                  "Interval": [dates[key] for key in values]}), hide_index=True)


def reservoirs_page():
    (kind, number, _), as_of = heading("Reservoir data")
    with display_data_errors("NVE"):
        data = reservoir_data()
        years = st.slider("Years to inspect", 1, 25, 5)
        start = as_of - pd.DateOffset(years=years)
        data = data.loc[data.date.between(start, as_of - pd.Timedelta(days=3))]
        selected = data.loc[data.area_type.eq(kind) & data.area_number.eq(number)].set_index("date")
        if selected.empty:
            st.info("No archived observations in this date range.")
            return
        metric = st.selectbox("Measurement", tuple(DISPLAY_NAMES), format_func=DISPLAY_NAMES.get)
        monthly = st.radio("Chart resolution", ("Weekly", "Monthly mean"), horizontal=True) == "Monthly mean"
        compare = kind != "NO" and st.checkbox("Compare all areas in this group")
        if compare:
            names = {(value[0], value[1]): key for key, value in AREAS.items()}
            chart = area_series(data, kind, metric, area_names=names, monthly=monthly)
        else:
            chart = selected[metric].rename(DISPLAY_NAMES[metric])
            if monthly:
                chart = chart.resample("MS").mean()
        show_plot(lines(chart, DISPLAY_NAMES[metric]))
        table = selected[list(DISPLAY_NAMES)].rename(columns=DISPLAY_NAMES).sort_index(ascending=False)
        st.dataframe(table)
        st.download_button("Download displayed reservoir data", table.to_csv(), "reservoir_data.csv")


def fx_page():
    _, as_of = heading("Norges Bank exchange rates")
    years = st.slider("Years of exchange rates", 1, 10, 2)
    with display_data_errors("Norges Bank"):
        rates = fx_data((as_of - pd.DateOffset(years=years)).date(), as_of.date())
        show_plot(lines(rates, "Norwegian kroner per unit"))
        st.dataframe(rates.tail(10).sort_index(ascending=False))


def patterns_page():
    (kind, number, _), as_of = heading("Reservoir patterns")
    with display_data_errors("NVE reservoir patterns"):
        data = reservoir_data()
        series = weekly_filling(data[data.date.le(as_of - pd.Timedelta(days=3))], kind, number)
        years = st.slider("Years of weekly observations", 3, 25, 10)
        series = series.loc[as_of - pd.DateOffset(years=years):]
        if len(series) < 104:
            st.info("STL needs at least two years of weekly data for this selection.")
            return
        st.subheader("Seasonal decomposition")
        result = STL(series, period=52, seasonal=13, trend=79, robust=True).fit()
        labels = ("Observed", "Trend", "Seasonal", "Residual")
        fig = make_subplots(rows=4, cols=1, shared_xaxes=True, subplot_titles=labels)
        for row, (label, values) in enumerate(zip(labels, (series, result.trend, result.seasonal, result.resid)), 1):
            fig.add_scatter(x=series.index, y=values, name=label, row=row, col=1,
                            line={"color": COLORS[row - 1]})
            fig.update_yaxes(title_text="%", row=row, col=1)
        fig.update_layout(height=665, showlegend=False)
        show_plot(fig)

        st.subheader("Spectrogram")
        window = st.slider("Window length (weeks)", 52, min(260, len(series)), min(156, len(series)))
        overlap = st.slider("Overlap (%)", 0, 90, 75)
        frequency, offset, power = spectrogram(series.to_numpy(), fs=1, window="hann",
                                               nperseg=window, noverlap=int(window * overlap / 100),
                                               detrend="linear")
        timestamp = series.index[0] + pd.to_timedelta(offset * 7, unit="D")
        fig = go.Figure(go.Heatmap(x=timestamp, y=frequency[1:] * 52,
                                  z=10 * np.log10(np.maximum(power[1:], 1e-12)),
                                  colorscale="Teal", colorbar={"title": "Power (dB)"}))
        fig.update_yaxes(type="log", title="Cycles per year")
        show_plot(fig)


def weather_page():
    (_, _, region), as_of = heading("Weather anomalies")
    end = archive_end(as_of)
    days = st.slider("Days of hourly weather", 3, 42, 14)
    start = end - pd.Timedelta(days=days - 1)
    st.caption(f"{start:%d %b}–{end:%d %b %Y} (UTC). The app uses 24 sampled locations per area.")
    if not st.checkbox("Load hourly weather", key=f"load_hourly_{region}"):
        return
    with display_data_errors("Open-Meteo"):
        weather = weather_hourly(region, start.date(), end.date())
        satv_tab, lof_tab, spc_tab = st.tabs(["SATV", "Local Outlier Factor", "Precipitation control chart"])
        with satv_tab:
            key = st.selectbox("SATV weather property", tuple(WEATHER_LABELS), format_func=WEATHER_LABELS.get)
            tv = st.slider("Signal smoothing", 0.25, 6.0, 2.0)
            penalty = st.slider("Penalty for sparse anomalies", 0.5, 5.0, 2.5)
            result = sparse_tv(weather[key], tv, penalty)
            fig = lines(result[["Observed", "SATV baseline"]], WEATHER_LABELS[key])
            flags = result.loc[result["Sparse component"].abs() > 1e-6]
            fig.add_scatter(x=flags.index, y=flags.Observed, mode="markers", name="Sparse anomalies",
                            marker={"color": COLORS[3]})
            show_plot(fig)
            st.caption(f"{len(flags):,} hourly observations flagged.")
        with lof_tab:
            key = st.selectbox("LOF weather property", tuple(WEATHER_LABELS), format_func=WEATHER_LABELS.get)
            fraction = st.slider("Expected anomaly share (%)", 0.5, 10.0, 1.0)
            result = weather_lof(weather[key], fraction / 100)
            flags = result.loc[result.Flagged]
            fig = lines(result.Observed, WEATHER_LABELS[key])
            fig.add_scatter(x=flags.index, y=flags.Observed, mode="markers", name="LOF anomalies",
                            marker={"color": COLORS[3]}, customdata=flags[["LOF score"]],
                            hovertemplate="Value: %{y:.2f}<br>LOF: %{customdata[0]:.2f}")
            show_plot(fig)
            st.dataframe(flags.sort_values("LOF score", ascending=False).head(15))
        with spc_tab:
            cutoff = st.number_input("DCT cutoff (days)", 1, 120, 30)
            deviations = st.number_input("Robust deviations", 1.0, 10.0, 4.0, step=0.5)
            frame, sigma = precipitation_control_data(weather["precipitation"], cutoff, deviations)
            chart = frame.drop(columns="flagged").rename(columns={
                "precipitation_mm": "Observed", "lower_limit": "Lower limit", "upper_limit": "Upper limit",
            })
            fig = lines(chart, WEATHER_LABELS["precipitation"])
            flagged = frame.loc[frame.flagged]
            fig.add_scatter(x=flagged.index, y=flagged.precipitation_mm, mode="markers",
                            name="Outliers", marker={"color": COLORS[3]})
            show_plot(fig)
            st.caption(f"{len(flagged):,} hourly outliers. Robust scale: {sigma:.3f} mm.")


def correlation_page():
    (kind, number, region), as_of = heading("Weather and reservoir filling")
    key = st.selectbox("Weather property", tuple(WEATHER_LABELS), format_func=WEATHER_LABELS.get)
    window = st.slider("Correlation window (weeks)", 6, 52, 16)
    lag = st.slider("Lag (weeks)", -12, 12, 0)
    target = st.radio("Reservoir variable", ("change", "level"), horizontal=True)
    years = st.slider("Years of observations", 2, 6, 3)
    st.caption("Positive lag means weather comes first. Filling change is measured in percentage points.")
    if not st.checkbox("Load data and show correlation", key=f"load_correlation_{region}"):
        return
    with display_data_errors("NVE and Open-Meteo"):
        end = archive_end(as_of)
        start = end - pd.DateOffset(years=years)
        weather = period_weather(weather_daily(region, start.date(), end.date()), "W-SUN", hourly=False)
        filling = reservoir_observations(reservoir_data(), (kind, number))
        filling = filling.loc[start:as_of - pd.Timedelta(days=3)]
        corr = rolling_correlation(filling, weather[key], window, lag, target).dropna()
        if corr.empty:
            st.info("No complete overlapping window. Choose a smaller window or longer interval.")
            return
        fig = lines(corr, "Pearson correlation")
        fig.update_yaxes(range=[-1.05, 1.05])
        fig.add_hline(y=0, line_dash="dot")
        show_plot(fig)


@st.cache_data(show_spinner="Fitting River models for each forecast date…", max_entries=32)
def cached_forecast(filling, drivers, **settings):
    return forecast_filling(filling, drivers, **settings)


def animated_forecast(history, result):
    """Keep chart axes fixed while revealing the forecast one period at a time."""
    history = history.tail(52)
    names = ["River", "Persistence", "Seasonal naive"]
    fig = go.Figure()
    fig.add_scatter(x=history.index, y=history, name="Observed", line={"color": "#133437"})
    for name, color in zip(names, COLORS):
        fig.add_scatter(x=result.index[:1], y=result[name].iloc[:1], name=name,
                        mode="lines+markers", line={"color": color, "dash": "solid" if name == "River" else "dot"})
    fig.frames = [
        go.Frame(name=str(step), traces=[1, 2, 3],
                 data=[go.Scatter(x=result.index[:step], y=result[name].iloc[:step]) for name in names])
        for step in range(1, len(result) + 1)
    ]
    fig.update_layout(
        xaxis={"range": [history.index.min(), result.index[-1]], "title": "Date"},
        yaxis={"range": [0, 100], "title": "Reservoir filling (%)"},
        updatemenus=[{"type": "buttons", "x": 0, "y": -0.2, "buttons": [
            {"label": "Play forecast", "method": "animate",
             "args": [None, {"frame": {"duration": 200, "redraw": False}, "fromcurrent": True}]},
            {"label": "Pause", "method": "animate",
             "args": [[None], {"mode": "immediate", "frame": {"duration": 0, "redraw": False}}]},
        ]}],
        sliders=[{"active": 0, "currentvalue": {"prefix": "Through "}, "steps": [
            {"label": date.strftime("%d %b"), "method": "animate",
             "args": [[str(step)], {"mode": "immediate", "frame": {"duration": 0, "redraw": False}}]}
            for step, date in enumerate(result.index, 1)
        ]}],
    )
    return fig


def forecast_page():
    (kind, number, region), as_of = heading("Reservoir filling forecast")
    horizon = st.session_state.horizon
    st.caption(f"Forecast horizon: {horizon} months from the shared date. Change both in the sidebar.")
    with st.form("forecast_settings"):
        left, right = st.columns(2)
        resolution = left.selectbox("Time resolution", list(PERIODS), index=list(PERIODS).index(DEFAULT["resolution"]))
        years = right.slider("Years of training history", 3, 15, DEFAULT["history_years"])
        lags = left.slider("Number of target lags", 1, 12, DEFAULT["lags"])
        rate = right.select_slider("Learning rate", options=[0.001, 0.0025, 0.005, 0.01, 0.02],
                                   value=DEFAULT["rate"])
        sources = st.multiselect("External predictors", tuple(DRIVER_LABELS),
                                 default=DEFAULT["sources"], format_func=DRIVER_LABELS.get)
        requested = st.form_submit_button("Run forecast")
    if requested:
        st.session_state.last_forecast_request = (region, as_of, horizon, resolution, years, lags, rate, tuple(sources))
    settings = st.session_state.get("last_forecast_request")
    if not settings or settings[:3] != (region, as_of, horizon):
        st.info("Choose model inputs and run the forecast for the selected area and date.")
        return
    _, _, _, resolution, years, lags, rate, sources = settings
    with display_data_errors("Filling forecast"):
        filling = reservoir_observations(reservoir_data(), (kind, number))
        start = as_of - pd.DateOffset(years=years) - pd.Timedelta(days=35)
        drivers = pd.DataFrame(index=pd.DatetimeIndex([]))
        if set(sources).intersection(WEATHER_LABELS):
            drivers = weather_daily(region, start.date(), archive_end(as_of).date())
        if set(sources).intersection({"EUR", "USD"}):
            drivers = drivers.join(fx_data(start.date(), as_of.date()), how="outer")
        result = cached_forecast(filling, drivers, as_of=as_of, horizon_months=horizon,
                                 resolution=resolution, history_years=years, lags=lags,
                                 rate=rate, sources=sources)
        history = filling.loc[:result.attrs["last_observed"]]
        show_plot(animated_forecast(history, result))
        st.caption("Direct forecasts use values known at the selected origin, with a lag for weather and exchange rates. Each line is in percent.")
        table = result.round(2)
        table.attrs.clear()
        st.dataframe(table)
