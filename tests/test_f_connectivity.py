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


def test_resistance_surface_blends_terms_and_barriers_water(tmp_path):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    from src.f_connectivity import resistance_surface

    # 4x4, 10 m grid. CLC: left half forest (25), right half water (48).
    grid = tmp_path / "grid.tif"
    clc = tmp_path / "clc.tif"
    for p, arr, dt in [(grid, np.zeros((4, 4), "float32"), "float32"),
                       (clc, np.array([[25, 25, 48, 48]] * 4, "uint8"), "uint8")]:
        with rasterio.open(p, "w", driver="GTiff", crs="EPSG:3067",
                           transform=from_origin(0, 40, 10, 10), width=4, height=4,
                           count=1, dtype=dt, nodata=0) as dst:
            dst.write(arr, 1)

    # one old, closed, deciduous stand over the whole left column-pair
    stands = gpd.GeoDataFrame(
        {"meanage": [150.0], "basalarea": [30.0], "proportionother": [0.6],
         "geometry": [Polygon([(0, 0), (20, 0), (20, 40), (0, 40)])]}, crs="EPSG:3067")

    cfg_res = {
        "scale_min": 1.0, "scale_max": 100.0, "water_resistance": 1000.0,
        "age_cap_years": 120, "basal_area_cap_m2_ha": 25.0, "deciduous_share_ref": 0.5,
        "weights": {"age": 0.3, "structure": 0.25, "species": 0.2, "landcover": 0.25},
        "landcover_resistance": {"forest": 0.1, "transitional": 0.5, "open_veg": 0.55,
                                 "mire": 0.4, "agriculture": 0.8, "bare": 0.7,
                                 "built": 0.9, "water": 1.0},
    }
    r, prof = resistance_surface(stands, str(clc), str(grid), cfg_res)
    assert prof["dtype"] == "float32"
    # left cells: old/closed/deciduous stand -> age/structure/species terms 0;
    # only the landcover term (forest = 0.1, weight 0.25) contributes
    # r01 = 0.25 * 0.1 = 0.025 -> r = 1 + 0.025 * 99
    assert np.allclose(r[:, :2], 1.0 + 0.025 * 99.0, atol=1e-3)
    # right cells: water barrier
    assert np.allclose(r[:, 2:], 1000.0)


def test_resistance_surface_off_stand_falls_back_to_landcover(tmp_path):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    from src.f_connectivity import resistance_surface

    grid = tmp_path / "grid.tif"
    clc = tmp_path / "clc.tif"
    for p, arr, dt in [(grid, np.zeros((3, 3), "float32"), "float32"),
                       (clc, np.full((3, 3), 17, "uint8"), "uint8")]:  # 17 = arable
        with rasterio.open(p, "w", driver="GTiff", crs="EPSG:3067",
                           transform=from_origin(0, 30, 10, 10), width=3, height=3,
                           count=1, dtype=dt, nodata=0) as dst:
            dst.write(arr, 1)

    empty = gpd.GeoDataFrame({"meanage": [], "basalarea": [], "proportionother": [],
                              "geometry": []}, crs="EPSG:3067")
    cfg_res = {
        "scale_min": 1.0, "scale_max": 100.0, "water_resistance": 1000.0,
        "age_cap_years": 120, "basal_area_cap_m2_ha": 25.0, "deciduous_share_ref": 0.5,
        "weights": {"age": 0.3, "structure": 0.25, "species": 0.2, "landcover": 0.25},
        "landcover_resistance": {"forest": 0.1, "transitional": 0.5, "open_veg": 0.55,
                                 "mire": 0.4, "agriculture": 0.8, "bare": 0.7,
                                 "built": 0.9, "water": 1.0},
    }
    r, _ = resistance_surface(empty, str(clc), str(grid), cfg_res)
    # all terms fall back to landcover (arable = 0.8) -> r01 = 0.8 -> r = 1 + 0.8*99
    assert np.allclose(r, 1.0 + 0.8 * 99.0, atol=1e-3)


def test_f3_connectivity_pipeline_on_a_tiny_synthetic_landscape():
    import numpy as np

    from src.f_connectivity import (
        backbone_edges, corridor_density, patch_dpc, patch_least_cost,
        per_stand_corridor_score)
    from rasterio.transform import from_origin

    # 1 m grid, 20x20, uniform low resistance; three patches in a line
    arr = np.ones((20, 20), dtype="float64")
    transform = from_origin(0, 20, 1, 1)
    patches = gpd.GeoDataFrame(
        {"patch_id": [0, 1, 2], "area_ha": [1.0, 1.0, 1.0],
         "geometry": [_poly(1), _poly(9), _poly(17)]}, crs="EPSG:3067")
    # _poly makes a 1x1 square at y in [0,1]; nudge into the grid interior
    patches["geometry"] = patches.geometry.translate(yoff=10)

    cm, fields = patch_least_cost(patches, arr, transform)
    assert cm.shape == (3, 3)
    assert cm[0, 2] > cm[0, 1] > 0          # middle patch is closer than the far one
    assert np.allclose(cm, cm.T)

    dpc, pc = patch_dpc(cm, patches["area_ha"].to_numpy(), dispersal_cost=10.0)
    assert pc > 0 and len(dpc) == 3
    assert dpc[1] >= dpc[0] and dpc[1] >= dpc[2]   # the middle patch is the connector

    edges = backbone_edges(cm, k_nearest=2)
    assert (0, 1) in edges and (1, 2) in edges
    dens = corridor_density(fields, cm, patches["area_ha"].to_numpy(), arr.shape,
                            edges, dispersal_cost=10.0, slack=0.3)
    assert dens.shape == arr.shape and dens.max() > 0

    stands = gpd.GeoDataFrame(
        geometry=gpd.GeoSeries([_poly(5)], crs="EPSG:3067").translate(yoff=10))
    score = per_stand_corridor_score(stands, dens, transform)
    assert score.shape == (1,) and score[0] >= 0


def test_perturb_resistance_cfg_is_seeded_and_in_range():
    import numpy as np

    from src.f_connectivity import perturb_resistance_cfg

    cfg_res = {
        "weights": {"age": 0.3, "structure": 0.25, "species": 0.2, "landcover": 0.25},
        "landcover_resistance": {"forest": 0.1, "water": 1.0, "built": 0.9},
        "water_resistance": 1000.0,
    }
    cfg_conn = {"dispersal_cost": 8000.0, "coarsen_factor": 8, "backbone_k_nearest": 3,
                "corridor_slack": 0.15}
    cfg_sens = {"weight_perturbation": 0.4, "landcover_perturbation": 0.3,
                "dispersal_perturbation": 0.5}

    a1, c1 = perturb_resistance_cfg(cfg_res, cfg_conn, cfg_sens, np.random.default_rng(0))
    a2, c2 = perturb_resistance_cfg(cfg_res, cfg_conn, cfg_sens, np.random.default_rng(0))
    assert a1 == a2 and c1 == c2                                   # seeded -> reproducible
    assert abs(sum(a1["weights"].values()) - 1.0) < 1e-9          # renormalised
    assert all(0.02 <= v <= 1.0 for v in a1["landcover_resistance"].values())
    assert 4000.0 <= c1["dispersal_cost"] <= 12000.0
    assert c1["coarsen_factor"] == 8                              # numerical settings untouched

    a3, _ = perturb_resistance_cfg(cfg_res, cfg_conn, cfg_sens, np.random.default_rng(1))
    assert a3["weights"] != a1["weights"]                         # different seed -> different draw
