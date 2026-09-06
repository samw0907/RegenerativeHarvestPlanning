# regenerative-harvest-planning/fi_forest_data/metsakeskus.py
"""Metsakeskus (Finnish Forest Centre) open forest and nature data.

GeoServer WFS 2.0.0, one feature type per URL path, EPSG:3067 native. This module
fetches vector layers (stands, forest use declarations, forest mask, habitat, grid
cells) as GeoDataFrames, with startIndex/count paging and a local GeoPackage cache
in data/raw/. Each fetch writes a .meta.json sidecar recording the endpoint,
typeName, WFS version and fetch date.

Routes and field notes: docs/DATA_SOURCES.md section 1. Coded values decode via
the KOOD V35 workbook (see docs/DATA_SOURCES.md).
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import geopandas as gpd
import requests

BASE = "https://avoin.metsakeskus.fi/rajapinnat"
WFS_VERSION = "2.0.0"
CRS = "EPSG:3067"
_SRS_URI = "urn:ogc:def:crs:EPSG::3067"
_PAGE = 10000  # GeoServer CountDefault for this service
_TIMEOUT = 180
_RETRIES = 3
_UA = "finnish-forest-analytics/0.1 (portfolio pipeline; contact via github.com/samw0907)"

# layer_key -> (url path segment, WFS typeName)
LAYERS = {
    "stand": ("v2/stand", "v2:stand"),
    "forestusedeclaration": ("v1/forestusedeclaration", "forestusedeclaration"),
    "forestmask": ("v2/forestmask", "v2:forestmask"),
    "habitat": ("v2/habitat", "v2:habitat"),
    "gridcell": ("v2/gridcell", "v2:gridcell"),
}


def _bbox_param(bbox_3067) -> str:
    minx, miny, maxx, maxy = bbox_3067
    return f"{minx},{miny},{maxx},{maxy},{_SRS_URI}"


def _get_json(session: requests.Session, url: str, params: dict) -> dict:
    last_exc = None
    for attempt in range(1, _RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict) and payload.get("type") == "ExceptionReport":
                raise RuntimeError(f"WFS exception: {json.dumps(payload)[:400]}")
            return payload
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_exc = exc
            if attempt < _RETRIES:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Metsakeskus WFS request failed after {_RETRIES} tries: {last_exc}")


def _paged_features(session: requests.Session, url: str, base_params: dict, page: int = _PAGE):
    """Yield GeoJSON feature dicts across startIndex/count pages."""
    start = 0
    while True:
        params = dict(base_params, count=page, startIndex=start)
        fc = _get_json(session, url, params)
        feats = fc.get("features", [])
        yield from feats
        if len(feats) < page:
            return
        start += page


def _cache_paths(cache_dir: Path, layer_key: str, aoi_name: str):
    stem = cache_dir / "metsakeskus" / f"{layer_key}__{aoi_name}"
    return stem.with_suffix(".gpkg"), stem.with_suffix(".meta.json")


def fetch_layer(
    layer_key: str,
    aoi,
    *,
    cache_dir: str | Path = "data/raw",
    force: bool = False,
    session: requests.Session | None = None,
) -> gpd.GeoDataFrame:
    """Fetch a Metsakeskus WFS vector layer for the AOI as an EPSG:3067 GeoDataFrame.

    Caches to {cache_dir}/metsakeskus/{layer_key}__{aoi.name}.gpkg and returns the
    cache on repeat calls unless force=True.
    """
    if layer_key not in LAYERS:
        raise KeyError(f"unknown layer_key {layer_key!r}; known: {sorted(LAYERS)}")
    path_seg, type_name = LAYERS[layer_key]
    cache_dir = Path(cache_dir)
    gpkg, meta = _cache_paths(cache_dir, layer_key, aoi.name)

    if gpkg.exists() and not force:
        return gpd.read_file(gpkg)

    url = f"{BASE}/{path_seg}/ows"
    base_params = {
        "service": "WFS",
        "version": WFS_VERSION,
        "request": "GetFeature",
        "typeNames": type_name,
        "srsName": _SRS_URI,
        "bbox": _bbox_param(aoi.bbox_3067),
        "outputFormat": "application/json",
    }
    own_session = session is None
    session = session or requests.Session()
    if own_session:
        session.headers.update({"User-Agent": _UA})

    try:
        feats = list(_paged_features(session, url, base_params))
    finally:
        if own_session:
            session.close()

    if not feats:
        gdf = gpd.GeoDataFrame(geometry=[], crs=CRS)
    else:
        gdf = gpd.GeoDataFrame.from_features(feats, crs=CRS)
        if gdf.crs is None or gdf.crs.to_epsg() != 3067:
            gdf = gdf.set_crs(CRS, allow_override=True)

    gpkg.parent.mkdir(parents=True, exist_ok=True)
    if len(gdf):
        gdf.to_file(gpkg, driver="GPKG")
    meta.write_text(
        json.dumps(
            {
                "source": "metsakeskus",
                "endpoint": url,
                "typeName": type_name,
                "wfs_version": WFS_VERSION,
                "crs": CRS,
                "aoi_name": aoi.name,
                "aoi_bbox_3067": list(aoi.bbox_3067),
                "feature_count": int(len(gdf)),
                "fetch_date": date.today().isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return gdf


def fetch_raster(coverage: str, aoi, *, cache_dir: str | Path = "data/raw",
                 tile_km: float = 3.0, force: bool = False) -> str:
    """A Metsakeskus WCS 2.0.1 coverage for the AOI bbox, as one local GeoTIFF.

    `coverage` is the WCS layer name (e.g. "RUSLE-eroosiomalli"); the coverage
    id is `v1__<coverage>`. A whole-AOI GetCoverage times out on the server
    (504), so the bbox is split into tile_km x tile_km tiles fetched
    individually and mosaicked. EPSG:3067 throughout.
    """
    import math

    import rasterio
    from rasterio.merge import merge

    cache_dir = Path(cache_dir)
    out = cache_dir / "metsakeskus" / f"{coverage}__{aoi.name}.tif"
    if out.exists() and not force:
        return str(out)

    base = f"{BASE}/v1/{coverage}/wcs"
    minx, miny, maxx, maxy = aoi.bbox_3067
    step = tile_km * 1000.0
    nx = max(1, math.ceil((maxx - minx) / step))
    ny = max(1, math.ceil((maxy - miny) / step))

    tile_dir = cache_dir / "metsakeskus" / f"_{coverage}_tiles_{aoi.name}"
    tile_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": _UA})
    tile_paths = []
    try:
        for i in range(nx):
            for j in range(ny):
                tminx, tmaxx = minx + i * step, min(minx + (i + 1) * step, maxx)
                tminy, tmaxy = miny + j * step, min(miny + (j + 1) * step, maxy)
                tpath = tile_dir / f"tile_{i}_{j}.tif"
                if not tpath.exists() or force:
                    params = {
                        "service": "WCS", "version": "2.0.1", "request": "GetCoverage",
                        "coverageId": f"v1__{coverage}", "format": "image/tiff",
                        "subset": [f"E({tminx},{tmaxx})", f"N({tminy},{tmaxy})"],
                    }
                    resp = session.get(base, params=params, timeout=_TIMEOUT)
                    resp.raise_for_status()
                    if resp.content[:2] not in (b"II", b"MM"):
                        raise RuntimeError(
                            f"WCS {coverage} tile {i},{j} did not return a TIFF: "
                            f"{resp.content[:200]!r}")
                    tpath.write_bytes(resp.content)
                tile_paths.append(tpath)
    finally:
        session.close()

    srcs = [rasterio.open(p) for p in tile_paths]
    mosaic, transform = merge(srcs)
    profile = dict(srcs[0].profile, height=mosaic.shape[1], width=mosaic.shape[2],
                   transform=transform, driver="GTiff")
    for s in srcs:
        s.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(mosaic)
    out.with_suffix(".meta.json").write_text(json.dumps({
        "source": base, "coverage_id": f"v1__{coverage}", "wcs_version": "2.0.1",
        "aoi": aoi.name, "aoi_bbox_3067": [minx, miny, maxx, maxy],
        "n_tiles": len(tile_paths), "tile_km": tile_km,
        "shape": [int(x) for x in mosaic.shape[1:]],
        "fetch_date": date.today().isoformat(),
    }, indent=2), encoding="utf-8")
    return str(out)


_KEMERA_URL = ("https://avoin.metsakeskus.fi/aineistot/Kemera/Maakunta/"
               "Kemera_{region}.zip")
_KEMERA_ENV_LAYER = "application_stand_11_90"  # Kemera nature-management / ymparistotuki polygons (workcode 641)


def fetch_kemera_environmental(aoi, *, region: str = "Keski-Suomi",
                               cache_dir: str | Path = "data/raw",
                               force: bool = False):
    """Environmental-support / forest-nature-management polygons (ymparistotuki)
    for the AOI, from the Metsakeskus Kemera regional GeoPackage.

    `region` is the maakunta name in the download path (default "Keski-Suomi",
    the Project 2 AOI's region). The layer is `application_stand_11_90` -
    workcode 641, the only Kemera layer carrying `environmentmanagementtype`.
    The 156 MB zip is downloaded once and cached; then the layer is read with a
    bbox filter and clipped to the AOI. EPSG:3067.
    """
    import zipfile

    import geopandas as gpd

    cache_dir = Path(cache_dir)
    zip_path = cache_dir / "metsakeskus" / f"kemera_{region}.zip"
    out = cache_dir / "metsakeskus" / f"kemera_env_{aoi.name}.gpkg"
    if out.exists() and not force:
        return gpd.read_file(out)

    if not zip_path.exists() or force:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        session = requests.Session()
        session.headers.update({"User-Agent": _UA})
        resp = session.get(_KEMERA_URL.format(region=region), timeout=600)
        resp.raise_for_status()
        zip_path.write_bytes(resp.content)
        session.close()

    with zipfile.ZipFile(zip_path) as zf:
        gpkg_name = next(n for n in zf.namelist() if n.endswith(".gpkg"))
        extract_dir = cache_dir / "metsakeskus" / f"kemera_{region}"
        zf.extract(gpkg_name, extract_dir)
    gpkg = extract_dir / gpkg_name

    gdf = gpd.read_file(gpkg, layer=_KEMERA_ENV_LAYER, bbox=aoi.bbox_3067)
    gdf = gdf.set_crs("EPSG:3067", allow_override=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out, driver="GPKG")
    out.with_suffix(".meta.json").write_text(json.dumps({
        "source": _KEMERA_URL.format(region=region), "layer": _KEMERA_ENV_LAYER,
        "region": region, "aoi": aoi.name, "aoi_bbox_3067": list(aoi.bbox_3067),
        "n_features": int(len(gdf)), "fetch_date": date.today().isoformat(),
    }, indent=2), encoding="utf-8")
    return gdf
