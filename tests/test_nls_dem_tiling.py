# regenerative-harvest-planning/tests/test_nls_dem_tiling.py
"""fetch_dem_tiled's tiling grid, exercised without network access.

fetch_dem itself needs the NLS API key and a live call, so this test monkeypatches
it to record the tile bboxes it was asked for and return a tiny synthetic GeoTIFF,
checking only the tiling/mosaic mechanics: every tile stays <= 100 km2, the tiles
cover the AOI, and the mosaic's bounds match.
"""

from dataclasses import replace

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from fi_forest_data import nls
from fi_forest_data.aoi import AOI


def _write_tile(path, bbox, value, res=200):
    minx, miny, maxx, maxy = bbox
    w = max(1, int(round((maxx - minx) / res)))
    h = max(1, int(round((maxy - miny) / res)))
    arr = np.full((h, w), value, dtype="float32")
    with rasterio.open(path, "w", driver="GTiff", crs="EPSG:3067",
                       transform=from_origin(minx, maxy, res, res),
                       width=w, height=h, count=1, dtype="float32",
                       nodata=-9999.0) as dst:
        dst.write(arr, 1)


def test_fetch_dem_tiled_covers_aoi_with_subcap_tiles(tmp_path, monkeypatch):
    aoi = AOI(name="test_catchment", bbox_3067=(0.0, 0.0, 14000.0, 19000.0))
    seen_bboxes = []

    def fake_fetch_dem(tile_aoi, *, resolution_m, cache_dir, force):
        bbox = tile_aoi.bbox_3067
        seen_bboxes.append(bbox)
        minx, miny, maxx, maxy = bbox
        area_km2 = (maxx - minx) * (maxy - miny) / 1e6
        assert area_km2 <= 100.0 + 1e-6
        p = tmp_path / f"tile_{tile_aoi.name}.tif"
        _write_tile(p, bbox, value=float(len(seen_bboxes)))
        return str(p)

    monkeypatch.setattr(nls, "fetch_dem", fake_fetch_dem)

    out = nls.fetch_dem_tiled(aoi, cache_dir=tmp_path, tile_km=9.0)

    with rasterio.open(out) as ds:
        b = ds.bounds
        assert b.left <= aoi.bbox_3067[0] + 1e-6
        assert b.bottom <= aoi.bbox_3067[1] + 1e-6
        assert b.right >= aoi.bbox_3067[2] - 1e-6
        assert b.top >= aoi.bbox_3067[3] - 1e-6

    # a 14 x 19 km AOI at 9 km tiles needs a 2 x 3 grid
    assert len(seen_bboxes) == 6


def test_fetch_dtw_rejects_unknown_threshold_and_vintage():
    import pytest

    from fi_forest_data.luke import fetch_dtw

    aoi = AOI(name="t", bbox_3067=(0.0, 0.0, 1000.0, 1000.0))
    with pytest.raises(KeyError):
        fetch_dtw(3.0, aoi)
    with pytest.raises(NotImplementedError):
        fetch_dtw(1.0, aoi, year=2019)


def test_aoi_replace_keeps_frozen_dataclass_semantics():
    aoi = AOI(name="a", bbox_3067=(0.0, 0.0, 1000.0, 1000.0))
    tile = replace(aoi, name="a_tile_0_0", bbox_3067=(0.0, 0.0, 500.0, 500.0))
    assert tile.name == "a_tile_0_0"
    assert aoi.bbox_3067 == (0.0, 0.0, 1000.0, 1000.0)


def test_resample_dem_block_averages_to_the_target_resolution(tmp_path):
    # a 20x20, 2 m raster with a simple gradient, so each 8x8 output block's
    # average is easy to check by hand
    res = 2.0
    arr = np.arange(400, dtype="float32").reshape(20, 20)
    src = tmp_path / "src.tif"
    with rasterio.open(src, "w", driver="GTiff", crs="EPSG:3067",
                       transform=from_origin(0, 40, res, res),
                       width=20, height=20, count=1, dtype="float32") as dst:
        dst.write(arr, 1)

    out = nls.resample_dem(src, tmp_path / "out.tif", target_resolution_m=8.0)

    with rasterio.open(out) as ds:
        assert ds.width == 5 and ds.height == 5
        assert ds.res == (8.0, 8.0)
        out_arr = ds.read(1)
        # top-left output cell averages the source's top-left 4x4 block
        assert out_arr[0, 0] == pytest.approx(arr[:4, :4].mean(), rel=1e-5)
        b = ds.bounds
        assert b.left == pytest.approx(0.0) and b.top == pytest.approx(40.0)


def test_resample_dem_rejects_a_finer_target_resolution(tmp_path):
    src = tmp_path / "src.tif"
    _write_tile(src, (0.0, 0.0, 200.0, 200.0), value=1.0, res=10)
    with pytest.raises(ValueError):
        nls.resample_dem(src, tmp_path / "out.tif", target_resolution_m=5.0)
