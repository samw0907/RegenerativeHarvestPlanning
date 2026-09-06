# regenerative-harvest-planning/tests/test_e_plus_site_planning.py
"""E1b/E1c: pure logic and rasterisation/distance-transform math, no network.
`derive_channel_network` itself needs the real WhiteboxTools binary and a
multi-minute run on the full-AOI 16 m DEM, same testing philosophy as D1's
`reimplement_dtw` (see tests/test_d1_dtw_compare.py)."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString, Point

from src.e_plus_site_planning import (
    buffer_comparison, ccf_area_summary, cells_for_distance, distance_to_features_m,
    rasterize_lines, select_ccf_peatland,
)

CCF_CFG = {
    "peat_soiltype_min": 60,
    "fertility_class_max": 3,
    "drained_states": [7, 8, 9],
    "spruce_share_min": 0.5,
}


def test_cells_for_distance_converts_metres_to_whole_cells():
    assert cells_for_distance(2000.0, 16.0) == 125
    assert cells_for_distance(2000.0, 2.0) == 1000


def test_cells_for_distance_floors_at_one_cell():
    assert cells_for_distance(1.0, 16.0) == 1
    assert cells_for_distance(0.0, 16.0) == 1


@pytest.fixture
def grid_path(tmp_path):
    """A 10x10, 10 m grid, origin (0, 100) - column c spans x in [10c, 10c+10)."""
    path = tmp_path / "grid.tif"
    with rasterio.open(path, "w", driver="GTiff", crs="EPSG:3067",
                       transform=from_origin(0, 100, 10, 10),
                       width=10, height=10, count=1, dtype="float32") as dst:
        dst.write(np.zeros((10, 10), dtype="float32"), 1)
    return path


def _vertical_line(x):
    return gpd.GeoDataFrame(geometry=[LineString([(x, 0), (x, 100)])], crs="EPSG:3067")


def test_rasterize_lines_marks_the_correct_column(grid_path):
    lines = _vertical_line(25.0)  # centre of column index 2
    mask = rasterize_lines(lines, grid_path)
    assert mask.shape == (10, 10)
    assert (mask[:, 2] == 1).all()
    assert (mask[:, [c for c in range(10) if c != 2]] == 0).all()


def test_rasterize_lines_handles_empty_input(grid_path):
    empty = gpd.GeoDataFrame(geometry=[], crs="EPSG:3067")
    mask = rasterize_lines(empty, grid_path)
    assert mask.sum() == 0


def test_distance_to_features_m_is_zero_on_the_feature_and_scales_with_resolution():
    mask = np.zeros((5, 5), dtype=bool)
    mask[:, 2] = True
    dist = distance_to_features_m(mask, resolution_m=10.0)
    assert (dist[:, 2] == 0).all()
    assert np.allclose(dist[:, 1], 10.0)
    assert np.allclose(dist[:, 0], 20.0)


def test_distance_to_features_m_is_inf_everywhere_when_mask_is_empty():
    mask = np.zeros((3, 3), dtype=bool)
    dist = distance_to_features_m(mask, resolution_m=10.0)
    assert np.isinf(dist).all()


def test_buffer_comparison_areas_and_additional_area(grid_path):
    # derived at column 2 (x=25), mapped at column 7 (x=75) - 50 m apart on a
    # 10-column, 10 m grid - chosen so a 30 m buffer gives a real overlap to
    # check the set-difference ("additional") logic, not just the disjoint case
    derived = _vertical_line(25.0)
    mapped = _vertical_line(75.0)

    results = {r["buffer_width_m"]: r for r in buffer_comparison(derived, mapped, grid_path, [10, 20, 30])}

    assert results[10]["derived_buffer_ha"] == pytest.approx(0.3)
    assert results[10]["mapped_buffer_ha"] == pytest.approx(0.3)
    assert results[10]["additional_ha"] == pytest.approx(0.3)  # fully disjoint

    assert results[20]["derived_buffer_ha"] == pytest.approx(0.5)
    assert results[20]["additional_ha"] == pytest.approx(0.5)  # still disjoint

    assert results[30]["derived_buffer_ha"] == pytest.approx(0.6)
    assert results[30]["mapped_buffer_ha"] == pytest.approx(0.6)
    # columns 4-5 now fall in both buffers (20 cells worth = 0.2 ha overlap)
    assert results[30]["additional_ha"] == pytest.approx(0.4)


def _stands(rows):
    """rows: list of (soiltype, fertilityclass, drainagestate, proportionspruce, area_ha)."""
    recs = [
        {"soiltype": s, "fertilityclass": f, "drainagestate": d,
         "proportionspruce": sp, "area": a, "geometry": Point(i, 0)}
        for i, (s, f, d, sp, a) in enumerate(rows)
    ]
    return gpd.GeoDataFrame(recs, crs="EPSG:3067")


def test_select_ccf_peatland_requires_all_four_conditions():
    stands = _stands([
        (60, 2, 9, 0.7, 10.0),   # all pass -> True
        (50, 2, 9, 0.7, 10.0),   # mineral soil -> False
        (60, 4, 9, 0.7, 10.0),   # too poor a site (fertility 4) -> False
        (60, 2, 1, 0.7, 10.0),   # undrained -> False
        (60, 2, 9, 0.3, 10.0),   # not spruce-dominated -> False
        (61, 3, 7, 0.5, 10.0),   # boundary values all just pass -> True
    ])
    out = select_ccf_peatland(stands, CCF_CFG)
    assert list(out) == [True, False, False, False, False, True]


def test_select_ccf_peatland_coerces_strings_and_handles_missing():
    stands = _stands([("60", "2", "9", "0.8", 5.0)])
    stands.loc[len(stands)] = {"soiltype": None, "fertilityclass": 2,
                               "drainagestate": 9, "proportionspruce": 0.9,
                               "area": 5.0, "geometry": Point(9, 9)}
    out = select_ccf_peatland(stands, CCF_CFG)
    assert list(out) == [True, False]


def test_ccf_area_summary_area_breakdown_and_strict_fertility():
    stands = _stands([
        (60, 2, 9, 0.7, 100.0),  # eligible at both fertility<=3 and <=2
        (60, 3, 8, 0.6, 50.0),   # eligible only at fertility<=3
        (70, 5, 7, 0.9, 20.0),   # peat + drained, but too poor -> not eligible
        (30, 3, 1, 0.8, 30.0),   # mineral, undrained -> just contributes to total
    ])
    s = ccf_area_summary(stands, CCF_CFG)
    assert s["n_stands"] == 4
    assert s["total_stand_area_ha"] == pytest.approx(200.0)
    assert s["peatland_forest_ha"] == pytest.approx(170.0)         # 100 + 50 + 20
    assert s["drained_peatland_forest_ha"] == pytest.approx(170.0)
    assert s["ccf_eligible_ha"] == pytest.approx(150.0)            # 100 + 50
    assert s["ccf_eligible_strict_fertility_ha"] == pytest.approx(100.0)
    assert s["ccf_eligible_pct_of_drained_peatland"] == pytest.approx(88.2, abs=0.1)
    assert s["ccf_eligible_pct_of_total_forest"] == pytest.approx(75.0)


def test_ccf_rootrot_conflict_overlap_is_near_total_by_construction():
    from src.e_plus_site_planning import ccf_rootrot_conflict

    d3_cfg = {"mineral_soil_conifer_volume_share_min": 0.5,
              "peat_soil_spruce_volume_share_min": 0.5}
    stands = _stands([
        (60, 2, 9, 0.7, 100.0),  # CCF-eligible; spruce 0.7 >= 0.5 -> root-rot trigger too -> conflict
        (60, 3, 8, 0.5, 40.0),   # CCF-eligible at the boundary; spruce 0.5 -> trigger -> conflict
        (30, 3, 1, 0.9, 25.0),   # mineral, undrained -> not CCF-eligible -> not counted
    ])
    # add proportionpine so species_soil_rule has the column it reads
    stands["proportionpine"] = [0.2, 0.4, 0.05]

    out = ccf_rootrot_conflict(stands, CCF_CFG, d3_cfg)
    assert out["ccf_eligible_ha"] == pytest.approx(140.0)
    assert out["ccf_eligible_and_rootrot_trigger_ha"] == pytest.approx(140.0)
    assert out["conflict_share_of_ccf_eligible"] == pytest.approx(1.0)
    assert out["n_conflict_stands"] == 2


def test_conflict_free_felling_window_counts_only_frozen_days_outside_the_mandatory_period():
    from src.e_plus_site_planning import conflict_free_felling_window

    idx = pd.date_range("2000-07-01", "2003-06-30", freq="D")
    tmin = pd.Series(5.0, index=idx)
    # a 20-day hard frost each Jan (Dec-Apr -> counts) and each Oct (in the
    # 1 May-30 Nov mandatory period -> must not count)
    for yr in (2001, 2002, 2003):
        tmin.loc[f"{yr}-01-10":f"{yr}-01-29"] = -10.0
    for yr in (2000, 2001, 2002):
        tmin.loc[f"{yr}-10-05":f"{yr}-10-24"] = -10.0
    daily = pd.DataFrame({"tmin": tmin})

    out = conflict_free_felling_window(daily, {"mandatory_period": {"start": "05-01", "end": "11-30"}})
    # three complete winters (2000, 2001, 2002 by Jul->Jun attribution), each
    # with exactly the 20 January frost days and none of the October ones
    assert set(out["per_winter_days"].values()) == {20}
    assert out["by_decade_mean_days"] == {2000: 20.0}


def test_habitat_proximity_counts_stands_within_each_setback():
    from shapely.geometry import Polygon

    from src.e_plus_site_planning import habitat_proximity

    # one habitat polygon at x in [100, 110]; three stands 5 m / 15 m / 25 m west of it
    hab = gpd.GeoDataFrame(
        {"habitattype": [1]},
        geometry=[Polygon([(100, 0), (110, 0), (110, 10), (100, 10)])], crs="EPSG:3067")

    def sq(x0):
        return Polygon([(x0, 0), (x0 + 5, 0), (x0 + 5, 10), (x0, 10)])

    stands = gpd.GeoDataFrame(
        {"area": [1.0, 2.0, 4.0]},
        geometry=[sq(90), sq(80), sq(70)], crs="EPSG:3067")  # gaps: 5, 15, 25 m

    out = {r["setback_m"]: r for r in habitat_proximity(stands, hab, [10, 20, 30])}
    assert out[10]["n_stands_within"] == 1 and out[10]["stand_area_ha_within"] == pytest.approx(1.0)
    assert out[20]["n_stands_within"] == 2 and out[20]["stand_area_ha_within"] == pytest.approx(3.0)
    assert out[30]["n_stands_within"] == 3 and out[30]["stand_area_ha_within"] == pytest.approx(7.0)
    assert out[30]["stand_area_ha_nearest_habtype_1"] == pytest.approx(7.0)


def _write_tif(path, arr, res=10.0, nodata=-9999.0):
    with rasterio.open(path, "w", driver="GTiff", crs="EPSG:3067",
                       transform=from_origin(0, arr.shape[0] * res, res, res),
                       width=arr.shape[1], height=arr.shape[0], count=1,
                       dtype="float64", nodata=nodata) as dst:
        dst.write(arr.astype("float64"), 1)


def test_ls_factor_moore_burch_value_and_flat_zero(tmp_path):
    from src.e_plus_site_planning import ls_factor

    slope = np.full((4, 4), 5.0)
    slope[0, 0] = 0.0                     # a flat cell -> LS 0
    accum = np.full((4, 4), 50.0)         # 50 cells * 10 m = 500 m, capped to 100 m
    sp, ap = tmp_path / "s.tif", tmp_path / "a.tif"
    _write_tif(sp, slope)
    _write_tif(ap, accum)

    ls, prof = ls_factor(sp, ap, exponent_m=0.4, exponent_n=1.3, specific_area_cap_m=100.0)
    assert prof["dtype"] == "float32"
    assert ls[0, 0] == pytest.approx(0.0)
    # (100/22.13)**0.4 * (sin 5deg / 0.0896)**1.3
    expected = (100 / 22.13) ** 0.4 * (np.sin(np.deg2rad(5.0)) / 0.0896) ** 1.3
    assert ls[1, 1] == pytest.approx(expected, rel=1e-4)


def test_ls_factor_zeroes_nodata_cells(tmp_path):
    from src.e_plus_site_planning import ls_factor

    slope = np.full((3, 3), 10.0)
    slope[2, 2] = -9999.0
    accum = np.full((3, 3), 30.0)
    sp, ap = tmp_path / "s.tif", tmp_path / "a.tif"
    _write_tif(sp, slope)
    _write_tif(ap, accum)

    ls, _ = ls_factor(sp, ap)
    assert ls[2, 2] == 0.0
    assert ls[0, 0] > 0.0


def test_k_factor_maps_soiltype_codes_and_defaults_gaps(tmp_path):
    from shapely.geometry import Polygon

    from src.e_plus_site_planning import k_factor

    grid = tmp_path / "grid.tif"
    _write_tif(grid, np.zeros((10, 10)), res=10.0)  # 100 x 100 m, origin (0, 100)

    stands = gpd.GeoDataFrame(
        {"soiltype": ["12", "20", "999"]},   # sorted-coarse, fine mineral, unknown
        geometry=[
            Polygon([(0, 90), (30, 90), (30, 100), (0, 100)]),    # rows 0, cols 0-2
            Polygon([(30, 90), (60, 90), (60, 100), (30, 100)]),  # rows 0, cols 3-5
            Polygon([(60, 90), (90, 90), (90, 100), (60, 100)]),  # rows 0, cols 6-8
        ], crs="EPSG:3067")

    k = k_factor(stands, grid, {12: 0.013, 20: 0.043}, k_default=0.025)
    assert k[0, 1] == pytest.approx(0.013)     # soiltype 12
    assert k[0, 4] == pytest.approx(0.043)     # soiltype 20
    assert k[0, 7] == pytest.approx(0.025)     # unknown code -> default
    assert k[5, 5] == pytest.approx(0.025)     # no polygon -> default


def test_stand_coverage_mask_true_only_under_polygons(tmp_path):
    from shapely.geometry import Polygon

    from src.e_plus_site_planning import stand_coverage_mask

    grid = tmp_path / "grid.tif"
    _write_tif(grid, np.zeros((10, 10)), res=10.0)
    stands = gpd.GeoDataFrame(
        geometry=[Polygon([(0, 90), (20, 90), (20, 100), (0, 100)])], crs="EPSG:3067")
    m = stand_coverage_mask(stands, grid)
    assert m.dtype == bool
    assert m[0, 0] and m[0, 1]
    assert not m[5, 5]


def test_c_factor_maps_clc_classes_onto_the_grid(tmp_path):
    from src.e_plus_site_planning import c_factor

    grid = tmp_path / "grid.tif"
    _write_tif(grid, np.zeros((4, 4)), res=10.0)   # 40 x 40 m, origin (0, 40)

    # a matching-resolution CLC raster: left half forest (25), right half clearcut (33)
    clc = tmp_path / "clc.tif"
    cls = np.array([[25, 25, 33, 33]] * 4, dtype="uint8")
    with rasterio.open(clc, "w", driver="GTiff", crs="EPSG:3067",
                       transform=from_origin(0, 40, 10, 10),
                       width=4, height=4, count=1, dtype="uint8", nodata=0) as dst:
        dst.write(cls, 1)

    c = c_factor(clc, grid, {25: 0.0015, 33: 0.10}, c_default=0.01)
    assert c.shape == (4, 4)
    assert np.allclose(c[:, :2], 0.0015)
    assert np.allclose(c[:, 2:], 0.10)


def test_c_factor_unlisted_class_falls_to_default(tmp_path):
    from src.e_plus_site_planning import c_factor

    grid = tmp_path / "grid.tif"
    _write_tif(grid, np.zeros((3, 3)), res=10.0)
    clc = tmp_path / "clc.tif"
    with rasterio.open(clc, "w", driver="GTiff", crs="EPSG:3067",
                       transform=from_origin(0, 30, 10, 10),
                       width=3, height=3, count=1, dtype="uint8", nodata=0) as dst:
        dst.write(np.full((3, 3), 99, dtype="uint8"), 1)
    c = c_factor(clc, grid, {25: 0.0015}, c_default=0.02)
    assert np.allclose(c, 0.02)


def test_assemble_rusle_is_elementwise_product():
    from src.e_plus_site_planning import assemble_rusle

    ls = np.array([[1.0, 2.0], [0.0, 4.0]])
    k = np.array([[0.02, 0.04], [0.03, 0.01]])
    c = np.array([[0.1, 0.0015], [0.5, 0.05]])
    a = assemble_rusle(ls, k, c, r_factor=300.0)
    assert a.dtype == np.float32
    assert a[0, 0] == pytest.approx(300.0 * 0.02 * 1.0 * 0.1)
    assert a[1, 0] == pytest.approx(0.0)          # LS 0 -> A 0
    assert a[0, 1] == pytest.approx(300.0 * 0.04 * 2.0 * 0.0015)


def test_rusle_benchmark_correlations_on_synthetic_rasters(tmp_path):
    from src.e_plus_site_planning import rusle_benchmark

    rng = np.random.default_rng(0)
    base = rng.uniform(0.01, 5.0, (40, 40))
    ours = tmp_path / "ours.tif"
    mk = tmp_path / "mk.tif"
    cover = tmp_path / "cover.tif"
    _write_tif(ours, base, res=10.0)
    _write_tif(mk, base * 120.0 + rng.normal(0, 1.0, base.shape), res=10.0)  # scaled + noise -> high corr
    _write_tif(cover, np.ones_like(base), res=10.0)

    out = rusle_benchmark(ours, mk, cover)
    assert out["our_A"]["n"] >= 1590   # a few edge cells may drop on resample
    assert out["our_A"]["spearman_r"] > 0.95
    assert 80 < out["our_A"]["median_ratio_mk_over_x"] < 160
