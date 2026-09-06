# regenerative-harvest-planning/src/d_validation.py
"""Module D validation: does declared harvest timing concentrate in the periods
D1+D2+frozen-ground predict as workable?

Method: for each forest-use declaration, sample the five Luke DTW 2023 CMv2
threshold rasters at the declaration's location, blend them with D2's
per-date threshold selection (from real FMI weather on the declaration's
arrival date), apply the soil term from the declaration's own `SOILTYPE`
field, and classify workable/not with the frozen-ground override. Compare the
workable rate on declared dates against a negative control - the same
locations assigned a random date instead - the same design Module B used in
Project 1 for its false-positive rate, and the same caveat applies: a
declaration is a permit, not a felling record, so this measures whether
declared *intent* clusters in workable conditions, not proven execution dates.

Data tiers: forest-use declarations FETCH; the workability classification
DERIVE ONLY (built from D1/D2/D3, no official date-specific product exists to
benchmark against).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import rasterio

from src.d2_dtw_extend import (
    THRESHOLDS_HA, frozen_ground_days, is_workable, select_threshold_ha,
    soil_adjusted_dtw, wetness_percentile,
)
from src.d3_rootrot_rules import is_peat_soil

_LUKE_DIR_SUFFIX = {0.5: "050", 1: "1", 2: "2", 4: "4", 10: "10"}


def sample_raster_at_points(xs, ys, raster_path: str, *, scale: float = 1.0) -> np.ndarray:
    """Nearest-pixel sample of one raster at a set of point coordinates,
    NaN where a point falls outside the raster or on nodata."""
    with rasterio.open(raster_path) as src:
        arr = src.read(1).astype("float64")
        nod = src.nodata
        inv = ~src.transform
    col, row = inv * (np.asarray(xs), np.asarray(ys))
    col = np.round(col).astype(int)
    row = np.round(row).astype(int)
    h, w = arr.shape
    ok = (row >= 0) & (row < h) & (col >= 0) & (col < w)
    out = np.full(len(np.atleast_1d(xs)), np.nan)
    vals = arr[row[ok], col[ok]]
    if nod is not None:
        vals = np.where(vals == nod, np.nan, vals)
    out[ok] = vals * scale
    return out


def sample_luke_dtw_at_points(xs, ys, luke_dtw_paths: dict[float, str]) -> pd.DataFrame:
    """Point samples (metres) from each of the 5 Luke threshold rasters."""
    return pd.DataFrame({
        th: sample_raster_at_points(xs, ys, luke_dtw_paths[th], scale=0.01)
        for th in THRESHOLDS_HA
    })


def blend_at_threshold(point_values: pd.DataFrame, threshold_ha: np.ndarray) -> np.ndarray:
    """Per-row log-weighted linear blend of the 5 sampled threshold values at
    each row's own selected threshold_ha - the point-sample equivalent of
    `d2_dtw_extend.interpolate_dtw_surface`, vectorised over many rows/dates
    instead of building a full raster per unique threshold."""
    known = np.array(sorted(point_values.columns), dtype="float64")
    thr = np.clip(np.asarray(threshold_ha, dtype="float64"), known[0], known[-1])
    log_known = np.log(known)
    log_thr = np.log(thr)
    hi_idx = np.searchsorted(log_known, log_thr, side="left").clip(1, len(known) - 1)
    lo_idx = hi_idx - 1
    lo, hi = known[lo_idx], known[hi_idx]
    t = np.where(hi > lo, (log_thr - np.log(lo)) / (np.log(hi) - np.log(lo)), 0.0)
    vals = point_values[known].to_numpy()
    lo_val = vals[np.arange(len(vals)), lo_idx]
    hi_val = vals[np.arange(len(vals)), hi_idx]
    return lo_val * (1 - t) + hi_val * t


def evaluate_declarations(
    declarations,
    daily_weather: pd.DataFrame,
    luke_dtw_paths: dict[float, str],
    cfg_d2: dict,
    *,
    wet_threshold_m: float = 1.0,
    date_field: str = "DECLARATIONARRIVALDATE",
) -> pd.DataFrame:
    """Workability classification for a set of declarations on their own
    arrival dates. `declarations` needs geometry, SOILTYPE and date_field."""
    # These timestamps are local Finnish wall-clock midnight with a mixed
    # +02:00/+03:00 (EET/EEST) offset (e.g. "2009-01-08T00:00:00+02:00").
    # Parsing with utc=True (needed - pandas rejects mixed offsets otherwise)
    # converts to UTC first, shifting the date back a day (-> 2009-01-07
    # 22:00), which then fails to match daily_weather's midnight-normalised
    # index and silently NaNs every downstream value. The calendar date is
    # already unambiguous in the string, so take it directly instead.
    dates = pd.to_datetime(declarations[date_field].astype(str).str.slice(0, 10))
    xs = declarations.geometry.centroid.x.to_numpy()
    ys = declarations.geometry.centroid.y.to_numpy()

    samples = sample_luke_dtw_at_points(xs, ys, luke_dtw_paths)
    pct_by_day = wetness_percentile(
        daily_weather, windows_days=cfg_d2["weather_term"]["antecedent_precip_days"])
    pct = pct_by_day.reindex(dates).to_numpy()
    thr_ha = select_threshold_ha(pct)
    dtw_m = blend_at_threshold(samples, thr_ha)

    peat = is_peat_soil(declarations["SOILTYPE"])
    penalty = cfg_d2["soil_term"]["peat_bearing_penalty"]
    adjusted = soil_adjusted_dtw(dtw_m, peat, peat_bearing_penalty=penalty)

    frozen_series = frozen_ground_days(daily_weather)
    frozen = frozen_series.reindex(dates).fillna(False).to_numpy()
    workable = is_workable(adjusted, frozen, wet_threshold_m=wet_threshold_m)

    return pd.DataFrame({
        "date": dates.to_numpy(), "dtw_m": dtw_m, "is_peat": peat,
        "adjusted_dtw_m": adjusted, "frozen": frozen, "workable": workable,
    })


def negative_control(declarations, daily_weather: pd.DataFrame,
                     luke_dtw_paths: dict[float, str], cfg_d2: dict, *,
                     wet_threshold_m: float = 1.0, seed: int = 0) -> pd.DataFrame:
    """Same declaration locations, a random date each instead of the real
    arrival date - the baseline workable rate against which the real
    concordance is judged."""
    rng = np.random.default_rng(seed)
    span_days = (daily_weather.index.max() - daily_weather.index.min()).days
    random_dates = daily_weather.index.min() + pd.to_timedelta(
        rng.integers(0, span_days, size=len(declarations)), unit="D")
    fake = declarations.copy()
    fake["_random_date"] = random_dates
    return evaluate_declarations(fake, daily_weather, luke_dtw_paths, cfg_d2,
                                 wet_threshold_m=wet_threshold_m, date_field="_random_date")


def concordance_summary(declared: pd.DataFrame, control: pd.DataFrame) -> dict:
    """Workable rate on declared dates vs the random-date negative control."""
    return {
        "n_declared": int(len(declared)),
        "workable_rate_declared": round(float(declared["workable"].mean()), 4),
        "workable_rate_control": round(float(control["workable"].mean()), 4),
        "lift": round(float(declared["workable"].mean() / max(control["workable"].mean(), 1e-9)), 3),
        "frozen_share_declared": round(float(declared["frozen"].mean()), 4),
        "frozen_share_control": round(float(control["frozen"].mean()), 4),
    }


def korjuukelpoisuus_benchmark(
    luke_dtw_2ha_path: str,
    msnfi_soil_path: str,
    korjuu_path: str,
    cfg_d2: dict,
    *,
    wet_threshold_m: float = 1.0,
    peat_soil_classes=(2, 3, 4),
) -> dict:
    """Benchmark the D2 soil-adjusted DTW (the bearing-capacity part of the
    workability model, before the frozen-ground override) against Metsakeskus's
    operational **Korjuukelpoisuus** harvest-trafficability raster
    (HarvestAccessibilityType 1 = year-round even in thaw ... 6 = winter-harvest
    only). This is the DERIVE-AND-BENCHMARK comparison for D2 that the
    declaration-timing check could not provide.

    All three rasters are aligned onto the Luke 2 ha DTW grid (2 ha = Luke's
    own "average conditions" threshold). Reports, on cells classified 1-6:
    Spearman rank correlation between soil-adjusted DTW and the Korjuu class
    (expected strongly negative - drier ground, lower/better class), the median
    soil-adjusted DTW per class, and the share D2 would call workable
    (soil-adjusted DTW > wet_threshold_m) per class.
    """
    import rasterio
    from rasterio.warp import Resampling, reproject
    from scipy.stats import spearmanr

    with rasterio.open(luke_dtw_2ha_path) as src:
        dtw_m = src.read(1).astype("float64") * 0.01
        dtw_nodata = (src.read(1) == src.nodata) if src.nodata is not None else None
        transform, crs, shape = src.transform, src.crs, (src.height, src.width)

    def _onto_grid(path, dtype):
        with rasterio.open(path) as s:
            out = np.zeros(shape, dtype=dtype)
            reproject(s.read(1), out, src_transform=s.transform, src_crs=s.crs,
                      dst_transform=transform, dst_crs=crs,
                      resampling=Resampling.nearest, src_nodata=s.nodata, dst_nodata=0)
        return out

    soil = _onto_grid(msnfi_soil_path, "int32")
    korjuu = _onto_grid(korjuu_path, "int32")

    peat = np.isin(soil, np.asarray(peat_soil_classes, dtype="int32"))
    penalty = cfg_d2["soil_term"]["peat_bearing_penalty"]
    adj = soil_adjusted_dtw(dtw_m, peat, peat_bearing_penalty=penalty)

    valid = (korjuu >= 1) & (korjuu <= 6) & np.isfinite(adj) & (dtw_m > 0)
    if dtw_nodata is not None:
        valid &= ~dtw_nodata

    a, k = adj[valid], korjuu[valid]
    sr = spearmanr(a, k).correlation
    per_class = {}
    for cls in range(1, 7):
        m = k == cls
        if m.any():
            per_class[cls] = {
                "n_cells": int(m.sum()),
                "median_soil_adj_dtw_m": round(float(np.median(a[m])), 3),
                "share_d2_workable": round(float((a[m] > wet_threshold_m).mean()), 3),
            }
    return {
        "n_cells": int(valid.sum()),
        "spearman_soil_adj_dtw_vs_korjuu_class": round(float(sr), 3),
        "d2_workable_share_class_1_3": round(float(
            (a[np.isin(k, [1, 2, 3])] > wet_threshold_m).mean()), 3),
        "d2_workable_share_class_6": round(float(
            (a[k == 6] > wet_threshold_m).mean()), 3),
        "per_class": per_class,
    }
