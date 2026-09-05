# regenerative-harvest-planning/src/d2_dtw_extend.py
"""Module D2 - the DTW extension: adding soil and weather.

**Weather term.** The five official DTW thresholds are themselves wetness-
condition proxies (Luke's own product description): 0.5 ha very wet
(snowmelt, prolonged rain) through 10 ha drier than average. Rather than a
user picking one by judgement, this derives a continuous per-date wetness
signal from FMI daily data - antecedent precipitation (rolling sums over
several windows) plus an active-snowmelt signal (day-over-day snow-depth
loss) - ranks it against the station's own long-run distribution (so the
mapping is calibrated from real climatology, not an arbitrary cutoff), and
log-interpolates between the two threshold rasters that bracket the resulting
continuous "effective threshold". This is a genuine design choice (the plan
specifies the goal - "select the appropriate threshold surface per date" -
not an exact formula), recorded here so the reasoning is traceable.

**Soil term.** Peat holds water and has low bearing capacity even where DTW
reads dry, because DTW is derived purely from topography. Modulate the
DTW-implied wetness by MS-NFI soil main type: a peat cell is read as wetter
than its raw DTW value by `peat_bearing_penalty` (config), i.e. it behaves as
though its effective threshold were smaller (wetter) than the topography alone
implies.

**Workability.** `frozen_ground_days` classes a day as frozen ground from a
simple, transparent temperature-run proxy (frozen soil bearing capacity is not
itself an FMI-measured quantity). `is_workable` combines the soil-adjusted DTW
with frozen-ground status: dry-enough DTW OR frozen ground makes a site
workable - frozen ground overrides a wet DTW reading, which is exactly why
winter logging on wet/peat ground is standard Nordic practice. The wet/dry
cutoff (default 1.0 m) is the value the plan's Module E config carries
(`dtw_wet_threshold_m`, from Hilli & Mykra et al. 2022's 0.8-1.2 m upland/wet
species boundary) - reused here rather than duplicated, since it is the same
physical cutoff.

Data tiers: FMI daily observations FETCH; MS-NFI soil main type FETCH; the
combined surface DERIVE ONLY (no official date-specific product exists).

Validation: see `src/d_validation.py` - does declared harvest activity on
poor-bearing-capacity stands actually concentrate in the predicted frozen/dry
windows? A declaration is a permit, not a felling record - state that plainly,
as Module B had to learn in Project 1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

THRESHOLDS_HA = (0.5, 1.0, 2.0, 4.0, 10.0)  # wettest -> driest, Luke's official set
_RRDAY_DRY_SENTINEL = -1.0   # FMI convention: -1 means "no precipitation"
_SNOW_ABSENT_SENTINEL = -1.0  # FMI convention: -1 means "no snow on the ground"


def antecedent_precipitation(daily: pd.DataFrame, windows_days=(7, 14, 30)) -> pd.DataFrame:
    """Rolling precipitation sum (mm) over each window, per day.

    `rrday` uses -1 as a "dry day" sentinel (not a real negative value); that
    is clipped to 0 before summing.
    """
    precip = daily["rrday"].clip(lower=0)
    return pd.DataFrame({f"api_{w}d": precip.rolling(w, min_periods=1).sum()
                         for w in windows_days}, index=daily.index)


def snowmelt_signal(daily: pd.DataFrame) -> pd.Series:
    """Day-over-day decrease in snow depth (cm), i.e. active meltwater input.

    0 where snow is absent (-1 sentinel) or depth is flat/increasing.
    """
    snow = daily["snow"].clip(lower=0)
    melt = (-snow.diff()).clip(lower=0)
    return melt.fillna(0.0).rename("snowmelt_cm")


def wetness_percentile(daily: pd.DataFrame, *, windows_days=(7, 14, 30),
                       window_weights=(3.0, 2.0, 1.0), snowmelt_weight: float = 2.0) -> pd.Series:
    """A per-day wetness signal, ranked against the station's own full-record
    distribution so the scale is calibrated from real climatology (1.0 =
    wettest day on record, 0.0 = driest).

    The combination (shorter antecedent-precipitation windows weighted more,
    since they reflect "right now" conditions more than a 30-day total; a
    snowmelt day of 1 cm melt treated as comparable to snowmelt_weight mm of
    rain) is a design choice, not a published formula - the plan leaves the
    exact selection rule open. Documented in the module docstring.
    """
    api = antecedent_precipitation(daily, windows_days)
    weights = np.asarray(window_weights[: api.shape[1]], dtype="float64")
    api_signal = (api.to_numpy() * weights).sum(axis=1) / weights.sum()
    melt = snowmelt_signal(daily).to_numpy()
    raw = api_signal + snowmelt_weight * melt
    return pd.Series(raw, index=daily.index, name="raw_wetness").rank(pct=True)


def select_threshold_ha(percentile: float | np.ndarray, thresholds_ha=THRESHOLDS_HA):
    """Map a wetness percentile (1 = wettest) to a continuous threshold value,
    log-interpolated across the official thresholds (0.5 ha at percentile 1,
    10 ha at percentile 0)."""
    log_thr = np.log(np.asarray(thresholds_ha, dtype="float64"))
    x_known = np.linspace(1.0, 0.0, len(thresholds_ha))  # 1=wettest -> first threshold
    return np.exp(np.interp(percentile, x_known[::-1], log_thr[::-1]))


def interpolate_dtw_surface(threshold_ha: float, surfaces: dict[float, np.ndarray]) -> np.ndarray:
    """Pixel-wise interpolation between the two threshold rasters bracketing
    `threshold_ha`. `surfaces` maps each of THRESHOLDS_HA to its (already-
    loaded) array; all must share the same shape.

    The blend *position* is log-weighted (the 5 official thresholds are
    themselves roughly log-spaced), but the raster *values* are blended
    linearly, not their logs - DTW = 0 (a channel cell) is common and valid,
    and log(0) is undefined, so a true log-of-values interpolation would break
    on exactly the cells nearest water."""
    known = sorted(surfaces)
    if threshold_ha <= known[0]:
        return surfaces[known[0]]
    if threshold_ha >= known[-1]:
        return surfaces[known[-1]]
    hi = next(k for k in known if k >= threshold_ha)
    lo = max(k for k in known if k <= threshold_ha)
    if hi == lo:
        return surfaces[lo]
    t = (np.log(threshold_ha) - np.log(lo)) / (np.log(hi) - np.log(lo))
    return surfaces[lo] * (1 - t) + surfaces[hi] * t


def soil_adjusted_dtw(dtw_m: np.ndarray, is_peat: np.ndarray, *,
                      peat_bearing_penalty: float = 0.5) -> np.ndarray:
    """Scale down the effective DTW on peat cells so they read wetter than
    their raw topographic value - peat holds water and has low bearing
    capacity that DTW (elevation/slope only) cannot see. `peat_bearing_penalty`
    is the fractional reduction (0.5 = a peat cell's effective DTW is half its
    raw value, i.e. it looks twice as close to "wet" as the topography implies)."""
    factor = np.where(is_peat, 1.0 - peat_bearing_penalty, 1.0)
    return dtw_m * factor


def frozen_ground_days(daily_weather: pd.DataFrame, *, frost_temp_c: float = -2.0,
                       min_run_days: int = 3) -> pd.Series:
    """Days classed as frozen ground: part of a run of >= min_run_days
    consecutive days with tmin <= frost_temp_c.

    A simple, transparent proxy (frozen soil bearing capacity is not itself an
    FMI-measured quantity) - winter logging on wet/peat ground is standard
    Nordic practice specifically because frost overrides the DTW-based
    trafficability limit, which is what `is_workable` uses this for.
    """
    cold = (daily_weather["tmin"] <= frost_temp_c).to_numpy()
    frozen = np.zeros(len(cold), dtype=bool)
    run_start = None
    for i, v in enumerate(cold):
        if v and run_start is None:
            run_start = i
        elif not v and run_start is not None:
            if i - run_start >= min_run_days:
                frozen[run_start:i] = True
            run_start = None
    if run_start is not None and len(cold) - run_start >= min_run_days:
        frozen[run_start:] = True
    return pd.Series(frozen, index=daily_weather.index, name="frozen_ground")


def is_workable(dtw_m: np.ndarray, is_frozen, *, wet_threshold_m: float = 1.0) -> np.ndarray:
    """A site is workable if it is dry enough (effective DTW above
    wet_threshold_m - the 0.8-1.2 m band Hilli & Mykra et al. 2022 found
    characterises the upland/wet species boundary, config's default 1.0 m) OR
    the ground is frozen, which overrides a wet DTW reading entirely."""
    return (np.asarray(dtw_m, dtype="float64") > wet_threshold_m) | np.asarray(is_frozen, dtype=bool)
