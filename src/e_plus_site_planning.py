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


def ccf_rootrot_conflict(stands: gpd.GeoDataFrame, cfg_ccf: dict, cfg_d3: dict) -> dict:
    """Overlay of the Plus CCF-on-peatland prescription and the D3 root-rot
    species/soil trigger. The two pull in opposite directions: Plus keeps
    spruce as continuous cover on these sites, while high Heterobasidion risk
    argues against perpetuating spruce there through repeated CCF entries
    (successive fellings on connected root systems spread butt rot more than a
    single clearcut followed by a species change would).

    Reuses D3's `species_soil_rule` unchanged. Because the CCF filter already
    requires spruce-dominated peat and the peat-soil root-rot trigger is
    "spruce share >= 0.5", the overlap is expected to be near-total by
    construction - that near-totality is the finding, not a coincidence: the
    prescription targets exactly the stand type the root-rot rule also covers."""
    from src.d3_rootrot_rules import is_peat_soil, species_soil_rule

    area_ha = pd.to_numeric(stands["area"], errors="coerce").fillna(0.0).to_numpy()
    ccf = select_ccf_peatland(stands, cfg_ccf).to_numpy()

    peat = is_peat_soil(stands["soiltype"])
    pine = pd.to_numeric(stands["proportionpine"], errors="coerce").fillna(0.0).to_numpy()
    spruce = pd.to_numeric(stands["proportionspruce"], errors="coerce").fillna(0.0).to_numpy()
    rootrot = np.asarray(species_soil_rule(peat, pine, spruce, cfg_d3), dtype=bool)

    conflict = ccf & rootrot
    ccf_ha = float(area_ha[ccf].sum())
    conflict_ha = float(area_ha[conflict].sum())
    return {
        "ccf_eligible_ha": round(ccf_ha, 1),
        "ccf_eligible_and_rootrot_trigger_ha": round(conflict_ha, 1),
        "conflict_share_of_ccf_eligible": round(conflict_ha / ccf_ha, 3) if ccf_ha else None,
        "n_conflict_stands": int(conflict.sum()),
    }


