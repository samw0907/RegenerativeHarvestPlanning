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
