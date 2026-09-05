# regenerative-harvest-planning/tests/test_d2_dtw_extend.py
"""D2 weather and soil terms: pure numpy/pandas logic, no network or WhiteboxTools."""

import numpy as np
import pandas as pd

from src.d2_dtw_extend import (
    THRESHOLDS_HA, antecedent_precipitation, interpolate_dtw_surface,
    select_threshold_ha, snowmelt_signal, soil_adjusted_dtw, wetness_percentile,
)


def _daily(n=60, seed=0):
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    rng = np.random.default_rng(seed)
    rrday = rng.choice([-1.0], size=n).astype("float64")
    rrday[::10] = rng.uniform(1, 20, size=len(rrday[::10]))
    # melts from 50 cm to 0 over the first half, then no snow (-1 sentinel) for the rest
    half = n // 2
    snow = np.concatenate([np.linspace(50, 0, half), np.full(n - half, -1.0)])
    return pd.DataFrame({"rrday": rrday, "tday": rng.uniform(-5, 15, n), "snow": snow}, index=idx)


def test_antecedent_precipitation_treats_dry_sentinel_as_zero():
    daily = _daily()
    api = antecedent_precipitation(daily, windows_days=(7,))
    assert (api["api_7d"] >= 0).all()
    # a pure -1 day contributes 0, not -1, to the rolling sum
    dry_only = daily.copy()
    dry_only["rrday"] = -1.0
    api_dry = antecedent_precipitation(dry_only, windows_days=(7,))
    assert (api_dry["api_7d"] == 0).all()


def test_snowmelt_signal_is_positive_only_while_snow_is_present_and_declining():
    daily = _daily()
    melt = snowmelt_signal(daily)
    assert (melt >= 0).all()
    # once snow has fully gone (sentinel -1 clipped to 0), further "melt" is 0
    tail_snow = daily["snow"].clip(lower=0).iloc[-5:]
    assert (tail_snow == 0).all()
    assert (melt.iloc[-4:] == 0).all()  # no further melt once already at 0


def test_wetness_percentile_ranks_the_wettest_day_highest():
    daily = _daily()
    daily.loc[daily.index[30], "rrday"] = 200.0  # an extreme storm day
    pct = wetness_percentile(daily, windows_days=(7, 14, 30))
    assert pct.max() <= 1.0 and pct.min() >= 0.0
    # the storm day (and its immediate aftermath, still carrying it in the
    # rolling windows) should rank at or very near the top
    assert pct.loc[daily.index[30]] > 0.9


def test_select_threshold_ha_endpoints_and_monotonicity():
    assert select_threshold_ha(1.0) == THRESHOLDS_HA[0]
    assert abs(select_threshold_ha(0.0) - THRESHOLDS_HA[-1]) < 1e-9
    pcts = np.linspace(0, 1, 11)
    thr = select_threshold_ha(pcts)
    assert np.all(np.diff(thr) <= 0)  # wetter (higher percentile) -> smaller threshold


def test_interpolate_dtw_surface_log_weighted_linear_blend():
    lo = np.full((3, 3), 1.0)
    hi = np.full((3, 3), 4.0)
    surfaces = {1.0: lo, 4.0: hi}
    # DTW=0 (a channel cell) is a valid, common value, so the blend weight is
    # log-spaced (position between the two thresholds) but the raster VALUES
    # are blended linearly - a true log-of-values interpolation is undefined
    # wherever either surface is exactly 0.
    mid = interpolate_dtw_surface(2.0, surfaces)  # log-midpoint of 1 and 4
    assert np.allclose(mid, 2.5, atol=1e-6)
    assert np.array_equal(interpolate_dtw_surface(0.5, surfaces), lo)  # clamped below range
    assert np.array_equal(interpolate_dtw_surface(10.0, surfaces), hi)  # clamped above range


def test_soil_adjusted_dtw_only_changes_peat_cells():
    dtw = np.array([[10.0, 10.0], [10.0, 10.0]])
    is_peat = np.array([[True, False], [False, True]])
    out = soil_adjusted_dtw(dtw, is_peat, peat_bearing_penalty=0.5)
    assert np.allclose(out[is_peat], 5.0)
    assert np.allclose(out[~is_peat], 10.0)
