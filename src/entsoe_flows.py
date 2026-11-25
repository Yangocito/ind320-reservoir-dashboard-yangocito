"""ENTSO-E physical flow API client; all timestamps are UTC."""

import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from http.client import RemoteDisconnected

import pandas as pd

API_URL = "https://web-api.tp.entsoe.eu/api"
# Named bidding zones from ENTSO-E's EIC area list. Two connections give four
# separate direction/connection series, while keeping a two-year pull manageable.
CONNECTIONS = {
    "NO1–SE3": ("10YNO-1--------2", "10Y1001A1001A46L"),
    "NO2–DK1": ("10YNO-2--------T", "10YDK-1--------W"),
}
COLUMNS = ["connection", "direction", "timestamp_utc", "quantity_mw", "duration_hours"]


def _children(element, tag):
    """Find immediate XML children without assuming a namespace version."""
    return [child for child in element if child.tag.split("}")[-1] == tag]


def _first(element, tag):
    matches = _children(element, tag)
    return matches[0] if matches else None


def _text(element, tag):
    found = _first(element, tag) if element is not None else None
    return found.text if found is not None else None


def _duration_hours(value: str) -> float:
    """Parse the ISO duration resolutions ENTSO-E uses for market periods."""
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", value or "")
    if not match:
        raise ValueError(f"Unknown ENTSO-E period resolution: {value}")
    return int(match.group(1) or 0) + int(match.group(2) or 0) / 60


def parse_physical_flow_xml(xml_bytes: bytes, connection: str, direction: str) -> pd.DataFrame:
    """Parse Point positions, MW values and the period's UTC resolution."""
    root = ET.fromstring(xml_bytes)
    if root.tag.split("}")[-1].startswith("Acknowledgement"):
        reasons = [el.text for el in root.iter() if el.tag.split("}")[-1] in {"text", "code"}]
        reason = " ".join(item for item in reasons if item)
        if "No matching data found" in reason:
            return pd.DataFrame(columns=COLUMNS)
        raise RuntimeError(f"ENTSO-E rejected the request: {reason}")
    rows = []
    for series in root.iter():
        if series.tag.split("}")[-1] != "TimeSeries":
            continue
        curve_type = _text(series, "curveType") or "A01"
        if curve_type not in ("A01", "A03"):
            raise ValueError(f"Unsupported ENTSO-E curve type: {curve_type}")
        for period in _children(series, "Period"):
            interval = _first(period, "timeInterval")
            start = pd.Timestamp(_text(interval, "start"))
            end = pd.Timestamp(_text(interval, "end"))
            hours = _duration_hours(_text(period, "resolution"))
            if start.tzinfo is None or end.tzinfo is None or hours <= 0:
                raise ValueError("ENTSO-E returned a period without UTC time/resolution.")
            points = []
            for point in _children(period, "Point"):
                position = int(_text(point, "position"))
                quantity = _text(point, "quantity")
                if quantity is None:
                    continue
                points.append((position, float(quantity)))
            points.sort()
            # A03 lists only changed blocks; each value lasts until the next
            # position (or the end of the Period). A01 lists every position.
            total_positions = round((end - start) / pd.Timedelta(hours=hours))
            for index, (position, quantity) in enumerate(points):
                stop = (points[index + 1][0] if curve_type == "A03" and
                        index + 1 < len(points) else
                        total_positions + 1 if curve_type == "A03" else position + 1)
                for slot in range(position, stop):
                    rows.append({
                        "connection": connection, "direction": direction,
                        "timestamp_utc": start + pd.Timedelta(hours=hours * (slot - 1)),
                        "quantity_mw": quantity, "duration_hours": hours,
                    })
    result = pd.DataFrame(rows, columns=COLUMNS)
    if not result.empty:
        result = result.drop_duplicates(["connection", "direction", "timestamp_utc"], keep="last")
    return result


def month_windows(start: pd.Timestamp, end: pd.Timestamp):
    """Yield short UTC query windows, including partial first/last months."""
    cursor = start
    while cursor < end:
        year, month = cursor.year, cursor.month
        next_month = pd.Timestamp(
            year=year + (month == 12), month=1 if month == 12 else month + 1,
            day=1, tz="UTC",
        )
        finish = min(next_month, end)
        yield cursor, finish
        cursor = finish


def fetch_physical_flows(token: str, start: pd.Timestamp, end: pd.Timestamp,
                         connections: dict = CONNECTIONS) -> pd.DataFrame:
    """Fetch realised physical flows in both directions on selected borders.

    ENTSO-E publishes average MW per market period. MWh is calculated later as
    MW times period duration. UTC avoids repeated/missing clock hours at DST.
    """
    if not token:
        raise ValueError("ENTSOE_TOKEN is missing.")
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("Provide increasing timezone-aware UTC start and end times.")
    frames = []
    for connection, (norway, neighbour) in connections.items():
        for direction, source, target in (
            ("Out of Norway", norway, neighbour),
            ("Into Norway", neighbour, norway),
        ):
            for window_start, window_end in month_windows(start, end):
                params = {
                    "securityToken": token, "documentType": "A11",
                    "in_Domain": target, "out_Domain": source,
                    "periodStart": window_start.tz_convert("UTC").strftime("%Y%m%d%H%M"),
                    "periodEnd": window_end.tz_convert("UTC").strftime("%Y%m%d%H%M"),
                }
                # Retry transient network/rate-limit responses, not authentication errors.
                request = Request(f"{API_URL}?{urlencode(params)}", headers={"User-Agent": "IND320-course-project/2"})
                for attempt in range(3):
                    try:
                        with urlopen(request, timeout=60) as response:
                            body = response.read()
                        break
                    except HTTPError as exc:
                        if exc.code == 400:
                            # ENTSO-E can put the actual rejection reason in XML.
                            body = exc.read()
                            break
                        if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                            raise RuntimeError(f"ENTSO-E HTTP {exc.code} for {connection}, {direction}") from exc
                    except (URLError, RemoteDisconnected, TimeoutError, ConnectionResetError):
                        if attempt == 2:
                            raise
                    time.sleep(2 ** attempt)
                frame = parse_physical_flow_xml(body, connection, direction)
                if not frame.empty:
                    frames.append(frame)
    if not frames:
        raise ValueError("ENTSO-E supplied no points for the selected borders/period.")
    return (pd.concat(frames, ignore_index=True)
            .drop_duplicates(["connection", "direction", "timestamp_utc"], keep="last")
            .sort_values(["connection", "direction", "timestamp_utc"])
            .reset_index(drop=True))
