# regenerative-harvest-planning/src/e_plus_site_planning.py
"""Module E - Metsa Group Plus site planning.

Turns the quantified Plus measures into a per-stand site plan:
- Waterway buffers (10/20/30 m) on a full-AOI derived channel network, compared
  against buffers from mapped hydrography alone (NLS topographic database) to
  quantify the additional area captured by streams mapped hydrography omits.
- Peatland continuous-cover prescription: lush, drained, spruce-dominated peat
  stands (site fertility, drainage status, spruce share - all in MS-NFI /
  Metsakeskus stand data), quantified against the +30% continuous-cover-share
  target.
- Retention and deadwood deficit against the gap to 30 retention trees/ha
  (>15 cm dbh), 20 dead trees/ha, 10 high-biodiversity stumps/ha. **Decision D2
  resolved** (docs/TASK_00_FINDINGS.md, docs/MODULE_E_NOTES.md 2.1): no
  per-stand or per-pixel deadwood source exists anywhere in the open data
  (confirmed live - MS-NFI has no deadwood theme, Metsakeskus's own
  `deadwoodpotential` habitat field is null across the D1 catchment and covers
  under 0.1% of it regardless). Deadwood is reported as one aggregate Luke VMI
  regional statistic against the AOI's total forest area, not a per-stand
  deficit map; retention trees and stumps stay flat legal-target constants.
- Valuable §10 habitat proximity and required setbacks.
- The conflict overlay: D3's root-rot risk vs the peatland continuous-cover
  prescription (CCF is best done in winter and discouraged under high root-rot
  risk) - surface the stands where the two disagree, do not average over it.

**Channel network: full AOI, 16 m, D8 - not D1's 2 m D-infinity.** D1's DTW
reimplementation is DERIVE AND BENCHMARK (Luke's DTW raster is the full-AOI
product to consume once validated) and stays at the 148 km2 catchment. Waterway
buffers need an actual vector stream network, which Luke does not publish -
DERIVE ONLY, so it must cover the real AOI (docs/MODULE_E_NOTES.md 2.2).
D-infinity has no single-direction pointer, so WhiteboxTools'
`raster_streams_to_vector` (which needs one to trace connected line topology)
requires D8 - used consistently here for the pointer, the accumulation, and the
threshold, rather than mixing flow algorithms within one derivation. D8 is
Tarboton/O'Callaghan & Mark's own classical routing algorithm, the same
documented-method tier as D-infinity, not a new class of method.

Data tiers: §10 habitats and mapped hydrography FETCH; RUSLE erosion risk DERIVE
AND BENCHMARK against Metsakeskus's own RUSLE (state this as agreement, not
independent validation, from the first draft - both derive from the same NLS
DEM; see the Project 1 lesson in the plan doc). Channel network, buffers and the
deficit gap DERIVE ONLY.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from src.d1_dtw_derive import _run, _wbt

_HA_TO_M2 = 10_000.0


def cells_for_distance(distance_m: float, resolution_m: float) -> int:
    """A physical distance in metres, converted to a whole number of cells at
    the given resolution (minimum 1) - used to keep search-radius-style
    WhiteboxTools parameters (e.g. breach distance) comparable in real terms
    across DEMs of different resolutions, rather than reusing a raw cell count
    that meant something different at D1's 2 m."""
    return max(1, round(distance_m / resolution_m))


def prepare_flow_accumulation(
    dem_path: str | Path,
    *,
    work_dir: str | Path = "data/interim/e",
    breach_dist_m: float = 2000.0,
    force: bool = False,
) -> tuple[Path, float]:
    """BreachDepressionsLeastCost (Lindsay 2016) -> D8Pointer -> D8FlowAccumulation,
    computed once and shared across every threshold in `extract_channel_network` -
    only the cheap extract/vectorise steps are threshold-dependent, so deriving
    several waterway-class thresholds does not mean re-running this each time.

    Returns (work_dir, cell_area_m2). Skips recomputation if the accumulation
    raster already exists in `work_dir`, unless `force`.
    """
    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    dem_path = Path(dem_path).resolve()

    with rasterio.open(dem_path) as src:
        res_x = abs(src.transform.a)
        res_y = abs(src.transform.e)
    cell_area_m2 = res_x * res_y

    accum_path = work_dir / "d8_accum_cells.tif"
    if accum_path.exists() and not force:
        return work_dir, cell_area_m2

    wbt = _wbt(work_dir)
    breach_dist_cells = cells_for_distance(breach_dist_m, res_x)

    _run(wbt, "breach_depressions_least_cost", expect_output="dem_breached.tif",
         dem=str(dem_path), output="dem_breached.tif", dist=breach_dist_cells, fill=True)

    _run(wbt, "d8_pointer", expect_output="d8_pointer.tif",
         dem="dem_breached.tif", output="d8_pointer.tif")

    _run(wbt, "d8_flow_accumulation", expect_output="d8_accum_cells.tif",
         i="d8_pointer.tif", output="d8_accum_cells.tif", out_type="cells", pntr=True)

    return work_dir, cell_area_m2


