# regenerative-harvest-planning/tests/test_f_connectivity.py
"""F1 node assembly: pure merge logic, no network."""

import geopandas as gpd
from shapely.geometry import Polygon

from src.f_connectivity import assemble_nodes


def _poly(x):
    return Polygon([(x, 0), (x + 1, 0), (x + 1, 1), (x, 1)])


def test_assemble_nodes_tags_each_source_and_filters_old_stands():
    pa = gpd.GeoDataFrame({"pa_source": ["state", "natura_sac"],
                           "geometry": [_poly(0), _poly(2)]}, crs="EPSG:3067")
    hab = gpd.GeoDataFrame({"geometry": [_poly(4)]}, crs="EPSG:3067")
    yt = gpd.GeoDataFrame({"geometry": [_poly(6)]}, crs="EPSG:3067")
    stands = gpd.GeoDataFrame({"meanage": [30, 140, 200],
                               "geometry": [_poly(8), _poly(10), _poly(12)]}, crs="EPSG:3067")

    nodes = assemble_nodes(pa, hab, yt, stands, old_stand_age_min_years=120)
    counts = nodes["node_type"].value_counts().to_dict()
    assert counts == {"pa_state": 1, "pa_natura_sac": 1, "habitat_s10": 1,
                      "ymparistotuki": 1, "old_stand": 2}
    assert nodes.crs.to_epsg() == 3067
    assert list(nodes.columns) == ["node_type", "geometry"]


def test_assemble_nodes_handles_empty_sources():
    empty = gpd.GeoDataFrame({"geometry": []}, crs="EPSG:3067")
    pa_empty = gpd.GeoDataFrame({"pa_source": [], "geometry": []}, crs="EPSG:3067")
    stands = gpd.GeoDataFrame({"meanage": [10], "geometry": [_poly(0)]}, crs="EPSG:3067")
    nodes = assemble_nodes(pa_empty, empty, empty, stands, old_stand_age_min_years=120)
    assert len(nodes) == 0
