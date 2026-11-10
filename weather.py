"""Sample NVE polygons and obtain hourly area averages from Open-Meteo ERA5."""

import hashlib
import json
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd
import shapefile
from matplotlib.path import Path as PolygonPath

REGION_DIR = Path(__file__).resolve().parent / "data" / "regions"
CACHE_DIR = Path(__file__).resolve().parent / ".weather-cache"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
VARIABLES = ("temperature_2m", "precipitation", "relative_humidity_2m")
REGION_PARTS = {
    "VASS1": ("RS", "RØ"),
    "VASS2": ("RV",),
    "VASS3": ("RM",),
    "VASS4": ("RN",),
    "NORWAY": ("RS", "RØ", "RV", "RM", "RN"),
}
PRICE_AREAS = tuple(f"NO{i}" for i in range(1, 6))


def load_region_shapes():
    """Read WGS84 polygons, including any islands and interior rings."""
    shapes = {}
    for name in ("elspotomrader", "nve_forvaltningsomrader"):
        with shapefile.Reader(str(REGION_DIR / name), encoding="utf-8") as source:
            for item in source.iterShapeRecords():
                geometry = item.shape.__geo_interface__
                coordinates = geometry["coordinates"]
                shapes[item.record[0]] = (
                    [coordinates] if geometry["type"] == "Polygon" else coordinates
                )
    return shapes


def sample_locations(count=1000, seed=320, regions=None):
    """Return reproducible (longitude, latitude) points for each requested area."""
    shapes = load_region_shapes()
    if regions is None:
        regions = (*PRICE_AREAS, *REGION_PARTS, *REGION_PARTS["NORWAY"])
    result = {}
    for region in regions:
        rng = np.random.default_rng(seed)
        polygons = [polygon for part in REGION_PARTS.get(region, (region,))
                    for polygon in shapes[part]]
        paths = [[PolygonPath(ring) for ring in polygon] for polygon in polygons]
        bounds = np.array([rings[0].get_extents().extents for rings in paths])
        west, south = bounds[:, :2].min(axis=0)
        east, north = bounds[:, 2:].max(axis=0)
        accepted = []
        while len(accepted) < count:
            # Uniform sin(latitude) gives equal areas on a spherical Earth.
            longitude = rng.uniform(west, east, 4096)
            latitude = np.degrees(np.arcsin(rng.uniform(
                np.sin(np.radians(south)), np.sin(np.radians(north)), 4096
            )))
            points = np.column_stack((longitude, latitude))
            inside = np.zeros(len(points), dtype=bool)
            for rings, (x0, y0, x1, y1) in zip(paths, bounds):
                candidates = np.flatnonzero((longitude >= x0) & (longitude <= x1)
                                            & (latitude >= y0) & (latitude <= y1))
                if not candidates.size:
                    continue
                subset = points[candidates]
                mask = rings[0].contains_points(subset)
                for hole in rings[1:]:
                    mask &= ~hole.contains_points(subset)
                inside[candidates[mask]] = True
            accepted.extend(map(tuple, points[inside]))
        result[region] = accepted[:count]
    return result


def grid_weights(locations):
    """Count sampled points represented by each native ERA5 cell."""
    # Nearest-cell selection without elevation downscaling gives one time series
    # per cell. Keeping the counts preserves the weight of all sampled locations.
    return Counter((round(lon * 4) / 4, round(lat * 4) / 4) for lon, lat in locations)


def _download_batch(cells, start, end):
    params = {
        "longitude": ",".join(str(lon) for lon, _ in cells),
        "latitude": ",".join(str(lat) for _, lat in cells),
        "start_date": start, "end_date": end, "hourly": ",".join(VARIABLES),
        "models": "era5", "timezone": "GMT", "cell_selection": "nearest",
        "elevation": ",".join(["nan"] * len(cells)),
    }
    query = urlencode(params)
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / (hashlib.sha256(query.encode()).hexdigest() + ".json")
    try:
        return json.loads(path.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    for attempt in range(2):
        try:
            with urlopen(f"{ARCHIVE_URL}?{query}", timeout=75) as response:
                payload = json.load(response)
            break
        except HTTPError as exc:
            if exc.code != 429:
                raise
            reason = exc.read().decode(errors="replace")
            if attempt == 0 and "daily" not in reason.lower() and "hourly" not in reason.lower():
                sleep(45)
                continue
            raise RuntimeError(
                f"Open-Meteo request limit reached. Retry later; completed batches are cached. {reason}"
            ) from exc
    payload = payload if isinstance(payload, list) else [payload]
    if len(payload) != len(cells):
        raise ValueError("Open-Meteo did not return one response per ERA5 cell.")
    for item, (lon, lat) in zip(payload, cells):
        if ("hourly" not in item or abs(item["latitude"] - lat) > 0.001
                or abs(item["longitude"] - lon) > 0.001):
            raise ValueError("Open-Meteo returned a different ERA5 cell than requested.")
    # Exclusive temporary files allow parallel app sessions to write safely.
    with NamedTemporaryFile(mode="w", dir=CACHE_DIR, delete=False) as temp:
        json.dump(payload, temp, separators=(",", ":"))
    Path(temp.name).replace(path)
    return payload


def download_weather(region, start_date, end_date, locations_by_region=None, batch_size=12):
    """Download hourly ERA5 and return the weighted region mean in UTC."""
    start, end = pd.Timestamp(start_date).date(), pd.Timestamp(end_date).date()
    if start > end or not 1 <= batch_size <= 50:
        raise ValueError("Use an increasing date interval and a batch size from 1 to 50.")
    if locations_by_region is None:
        locations_by_region = sample_locations(regions=[region])
    locations = locations_by_region[region]
    weights = grid_weights(locations)
    if not weights:
        raise ValueError(f"No sampled locations for {region}.")
    index = pd.date_range(start, pd.Timestamp(end) + pd.Timedelta(hours=23),
                          freq="h", tz="UTC")
    total = np.zeros((len(index), len(VARIABLES)))
    count = np.zeros_like(total)
    cells = sorted(weights)
    for offset in range(0, len(cells), batch_size):
        batch = cells[offset:offset + batch_size]
        for cell, item in zip(batch, _download_batch(batch, str(start), str(end))):
            hourly = item["hourly"]
            dates = pd.to_datetime(hourly["time"], utc=True)
            if not dates.equals(index):
                raise ValueError("Open-Meteo returned an unexpected hourly timeline.")
            values = np.column_stack([np.asarray(hourly[key], dtype=float) for key in VARIABLES])
            valid = np.isfinite(values)
            total += np.where(valid, values, 0) * weights[cell]
            count += valid * weights[cell]
    averaged = np.divide(total, count, out=np.full_like(total, np.nan), where=count > 0)
    frame = pd.DataFrame(averaged, columns=VARIABLES, index=index.rename("time_utc"))
    frame.attrs.update(region=region, sampled_locations=len(locations), era5_cells=len(cells))
    return frame
