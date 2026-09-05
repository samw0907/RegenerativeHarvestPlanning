# regenerative-harvest-planning/tests/test_syke_catchment.py
"""fetch_catchment: caching and CRS behaviour, without a network call."""

import geopandas as gpd
from shapely.geometry import box

from fi_forest_data import syke


def test_fetch_catchment_caches_and_sets_crs(tmp_path, monkeypatch):
    calls = []

    real_read_file = gpd.read_file

    def fake_read_file(url, *, layer=None, where=None):
        if layer is None:  # the cache-hit path: gpd.read_file(out) with no kwargs
            return real_read_file(url)
        calls.append((url, layer, where))
        return gpd.GeoDataFrame(
            {"taso4_osat": ["FI1-14.06.161"], "taso4_id": [11406161]},
            geometry=[box(414920, 6945300, 429010, 6964880)],
        )  # deliberately no CRS, like the live source's untagged PROJCS

    monkeypatch.setattr(syke.gpd, "read_file", fake_read_file)

    out = syke.fetch_catchment("FI1-14.06.161", cache_dir=tmp_path)
    assert out.crs is not None and out.crs.to_epsg() == 3067
    assert len(calls) == 1
    assert calls[0][1] == "Valumaaluejako_taso4"
    assert "taso4_osat = 'FI1-14.06.161'" in calls[0][2]

    cache_file = tmp_path / "syke" / "catchment_taso4_FI1-14.06.161.gpkg"
    assert cache_file.exists()

    # second call hits the cache, not the (fake) network read
    out2 = syke.fetch_catchment("FI1-14.06.161", cache_dir=tmp_path)
    assert len(calls) == 1
    assert out2.crs.to_epsg() == 3067


def test_fetch_catchment_rejects_unknown_level(tmp_path):
    import pytest

    with pytest.raises(KeyError):
        syke.fetch_catchment("x", level="taso2", cache_dir=tmp_path)
