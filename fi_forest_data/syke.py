# regenerative-harvest-planning/fi_forest_data/syke.py
"""SYKE (Finnish Environment Institute) data.

New to this repo - Project 1 did not use SYKE. GeoServer WFS is disabled on
almost every SYKE workspace (confirmed TASK 00); use the direct download tree
at wwwd3.ymparisto.fi instead, reading zipped shapefiles/GeoTIFFs via
`/vsizip//vsicurl/` where a full download is not needed (the watershed file is
259 MB; the AOI's sub-catchments are a small fraction of it).

Routes (docs/DATA_SOURCES.md section 7):
- `d3/gis_data/spesific/luonnonsuojelualueet_valtio.zip` (state protected areas,
  `LsAlueValtio.shp`), `_yksityinen.zip` (private, `LsAlueYks.shp`),
  `natura.zip` (`natura2000sac_alueet.shp`, `natura2000spa_alueet.shp`) - Module F
  connectivity nodes.
- `d3/Static_rs/spesific/clc2018_fi20m.zip` - CORINE Land Cover 2018, 20 m
  GeoTIFF. Check for a CLC2024 release at Project 2 start (TASK 00 D4, open).
  Module E RUSLE C-factor.
- `d3/gis_data/spesific/valumaalueet.zip` - Valuma-aluejako watershed hierarchy
  (taso1-5 + outlets), incl. the pinned D1 validation catchment `FI1-14.06.161`.

Public interface (planned):
    fetch_protected_areas(aoi) -> gpd.GeoDataFrame   # state + private + Natura, merged
    fetch_clc(aoi, year=2018) -> str                 # path to a windowed COG
    fetch_catchment(catchment_id) -> gpd.GeoDataFrame  # one taso4/5 polygon by id

No implementation yet - scaffold only.
"""
