# regenerative-harvest-planning/tests/test_d_validation.py
"""Module D validation: pure numpy/pandas/rasterio logic, no network.

Covers the raster point-sampling, the per-row threshold blend, and a fully
synthetic end-to-end run of evaluate_declarations/negative_control/
concordance_summary - built specifically to catch regressions like the
DECLARATIONARRIVALDATE mixed-offset parsing bug this module already hit once
(see docs/MODULE_D_NOTES.md, "D validation" section).
"""

import numpy as np
import pandas as pd
import pytest

from src.d_validation import (
    blend_at_threshold, concordance_summary, evaluate_declarations,
    negative_control, sample_raster_at_points,
)

gpd = pytest.importorskip("geopandas")
rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402


CFG_D2 = {
    "weather_term": {"antecedent_precip_days": [7, 14, 30]},
    "soil_term": {"peat_bearing_penalty": 0.5},
}


def _write_raster(path, value, *, nodata=None):
    """A flat 10x10, 10 m-pixel raster at origin (0, 100) so pixel (r, c)
    covers x in [10c, 10c+10), y in [100-10(r+1), 100-10r)."""
    arr = np.full((10, 10), value, dtype="float64")
    transform = from_origin(0, 100, 10, 10)
    with rasterio.open(
        path, "w", driver="GTiff", height=10, width=10, count=1,
        dtype="float64", crs="EPSG:3067", transform=transform, nodata=nodata,
    ) as dst:
        dst.write(arr, 1)


def test_sample_raster_at_points_reads_values_and_flags_out_of_bounds(tmp_path):
    path = tmp_path / "flat.tif"
    _write_raster(path, 5.0)
    xs = [15.0, 500.0]  # second point well outside the 100x100 m raster
    ys = [95.0, 500.0]
    out = sample_raster_at_points(xs, ys, str(path))
    assert out[0] == pytest.approx(5.0)
    assert np.isnan(out[1])


def test_sample_raster_at_points_maps_nodata_to_nan(tmp_path):
    path = tmp_path / "nodata.tif"
    _write_raster(path, 32767.0, nodata=32767.0)
    out = sample_raster_at_points([15.0], [95.0], str(path))
    assert np.isnan(out[0])


def test_blend_at_threshold_interpolates_log_weighted_position():
    df = pd.DataFrame({0.5: [1.0], 1.0: [4.0]})
    out = blend_at_threshold(df, np.array([1.0]))  # at the known upper threshold
    assert out[0] == pytest.approx(4.0)
    out_lo = blend_at_threshold(df, np.array([0.5]))
    assert out_lo[0] == pytest.approx(1.0)


def test_blend_at_threshold_clips_outside_known_range():
    df = pd.DataFrame({0.5: [1.0], 10.0: [9.0]})
    out = blend_at_threshold(df, np.array([100.0]))
    assert out[0] == pytest.approx(9.0)  # clamped to the driest known threshold


def _synthetic_declarations(n=20, seed=0):
    rng = np.random.default_rng(seed)
    xs = rng.uniform(10, 90, n)
    ys = rng.uniform(10, 90, n)
    dates = pd.date_range("2000-01-01", periods=n, freq="30D")
    # mixed +02:00/+03:00 offsets, matching the real DECLARATIONARRIVALDATE
    # format that caused the original parsing bug
    offsets = np.where(dates.month.isin([4, 5, 6, 7, 8, 9]), "+03:00", "+02:00")
    date_strings = [f"{d.date()}T00:00:00{o}" for d, o in zip(dates, offsets)]
    soiltype = rng.choice(["10", "65"], n)  # a mix of mineral and peat
    return gpd.GeoDataFrame(
        {"DECLARATIONARRIVALDATE": date_strings, "SOILTYPE": soiltype},
        geometry=gpd.points_from_xy(xs, ys), crs="EPSG:3067",
    )


def _synthetic_daily(n=700, seed=0):
    idx = pd.date_range("2000-01-01", periods=n, freq="D")
    rng = np.random.default_rng(seed)
    rrday = rng.choice([-1.0], size=n).astype("float64")
    rrday[::5] = rng.uniform(1, 15, size=len(rrday[::5]))
    tmin = rng.uniform(-15, 10, n)
    return pd.DataFrame(
        {"rrday": rrday, "snow": np.full(n, -1.0), "tmin": tmin}, index=idx)


def test_evaluate_declarations_parses_mixed_offset_dates_without_nans(tmp_path):
    luke_paths = {}
    for th, val in zip((0.5, 1.0, 2.0, 4.0, 10.0), (10, 30, 60, 120, 300)):
        path = tmp_path / f"dtw_{th}.tif"
        _write_raster(path, float(val))
        luke_paths[th] = str(path)

    decl = _synthetic_declarations()
    daily = _synthetic_daily()
    out = evaluate_declarations(decl, daily, luke_paths, CFG_D2)

    assert len(out) == len(decl)
    # the mixed-offset bug produced 100% NaN dtw_m - this is the regression guard
    assert out["dtw_m"].notna().all()
    # utc=True parsing shifted +02:00/+03:00 midnight timestamps back a
    # calendar day; confirm the parsed date matches the string's own date,
    # not a UTC-shifted one
    expected_dates = pd.to_datetime(
        decl["DECLARATIONARRIVALDATE"].astype(str).str.slice(0, 10))
    assert (out["date"].to_numpy() == expected_dates.to_numpy()).all()
    assert out["workable"].dtype == bool


def test_negative_control_and_concordance_summary_shapes(tmp_path):
    luke_paths = {}
    for th, val in zip((0.5, 1.0, 2.0, 4.0, 10.0), (10, 30, 60, 120, 300)):
        path = tmp_path / f"dtw_{th}.tif"
        _write_raster(path, float(val))
        luke_paths[th] = str(path)

    decl = _synthetic_declarations()
    daily = _synthetic_daily()
    declared = evaluate_declarations(decl, daily, luke_paths, CFG_D2)
    control = negative_control(decl, daily, luke_paths, CFG_D2, seed=0)

    summary = concordance_summary(declared, control)
    assert summary["n_declared"] == len(decl)
    assert 0.0 <= summary["workable_rate_declared"] <= 1.0
    assert 0.0 <= summary["workable_rate_control"] <= 1.0
    assert summary["lift"] > 0.0
