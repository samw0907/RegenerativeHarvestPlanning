# regenerative-harvest-planning/fi_forest_data/fmi.py
"""Finnish Meteorological Institute (FMI) open data.

Daily weather observations from the FMI WFS (opendata.fmi.fi, no key), stored
query fmi::observations::weather::daily::simple: rrday (precip, -1 = dry), tday
(mean T), tmin, tmax, snow. Query by fmisid + starttime/endtime; the span is
capped near a year, so fetch_daily pages by calendar year.

    stations_near(aoi, max_distance_km=40) -> DataFrame[fmisid, name, lat, lon]
    fetch_daily(fmisid, start, end, variables=...) -> DataFrame indexed by date

Copied from boreal-stand-intelligence, where FMI was not load-bearing (the
Project 1 AOI is too small for summer weather to vary spatially - see
docs/MODULE_C_NOTES.md). It is load-bearing here: D2's weather term (dynamic
wetness-threshold selection) and D3's root-rot exemption both need it daily,
year-round. `fetch_daily` is functional. `stations_near` currently returns the
whole national network (the WFS bbox filter on `fmi::ef::stations` does not
constrain results) and needs a client-side haversine-distance filter - fix this
before D2/D3, since the pinned station (fmisid 101537, Viitasaari Haapaniemi,
daily from 1970) is already known and stations_near is only needed if that
station's coverage or a second station is ever in question.
"""

from __future__ import annotations

import datetime as _dt
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests

WFS = "https://opendata.fmi.fi/wfs"
_DAILY_QUERY = "fmi::observations::weather::daily::simple"
_STATION_QUERY = "fmi::ef::stations"
_DEFAULT_VARS = ("rrday", "tday", "tmin", "tmax")
_NS = {
    "wfs": "http://www.opengis.net/wfs/2.0",
    "BsWfs": "http://xml.fmi.fi/schema/wfs/2.0",
    "gml": "http://www.opengis.net/gml/3.2",
    "ef": "http://inspire.ec.europa.eu/schemas/ef/4.0",
    "gmd": "http://www.isotc211.org/2005/gmd",
    "gco": "http://www.isotc211.org/2005/gco",
}


def _get(params: dict, *, session=None) -> ET.Element:
    r = (session or requests).get(WFS, params=params, timeout=120)
    r.raise_for_status()
    return ET.fromstring(r.content)


def stations_near(aoi, max_distance_km: float = 40.0, *, session=None) -> pd.DataFrame:
    """FMI weather stations within max_distance_km of the AOI.

    The `fmi::ef::stations` WFS bbox parameter does not actually constrain the
    result (confirmed empirically - it returns the whole national network
    regardless), so this filters client-side by great-circle distance from
    each station to the nearest point on the AOI bbox.
    """
    from pyproj import Geod

    root = _get({
        "service": "WFS", "version": "2.0.0", "request": "getFeature",
        "storedquery_id": _STATION_QUERY,
    }, session=session)

    rows = []
    for ef in root.iter("{http://inspire.ec.europa.eu/schemas/ef/4.0}EnvironmentalMonitoringFacility"):
        name_el = ef.find(".//gml:name", _NS)
        pos = ef.find(".//gml:pos", _NS)
        fmisid = None
        for ident in ef.iter("{http://www.opengis.net/gml/3.2}identifier"):
            if ident.text and ident.text.strip().isdigit():
                fmisid = ident.text.strip()
        if pos is None or fmisid is None:
            continue
        lat, lon = (float(v) for v in pos.text.split()[:2])
        rows.append({"fmisid": fmisid,
                     "name": name_el.text if name_el is not None else "",
                     "lat": lat, "lon": lon})
    stations = pd.DataFrame(rows).drop_duplicates("fmisid").reset_index(drop=True)
    if stations.empty:
        return stations

    lon0, lat0, lon1, lat1 = aoi.bbox_wgs84()
    clamp_lon = stations["lon"].clip(lon0, lon1)
    clamp_lat = stations["lat"].clip(lat0, lat1)
    geod = Geod(ellps="WGS84")
    _, _, dist_m = geod.inv(stations["lon"], stations["lat"], clamp_lon, clamp_lat)
    stations["distance_km"] = dist_m / 1000.0
    return (stations[stations["distance_km"] <= max_distance_km]
            .sort_values("distance_km").reset_index(drop=True))


def _fetch_year(fmisid, start, end, variables, *, session) -> pd.DataFrame:
    root = _get({
        "service": "WFS", "version": "2.0.0", "request": "getFeature",
        "storedquery_id": _DAILY_QUERY, "fmisid": str(fmisid),
        "starttime": start, "endtime": end, "parameters": ",".join(variables),
    }, session=session)
    recs = []
    for el in root.iter("{http://xml.fmi.fi/schema/wfs/2.0}BsWfsElement"):
        t = el.find("BsWfs:Time", _NS).text
        name = el.find("BsWfs:ParameterName", _NS).text
        val = el.find("BsWfs:ParameterValue", _NS).text
        recs.append((t[:10], name, float(val) if val not in (None, "NaN") else None))
    if not recs:
        return pd.DataFrame(columns=list(variables))
    df = pd.DataFrame(recs, columns=["date", "param", "value"])
    return df.pivot_table(index="date", columns="param", values="value")


def fetch_daily(fmisid, start: str, end: str,
                variables=_DEFAULT_VARS, *, session=None,
                cache_dir: str | Path | None = "data/raw", force: bool = False) -> pd.DataFrame:
    """Daily observations for one station, start/end as YYYY-MM-DD, paged by year.

    Cached as a CSV keyed on station/dates/variables so a multi-decade fetch
    (e.g. for D2's climatology or the frozen-season-length trend) is not
    re-requested every run. Pass cache_dir=None to skip caching.
    """
    cache_path = None
    if cache_dir is not None:
        var_key = "-".join(variables)
        cache_path = Path(cache_dir) / "fmi" / f"daily_{fmisid}_{start}_{end}_{var_key}.csv"
        if cache_path.exists() and not force:
            return pd.read_csv(cache_path, index_col="date", parse_dates=["date"])

    s = _dt.date.fromisoformat(start)
    e = _dt.date.fromisoformat(end)
    frames = []
    for yr in range(s.year, e.year + 1):
        y0 = max(s, _dt.date(yr, 1, 1)).isoformat() + "T00:00:00Z"
        y1 = min(e, _dt.date(yr, 12, 31)).isoformat() + "T00:00:00Z"
        frames.append(_fetch_year(fmisid, y0, y1, variables, session=session))
    out = pd.concat(frames) if frames else pd.DataFrame(columns=list(variables))
    out.index = pd.to_datetime(out.index)
    out.index.name = "date"
    out = out.sort_index()

    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(cache_path)
    return out