def extract_channel_network(
    dem_path: str | Path,
    threshold_ha: float,
    *,
    work_dir: str | Path = "data/interim/e",
    breach_dist_m: float = 2000.0,
) -> gpd.GeoDataFrame:
    """Full-AOI stream vector network at one channel-initiation threshold
    (a waterway size class - smaller threshold_ha = more inclusive network).

    Calls `prepare_flow_accumulation` (a no-op if already done in `work_dir`),
    then ExtractStreams at `threshold_ha` -> RasterStreamsToVector. Returns the
    line network as a GeoDataFrame in the DEM's own CRS (WhiteboxTools'
    shapefile output does not always carry a .prj, so the CRS is set
    explicitly from the source raster, not assumed).
    """
    work_dir, cell_area_m2 = prepare_flow_accumulation(
        dem_path, work_dir=work_dir, breach_dist_m=breach_dist_m)
    wbt = _wbt(work_dir)
    with rasterio.open(dem_path) as src:
        crs = src.crs

    threshold_cells = threshold_ha * _HA_TO_M2 / cell_area_m2
    stream_file = f"streams_{threshold_ha}ha.tif"
    _run(wbt, "extract_streams", expect_output=stream_file,
         flow_accum="d8_accum_cells.tif", output=stream_file, threshold=threshold_cells)

    vector_file = f"streams_{threshold_ha}ha.shp"
    _run(wbt, "raster_streams_to_vector", expect_output=vector_file,
         streams=stream_file, d8_pntr="d8_pointer.tif", output=vector_file)

    lines = gpd.read_file(work_dir / vector_file)
    lines = lines.set_crs(crs, allow_override=True)
    return lines


def rasterize_lines(lines: gpd.GeoDataFrame, grid_path: str | Path) -> np.ndarray:
    """A line GeoDataFrame burned onto `grid_path`'s exact grid (same transform
    and shape), 1 where a line touches a cell, 0 elsewhere. `all_touched=True`
    so a line does not skip a cell it clips only at a corner - appropriate here
    since the output feeds a distance transform, not an area count in its own
    right."""
    from rasterio.features import rasterize

    with rasterio.open(grid_path) as src:
        transform, shape = src.transform, (src.height, src.width)
    if lines.empty:
        return np.zeros(shape, dtype="uint8")
    return rasterize(
        [(geom, 1) for geom in lines.geometry if geom is not None],
        out_shape=shape, transform=transform, fill=0, dtype="uint8", all_touched=True,
    )


def distance_to_features_m(mask: np.ndarray, resolution_m: float) -> np.ndarray:
    """Euclidean distance in metres from each cell to the nearest True cell in
    `mask` (a square-celled grid at `resolution_m`)."""
    from scipy.ndimage import distance_transform_edt

    mask = mask.astype(bool)
    if not mask.any():
        return np.full(mask.shape, np.inf, dtype="float64")
    return distance_transform_edt(~mask) * resolution_m


