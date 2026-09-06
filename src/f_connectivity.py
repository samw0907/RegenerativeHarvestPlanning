# regenerative-harvest-planning/src/f_connectivity.py
"""Module F - biodiversity network connectivity.

Nodes: protected areas (SYKE/Metsahallitus), Forest Act §10 habitats,
environmental support (ymparistotuki) sites, old or structurally rich stands.
Resistance surface from stand age, canopy structure, species composition and
land cover. Connectivity via least-cost paths and graph-theoretic importance
measures. Rank candidate stands by marginal connectivity gain if a Plus
retention measure were applied there.

Data tier: FETCH throughout (registers and designations); the connectivity
analysis itself is transparent graph analysis, not a fitted model.

The honesty requirement (already the standard the other modules should match,
not a new lesson): resistance surfaces are assumption-laden. Run a sensitivity
sweep across plausible parameterisations (`resistance_sensitivity_runs` in
config) and report which stands are robustly high-value across all of them
versus which are artefacts of one parameter choice. The robust set is the
deliverable. Presented as an exploratory prioritisation method, not a
recommendation - the least certain of the three modules, and the README says so.

F1 (node assembly) implemented below.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

# SYKE CLC2018 49-class pixel value -> broad category (a fixed property of the
# scheme, not a tuning choice; resistance per category is in config).
_CLC_GROUPS = {
    "forest": (23, 24, 25, 26, 27, 28, 29, 30),
    "transitional": (33, 34, 35, 36, 37),
    "open_veg": (31, 32),
    "mire": (41, 43, 45),
    "agriculture": (17, 18, 19, 20, 21, 22),
    "bare": (38, 39, 40, 44),
    "built": (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16),
    "water": (42, 46, 47, 48, 49),
}
_CLC_CATEGORY = {v: cat for cat, vals in _CLC_GROUPS.items() for v in vals}


def assemble_nodes(
    protected_areas: gpd.GeoDataFrame,
    habitats_s10: gpd.GeoDataFrame,
    ymparistotuki: gpd.GeoDataFrame,
    stands: gpd.GeoDataFrame,
    *,
    old_stand_age_min_years: int = 120,
) -> gpd.GeoDataFrame:
    """Merge the four Module F node sources into one polygon GeoDataFrame with a
    `node_type` column ("pa_state" / "pa_private" / "pa_natura_sac" /
    "pa_natura_spa" / "habitat_s10" / "ymparistotuki" / "old_stand").

    Old stands are Metsakeskus stands with `meanage >= old_stand_age_min_years`
    (config default 120). All inputs must be EPSG:3067; only geometry and
    node_type are kept."""
    parts = []

    if len(protected_areas):
        pa = protected_areas.copy()
        pa["node_type"] = "pa_" + pa["pa_source"].astype(str)
        parts.append(pa[["node_type", "geometry"]])

    if len(habitats_s10):
        parts.append(gpd.GeoDataFrame(
            {"node_type": "habitat_s10", "geometry": habitats_s10.geometry.values},
            crs="EPSG:3067"))

    if len(ymparistotuki):
        parts.append(gpd.GeoDataFrame(
            {"node_type": "ymparistotuki", "geometry": ymparistotuki.geometry.values},
            crs="EPSG:3067"))

    age = pd.to_numeric(stands.get("meanage"), errors="coerce")
    old = stands[age >= old_stand_age_min_years]
    if len(old):
        parts.append(gpd.GeoDataFrame(
            {"node_type": "old_stand", "geometry": old.geometry.values},
            crs="EPSG:3067"))

    if not parts:
        return gpd.GeoDataFrame({"node_type": [], "geometry": []}, crs="EPSG:3067")
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:3067")


def _clc_resistance_lut(landcover_resistance: dict) -> np.ndarray:
    """256-length lookup: SYKE CLC pixel value -> [0,1] resistance term."""
    default = float(np.mean(list(landcover_resistance.values())))
    lut = np.full(256, default, dtype="float32")
    for value, category in _CLC_CATEGORY.items():
        lut[value] = float(landcover_resistance[category])
    return lut


def resistance_surface(
    stands: gpd.GeoDataFrame,
    clc_path: str,
    grid_path: str,
    cfg_res: dict,
) -> tuple[np.ndarray, dict]:
    """Movement-cost surface on `grid_path`'s grid. Four terms, each normalised
    to [0,1] (0 = best habitat, 1 = worst) and combined by the config weights:

    - age:       1 - min(meanage / age_cap, 1)          old forest -> 0
    - structure: 1 - min(basalarea / ba_cap, 1)         closed stand -> 0
    - species:   1 - min(proportionother / decid_ref, 1) deciduous -> 0
    - landcover: a CLC-category lookup (config)

    The three stand terms come from rasterised Metsakeskus stand polygons; where
    a stand value is missing (off stand land, or a null attribute) that term
    falls back to the land-cover term. The blended [0,1] surface is rescaled to
    [scale_min, scale_max]; water cells are then overwritten with
    `water_resistance` (a near-absolute barrier). Returns (float32 array,
    write_profile).

    Every constant is in config `module_f_connectivity.resistance` - this is
    the surface F3 sweeps for the "robust set"."""
    import rasterio
    from rasterio.features import rasterize
    from rasterio.warp import Resampling, reproject

    w = cfg_res["weights"]
    with rasterio.open(grid_path) as g:
        transform, crs = g.transform, g.crs
        shape = (g.height, g.width)
        profile = g.profile

    with rasterio.open(clc_path) as src:
        classes = np.zeros(shape, dtype="int16")
        reproject(src.read(1).astype("int16"), classes,
                  src_transform=src.transform, src_crs=src.crs,
                  dst_transform=transform, dst_crs=crs,
                  resampling=Resampling.nearest, src_nodata=src.nodata, dst_nodata=0)
    f_lc = _clc_resistance_lut(cfg_res["landcover_resistance"])[classes.clip(0, 255)]

    def _term(col, cap, invert_ref=None):
        vals = pd.to_numeric(stands[col], errors="coerce").to_numpy()
        shp = [(geom, float(v)) for geom, v in zip(stands.geometry, vals)
               if geom is not None and np.isfinite(v)]
        arr = rasterize(shp, out_shape=shape, transform=transform,
                        fill=np.nan, dtype="float32") if shp else np.full(shape, np.nan, "float32")
        ref = invert_ref if invert_ref is not None else cap
        term = 1.0 - np.clip(arr / ref, 0.0, 1.0)
        return np.where(np.isnan(arr), f_lc, term)

    f_age = _term("meanage", cfg_res["age_cap_years"])
    f_struct = _term("basalarea", cfg_res["basal_area_cap_m2_ha"])
    f_species = _term("proportionother", None, invert_ref=cfg_res["deciduous_share_ref"])

    r01 = (w["age"] * f_age + w["structure"] * f_struct
           + w["species"] * f_species + w["landcover"] * f_lc)
    lo, hi = cfg_res["scale_min"], cfg_res["scale_max"]
    resistance = lo + r01 * (hi - lo)

    water = np.isin(classes, np.array(_CLC_GROUPS["water"], dtype="int16"))
    resistance = np.where(water, cfg_res["water_resistance"], resistance)

    out_profile = dict(profile, dtype="float32", nodata=0.0, count=1)
    return resistance.astype("float32"), out_profile


# ----------------------------------------------------------------------------
# F3 - least-cost connectivity
# ----------------------------------------------------------------------------

def _coarsen(resistance_path: str, factor: int, water_resistance: float):
    """Average-resample the resistance raster by an integer factor. Cells whose
    coarse average exceeds half the water value are snapped back to the water
    barrier so lakes stay impassable after smoothing. Returns (array,
    transform, crs)."""
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(resistance_path) as src:
        h, w = src.height // factor, src.width // factor
        arr = src.read(1, out_shape=(h, w), resampling=Resampling.average).astype("float64")
        transform = src.transform * src.transform.scale(src.width / w, src.height / h)
        crs = src.crs
    arr = np.where(arr > water_resistance / 2.0, water_resistance, np.clip(arr, 1e-3, None))
    return arr, transform, crs


def build_patches(nodes: gpd.GeoDataFrame, *, merge_buffer_m: float = 200.0,
                  min_area_ha: float = 0.5) -> gpd.GeoDataFrame:
    """Dissolve the F1 node polygons into connected patches: buffer out by
    `merge_buffer_m`, union, buffer back, explode to single polygons, keep
    those >= `min_area_ha`. A `patch_id` and `area_ha` column are added."""
    merged = nodes.geometry.buffer(merge_buffer_m).union_all().buffer(-merge_buffer_m)
    patches = gpd.GeoDataFrame(geometry=gpd.GeoSeries(merged, crs=nodes.crs)).explode(
        index_parts=False).reset_index(drop=True)
    patches["area_ha"] = patches.geometry.area / 1e4
    patches = patches[patches["area_ha"] >= min_area_ha].reset_index(drop=True)
    patches["patch_id"] = np.arange(len(patches))
    return patches[["patch_id", "area_ha", "geometry"]]


def patch_least_cost(patches: gpd.GeoDataFrame, coarse_arr: np.ndarray, transform):
    """One least-cost (MCP_Geometric) accumulation per patch across the coarse
    resistance grid. Returns (cost_matrix, cost_fields):

    - cost_matrix[i, j] = minimum accumulated cost from patch i to any cell of
      patch j (symmetrised by min), inf if unreachable
    - cost_fields[patch_id] = the full accumulated-cost array from that patch
    """
    from rasterio.features import rasterize
    from skimage.graph import MCP_Geometric

    shape = coarse_arr.shape
    n = len(patches)
    labels = rasterize([(g, int(i) + 1) for i, g in zip(patches["patch_id"], patches.geometry)],
                       out_shape=shape, transform=transform, fill=0, dtype="int32")

    cost_fields = {}
    raw = np.full((n, n), np.inf)
    for pid in patches["patch_id"]:
        starts = np.argwhere(labels == pid + 1)
        if not len(starts):
            continue
        mcp = MCP_Geometric(coarse_arr)
        cum, _ = mcp.find_costs([tuple(s) for s in starts])
        cost_fields[int(pid)] = cum
        for jid in patches["patch_id"]:
            if jid == pid:
                raw[pid, jid] = 0.0
                continue
            cells = labels == jid + 1
            if cells.any():
                raw[pid, jid] = float(np.nanmin(cum[cells]))
    cost_matrix = np.minimum(raw, raw.T)
    return cost_matrix, cost_fields


def patch_dpc(cost_matrix: np.ndarray, areas: np.ndarray, *, dispersal_cost: float,
              landscape_area: float | None = None) -> tuple[np.ndarray, float]:
    """Probability of Connectivity (Saura & Pascual-Hortal 2007) and each
    patch's dPC - the percentage drop in PC if that patch were removed.
    `p_ij = exp(-cost_ij / dispersal_cost)`, with the max-product path replaced
    here by the direct pairwise term (adequate at this patch count)."""
    p = np.exp(-cost_matrix / dispersal_cost)
    np.fill_diagonal(p, 1.0)
    a_l = landscape_area if landscape_area is not None else float(areas.sum())

    def _pc(mask):
        a = areas[mask]
        pm = p[np.ix_(mask, mask)]
        return float((np.outer(a, a) * pm).sum() / (a_l ** 2))

    full = np.ones(len(areas), dtype=bool)
    pc_all = _pc(full)
    dpc = np.zeros(len(areas))
    for k in range(len(areas)):
        m = full.copy()
        m[k] = False
        dpc[k] = 100.0 * (pc_all - _pc(m)) / pc_all if pc_all > 0 else 0.0
    return dpc, pc_all


def backbone_edges(cost_matrix: np.ndarray, *, k_nearest: int) -> list[tuple[int, int]]:
    """The connectivity backbone: each patch joined to its `k_nearest`
    lowest-cost (finite, non-self) neighbours, returned as a de-duplicated list
    of undirected `(i, j)` edges with `i < j`. This keeps the corridor map to
    the network's actual skeleton instead of every patch pair."""
    n = cost_matrix.shape[0]
    edges = set()
    for i in range(n):
        row = cost_matrix[i].copy()
        row[i] = np.inf
        order = np.argsort(row)
        taken = 0
        for j in order:
            if not np.isfinite(row[j]):
                break
            edges.add((min(i, j), max(i, j)))
            taken += 1
            if taken >= k_nearest:
                break
    return sorted(edges)


