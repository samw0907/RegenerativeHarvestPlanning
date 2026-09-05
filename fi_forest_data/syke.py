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
  GeoTIFF. Check for a CLC2024 release at Project 2 start (TASK 00 D4, open).
  Module E RUSLE C-factor. Not yet implemented.

Public interface:
    fetch_catchment(catchment_id, level="taso4") -> gpd.GeoDataFrame   # done

Planned, not yet implemented:
    fetch_protected_areas(aoi) -> gpd.GeoDataFrame   # state + private + Natura, merged
    fetch_clc(aoi, year=2018) -> str                 # path to a windowed COG
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd

_VALUMA_URL = "https://wwwd3.ymparisto.fi/d3/gis_data/spesific/valumaalueet.zip"
_ID_FIELD = {"taso4": "taso4_osat", "taso5": "taso5_osat"}


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