def buffer_comparison(
    derived_lines: gpd.GeoDataFrame,
    mapped_lines: gpd.GeoDataFrame,
    grid_path: str | Path,
    buffer_widths_m: list[float],
) -> list[dict]:
    """For each buffer width: area (ha) within that distance of the derived
    channel network, of mapped hydrography, and the *additional* area the
    derived network's buffer covers that mapped hydrography's does not - the
    "hectares of buffer that mapped hydrography misses" figure the plan names
    as a concrete water-protection output.

    Rasterised and computed as a distance-transform threshold rather than
    buffering and unioning vector polygons: at 378k+ derived-network line
    segments (see docs/MODULE_E_NOTES.md E1b), a vector union at this feature
    count is a well-known performance cliff for GEOS-backed buffering, and the
    only thing actually needed here is an area figure, not buffer polygon
    geometry - matching the raster-first approach already used throughout this
    project's other surfaces (DTW, wetness).
    """
    with rasterio.open(grid_path) as src:
        res_x = abs(src.transform.a)
        res_y = abs(src.transform.e)
    cell_area_ha = res_x * res_y / _HA_TO_M2

    derived_dist = distance_to_features_m(rasterize_lines(derived_lines, grid_path), res_x)
    mapped_dist = distance_to_features_m(rasterize_lines(mapped_lines, grid_path), res_x)

    results = []
    for width in buffer_widths_m:
        derived_buf = derived_dist <= width
        mapped_buf = mapped_dist <= width
        additional = derived_buf & ~mapped_buf
        results.append({
            "buffer_width_m": width,
            "derived_buffer_ha": round(float(derived_buf.sum() * cell_area_ha), 1),
            "mapped_buffer_ha": round(float(mapped_buf.sum() * cell_area_ha), 1),
            "additional_ha": round(float(additional.sum() * cell_area_ha), 1),
        })
    return results


def select_ccf_peatland(stands: gpd.GeoDataFrame, cfg_ccf: dict) -> pd.Series:
    """Boolean mask over `stands`: the Plus "lush drained spruce-dominated
    peatland" prescription category - peat soil, lush-to-mesic fertility, a
    drained-mire transformation stage (ojikko/muuttuma/turvekangas), and
    spruce-dominated by volume share. All four attributes are read straight
    from the Metsakeskus stand layer (`soiltype`, `fertilityclass`,
    `drainagestate`, `proportionspruce`), same field conventions as D3."""
    soiltype = pd.to_numeric(stands["soiltype"], errors="coerce")
    fertility = pd.to_numeric(stands["fertilityclass"], errors="coerce")
    drainage = pd.to_numeric(stands["drainagestate"], errors="coerce")
    spruce = pd.to_numeric(stands["proportionspruce"], errors="coerce")
    return (
        (soiltype >= cfg_ccf["peat_soiltype_min"])
        & (fertility <= cfg_ccf["fertility_class_max"])
        & (drainage.isin(cfg_ccf["drained_states"]))
        & (spruce >= cfg_ccf["spruce_share_min"])
    ).fillna(False)


def ccf_area_summary(stands: gpd.GeoDataFrame, cfg_ccf: dict) -> dict:
    """Area breakdown for the CCF-on-peatland prescription across the AOI:
    total stand area, peatland forest, drained peatland forest, and the
    CCF-eligible area (the full four-way filter), each in hectares, plus the
    eligible area at the stricter fertility <= 2 ("reheva" proper) cut so the
    fertility-band choice's sensitivity is on the table rather than hidden.

    "+30% share of CCF in peatland forest regeneration" (Plus 2030 target) is a
    relative increase against an unpublished baseline, so this does not report
    "% of target met" - it quantifies the addressable area (how much
    regeneration felling the prescription would redirect from clearcut to CCF
    if applied supply-area-wide), which is the plan's "physical implication
    across one mill's supply area" framing."""
    area_ha = pd.to_numeric(stands["area"], errors="coerce").fillna(0.0)
    soiltype = pd.to_numeric(stands["soiltype"], errors="coerce")
    drainage = pd.to_numeric(stands["drainagestate"], errors="coerce")

    peat = soiltype >= cfg_ccf["peat_soiltype_min"]
    drained_peat = peat & drainage.isin(cfg_ccf["drained_states"])
    eligible = select_ccf_peatland(stands, cfg_ccf)
    eligible_strict = select_ccf_peatland(stands, {**cfg_ccf, "fertility_class_max": 2})

    total = float(area_ha.sum())

    def _ha(mask):
        return round(float(area_ha[mask.to_numpy()].sum()), 1)

    drained_peat_ha = _ha(drained_peat)
    elig_ha = _ha(eligible)
    return {
        "n_stands": int(len(stands)),
        "total_stand_area_ha": round(total, 1),
        "peatland_forest_ha": _ha(peat),
        "drained_peatland_forest_ha": drained_peat_ha,
        "ccf_eligible_ha": elig_ha,
        "ccf_eligible_strict_fertility_ha": _ha(eligible_strict),
        "ccf_eligible_pct_of_drained_peatland": (
            round(100 * elig_ha / drained_peat_ha, 1) if drained_peat_ha else None),
        "ccf_eligible_pct_of_total_forest": (
            round(100 * elig_ha / total, 1) if total else None),
    }
