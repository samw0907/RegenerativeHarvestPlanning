# regenerative-harvest-planning/fi_forest_data/nls.py
"""National Land Survey of Finland (Maanmittauslaitos, NLS) data.

Two routes (docs/DATA_SOURCES.md section 4):
- Funet/CSC mirror (no key): 2 m DEM, topographic database, 2008-2019 legacy laser.
- NLS file service, OGC API Processes
  (avoin-paikkatieto.maanmittauslaitos.fi/tiedostopalvelu/ogcproc/v1/): the
  2020+ open 0.5 p laser scanning product. Needs the free NLS_API_KEY.

This module implements the NLS file-service route: execute a process, poll the
job, download the result files. The API key is read via fi_forest_data.config and
is never logged or written to any output.

Copied from boreal-stand-intelligence. This repo has no ALS use, so `fetch_als`
is unused (kept for parity - do not build against it). `fetch_dem` is
load-bearing for Module D1 but `korkeusmalli_2m_bbox` caps at 100 km2 per
request; `fetch_dem_tiled` wraps it (splits the AOI into <=100 km2 tiles, each
individually cached, mosaics with rasterio.merge) for the D1 validation
catchment (148 km2) and the full AOI (3,400 km2).
`fetch_topographic` is the stub Module E's mapped-hydrography comparison needs;
not yet implemented.
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import requests

from fi_forest_data.config import get_secret

BASE = "https://avoin-paikkatieto.maanmittauslaitos.fi/tiedostopalvelu/ogcproc/v1"
_UA = "finnish-forest-analytics/0.1 (portfolio pipeline; github.com/samw0907)"
_POLL_EVERY = 10
_POLL_TIMEOUT = 1800  # 30 min


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Accept": "application/json"})
    return s


def _params(extra: dict | None = None) -> dict:
    p = {"api-key": get_secret("NLS_API_KEY")}
    if extra:
        p.update(extra)
    return p


def run_process(process_id: str, inputs: dict, *, session: requests.Session | None = None) -> list[dict]:
    """Execute an NLS file-service process, wait for it, return the output file records.

    Each record is {"fileName": ..., "url": ..., ...} from the job's jsonOutput.
    """
    own = session is None
    session = session or _session()
    try:
        # NLS requires the process id in the body as well as the URL path
        r = session.post(
            f"{BASE}/processes/{process_id}/execution",
            params=_params(), json={"id": process_id, "inputs": inputs}, timeout=120,
        )
        if r.status_code not in (200, 201, 202):
            raise RuntimeError(f"NLS execute {process_id}: HTTP {r.status_code} {r.text[:300]}")
        job = r.json()
        job_id = job.get("jobID") or job.get("jobId") or job.get("id")
        if not job_id:
            # synchronous response already carries results
            return _extract_files(job)

        deadline = time.time() + _POLL_TIMEOUT
        while time.time() < deadline:
            time.sleep(_POLL_EVERY)
            jr = session.get(f"{BASE}/jobs/{job_id}", params=_params(), timeout=60)
            jr.raise_for_status()
            status = jr.json().get("status")
            if status == "successful":
                res = session.get(f"{BASE}/jobs/{job_id}/results", params=_params(), timeout=60)
                res.raise_for_status()
                return _extract_files(res.json())
            if status in ("failed", "dismissed"):
                raise RuntimeError(f"NLS job {job_id} {status}: {jr.text[:400]}")
        raise TimeoutError(f"NLS job {job_id} not finished after {_POLL_TIMEOUT}s")
    finally:
        if own:
            session.close()


def _extract_files(payload: dict) -> list[dict]:
    """Normalise a job-results payload to a list of {fileName, url} records.

    NLS returns `results: [{"path": <url>, "format": ..., "length": ...}, ...]`
    plus a trailing `{"zipPath": <url>}` record (skipped - we take the files).
    """
    results = payload.get("results", payload)
    files = []
    for rec in results if isinstance(results, list) else []:
        url = rec.get("path")
        if not url:
            continue  # skip the zipPath aggregate record
        files.append({
            "fileName": url.rstrip("/").split("/")[-1],
            "url": url,
            "format": rec.get("format"),
            "length": int(rec["length"]) if rec.get("length") else None,
        })
    if not files:
        raise RuntimeError(f"no downloadable files in NLS result: {json.dumps(payload)[:400]}")
    return files


def _download(session: requests.Session, url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    with session.get(url, params=_params(), stream=True, timeout=1800) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
        tmp.replace(dest)
    return dest


def fetch_dem(aoi, *, resolution_m: int = 2, cache_dir: str | Path = "data/raw", force: bool = False) -> str:
    """2 m DEM GeoTIFF for the AOI bbox via `korkeusmalli_2m_bbox` (<= 100 km2)."""
    if resolution_m != 2:
        raise NotImplementedError("only the 2 m DEM is wired up")
    cache_dir = Path(cache_dir)
    out_dir = cache_dir / "nls" / f"dem2m_{aoi.name}"
    done = out_dir / "_files.json"
    if done.exists() and not force:
        recs = json.loads(done.read_text())
        return str(out_dir / recs[0]["fileName"])

    minx, miny, maxx, maxy = aoi.bbox_3067
    if (maxx - minx) * (maxy - miny) / 1e6 > 100:
        raise ValueError("korkeusmalli_2m_bbox caps at 100 km2; split the request")
    session = _session()
    try:
        recs = run_process("korkeusmalli_2m_bbox", {
            "boundingBoxInput": [minx, miny, maxx, maxy],
            "fileFormatInput": "TIFF",
        }, session=session)
        for rec in recs:
            _download(session, rec["url"], out_dir / rec["fileName"])
    finally:
        session.close()
    done.write_text(json.dumps(recs, indent=2))
    _write_meta(out_dir, "korkeusmalli_2m_bbox", aoi, recs)
    return str(out_dir / recs[0]["fileName"])


def fetch_dem_tiled(aoi, *, resolution_m: int = 2, cache_dir: str | Path = "data/raw",
                    tile_km: float = 9.0, force: bool = False) -> str:
    """2 m DEM mosaic for an AOI larger than the 100 km2 `fetch_dem` cap.

    Splits the AOI bbox into a grid of tile_km x tile_km tiles (default 9 km =
    81 km2, safely under the cap), fetches each with `fetch_dem` (so each tile
    is individually cached - a re-run after a partial failure only re-fetches
    what is missing), and mosaics them into one GeoTIFF covering the full AOI
    bbox. Needed for the D1 validation catchment (148 km2) and the full AOI
    (3,400 km2); use plain `fetch_dem` directly for anything <= 100 km2.
    """
    import math
    from dataclasses import replace as _replace

    import rasterio
    from rasterio.merge import merge

    cache_dir = Path(cache_dir)
    out = cache_dir / "nls" / f"dem2m_mosaic_{aoi.name}.tif"
    if out.exists() and not force:
        return str(out)

    minx, miny, maxx, maxy = aoi.bbox_3067
    step = tile_km * 1000.0
    nx = max(1, math.ceil((maxx - minx) / step))
    ny = max(1, math.ceil((maxy - miny) / step))

    tile_paths = []
    for i in range(nx):
        for j in range(ny):
            tminx, tmaxx = minx + i * step, min(minx + (i + 1) * step, maxx)
            tminy, tmaxy = miny + j * step, min(miny + (j + 1) * step, maxy)
            tile_aoi = _replace(aoi, name=f"{aoi.name}_tile_{i}_{j}",
                                bbox_3067=(tminx, tminy, tmaxx, tmaxy))
            tile_paths.append(fetch_dem(tile_aoi, resolution_m=resolution_m,
                                        cache_dir=cache_dir, force=force))

    srcs = [rasterio.open(p) for p in tile_paths]
    mosaic, transform = merge(srcs)
    profile = srcs[0].profile
    profile.update(height=mosaic.shape[1], width=mosaic.shape[2],
                   transform=transform, dtype=mosaic.dtype)
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(mosaic)
    for s in srcs:
        s.close()

    meta = out.with_suffix(".meta.json")
    meta.write_text(json.dumps({
        "source": "korkeusmalli_2m_bbox (NLS OGC API Processes, tiled)",
        "n_tiles": len(tile_paths), "tile_km": tile_km,
        "aoi": aoi.name, "aoi_bbox_3067": [minx, miny, maxx, maxy],
        "shape": [int(x) for x in mosaic.shape],
        "fetch_date": date.today().isoformat(),
    }, indent=2), encoding="utf-8")
    return str(out)


def resample_dem(src_path, out_path, *, target_resolution_m: float) -> str:
    """Downsample a DEM GeoTIFF to a coarser resolution by block averaging.

    Averaging is the physically appropriate reduction for elevation (unlike
    nearest, which would just pick one corner cell); GDAL's average resampling
    respects the source nodata mask. Used for Module E's full-AOI channel-
    network derivation, which runs coarser than D1's validated 2 m catchment
    work - see docs/MODULE_E_NOTES.md section 2.2 for why.
    """
    import rasterio
    from rasterio.enums import Resampling

    src_path = Path(src_path)
    out_path = Path(out_path)
    with rasterio.open(src_path) as src:
        scale = target_resolution_m / src.res[0]
        if scale <= 1:
            raise ValueError(
                f"target_resolution_m ({target_resolution_m}) must be coarser "
                f"than the source resolution ({src.res[0]})")
        new_width = max(1, round(src.width / scale))
        new_height = max(1, round(src.height / scale))
        data = src.read(
            out_shape=(src.count, new_height, new_width),
            resampling=Resampling.average,
        )
        new_transform = src.transform * src.transform.scale(
            src.width / new_width, src.height / new_height)
        profile = src.profile.copy()
        profile.update(height=new_height, width=new_width, transform=new_transform)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data)
    return str(out_path)


def mapsheets_for_bbox(bbox_3067, *, session: requests.Session, cache_dir: Path,
                       layer: str = "utm5") -> list[str]:
    """Map-sheet codes intersecting the bbox, from `karttalehtijako_koko_suomi` (cached).

    Default `utm5` = the 3 km sheets the 0.5 p laser tiles use (e.g. M5233C1).
    """
    import zipfile

    import geopandas as gpd

    grid_dir = cache_dir / "nls" / "karttalehtijako"
    gpkg = grid_dir / "karttalehtijako.gpkg"
    if not gpkg.exists():
        recs = run_process("karttalehtijako_koko_suomi",
                           {"fileFormatInput": "GPKG", "dataSetInput": "kaikki"}, session=session)
        for rec in recs:
            dl = _download(session, rec["url"], grid_dir / rec["fileName"])
            if dl.suffix.lower() == ".zip":
                with zipfile.ZipFile(dl) as z:
                    z.extractall(grid_dir)
        src = next(iter(grid_dir.rglob("*.gpkg")))
        if src != gpkg:
            src.replace(gpkg)

    g = gpd.read_file(gpkg, layer=layer)
    if g.crs is None or g.crs.to_epsg() != 3067:
        g = g.to_crs(3067)
    sel = g[g.intersects(_box(bbox_3067))]
    if sel.empty:
        raise RuntimeError(f"no {layer} map sheets intersect the bbox")
    return sorted(str(v) for v in sel["lehtitunnus"].dropna().unique())


def _box(bbox):
    from shapely.geometry import box as _b
    return _b(*bbox)


def fetch_als(aoi, *, dataset: str = "05p_2020-", cache_dir: str | Path = "data/raw",
              force: bool = False) -> list[str]:
    """0.5 p LAZ tiles covering the AOI bbox via `laserkeilausaineisto_05_karttalehti`.

    dataset: "05p_2020-" (default), "05p_2008-2019", or "Uusin".
    Returns the local LAZ paths.
    """
    cache_dir = Path(cache_dir)
    out_dir = cache_dir / "nls" / f"als_{aoi.name}"
    done = out_dir / "_files.json"
    if done.exists() and not force:
        recs = json.loads(done.read_text())
        return [str(out_dir / r["fileName"]) for r in recs]

    session = _session()
    try:
        sheets = mapsheets_for_bbox(aoi.bbox_3067, session=session, cache_dir=cache_dir)
        if not sheets:
            raise RuntimeError("no map sheets intersect the AOI bbox")
        if len(sheets) > 100:
            raise ValueError(f"{len(sheets)} sheets > 100/query limit; tile the request")
        recs = run_process("laserkeilausaineisto_05_karttalehti", {
            "mapSheetInput": sheets, "fileFormatInput": "LAZ", "dataSetInput": dataset,
        }, session=session)
        paths = []
        for rec in recs:
            paths.append(str(_download(session, rec["url"], out_dir / rec["fileName"])))
    finally:
        session.close()
    done.write_text(json.dumps(recs, indent=2))
    _write_meta(out_dir, "laserkeilausaineisto_05_karttalehti", aoi, recs, dataset=dataset,
                map_sheets=sheets)
    return paths


def fetch_topographic(theme: str, aoi):
    """Topographic database themes come from the Funet mirror (no key). Wired when P2 needs it."""
    raise NotImplementedError("topographic DB fetch is implemented when Project 2 needs it")


def _write_meta(out_dir: Path, process_id: str, aoi, recs, **extra) -> None:
    (out_dir / "_meta.json").write_text(json.dumps({
        "source": "nls_tiedostopalvelu",
        "process": process_id,
        "endpoint": BASE,
        "aoi_name": aoi.name,
        "aoi_bbox_3067": list(aoi.bbox_3067),
        "n_files": len(recs),
        "files": [r.get("fileName") for r in recs],
        "fetch_date": date.today().isoformat(),
        **extra,
    }, indent=2), encoding="utf-8")
