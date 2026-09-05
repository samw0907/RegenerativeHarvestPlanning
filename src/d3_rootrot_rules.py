# regenerative-harvest-planning/src/d3_rootrot_rules.py
"""Module D3 - root rot obligation, as a deterministic rule engine.

From the Forest Damages Prevention Act. Stump treatment mandatory where:
- mineral soil: pine and/or spruce together exceed 50% of pre-felling stand
  volume (config: mineral_soil_conifer_volume_share_min)
- peat soil: spruce alone exceeds 50% of pre-felling stand volume (config:
  peat_soil_spruce_volume_share_min)

...within the mandatory period (config: 1 May - 30 Nov), unless a cold-spell
exemption applies: the site's minimum temperature has been below
`exemption_min_temp_c` (-10 C) at some point in the `exemption_lookback_days`
(21) days before felling - spore viability is suppressed by hard frost even
inside the calendar period.

`spore_season_bounds` additionally computes the *actual* biologically active
season per year from temperature, using the same definition FMI itself
publishes as the Finnish "thermal growing season" (terminen kasvukausi): the
season starts on the first day of the first run of >= 5 consecutive days with
mean temperature >= `spore_dispersal_mean_temp_c` (+5 C), and ends on the last
day of the last such run. This is the analytical basis for "a warm spring
starts the season early and a mild autumn extends it" - the fixed calendar
period is the regulatory approximation; this is the measured season, and the
difference between them is itself a result worth reporting.

Data tiers: stand attributes (soil type, species volume shares) and FMI daily
temperature FETCH; the rule evaluation is a deterministic legal rule, not a
statistical model - no ML question arises here.

Urea watercourse setback (no urea within 10 m of a watercourse) uses D1's
derived channel network, not just mapped hydrography - see
`urea_setback_violation`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_MINERAL_SOILTYPE_MAX = 59  # Metsakeskus SoilTypeType: <60 mineral, >=60 peat/organic


def is_peat_soil(soiltype) -> np.ndarray:
    """Metsakeskus `soiltype` codes: 10-50-series are mineral, 60+ are peat/organic."""
    return pd.to_numeric(pd.Series(soiltype), errors="coerce").to_numpy() > _MINERAL_SOILTYPE_MAX


def species_soil_rule(is_peat, pine_share, spruce_share, cfg: dict) -> np.ndarray:
    """True where the pre-felling species/soil composition triggers the obligation."""
    is_peat = np.asarray(is_peat, dtype=bool)
    pine_share = np.asarray(pine_share, dtype="float64")
    spruce_share = np.asarray(spruce_share, dtype="float64")
    mineral_trigger = (pine_share + spruce_share) >= cfg["mineral_soil_conifer_volume_share_min"]
    peat_trigger = spruce_share >= cfg["peat_soil_spruce_volume_share_min"]
    return np.where(is_peat, peat_trigger, mineral_trigger)


def in_mandatory_period(dates, cfg: dict) -> np.ndarray:
    """True where the date falls within the fixed calendar period (MM-DD, inclusive)."""
    dates = pd.to_datetime(pd.Index(np.atleast_1d(dates)))
    md = dates.strftime("%m-%d")
    return (md >= cfg["mandatory_period"]["start"]) & (md <= cfg["mandatory_period"]["end"])


def cold_spell_exemption(daily_weather: pd.DataFrame, felling_dates, cfg: dict) -> np.ndarray:
    """True where a hard frost (tmin < exemption_min_temp_c) occurred at any point
    in the exemption_lookback_days before (and including) the felling date."""
    tmin = daily_weather["tmin"]
    lookback = int(cfg["exemption_lookback_days"])
    had_frost = (tmin < cfg["exemption_min_temp_c"]).rolling(
        f"{lookback}D", min_periods=1).max().reindex(tmin.index)

    felling_dates = pd.to_datetime(pd.Index(np.atleast_1d(felling_dates)))
    aligned = had_frost.reindex(felling_dates, method="ffill")
    return aligned.fillna(False).to_numpy().astype(bool)


def evaluate_obligation(is_peat, pine_share, spruce_share, felling_dates,
                        daily_weather: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Combine the species/soil rule, the calendar period and the cold-spell
    exemption into a per-stand, per-felling-date obligation table.

    is_peat/pine_share/spruce_share and felling_dates broadcast against each
    other (e.g. one felling date checked against many stands, or one stand
    checked against many candidate dates)."""
    trigger = np.atleast_1d(species_soil_rule(is_peat, pine_share, spruce_share, cfg))
    felling_dates = pd.to_datetime(pd.Index(np.atleast_1d(felling_dates)))
    period = in_mandatory_period(felling_dates, cfg)
    exempt = cold_spell_exemption(daily_weather, felling_dates, cfg)

    n = max(trigger.size, felling_dates.size)
    trigger = np.broadcast_to(trigger, (n,))
    period = np.broadcast_to(period, (n,))
    exempt = np.broadcast_to(exempt, (n,))
    dates_out = felling_dates if felling_dates.size == n else felling_dates.repeat(n)
    required = trigger & period & ~exempt
    return pd.DataFrame({
        "felling_date": dates_out, "species_soil_trigger": trigger,
        "in_mandatory_period": period, "cold_spell_exempt": exempt,
        "treatment_required": required,
    })


def _runs_at_least(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """Start/end (inclusive) integer-index pairs of runs of True of length >= min_len."""
    runs = []
    start = None
    for i, v in enumerate(np.append(mask, False)):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_len:
                runs.append((start, i - 1))
            start = None
    return runs


def spore_season_bounds(daily_weather: pd.DataFrame, year: int, cfg: dict,
                        min_run_days: int = 5) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """The measured (not calendar) root-rot risk season for one year: the first
    day of the first >= min_run_days run of mean temperature at or above
    spore_dispersal_mean_temp_c, to the last day of the last such run. This is
    FMI's own "thermal growing season" definition, reused here since spore
    dispersal and thermal growth share the same +5 C threshold in the Finnish
    literature. Returns (None, None) if the year has no qualifying run.
    """
    year_data = daily_weather.loc[str(year)]
    warm = (year_data["tday"] >= cfg["spore_dispersal_mean_temp_c"]).to_numpy()
    runs = _runs_at_least(warm, min_run_days)
    if not runs:
        return None, None
    start = year_data.index[runs[0][0]]
    end = year_data.index[runs[-1][1]]
    return start, end


def urea_setback_violation(stand_points, channel_network, setback_m: float) -> np.ndarray:
    """True where a stand point falls within setback_m of the D1 derived
    channel network - no urea may be applied there; an alternative stump
    treatment (mechanical, or a different biocide) is required instead.

    stand_points -- a GeoSeries/GeoDataFrame of points (e.g. stand centroids).
    channel_network -- a GeoDataFrame/GeoSeries of the channel line/cell geometry,
    same CRS as stand_points.
    """
    dist = stand_points.geometry.apply(lambda p: channel_network.distance(p).min())
    return (dist <= setback_m).to_numpy()
