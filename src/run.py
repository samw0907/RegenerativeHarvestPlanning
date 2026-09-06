# regenerative-harvest-planning/src/run.py
"""Pipeline entry point for Modules E and F.

Writes a run directory under `outputs/regenerative-harvest-planning/{e,f}/{run_id}/`
(run_id = {YYYYMMDD}_{HHMMSS}_{git_short_sha}) with report.json, the module's
vector outputs, figures/ and run_metadata.json.

The expensive derivations are prerequisites in `data/interim/{e,f}/`, produced
by the steps documented in `docs/MODULE_E_NOTES.md` / `docs/MODULE_F_NOTES.md`
(full-AOI 2 m DEM, 16 m channel network, RUSLE factor rasters, the F2
resistance surface). This entry point runs the fast analysis on top of them and
errors clearly if one is missing.

    python -m src.run              # Modules E and F baseline
    python -m src.run --sweep      # also run the F3b sensitivity sweep (~30 min)

Module D is run from its own notes-documented steps and is not wired here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import rasterio
import yaml

from fi_forest_data.aoi import AOI
from fi_forest_data.fmi import fetch_daily
from fi_forest_data.metsakeskus import (
    fetch_kemera_environmental, fetch_layer, fetch_raster)
from fi_forest_data.nls import fetch_topographic
from fi_forest_data.syke import fetch_protected_areas
from src import figures
from src.d_validation import korjuukelpoisuus_benchmark
from src.e_plus_site_planning import (
    buffer_comparison, build_site_plan, ccf_area_summary, ccf_rootrot_conflict,
    conflict_free_felling_window, deadwood_aggregate, extract_channel_network,
    habitat_proximity, rusle_benchmark, rusle_buffer_crossref,
)
from src.f_connectivity import (
    _coarsen, assemble_nodes, backbone_edges, build_patches, corridor_density,
    patch_dpc, patch_least_cost, per_stand_corridor_score, resistance_surface,
    sensitivity_sweep,
)

_E = Path("data/interim/e")
_F = Path("data/interim/f")
_E_PREREQS = ["dem16m_central_finland.tif", "A_ours_aoi16m.tif", "A_ours_catchment.tif",
              "ls_factor_catchment.tif", "stand_coverage_catchment.tif",
              "streams_0.5ha.tif", "streams_2.0ha.tif", "streams_10.0ha.tif"]
_CLC = "data/raw/syke/clc2018_central_finland.tif"
_THRESHOLDS = (0.5, 1.0, 2.0, 4.0, 10.0)
_CATCHMENT = AOI(name="fi1_14_06_161_bbox", bbox_3067=(414920, 6945300, 429010, 6964880))


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "nogit"


def _new_run_dir(module: str) -> tuple[str, Path]:
    run_id = f"{datetime.now():%Y%m%d_%H%M%S}_{_git_sha()}"
    out_dir = Path("outputs/regenerative-harvest-planning") / module / run_id
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    return run_id, out_dir


def _meta(out_dir: Path, run_id: str, module: str, **extra) -> None:
    (out_dir / "run_metadata.json").write_text(json.dumps({
        "run_id": run_id, "git_sha": _git_sha(),
        "created": datetime.now().isoformat(timespec="seconds"),
        "config": "config/pipeline.yaml", "module": module, **extra,
    }, indent=2), encoding="utf-8")


def run_module_e(cfg_all: dict, aoi: AOI) -> None:
    cfg_e, cfg_d3, cfg_d2 = (cfg_all["module_e_plus"], cfg_all["module_d3_rootrot"],
                             cfg_all["module_d2_dtw_extend"])
    missing = [p for p in _E_PREREQS if not (_E / p).exists()]
    if missing:
        sys.exit(f"missing Module E prerequisites in {_E}/: {missing}\n"
                 "produce them via docs/MODULE_E_NOTES.md section 3")

    run_id, out_dir = _new_run_dir("e")
    stands = fetch_layer("stand", aoi)
    habitats = fetch_layer("habitat", aoi)
    mapped = fetch_topographic(aoi)
    daily = fetch_daily(cfg_d2["weather_term"]["fmi_station_id"], "1970-01-01",
                        "2024-12-31", variables=("rrday", "tday", "tmin", "tmax", "snow"))
    mk_rusle = fetch_raster(cfg_e["rusle"]["benchmark_layer"], _CATCHMENT)

    dem16 = str(_E / "dem16m_central_finland.tif")
    buffers = {th: buffer_comparison(
        extract_channel_network(dem16, th, work_dir=str(_E)),
        mapped, dem16, cfg_e["buffer_widths_m"]) for th in _THRESHOLDS}

    report = {
        "run_id": run_id, "aoi": {"name": aoi.name, "bbox_3067": list(aoi.bbox_3067)},
        "waterway_buffers_by_threshold_ha": buffers,
        "ccf_peatland": ccf_area_summary(stands, cfg_e["ccf_peatland"]),
        "ccf_rootrot_conflict": ccf_rootrot_conflict(stands, cfg_e["ccf_peatland"], cfg_d3),
        "conflict_free_felling_window": conflict_free_felling_window(daily, cfg_d3),
        "habitat_proximity": habitat_proximity(stands, habitats, cfg_e["habitat_setback_widths_m"]),
        "rusle_benchmark": rusle_benchmark(
            str(_E / "A_ours_catchment.tif"), mk_rusle,
            str(_E / "stand_coverage_catchment.tif"),
            also_compare={"LS": str(_E / "ls_factor_catchment.tif")}),
        "rusle_buffer_crossref": {
            th: rusle_buffer_crossref(str(_E / "A_ours_aoi16m.tif"),
                                      str(_E / f"streams_{th}ha.tif"), cfg_e["buffer_widths_m"])
            for th in (0.5, 2.0, 10.0)},
        "deadwood_aggregate": deadwood_aggregate(stands, cfg_e),
    }

    # D2 workability benchmarked against the operational Korjuukelpoisuus raster,
    # if the D1-catchment inputs are present (see docs/MODULE_D_NOTES.md).
    luke = Path("data/raw/luke")
    korjuu_inputs = [luke / "dtw2023_2ha__fi1_14_06_161.tif",
                     luke / "msnfi_soil_main_type_2023__fi1_14_06_161_bbox.tif"]
    if all(p.exists() for p in korjuu_inputs):
        korjuu = fetch_raster("Korjuukelpoisuus", _CATCHMENT)
        report["d2_workability_vs_korjuukelpoisuus"] = korjuukelpoisuus_benchmark(
            str(korjuu_inputs[0]), str(korjuu_inputs[1]), korjuu, cfg_d2)

    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    site_plan = build_site_plan(stands, habitats, str(_E / "streams_0.5ha.tif"), cfg_e, cfg_d3)
    site_plan.to_file(out_dir / "site_plan.gpkg", driver="GPKG")

    figures.module_e_buffer_capture(buffers, out_dir / "figures" / "e_buffer_capture.png")
    figures.module_e_rusle_map(str(_E / "A_ours_aoi16m.tif"), str(_E / "streams_0.5ha.tif"),
                               out_dir / "figures" / "e_rusle_map.png")
    figures.module_e_site_plan_bars(out_dir / "site_plan.gpkg",
                                    out_dir / "figures" / "e_site_plan_bars.png")
    _meta(out_dir, run_id, "E", n_stands=int(len(stands)), n_site_plan_rows=int(len(site_plan)))
    print(f"wrote {out_dir}")


def run_module_f(cfg_all: dict, aoi: AOI, *, sweep: bool) -> None:
    cfg_f = cfg_all["module_f_connectivity"]
    cfg_res, cfg_conn, cfg_sens = cfg_f["resistance"], cfg_f["connectivity"], cfg_f["sensitivity"]
    grid = str(_E / "dem16m_central_finland.tif")
    if not Path(grid).exists() or not Path(_CLC).exists():
        sys.exit(f"missing Module F inputs: need {grid} and {_CLC}")

    run_id, out_dir = _new_run_dir("f")
    stands = fetch_layer("stand", aoi)
    nodes = assemble_nodes(fetch_protected_areas(aoi), fetch_layer("habitat", aoi),
                           fetch_kemera_environmental(aoi), stands,
                           old_stand_age_min_years=cfg_f["old_stand_age_min_years"])
    _F.mkdir(parents=True, exist_ok=True)
    nodes.to_file(_F / "nodes_aoi.gpkg", driver="GPKG")

    r, prof = resistance_surface(stands, _CLC, grid, cfg_res)
    with rasterio.open(_F / "resistance_baseline.tif", "w", **prof) as dst:
        dst.write(r, 1)

    coarse, tr, _ = _coarsen(str(_F / "resistance_baseline.tif"),
                             int(cfg_conn["coarsen_factor"]), cfg_res["water_resistance"])
    patches = build_patches(nodes, merge_buffer_m=cfg_conn["patch_merge_buffer_m"],
                            min_area_ha=cfg_conn["patch_min_area_ha"])
    cm, fields = patch_least_cost(patches, coarse, tr)
    areas = patches["area_ha"].to_numpy()
    dpc, pc = patch_dpc(cm, areas, dispersal_cost=cfg_conn["dispersal_cost"])
    patches = patches.assign(dpc=dpc)
    patches.to_file(_F / "patches.gpkg", driver="GPKG")

    edges = backbone_edges(cm, k_nearest=int(cfg_conn["backbone_k_nearest"]))
    dens = corridor_density(fields, cm, areas, coarse.shape, edges,
                            dispersal_cost=cfg_conn["dispersal_cost"], slack=cfg_conn["corridor_slack"])
    with rasterio.open(_F / "corridor_density.tif", "w",
                       **dict(prof, height=coarse.shape[0], width=coarse.shape[1], transform=tr)) as dst:
        dst.write(dens, 1)
    score = per_stand_corridor_score(stands, dens, tr)
    gpd.GeoDataFrame({"standid": stands.get("standid"), "corridor_score": score,
                      "geometry": stands.geometry.values}, crs=stands.crs).to_file(
        out_dir / "stand_connectivity_scores.gpkg", driver="GPKG")

    report = {
        "run_id": run_id, "aoi": {"name": aoi.name, "bbox_3067": list(aoi.bbox_3067)},
        "n_nodes": int(len(nodes)),
        "nodes_by_type": nodes["node_type"].value_counts().to_dict(),
        "n_patches": int(len(patches)),
        "probability_of_connectivity": round(pc, 6),
        "top_patch_dpc_pct": [round(x, 2) for x in sorted(dpc, reverse=True)[:10]],
        "n_stands_scored": int((score > 0).sum()),
    }

    if sweep:
        robust, run_summary = sensitivity_sweep(
            stands, patches, _CLC, grid, cfg_res, cfg_conn, cfg_sens,
            n_runs=int(cfg_f["resistance_sensitivity_runs"]))
        robust.to_file(out_dir / "stand_connectivity_robust.gpkg", driver="GPKG")
        (out_dir / "sensitivity_runs.json").write_text(json.dumps(run_summary, indent=2),
                                                       encoding="utf-8")
        pcs = [s["PC"] for s in run_summary]
        report["sensitivity_sweep"] = {
            "n_runs": len(run_summary),
            "pc_min": round(min(pcs), 4), "pc_max": round(max(pcs), 4),
            "n_robust_stands": int(robust["robust"].sum()),
            "robust_stand_area_ha": round(float(
                gpd.pd.to_numeric(stands["area"], errors="coerce")[robust["robust"].to_numpy()].sum()), 1),
        }
        figures.module_f_robustness_hist(out_dir / "stand_connectivity_robust.gpkg",
                                         out_dir / "figures" / "f_robustness_hist.png")

    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    figures.module_f_corridor_map(
        str(_F / "corridor_density.tif"), str(_F / "nodes_aoi.gpkg"),
        out_dir / "figures" / "f_corridor_map.png",
        robust_gpkg=(out_dir / "stand_connectivity_robust.gpkg") if sweep else None)
    figures.module_f_patch_dpc(str(_F / "patches.gpkg"), out_dir / "figures" / "f_patch_dpc.png")
    _meta(out_dir, run_id, "F", n_nodes=int(len(nodes)), n_patches=int(len(patches)),
          sweep=sweep)
    print(f"wrote {out_dir}")


def main() -> None:
    sweep = "--sweep" in sys.argv[1:]
    cfg_all = yaml.safe_load(open("config/pipeline.yaml"))
    aoi_cfg = yaml.safe_load(open("config/aoi_central.yaml"))
    aoi = AOI(name=aoi_cfg["name"], bbox_3067=tuple(aoi_cfg["bbox_3067"]))
    run_module_e(cfg_all, aoi)
    run_module_f(cfg_all, aoi, sweep=sweep)


if __name__ == "__main__":
    main()
