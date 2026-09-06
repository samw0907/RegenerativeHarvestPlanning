# regenerative-harvest-planning/src/figures.py
"""Figure generation.

Static matplotlib figures in the existing portfolio style (Prey Lang / Baltic /
Boreal Stand Intelligence): no emojis, attribution in the caption, legend
classes in English. PNGs go to a per-run figures directory.

Implemented for Module E:
    module_e_buffer_capture(buffer_rows_by_threshold, out_path)
    module_e_rusle_map(a_raster_path, stream_raster_path, out_path)
    module_e_site_plan_bars(site_plan_gpkg, out_path)
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

_ATTR = "Data: Finnish Forest Centre, NLS, Luke, SYKE (CC BY 4.0)"


def _finish(fig, out_path):
    fig.text(0.01, 0.01, _ATTR, fontsize=6, color="#555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return str(out_path)


def module_e_buffer_capture(buffer_rows_by_threshold: dict, out_path: str | Path) -> str:
    """Grouped bars: derived-network buffer area vs mapped-hydrography buffer
    area, and the additional area, by waterway-class threshold, at one buffer
    width (30 m). `buffer_rows_by_threshold` maps threshold_ha -> the list of
    dicts from `buffer_comparison`."""
    ths = sorted(buffer_rows_by_threshold)
    at30 = {th: next(r for r in buffer_rows_by_threshold[th] if r["buffer_width_m"] == 30)
            for th in ths}
    derived = [at30[th]["derived_buffer_ha"] / 1000 for th in ths]
    mapped = [at30[th]["mapped_buffer_ha"] / 1000 for th in ths]
    additional = [at30[th]["additional_ha"] / 1000 for th in ths]

    x = np.arange(len(ths))
    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    ax.bar(x - 0.27, derived, 0.27, label="Derived-network 30 m buffer", color="#1f4e79")
    ax.bar(x, mapped, 0.27, label="Mapped-hydrography 30 m buffer", color="#8a8a8a")
    ax.bar(x + 0.27, additional, 0.27, label="Additional area (derived - mapped)", color="#2b7a3d")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{th} ha" for th in ths])
    ax.set_xlabel("Channel-initiation threshold (waterway class)")
    ax.set_ylabel("Buffer area (1000 ha)")
    ax.set_title("Module E - waterway buffer area vs mapped hydrography")
    ax.legend(fontsize=8, framealpha=0.9)
    return _finish(fig, out_path)


def module_e_rusle_map(a_raster_path: str | Path, stream_raster_path: str | Path,
                       out_path: str | Path, *, downsample: int = 4) -> str:
    """Full-AOI RUSLE A (16 m, log colour) with the derived stream network
    overlaid. Decimated on read for a poster-scale PNG."""
    import rasterio

    with rasterio.open(a_raster_path) as src:
        h, w = src.height, src.width
        a = src.read(1, out_shape=(h // downsample, w // downsample))
        bounds = src.bounds
    with rasterio.open(stream_raster_path) as src:
        s = src.read(1, out_shape=(h // downsample, w // downsample))
        s = (s > 0) & (s != src.nodata)

    a = np.where(np.isfinite(a) & (a > 0), a, np.nan)
    extent = (bounds.left, bounds.right, bounds.bottom, bounds.top)
    fig, ax = plt.subplots(figsize=(6.4, 8.0))
    im = ax.imshow(np.log10(a), extent=extent, cmap="YlOrBr", origin="upper")
    ax.imshow(np.where(s, 1.0, np.nan), extent=extent, cmap="Blues", origin="upper",
              alpha=0.55, vmin=0, vmax=1)
    cb = fig.colorbar(im, ax=ax, shrink=0.6)
    cb.set_label("log10 RUSLE A (t/ha/yr)")
    ax.set_title("Module E - RUSLE erosion risk and derived stream network")
    ax.set_xlabel("Easting (EPSG:3067)")
    ax.set_ylabel("Northing (EPSG:3067)")
    return _finish(fig, out_path)


def module_e_site_plan_bars(site_plan_gpkg: str | Path, out_path: str | Path) -> str:
    """Horizontal bars: stand area under each Module E constraint flag."""
    import geopandas as gpd

    sp = gpd.read_file(site_plan_gpkg)
    flags = [
        ("Root-rot stump-treatment obligation", "rootrot_obligation"),
        ("Within 30 m of a S10 habitat", "within_habitat_setback"),
        ("Within 30 m of a derived stream", "within_stream_buffer"),
        ("CCF prescribed (lush drained spruce peat)", "ccf_prescribed"),
    ]
    labels = [lbl for lbl, _ in flags]
    areas = [sp.loc[sp[col], "area_ha"].sum() / 1000 for _, col in flags]

    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    ax.barh(labels, areas, color="#1f4e79")
    for i, v in enumerate(areas):
        ax.text(v, i, f" {v:,.0f}k ha", va="center", fontsize=8)
    ax.set_xlabel("Stand area (1000 ha)")
    ax.set_title("Module E - per-stand site-plan constraint area")
    ax.invert_yaxis()
    return _finish(fig, out_path)


def module_f_corridor_map(corridor_density_path: str | Path, nodes_gpkg: str | Path,
                          out_path: str | Path, *, robust_gpkg: str | Path | None = None) -> str:
    """Least-cost corridor density (log colour) with the node patches outlined
    and, if given, the robust connectivity-priority stands overlaid."""
    import geopandas as gpd
    import rasterio

    with rasterio.open(corridor_density_path) as src:
        d = src.read(1).astype("float64")
        b = src.bounds
    d = np.where(d > 0, d, np.nan)
    extent = (b.left, b.right, b.bottom, b.top)

    fig, ax = plt.subplots(figsize=(6.6, 8.4))
    im = ax.imshow(np.log10(d), extent=extent, cmap="magma", origin="upper")
    gpd.read_file(nodes_gpkg).boundary.plot(ax=ax, color="#2b7a3d", linewidth=0.3)
    if robust_gpkg is not None:
        r = gpd.read_file(robust_gpkg)
        r = r[r["robust"]] if "robust" in r.columns else r
        r.plot(ax=ax, facecolor="#1f4e79", edgecolor="none", alpha=0.6)
    cb = fig.colorbar(im, ax=ax, shrink=0.55)
    cb.set_label("log10 corridor density")
    ax.set_title("Module F - connectivity corridors, nodes and robust priority stands")
    ax.set_xlabel("Easting (EPSG:3067)")
    ax.set_ylabel("Northing (EPSG:3067)")
    return _finish(fig, out_path)


def module_f_robustness_hist(robust_gpkg: str | Path, out_path: str | Path) -> str:
    """Histogram of `top_decile_runs` - how many of the sensitivity-sweep runs
    put each stand in the top decile. The bimodal shape is the point: a stand is
    almost always high-priority or almost never."""
    import geopandas as gpd

    tdr = gpd.read_file(robust_gpkg)["top_decile_runs"].to_numpy()
    n_runs = int(tdr.max())
    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.hist(tdr[tdr > 0], bins=np.arange(1, n_runs + 2) - 0.5, color="#1f4e79")
    ax.set_xlabel(f"runs (of {n_runs}) with the stand in the top decile")
    ax.set_ylabel("stands")
    ax.set_title("Module F - stability of the connectivity-priority ranking")
    ax.set_yscale("log")
    return _finish(fig, out_path)


def module_f_patch_dpc(patches_gpkg: str | Path, out_path: str | Path, *, top_n: int = 12) -> str:
    """Bar chart of the highest-dPC node patches (% drop in Probability of
    Connectivity if that patch were removed)."""
    import geopandas as gpd

    p = gpd.read_file(patches_gpkg).sort_values("dpc", ascending=False).head(top_n)
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    ax.bar(range(len(p)), p["dpc"], color="#c0504d")
    ax.set_xticks(range(len(p)))
    ax.set_xticklabels([f"{a:,.0f} ha" for a in p["area_ha"]], rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("dPC (% loss of network connectivity if removed)")
    ax.set_title(f"Module F - top {top_n} node patches by connectivity importance")
    return _finish(fig, out_path)
