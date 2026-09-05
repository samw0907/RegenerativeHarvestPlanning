# regenerative-harvest-planning/tests/test_d1_dtw_compare.py
"""compare_to_reference: agreement stats on synthetic rasters, no WhiteboxTools call."""

import numpy as np
import rasterio
from rasterio.transform import from_origin

from src.d1_dtw_derive import compare_to_reference


def _write(path, arr, nodata):
    with rasterio.open(path, "w", driver="GTiff", crs="EPSG:3067",
                       transform=from_origin(0, 100, 2, 2), width=arr.shape[1],
                       height=arr.shape[0], count=1, dtype="float32",
                       nodata=nodata) as dst:
        dst.write(arr.astype("float32"), 1)


def test_compare_to_reference_matches_a_known_offset(tmp_path):
    rng = np.random.default_rng(0)
    luke_raw = rng.uniform(0, 500, size=(50, 50)).astype("float32")  # cm
    ours = luke_raw * 0.01 + 2.0  # our values = Luke's metres + a constant 2 m bias

    luke_path = tmp_path / "luke.tif"
    ours_path = tmp_path / "ours.tif"
    _write(luke_path, luke_raw, nodata=32767)
    _write(ours_path, ours, nodata=-9999)

    stats = compare_to_reference(ours_path, luke_path)
    assert stats["n"] == 2500
    assert abs(stats["bias_ours_minus_luke_m"] - 2.0) < 1e-4
    assert stats["r"] > 0.999
    assert stats["spearman_r"] > 0.999
    assert abs(stats["rmse_m"] - 2.0) < 1e-4  # a constant offset: RMSE == the bias exactly


def test_compare_to_reference_excludes_nodata_on_both_sides(tmp_path):
    rng = np.random.default_rng(1)
    luke_raw = rng.uniform(50, 150, size=(10, 10)).astype("float32")
    luke_raw[0, :] = 32767  # nodata row
    ours = (luke_raw * 0.01 + rng.normal(0, 0.1, size=(10, 10))).astype("float32")
    ours[:, 0] = -9999  # a different nodata column

    luke_path = tmp_path / "luke.tif"
    ours_path = tmp_path / "ours.tif"
    _write(luke_path, luke_raw, nodata=32767)
    _write(ours_path, ours, nodata=-9999)

    stats = compare_to_reference(ours_path, luke_path)
    # 100 cells total, minus the nodata row (10) and nodata column (10), plus
    # their 1-cell overlap counted twice -> 100 - 10 - 10 + 1 = 81
    assert stats["n"] == 81
