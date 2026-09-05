# regenerative-harvest-planning/fi_forest_data/luke.py
"""Luke (Natural Resources Institute Finland) data.

MS-NFI (multi-source national forest inventory) rasters: 16 m, EPSG:3067, UInt16,
one whole-Finland GeoTIFF per theme on the Funet mirror. Nodata 32766 (forestry
land without satellite cover) and 32767 (not forestry land or outside country)
have different meanings and must not be collapsed. Copied from
boreal-stand-intelligence; `fetch_msnfi` already scales to this repo's larger
AOI (COG-tiled source, windowed /vsicurl read).

    fetch_msnfi(theme, aoi, year=2023) -> str   # path to a windowed COG for the AOI

`fetch_dtw` - Luke DTW 2023 CMv2 depth-to-water, one channel-initiation
threshold at a time. Delivered as flat directories of 6x6 km tiles named by the
NLS UTM10 mapsheet code (confirmed live, 2026-09-05: `.../DTW_INT_CMv2_{050,1,
2,4,10}/{sheet}.tif`, e.g. `K3222B.tif`) - the same grid `nls.mapsheets_for_bbox`
already resolves, reused here rather than parsing Luke's own tile-index
shapefile. Int16, centimetres (metres x100), nodata 32767. Only 2023 CMv2 is
wired up (TASK 00 decision D3); the 2019 vintage uses millimetres and a
different threshold set, and mixing the two units is the one hard "do not do
this" for this module.

    fetch_dtw(threshold_ha, aoi, year=2023) -> str   # path to a mosaicked COG for the AOI

Routes confirmed in TASK 00, docs/DATA_SOURCES.md sections 2-3.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds

_BASE = "https://www.nic.funet.fi/index/geodata/luke/vmi"
_SUFFIX = {2023: "1923"}          # plot-year span baked into the 2023 product filenames

_DTW_BASE = "https://www.nic.funet.fi/index/geodata/luke/dtw"
_DTW_DIR = {0.5: "050", 1: "1", 2: "2", 4: "4", 10: "10"}   # 2023 CMv2 threshold dirs
DTW_NODATA = 32767

# friendly name -> Funet theme stem
THEMES = {
    "volume": "tilavuus",
    "volume_pine": "manty",
    "volume_spruce": "kuusi",
    "volume_birch": "koivu",
    "volume_other": "muulp",
    "mean_height": "keskipituus",     # decimetres
    "mean_diameter": "keskilapimitta",  # centimetres
    "basal_area": "ppa",              # m2/ha
    "age": "ika",                     # years
    "land_class": "maaluokka",        # 1 forest land, 2 scrub, ...
    "site_fertility": "kasvupaikka",  # site fertility class 1 (rich) .. 8 (poor)
    "canopy_cover": "latvuspeitto",   # %
    "soil_main_type": "paatyyppi",    # 1 kangas (mineral), 2-4 peatland (korpi/rame/letto) - D2 soil term
}

MSNFI_NODATA = (32766, 32767)


def _theme_url(theme: str, year: int) -> str:
    if theme not in THEMES:
        raise KeyError(f"unknown MS-NFI theme {theme!r}; known: {sorted(THEMES)}")
    if year not in _SUFFIX:
        raise KeyError(f"no MS-NFI filename suffix recorded for year {year}")
    return f"{_BASE}/{year}/{THEMES[theme]}_vmi1x_{_SUFFIX[year]}.tif"


def fetch_msnfi(
    theme: str,
    aoi,
    *,
    year: int = 2023,
    cache_dir: str | Path = "data/raw",
    force: bool = False,
) -> str:
    """Window the whole-Finland MS-NFI theme raster to the AOI and cache it as a COG.

    The two nodata codes are preserved (written as 32767 nodata, the 32766 cells
    left in place); callers mask both. Returns the local COG path.
    """
    cache_dir = Path(cache_dir)
    out = cache_dir / "luke" / f"msnfi_{theme}_{year}__{aoi.name}.tif"
    meta = out.with_suffix(".meta.json")
    if out.exists() and not force:
        return str(out)

    url = _theme_url(theme, year)
    minx, miny, maxx, maxy = aoi.bbox_3067
    with rasterio.open(f"/vsicurl/{url}") as src:
        win = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
        arr = src.read(1, window=win)
        wt = src.window_transform(win)
        src_nodata = src.nodata

    profile = {
        "driver": "COG", "crs": "EPSG:3067", "transform": wt,
        "width": arr.shape[1], "height": arr.shape[0], "count": 1,
        "dtype": "uint16", "nodata": 32767, "compress": "deflate",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(arr, 1)
        dst.update_tags(
            attribution="Contains Natural Resources Institute Finland MS-NFI data, CC BY 4.0",
            theme=theme, source_url=url, year=str(year),
        )

    valid = arr[~np.isin(arr, MSNFI_NODATA)]
    meta.write_text(json.dumps({
        "theme": theme, "funet_stem": THEMES[theme], "year": year,
        "source_url": url, "crs": "EPSG:3067", "resolution_m": 16,
        "source_nodata": src_nodata, "nodata_codes": list(MSNFI_NODATA),
        "aoi": aoi.name, "aoi_bbox_3067": [minx, miny, maxx, maxy],
        "shape": list(arr.shape),
        "valid_pixel_stats": {
            "n": int(valid.size),
            "min": int(valid.min()) if valid.size else None,
            "median": float(np.median(valid)) if valid.size else None,
            "max": int(valid.max()) if valid.size else None,
        },
        "fetch_date": date.today().isoformat(),
    }, indent=2), encoding="utf-8")
    return str(out)


def fetch_dtw(
    threshold_ha: float,
    aoi,
    *,
    year: int = 2023,
    cache_dir: str | Path = "data/raw",
    force: bool = False,
) -> str:
    """DTW mosaic for the AOI at one channel-initiation threshold (2023 CMv2).

    Values are centimetres (metres x100), Int16, nodata 32767. Finds the NLS
    UTM10 (6 km) mapsheets intersecting the AOI, downloads each threshold
    directory's `{sheet}.tif` from the Funet mirror, mosaics and crops to the
    AOI bbox exactly. A sheet with no HTTP 200 (edge of the DTW extent, e.g.
    over water or outside Finland) is skipped, not an error.
    """
    import requests
    from rasterio.merge import merge

    from fi_forest_data import nls

    if year != 2023:
        raise NotImplementedError("only the 2023 CMv2 product is wired up (TASK 00 decision D3)")
    if threshold_ha not in _DTW_DIR:
        raise KeyError(f"threshold_ha must be one of {sorted(_DTW_DIR)}, got {threshold_ha}")
    thr_dir = _DTW_DIR[threshold_ha]

    cache_dir = Path(cache_dir)
    out = cache_dir / "luke" / f"dtw2023_{thr_dir}ha__{aoi.name}.tif"
    if out.exists() and not force:
        return str(out)

    session = nls._session()
    try:
        sheets = nls.mapsheets_for_bbox(aoi.bbox_3067, session=session,
                                        cache_dir=cache_dir, layer="utm10")
    finally:
        session.close()

    tile_dir = cache_dir / "luke" / "dtw_tiles" / f"{thr_dir}ha"
    tile_dir.mkdir(parents=True, exist_ok=True)
    base_url = f"{_DTW_BASE}/{year}/DTW_INT_CMv2_{thr_dir}"
    paths = []
    for sheet in sheets:
        dest = tile_dir / f"{sheet}.tif"
        if not dest.exists() or force:
            r = requests.get(f"{base_url}/{sheet}.tif", timeout=120)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            dest.write_bytes(r.content)
        paths.append(dest)
    if not paths:
        raise RuntimeError(f"no DTW {threshold_ha} ha tiles found for {aoi.name}")

    srcs = [rasterio.open(p) for p in paths]
    mosaic, transform = merge(srcs, bounds=aoi.bbox_3067)
    profile = srcs[0].profile
    profile.update(height=mosaic.shape[1], width=mosaic.shape[2], transform=transform)
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(mosaic)
        dst.update_tags(
            attribution="Contains Natural Resources Institute Finland DTW data, CC BY 4.0",
            threshold_ha=str(threshold_ha), year=str(year), product="CMv2", unit="cm",
        )
    for s in srcs:
        s.close()

    meta = out.with_suffix(".meta.json")
    meta.write_text(json.dumps({
        "product": "dtw_2023_cmv2", "threshold_ha": threshold_ha, "year": year,
        "unit": "cm", "nodata": DTW_NODATA, "crs": "EPSG:3067",
        "n_tiles": len(paths), "sheets": [p.stem for p in paths],
        "aoi": aoi.name, "aoi_bbox_3067": list(aoi.bbox_3067),
        "fetch_date": date.today().isoformat(),
    }, indent=2), encoding="utf-8")
    return str(out)
