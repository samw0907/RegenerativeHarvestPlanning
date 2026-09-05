# regenerative-harvest-planning/tests/test_fmi.py
"""fetch_daily caching and stations_near's distance filter, without a real WFS call."""

import pandas as pd

from fi_forest_data import fmi
from fi_forest_data.aoi import AOI


def test_fetch_daily_caches_to_disk(tmp_path, monkeypatch):
    calls = []

    def fake_fetch_year(fmisid, start, end, variables, *, session):
        calls.append((fmisid, start[:4]))
        idx = pd.date_range(f"{start[:4]}-01-01", f"{start[:4]}-01-03", freq="D")
        return pd.DataFrame({v: 1.0 for v in variables}, index=idx.astype(str))

    monkeypatch.setattr(fmi, "_fetch_year", fake_fetch_year)

    df1 = fmi.fetch_daily(101537, "2020-01-01", "2020-01-03", cache_dir=tmp_path)
    assert len(calls) == 1
    assert list(df1.columns) == list(fmi._DEFAULT_VARS)

    df2 = fmi.fetch_daily(101537, "2020-01-01", "2020-01-03", cache_dir=tmp_path)
    assert len(calls) == 1  # second call hit the cache, not _fetch_year again
    pd.testing.assert_frame_equal(df1, df2)

    fmi.fetch_daily(101537, "2020-01-01", "2020-01-03", cache_dir=tmp_path, force=True)
    assert len(calls) == 2  # force bypasses the cache


def test_stations_near_filters_by_distance(monkeypatch):
    xml = b"""<?xml version="1.0"?>
    <root xmlns:ef="http://inspire.ec.europa.eu/schemas/ef/4.0"
         xmlns:gml="http://www.opengis.net/gml/3.2">
      <ef:EnvironmentalMonitoringFacility>
        <gml:name>Near station</gml:name>
        <gml:identifier>111</gml:identifier>
        <gml:pos>62.60 25.74</gml:pos>
      </ef:EnvironmentalMonitoringFacility>
      <ef:EnvironmentalMonitoringFacility>
        <gml:name>Far station</gml:name>
        <gml:identifier>222</gml:identifier>
        <gml:pos>70.00 25.74</gml:pos>
      </ef:EnvironmentalMonitoringFacility>
    </root>"""
    import xml.etree.ElementTree as ET

    monkeypatch.setattr(fmi, "_get", lambda params, session=None: ET.fromstring(xml))

    aoi = AOI(name="p2", bbox_3067=(404000, 6910000, 454000, 6978000))
    out = fmi.stations_near(aoi, max_distance_km=50)
    assert list(out["fmisid"]) == ["111"]  # the far station is excluded
    assert "distance_km" in out.columns
