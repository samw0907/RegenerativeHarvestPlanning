# regenerative-harvest-planning/tests/test_nls_topographic.py
"""fetch_topographic: caching, CRS and theme validation, without a network call."""

import geopandas as gpd
import pytest
from shapely.geometry import LineString

from fi_forest_data import nls
from fi_forest_data.aoi import AOI


def test_fetch_topographic_caches_and_sets_crs(tmp_path, monkeypatch):
    calls = []
    real_read_file = gpd.read_file

    def fake_read_file(path, *, layer=None, bbox=None):
        if layer is None:  # the cache-hit path: gpd.read_file(out) with no kwargs
            return real_read_file(path)
        calls.append((path, layer, bbox))
        return gpd.GeoDataFrame(
            {"id": [1]}, geometry=[LineString([(404100, 6910100), (404200, 6910200)])]
        )  # deliberately no CRS, like the live vsicurl read before set_crs

    monkeypatch.setattr("geopandas.read_file", fake_read_file)

    aoi = AOI(name="test_aoi", bbox_3067=(404000, 6910000, 454000, 6978000))
    out = nls.fetch_topographic(aoi, cache_dir=tmp_path)

    assert out.crs is not None and out.crs.to_epsg() == 3067
    assert len(calls) == 1
    assert calls[0][1] == "virtavesikapea"
    assert calls[0][2] == aoi.bbox_3067

    cache_file = tmp_path / "nls" / "mtk_streams_test_aoi.gpkg"
    assert cache_file.exists()

    # second call hits the cache, not the (fake) network read
    out2 = nls.fetch_topographic(aoi, cache_dir=tmp_path)
    assert len(calls) == 1
    assert out2.crs.to_epsg() == 3067


def test_fetch_topographic_rejects_unknown_theme(tmp_path):
    aoi = AOI(name="test_aoi", bbox_3067=(0.0, 0.0, 1000.0, 1000.0))
    with pytest.raises(KeyError):
        nls.fetch_topographic(aoi, theme="lakes", cache_dir=tmp_path)