def corridor_density(cost_fields: dict, cost_matrix: np.ndarray, areas: np.ndarray,
                     shape: tuple, edges: list[tuple[int, int]], *,
                     dispersal_cost: float, slack: float) -> np.ndarray:
    """Accumulated least-cost-corridor density over the given `edges` (patch
    pairs, e.g. from `backbone_edges`). Each corridor is the set of cells with
    `cost_i + cost_j <= min(cost_i + cost_j) * (1 + slack)`, added weighted by
    `a_i a_j exp(-cost_ij / dispersal_cost)`."""
    density = np.zeros(shape, dtype="float64")
    for a, b in edges:
        if a not in cost_fields or b not in cost_fields:
            continue
        c = cost_matrix[a, b]
        if not np.isfinite(c):
            continue
        wt = areas[a] * areas[b] * np.exp(-c / dispersal_cost)
        corr = cost_fields[a] + cost_fields[b]
        finite = np.isfinite(corr)
        if not finite.any():
            continue
        thresh = corr[finite].min() * (1.0 + slack)
        density[finite & (corr <= thresh)] += wt
    return density.astype("float32")


def per_stand_corridor_score(stands: gpd.GeoDataFrame, density: np.ndarray,
                             transform) -> np.ndarray:
    """Mean corridor density under each stand polygon (zonal mean on the coarse
    grid) - the per-stand connectivity-priority score. One rasterisation of all
    stands (burn value = row index + 1) plus a labelled `scipy.ndimage.mean`.
    Stands covering no coarse cell get 0."""
    from rasterio.features import rasterize
    from scipy import ndimage

    n = len(stands)
    labels = rasterize(
        ((g, i + 1) for i, g in enumerate(stands.geometry) if g is not None),
        out_shape=density.shape, transform=transform, fill=0, dtype="int32")
    present = np.unique(labels)
    present = present[present > 0]
    out = np.zeros(n, dtype="float64")
    if len(present):
        means = ndimage.mean(density, labels, index=present)
        out[present - 1] = means
    return out