def conflict_free_felling_window(daily_weather: pd.DataFrame, cfg_d3: dict) -> dict:
    """Days per winter that are both trafficable on wet peat - frozen ground,
    D2's `frozen_ground_days` proxy - and outside the root-rot mandatory
    stump-treatment period (1 May - 30 Nov, D3's `in_mandatory_period`). This
    is the window in which a CCF-eligible lush drained spruce peatland stand
    can be felled without hitting either the bearing-capacity limit or the
    treatment obligation.

    One figure for the whole CCF-eligible set, not per stand: those stands are
    all peat/drained/spruce/lush within one AOI served by one FMI station, and
    the mandatory period is a fixed national calendar, so there is nothing
    per-stand to resolve. "Workable" is taken here as "frozen" only - the plan
    frames CCF felling on these wet stands as a winter operation, and D2's peat
    bearing penalty makes the summer dry-DTW route unavailable in practice.

    Winters are attributed Jul->Jun so one winter's frozen days are not split
    across two calendar years; partial winters at the record ends are dropped.
    """
    from src.d2_dtw_extend import frozen_ground_days
    from src.d3_rootrot_rules import in_mandatory_period

    frozen = frozen_ground_days(daily_weather).to_numpy()
    in_period = np.asarray(in_mandatory_period(daily_weather.index, cfg_d3), dtype=bool)
    window = frozen & ~in_period

    idx = daily_weather.index
    winter_year = np.where(idx.month >= 7, idx.year, idx.year - 1)
    df = pd.DataFrame({"window": window, "winter_year": winter_year})
    per_winter = df.groupby("winter_year")["window"].sum()
    days_in_group = df.groupby("winter_year")["window"].size()
    per_winter = per_winter[days_in_group >= 350]  # drop partial winters at the ends

    decade = (per_winter.index // 10) * 10
    by_decade = per_winter.groupby(decade).mean().round(1)
    return {
        "per_winter_days": {int(k): int(v) for k, v in per_winter.items()},
        "by_decade_mean_days": {int(k): float(v) for k, v in by_decade.items()},
        "first_decade_mean": float(by_decade.iloc[0]),
        "last_decade_mean": float(by_decade.iloc[-1]),
    }


def habitat_proximity(
    stands: gpd.GeoDataFrame,
    habitats: gpd.GeoDataFrame,
    setback_widths_m: list[float],
) -> list[dict]:
    """Per setback width: the count and stand area within that distance of a
    Forest Act §10 valuable-habitat polygon, plus the split by the nearest
    habitat's `habitattype`.

    Distance to the nearest habitat is one STRtree-backed `sjoin_nearest` pass;
    a stand overlapping a habitat gets distance 0. The type split is by the
    *nearest* habitat only - a stand close to two habitat types is attributed
    to the closer one - so the per-type figures sum to the total but do not
    double-count. Reported for all stands, since a §10 setback binds whenever
    that stand is harvested, not only where a cutting is currently proposed."""
    left = stands[["geometry"]].copy()
    left["_row"] = np.arange(len(left))
    joined = gpd.sjoin_nearest(
        left, habitats[["habitattype", "geometry"]], how="left", distance_col="dist_m")
    joined = joined.sort_values("dist_m").drop_duplicates("_row").set_index("_row")
    joined = joined.reindex(np.arange(len(stands)))

    area_ha = pd.to_numeric(stands["area"], errors="coerce").fillna(0.0).to_numpy()
    dist = joined["dist_m"].to_numpy()
    htype = pd.to_numeric(joined["habitattype"], errors="coerce").to_numpy()
    types = sorted(int(t) for t in np.unique(htype[~np.isnan(htype)]))

    results = []
    for w in setback_widths_m:
        within = dist <= w
        row = {
            "setback_m": w,
            "n_stands_within": int(np.count_nonzero(within)),
            "stand_area_ha_within": round(float(area_ha[within].sum()), 1),
        }
        for t in types:
            m = within & (htype == t)
            row[f"stand_area_ha_nearest_habtype_{t}"] = round(float(area_ha[m].sum()), 1)
        results.append(row)
    return results


def ls_factor(
    slope_deg_path: str | Path,
    flow_accum_cells_path: str | Path,
    *,
    exponent_m: float = 0.4,
    exponent_n: float = 1.3,
    specific_area_cap_m: float = 100.0,
) -> tuple[np.ndarray, dict]:
    """RUSLE LS (slope-length x steepness) via the Moore & Burch (1986)
    unit-stream-power form:

        LS = (A_s / 22.13) ** m  *  (sin theta / 0.0896) ** n

    A_s is the specific catchment area - upslope contributing area per unit
    contour width, in metres - taken as (flow-accumulation cells x cell size).
    It is capped at `specific_area_cap_m`: RUSLE LS describes hillslope wash,
    not channel flow, and an uncapped A_s makes near-channel cells diverge.

    Reads the two rasters D1 already produced for the catchment
    (`slope_deg.tif`, `dinf_accum_cells.tif`); they must share one grid.
    Returns (ls_float32_array, write_profile). LS is 0 on nodata cells."""
    import rasterio

    with rasterio.open(slope_deg_path) as s_src:
        slope_deg = s_src.read(1).astype("float64")
        s_nodata = s_src.nodata
        profile = s_src.profile
        cell = abs(s_src.transform.a)
    with rasterio.open(flow_accum_cells_path) as a_src:
        accum = a_src.read(1).astype("float64")
        a_nodata = a_src.nodata

    valid = np.ones(slope_deg.shape, dtype=bool)
    if s_nodata is not None:
        valid &= slope_deg != s_nodata
    if a_nodata is not None:
        valid &= accum != a_nodata

    sin_theta = np.sin(np.deg2rad(np.clip(slope_deg, 0.0, None)))
    a_s = np.minimum(np.clip(accum, 0.0, None) * cell, specific_area_cap_m)

    with np.errstate(invalid="ignore", divide="ignore"):
        ls_all = (a_s / 22.13) ** exponent_m * (sin_theta / 0.0896) ** exponent_n
    ls = np.where(valid, np.nan_to_num(ls_all, nan=0.0, posinf=0.0, neginf=0.0), 0.0)

    out_profile = dict(profile, dtype="float32", nodata=0.0, count=1)
    return ls.astype("float32"), out_profile


def k_factor(
    stands: gpd.GeoDataFrame,
    grid_path: str | Path,
    k_by_soiltype: dict,
    *,
    k_default: float = 0.025,
) -> np.ndarray:
    """RUSLE K raster on `grid_path`'s grid, from the Metsakeskus stand
    polygons' `soiltype` code via the config lookup. Cells not covered by any
    stand polygon get `k_default` (stand data is private-forest only; the K
    surface still needs a value everywhere the benchmark covers).

    Proper K comes from soil texture, which the open data does not carry - this
    is a class-mean approximation keyed on the one distinction Metsakeskus
    `soiltype` does make (coarse till / sorted coarse / fine mineral / stony /
    rock / peat / erosion-sensitive peat / organic). See docs/MODULE_E_NOTES.md
    E5b."""
    from rasterio.features import rasterize

    lut = {int(k): float(v) for k, v in k_by_soiltype.items()}
    codes = pd.to_numeric(stands["soiltype"], errors="coerce").round()
    kvals = codes.map(lut).fillna(k_default).to_numpy()

    with rasterio.open(grid_path) as src:
        transform, shape = src.transform, (src.height, src.width)

    shapes = [(geom, float(k)) for geom, k in zip(stands.geometry, kvals) if geom is not None]
    if not shapes:
        return np.full(shape, k_default, dtype="float32")
    return rasterize(shapes, out_shape=shape, transform=transform,
                     fill=k_default, dtype="float32")


def stand_coverage_mask(stands: gpd.GeoDataFrame, grid_path: str | Path) -> np.ndarray:
    """Boolean raster on `grid_path`'s grid, True where a Metsakeskus stand
    polygon exists. The RUSLE benchmark is compared only on these cells - off
    stand land the K factor is a flat default, so `A` there is not a real
    derivation."""
    from rasterio.features import rasterize

    with rasterio.open(grid_path) as src:
        transform, shape = src.transform, (src.height, src.width)
    geoms = [(g, 1) for g in stands.geometry if g is not None]
    if not geoms:
        return np.zeros(shape, dtype=bool)
    return rasterize(geoms, out_shape=shape, transform=transform,
                     fill=0, dtype="uint8").astype(bool)


def c_factor(
    clc_path: str | Path,
    grid_path: str | Path,
    c_by_clc: dict,
    *,
    c_default: float = 0.01,
) -> np.ndarray:
    """RUSLE C raster on `grid_path`'s grid, from a SYKE CLC2018 raster.

    The CLC class raster is nearest-resampled onto the target grid (categorical,
    so nearest keeps class edges sharp), then each pixel's SYKE class value is
    mapped to a C value via the config lookup; unlisted values fall to
    `c_default`. Forest classes get a very low C, recent-clearcut / transitional
    woodland a higher one, water 0. See docs/MODULE_E_NOTES.md E5c."""
    import rasterio
    from rasterio.warp import Resampling, reproject

    with rasterio.open(grid_path) as g:
        dst_transform, dst_crs = g.transform, g.crs
        dst_shape = (g.height, g.width)
    with rasterio.open(clc_path) as src:
        src_arr = src.read(1)
        src_transform, src_crs, src_nodata = src.transform, src.crs, src.nodata

    classes = np.zeros(dst_shape, dtype=src_arr.dtype)
    reproject(src_arr, classes, src_transform=src_transform, src_crs=src_crs,
              dst_transform=dst_transform, dst_crs=dst_crs,
              resampling=Resampling.nearest, src_nodata=src_nodata, dst_nodata=0)

    lut = np.full(256, c_default, dtype="float32")
    for code, cval in c_by_clc.items():
        lut[int(code)] = float(cval)
    return lut[classes.astype(np.intp)]


def assemble_rusle(
    ls: np.ndarray,
    k: np.ndarray,
    c: np.ndarray,
    *,
    r_factor: float,
    p_factor: float = 1.0,
) -> np.ndarray:
    """RUSLE annual soil loss `A = R * K * LS * C * P` (t/ha/yr), element-wise
    over three factor grids that must share a shape. R is a scalar constant
    (see the R decision in docs/MODULE_E_NOTES.md E5), P is 1 for forestry
    (no support practices). Returns float32."""
    a = float(r_factor) * float(p_factor) * (
        np.asarray(k, "float64") * np.asarray(ls, "float64") * np.asarray(c, "float64"))
    return a.astype("float32")


def _resample_onto(src_path, dst_transform, dst_crs, dst_shape):
    import rasterio
    from rasterio.warp import Resampling, reproject

    with rasterio.open(src_path) as src:
        out = np.zeros(dst_shape, dtype="float64")
        reproject(src.read(1).astype("float64"), out,
                  src_transform=src.transform, src_crs=src.crs,
                  dst_transform=dst_transform, dst_crs=dst_crs,
                  src_nodata=src.nodata, dst_nodata=np.nan,
                  resampling=Resampling.average)
    return out


def rusle_benchmark(
    our_a_path: str | Path,
    mk_rusle_path: str | Path,
    stand_coverage_path: str | Path,
    *,
    also_compare: dict | None = None,
) -> dict:
    """Compare our RUSLE `A` against Metsakeskus's `RUSLE-eroosiomalli` on the
    cells where both are defined and a stand polygon exists (off stand land our
    K, hence A, is a flat default). Metsakeskus's grid is resampled onto ours.

    Reports Spearman (rank) and log-space Pearson correlation and the median
    value ratio. `also_compare` maps label -> raster path (e.g. {"LS": path})
    to run the same comparison for a single factor - the route by which E5e
    found the Metsakeskus product tracks LS and carries no C signal.

    Both sides derive from the same NLS 2 m DEM, so terrain agreement is
    expected and is not independent validation (Project 1 lesson)."""
    import rasterio
    from scipy.stats import pearsonr, spearmanr

    with rasterio.open(our_a_path) as a_src:
        a = a_src.read(1).astype("float64")
        transform, crs, shape = a_src.transform, a_src.crs, (a_src.height, a_src.width)
    with rasterio.open(stand_coverage_path) as c_src:
        cover = c_src.read(1).astype(bool)

    mk = _resample_onto(mk_rusle_path, transform, crs, shape)

    def _stats(x, label):
        m = cover & np.isfinite(x) & np.isfinite(mk) & (x > 0) & (mk > 0)
        n = int(m.sum())
        if n < 100:
            return {"label": label, "n": n}
        xs, ms = x[m], mk[m]
        return {
            "label": label, "n": n,
            "spearman_r": round(float(spearmanr(xs, ms).correlation), 3),
            "pearson_log_r": round(float(pearsonr(np.log1p(xs), np.log1p(ms))[0]), 3),
            "median_ratio_mk_over_x": round(float(np.median(ms / np.maximum(xs, 1e-9))), 1),
        }

    out = {"our_A": _stats(a, "our_A")}
    for label, path in (also_compare or {}).items():
        out[label] = _stats(_resample_onto(path, transform, crs, shape), label)
    return out
