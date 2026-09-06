# regenerative-harvest-planning/fi_forest_data/syke.py
"""SYKE (Finnish Environment Institute) data.

New to this repo - Project 1 did not use SYKE. GeoServer WFS is disabled on
almost every SYKE workspace (confirmed TASK 00); use the direct download tree
at wwwd3.ymparisto.fi instead, reading zipped shapefiles via
`/vsizip//vsicurl/` so a single-feature query does not download the whole
archive (confirmed live, 2026-09-05: the server sends `Accept-Ranges: bytes`,
and GDAL's vsicurl uses that to read only what a layer listing / attribute
filter needs).

Routes (docs/DATA_SOURCES.md section 7):
- `d3/gis_data/spesific/valumaalueet.zip` (259 MB) - Valuma-aluejako watershed
  hierarchy. Confirmed live: layers `Valumaaluejako_taso{1..5}` +
  `_purkupiste` (outlets); taso4 has 22,274 features, CRS is ETRS-TM35FIN
  (EPSG:3067, PROJCS has no top-level EPSG authority tag in the source but the
  parameters match exactly - `fetch_catchment` sets it explicitly). The
  catchment id field is `taso4_osat` (e.g. `"FI1-14.06.161"`, the pinned D1
  validation catchment - confirmed its polygon area is 148.22 km2, matching
  the plan, and its bounds match `config/pipeline.yaml`'s bbox exactly).
- `d3/gis_data/spesific/luonnonsuojelualueet_valtio.zip` (state protected areas,
  `LsAlueValtio.shp`), `_yksityinen.zip` (private, `LsAlueYks.shp`),
  `natura.zip` (`natura2000sac_alueet.shp`, `natura2000spa_alueet.shp`) - Module F
  connectivity nodes. Not yet implemented.
- `d3/Static_rs/spesific/clc2018_fi20m.zip` - CORINE Land Cover 2018, 20 m
  GeoTIFF (273 MB). Module E RUSLE C-factor. TASK 00 D4 resolved 2026-09-06:
  no CLC2024/2021/2020 at this route (checked live), CLC2018 is the latest.
  The raster carries SYKE's own 49-class national scheme in the pixel values
  (not the CLC Level-3 codes); the class legend is in the zip's `.tif.vat.dbf`.
  CRS is declared EPSG:25835 (ETRS89 / UTM 35N) - coordinate-identical to
  EPSG:3067 (same datum, projection and parameters), so `fetch_clc` assigns
  3067 for downstream consistency rather than warping.

Public interface:
    fetch_catchment(catchment_id, level="taso4") -> gpd.GeoDataFrame   # done
    fetch_clc(aoi, year=2018) -> str                 # path to the AOI-window GeoTIFF

Planned, not yet implemented:
    fetch_protected_areas(aoi) -> gpd.GeoDataFrame   # state + private + Natura, merged
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import geopandas as gpd

_VALUMA_URL = "https://wwwd3.ymparisto.fi/d3/gis_data/spesific/valumaalueet.zip"
_ID_FIELD = {"taso4": "taso4_osat", "taso5": "taso5_osat"}

_CLC_URL = {2018: "https://wwwd3.ymparisto.fi/d3/Static_rs/spesific/clc2018_fi20m.zip"}
_CLC_TIF = {2018: "Clc2018_FI20m.tif"}


def fetch_catchment(catchment_id: str, *, level: str = "taso4",
                    cache_dir: str | Path = "data/raw", force: bool = False) -> gpd.GeoDataFrame:
    """One Valuma-aluejako catchment polygon by its taso4/taso5 code.

    Reads the single matching feature via /vsizip//vsicurl/ (no full download
    of the 259 MB source), caches it as a small GeoPackage, and returns it as a
    one-row GeoDataFrame in EPSG:3067.
    """
    if level not in _ID_FIELD:
        raise KeyError(f"level must be one of {sorted(_ID_FIELD)}, got {level!r}")

    cache_dir = Path(cache_dir)
    safe_id = catchment_id.replace("/", "_")
    out = cache_dir / "syke" / f"catchment_{level}_{safe_id}.gpkg"
    if out.exists() and not force:
        return gpd.read_file(out)

    field = _ID_FIELD[level]
    url = f"/vsizip//vsicurl/{_VALUMA_URL}"
    gdf = gpd.read_file(url, layer=f"Valumaaluejako_{level}",
                        where=f"{field} = '{catchment_id}'")
    if gdf.empty:
        raise RuntimeError(f"no {level} catchment matched id {catchment_id!r}")
    gdf = gdf.set_crs("EPSG:3067", allow_override=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out, driver="GPKG")
    return gdf


def fetch_clc(aoi, *, year: int = 2018, cache_dir: str | Path = "data/raw",
              force: bool = False) -> str:
    """CORINE Land Cover for the AOI bbox, as a local GeoTIFF.

    Reads the AOI window out of SYKE's national 20 m raster via
    /vsizip//vsicurl/ (the server sends `Accept-Ranges: bytes`, so the 273 MB
    zip is not downloaded whole) and writes just that window to a cached
    GeoTIFF. Pixel values are SYKE's 49-class national scheme (see the module
    docstring). CRS is set to EPSG:3067 - the source declares the
    coordinate-identical EPSG:25835.
    """
    import rasterio
    from rasterio.windows import from_bounds

    if year not in _CLC_URL:
        raise KeyError(f"year must be one of {sorted(_CLC_URL)}, got {year}")

    cache_dir = Path(cache_dir)
    out = cache_dir / "syke" / f"clc{year}_{aoi.name}.tif"
    if out.exists() and not force:
        return str(out)

    src_path = f"/vsizip//vsicurl/{_CLC_URL[year]}/{_CLC_TIF[year]}"
    minx, miny, maxx, maxy = aoi.bbox_3067
    with rasterio.open(src_path) as src:
        window = from_bounds(minx, miny, maxx, maxy, src.transform)
        data = src.read(1, window=window)
        transform = src.window_transform(window)
        profile = dict(src.profile, height=data.shape[0], width=data.shape[1],
                       transform=transform, crs="EPSG:3067", driver="GTiff")

    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(data, 1)
    out.with_suffix(".meta.json").write_text(json.dumps({
        "source": _CLC_URL[year], "layer": _CLC_TIF[year], "year": year,
        "aoi": aoi.name, "aoi_bbox_3067": list(aoi.bbox_3067),
        "shape": [int(x) for x in data.shape], "fetch_date": date.today().isoformat(),
    }, indent=2), encoding="utf-8")
    return str(out)
