# regenerative-harvest-planning/tests/test_e_plus_site_planning.py
"""E1b/E1c: pure logic and rasterisation/distance-transform math, no network.
`derive_channel_network` itself needs the real WhiteboxTools binary and a
multi-minute run on the full-AOI 16 m DEM, same testing philosophy as D1's
`reimplement_dtw` (see tests/test_d1_dtw_compare.py)."""

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString

from src.e_plus_site_planning import (
    buffer_comparison, cells_for_distance, distance_to_features_m, rasterize_lines,
)


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
