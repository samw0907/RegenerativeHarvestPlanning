# regenerative-harvest-planning/tests/test_d3_rootrot_rules.py
"""D3 root-rot rule engine: pure logic, no network."""

import pandas as pd
import pytest

from src.d3_rootrot_rules import (
    cold_spell_exemption, evaluate_obligation, in_mandatory_period, is_peat_soil,
    species_soil_rule, spore_season_bounds, urea_setback_violation,
)

CFG = {
    "mandatory_period": {"start": "05-01", "end": "11-30"},
    "mineral_soil_conifer_volume_share_min": 0.50,
    "peat_soil_spruce_volume_share_min": 0.50,
    "exemption_min_temp_c": -10.0,
    "exemption_lookback_days": 21,
    "spore_dispersal_mean_temp_c": 5.0,
    "urea_watercourse_setback_m": 10,
}


def test_is_peat_soil_uses_the_60_boundary():
    out = is_peat_soil(["10", "50", "59", "60", "65", None])
    assert list(out) == [False, False, False, True, True, False]


def test_species_soil_rule_uses_different_thresholds_by_soil():
    # mineral: pine+spruce must reach 0.5; peat: spruce alone must reach 0.5
    is_peat = [False, False, True, True]
    pine = [0.3, 0.4, 0.1, 0.1]
    spruce = [0.3, 0.05, 0.4, 0.5]
    out = species_soil_rule(is_peat, pine, spruce, CFG)
    assert list(out) == [True, False, False, True]


def test_in_mandatory_period_boundaries_inclusive():
    dates = ["2020-04-30", "2020-05-01", "2020-11-30", "2020-12-01"]
    assert list(in_mandatory_period(dates, CFG)) == [False, True, True, False]


def test_cold_spell_exemption_true_only_after_a_recent_hard_frost():
    idx = pd.date_range("2020-04-01", "2020-05-15", freq="D")
    tmin = pd.Series(0.0, index=idx)
    tmin.loc["2020-04-10"] = -12.0  # one hard frost day
    daily = pd.DataFrame({"tmin": tmin})

    within_lookback = "2020-04-20"    # 10 days after the frost, inside 21-day window
    outside_lookback = "2020-05-05"   # 25 days after the frost, outside the window
    out = cold_spell_exemption(daily, [within_lookback, outside_lookback], CFG)
    assert list(out) == [True, False]


def test_evaluate_obligation_combines_all_three_conditions():
    idx = pd.date_range("2020-01-01", "2020-12-31", freq="D")
    daily = pd.DataFrame({"tmin": 0.0}, index=idx)  # no frost anywhere

    out = evaluate_obligation(
        is_peat=[False, False, False],
        pine_share=[0.6, 0.2, 0.6],
        spruce_share=[0.0, 0.1, 0.0],
        felling_dates=["2020-06-01", "2020-06-01", "2020-01-01"],
        daily_weather=daily, cfg=CFG,
    )
    # stand 1: triggers + in period + not exempt -> required
    # stand 2: does not trigger -> not required
    # stand 3: triggers but outside the mandatory period -> not required
    assert list(out["treatment_required"]) == [True, False, False]


def test_spore_season_bounds_requires_a_sustained_run():
    idx = pd.date_range("2021-01-01", "2021-12-31", freq="D")
    tday = pd.Series(-5.0, index=idx)
    tday.loc["2021-04-01":"2021-04-10"] = 6.0   # a real 10-day warm spell
    tday.loc["2021-03-01":"2021-03-02"] = 8.0   # a 2-day blip - too short to count
    tday.loc["2021-09-01":"2021-09-20"] = 7.0   # a later, longer warm spell
    daily = pd.DataFrame({"tday": tday})

    start, end = spore_season_bounds(daily, 2021, CFG, min_run_days=5)
    assert start == pd.Timestamp("2021-04-01")
    assert end == pd.Timestamp("2021-09-20")


def test_spore_season_bounds_returns_none_when_no_run_qualifies():
    idx = pd.date_range("2021-01-01", "2021-12-31", freq="D")
    daily = pd.DataFrame({"tday": pd.Series(-5.0, index=idx)})
    assert spore_season_bounds(daily, 2021, CFG, min_run_days=5) == (None, None)


def test_urea_setback_violation_flags_points_near_the_channel():
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import LineString, Point

    channel = gpd.GeoSeries([LineString([(0, 0), (100, 0)])], crs="EPSG:3067")
    points = gpd.GeoDataFrame(
        geometry=[Point(50, 5), Point(50, 50)], crs="EPSG:3067")
    out = urea_setback_violation(points, channel, setback_m=10)
    assert list(out) == [True, False]
