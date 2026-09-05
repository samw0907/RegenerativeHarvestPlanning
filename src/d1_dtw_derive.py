# regenerative-harvest-planning/src/d1_dtw_derive.py
"""Module D1 - reimplement depth-to-water, and benchmark it.

On the validation catchment (SYKE FI1-14.06.161, 148 km2): breach remaining
pits (Lindsay 2016), route flow and delineate channels with D-infinity
(Tarboton 1997) at 0.5/1/2/4/10 ha, then compute each cell's elevation above
the nearest downslope channel cell - a direct proxy for "depth to water" as a
modelled water-table height, which is the physical quantity DTW represents.
Compare against Luke DTW 2023 CMv2 (D8 flow routing, breaching pit-removal;
units: theirs is centimetres, ours is metres).

**Tool choice corrected after a first attempt failed a sanity check
(2026-09-05).** The first version used WhiteboxTools' `DownslopeDistanceToStream`
(horizontal flow-path distance to the nearest channel cell). That produced
values 30-40x larger than Luke's product (median 50 m vs Luke's 1.6 m at the
0.5 ha threshold) with only weak correlation (r ~ 0.4-0.47) - checked and
confirmed the fault was not D-infinity-specific (D8 mode gave the same
inflation) nor fixable by adding a slope floor to an isotropic cost-distance
(WhiteboxTools `CostDistance`; tested floors from 0.5 deg to 5 deg, all made it
worse). The root issue: horizontal distance-to-channel is the wrong physical
quantity - DTW approximates a *water-table height*, which `ElevationAboveStream`
(the vertical elevation drop to the nearest downslope channel cell) is a much
closer match to by construction. Re-tested and it agrees well (see D1c in
docs/MODULE_D_NOTES.md): r = 0.62-0.87 rising with threshold, bias only
+2.2 to +2.8 m, comparable medians. This is the metric used below.

Implementation is WhiteboxTools (Lindsay's own toolbox - the pit-breaching
algorithm it ships, BreachDepressionsLeastCost, is literally Lindsay 2016):
BreachDepressionsLeastCost -> DInfFlowAccumulation -> per-threshold streams
raster -> ElevationAboveStream. Two known simplifications, flagged not hidden:
(1) `ElevationAboveStream` has no D-infinity/D8 option - it uses WhiteboxTools'
own internal downslope-tracing rule, so D-infinity governs where the channel
network is (via DInfFlowAccumulation) but not the exact within-cell trace to
it. (2) it takes one DEM for both routing and elevation, so this uses the
breached (conditioned) DEM throughout rather than sourcing elevation from the
unmodified surface as the plan's wording specifies - a shallow least-cost
breach changes few cells, so the effect should be small.

Data tiers: 2 m DEM DERIVE input; Luke DTW 2023 CMv2 DERIVE AND BENCHMARK
reference, fetched at AOI scale after the validation-catchment comparison earns
it (three-tier rule - do not reprocess the full AOI at 2 m for no reason;
Project 1's Module A stopped short of this AOI-scale step, learn from that).

Culvert-burning (lowering the DEM at road/stream crossings) is deferred - see
docs/MODULE_D_NOTES.md D1c - and is not in this first pass.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.mask import mask as rio_mask

_HA_TO_M2 = 10_000.0


def clip_dem_to_catchment(dem_path: str | Path, catchment_gdf, out_path: str | Path) -> str:
    """Mask the DEM mosaic to the true (non-rectangular) catchment polygon."""
    out_path = Path(out_path)
    with rasterio.open(dem_path) as src:
        geom = [catchment_gdf.geometry.iloc[0].__geo_interface__]
        arr, transform = rio_mask(src, geom, crop=True, nodata=src.nodata)
        profile = src.profile
    profile.update(height=arr.shape[1], width=arr.shape[2], transform=transform)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(arr)
    return str(out_path)


def _wbt(work_dir: Path, verbose: bool = False):
    import whitebox

    wbt = whitebox.WhiteboxTools()
    # the working dir is passed to an external whitebox_tools.exe process, so it
    # must be absolute - a relative path resolves against that process's own
    # cwd, not Python's, and silently produces no output file.
    wbt.set_working_dir(str(Path(work_dir).resolve()))
    wbt.verbose = verbose
    return wbt


def _run(wbt, fn_name: str, *, expect_output: str, **kwargs) -> None:
    ret = getattr(wbt, fn_name)(**kwargs)
    out_file = Path(wbt.work_dir) / expect_output
    if ret != 0 or not out_file.exists():
        raise RuntimeError(
            f"WhiteboxTools {fn_name} failed (return code {ret}, "
            f"output exists: {out_file.exists()}): {out_file}"
        )


def reimplement_dtw(
    dem_path: str | Path,
    thresholds_ha: list[float],
    *,
    work_dir: str | Path = "data/interim/d1",
    breach_dist_cells: int = 1000,
) -> dict[float, str]:
    """Reimplement DTW on an already-catchment-clipped DEM, one file per threshold.

    Returns {threshold_ha: path_to_our_dtw_tif}. All work happens in work_dir
    (WhiteboxTools is a CLI wrapper and needs file paths, not in-memory arrays).
    """
    work_dir = Path(work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    wbt = _wbt(work_dir)

    dem_path = Path(dem_path).resolve()
    _run(wbt, "breach_depressions_least_cost", expect_output="dem_breached.tif",
         dem=str(dem_path), output="dem_breached.tif", dist=breach_dist_cells, fill=True)

    accum = work_dir / "dinf_accum_cells.tif"
    _run(wbt, "d_inf_flow_accumulation", expect_output="dinf_accum_cells.tif",
         i="dem_breached.tif", output="dinf_accum_cells.tif", out_type="cells")

    with rasterio.open(accum) as src:
        acc = src.read(1)
        acc_nodata = src.nodata
        profile = src.profile
        res_x = abs(src.transform.a)
        res_y = abs(src.transform.e)
    cell_area_m2 = res_x * res_y

    out_paths = {}
    for th in thresholds_ha:
        th_cells = th * _HA_TO_M2 / cell_area_m2
        streams = (acc >= th_cells).astype("uint8")
        if acc_nodata is not None:
            streams[acc == acc_nodata] = 0
        stream_prof = dict(profile, dtype="uint8", nodata=0, count=1)
        stream_file = work_dir / f"streams_{th}ha.tif"
        with rasterio.open(stream_file, "w", **stream_prof) as dst:
            dst.write(streams, 1)

        out_name = f"our_dtw_{th}ha.tif"
        _run(wbt, "elevation_above_stream", expect_output=out_name,
             dem="dem_breached.tif", streams=stream_file.name, output=out_name)
        out_paths[th] = str(work_dir / out_name)

    return out_paths


def compare_to_reference(our_path: str | Path, luke_path: str | Path,
                         *, luke_unit_scale: float = 0.01,
                         our_nodata: float | None = None,
                         spearman_sample: int = 200_000, seed: int = 0) -> dict:
    """Agreement stats between our DTW and Luke's, on the shared valid extent.

    luke_unit_scale converts Luke's raw values to metres (2023 CMv2 is
    centimetres, so 0.01). Returns Pearson r, Spearman rank r (subsampled -
    Spearman is O(n log n) per call and these rasters run to tens of millions
    of pixels), bias (ours - Luke), RMSE, and the n of pixels compared.
    """
    from scipy.stats import spearmanr

    with rasterio.open(our_path) as s1, rasterio.open(luke_path) as s2:
        if s1.shape != s2.shape:
            raise ValueError(f"shape mismatch: ours {s1.shape} vs Luke {s2.shape}")
        ours = s1.read(1).astype("float64")
        luke = s2.read(1).astype("float64") * luke_unit_scale
        nod1 = our_nodata if our_nodata is not None else s1.nodata
        nod2 = s2.nodata

    ok = np.isfinite(ours) & np.isfinite(luke)
    if nod1 is not None:
        ok &= ours != nod1
    if nod2 is not None:
        ok &= (luke != nod2 * luke_unit_scale)
    a, b = ours[ok], luke[ok]
    if a.size == 0:
        return {"n": 0, "r": None, "spearman_r": None, "bias": None, "rmse": None}
    err = a - b
    r = float(np.corrcoef(a, b)[0, 1]) if a.size > 1 else None
    rng = np.random.default_rng(seed)
    idx = rng.choice(a.size, size=min(spearman_sample, a.size), replace=False)
    spear = float(spearmanr(a[idx], b[idx]).correlation) if a.size > 1 else None
    return {
        "n": int(a.size),
        "r": round(r, 3) if r is not None else None,
        "spearman_r": round(spear, 3) if spear is not None else None,
        "bias_ours_minus_luke_m": round(float(err.mean()), 3),
        "rmse_m": round(float(np.sqrt(np.mean(err ** 2))), 3),
        "median_ours_m": round(float(np.median(a)), 2),
        "median_luke_m": round(float(np.median(b)), 2),
    }
