# regenerative-harvest-planning/tests/test_e_plus_site_planning.py
"""E1b channel network: pure logic only. `derive_channel_network` itself needs
the real WhiteboxTools binary and a multi-minute run on the full-AOI 16 m DEM,
same testing philosophy as D1's `reimplement_dtw` (see tests/test_d1_dtw_compare.py)."""

from src.e_plus_site_planning import cells_for_distance


def test_cells_for_distance_converts_metres_to_whole_cells():
    assert cells_for_distance(2000.0, 16.0) == 125
    assert cells_for_distance(2000.0, 2.0) == 1000


def test_cells_for_distance_floors_at_one_cell():
    assert cells_for_distance(1.0, 16.0) == 1
    assert cells_for_distance(0.0, 16.0) == 1
