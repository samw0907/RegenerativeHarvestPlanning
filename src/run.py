# regenerative-harvest-planning/src/run.py
"""Pipeline entry point.

Runs Module E end to end from cached inputs and writes a run directory under
`outputs/regenerative-harvest-planning/e/{run_id}/` (run_id =
{YYYYMMDD}_{HHMMSS}_{git_short_sha}) containing report.json, site_plan.gpkg,
figures/ and run_metadata.json.

Module E's expensive derivations (full-AOI 2 m DEM fetch, 16 m channel network,
RUSLE factor rasters) are prerequisites, produced by the steps documented in
`docs/MODULE_E_NOTES.md` and left in `data/interim/e/`. This entry point runs
the fast analysis and reporting on top of them; it errors clearly if a
prerequisite raster is missing.

Modules D and F are run from their own notes-documented steps and are not wired
here yet.

    python -m src.run          # uses config/pipeline.yaml
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

from fi_forest_data.aoi import AOI
from fi_forest_data.fmi import fetch_daily
from fi_forest_data.metsakeskus import fetch_layer, fetch_raster
from fi_forest_data.nls import fetch_topographic
from src import figures
from src.e_plus_site_planning import (
    buffer_comparison, ccf_area_summary, ccf_rootrot_conflict,
    conflict_free_felling_window, deadwood_aggregate, extract_channel_network,
    habitat_proximity, build_site_plan, rusle_benchmark, rusle_buffer_crossref,
)

_INTERIM = Path("data/interim/e")
_PREREQS = [
    "dem16m_central_finland.tif", "A_ours_aoi16m.tif", "A_ours_catchment.tif",
    "ls_factor_catchment.tif", "stand_coverage_catchment.tif",
    "streams_0.5ha.tif", "streams_2.0ha.tif", "streams_10.0ha.tif",
]
_THRESHOLDS = (0.5, 1.0, 2.0, 4.0, 10.0)


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "nogit"


def main() -> None:
    cfg_all = yaml.safe_load(open("config/pipeline.yaml"))
    cfg_e = cfg_all["module_e_plus"]
    cfg_d3 = cfg_all["module_d3_rootrot"]
    cfg_d2 = cfg_all["module_d2_dtw_extend"]
    aoi_cfg = yaml.safe_load(open("config/aoi_central.yaml"))
    aoi = AOI(name=aoi_cfg["name"], bbox_3067=tuple(aoi_cfg["bbox_3067"]))

    missing = [p for p in _PREREQS if not (_INTERIM / p).exists()]
    if missing:
        sys.exit(f"missing prerequisites in {_INTERIM}/: {missing}\n"
                 "produce them via the steps in docs/MODULE_E_NOTES.md section 3")

    run_id = f"{datetime.now():%Y%m%d_%H%M%S}_{_git_sha()}"
    out_dir = Path("outputs/regenerative-harvest-planning/e") / run_id
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)

    stands = fetch_layer("stand", aoi)
    habitats = fetch_layer("habitat", aoi)
    mapped = fetch_topographic(aoi)
    daily = fetch_daily(cfg_d2["weather_term"]["fmi_station_id"],
                        "1970-01-01", "2024-12-31",
                        variables=("rrday", "tday", "tmin", "tmax", "snow"))
    mk_rusle = fetch_raster(cfg_e["rusle"]["benchmark_layer"],
                            AOI(name="fi1_14_06_161_bbox",
                                bbox_3067=(414920, 6945300, 429010, 6964880)))

    buffers = {th: buffer_comparison(
        extract_channel_network(str(_INTERIM / "dem16m_central_finland.tif"), th,
                                work_dir=str(_INTERIM)),
        mapped, str(_INTERIM / "dem16m_central_finland.tif"), cfg_e["buffer_widths_m"])
        for th in _THRESHOLDS}

    report = {
        "run_id": run_id,
        "aoi": {"name": aoi.name, "bbox_3067": list(aoi.bbox_3067)},
        "waterway_buffers_by_threshold_ha": buffers,
        "ccf_peatland": ccf_area_summary(stands, cfg_e["ccf_peatland"]),
        "ccf_rootrot_conflict": ccf_rootrot_conflict(stands, cfg_e["ccf_peatland"], cfg_d3),
        "conflict_free_felling_window": conflict_free_felling_window(daily, cfg_d3),
        "habitat_proximity": habitat_proximity(stands, habitats, cfg_e["habitat_setback_widths_m"]),
        "rusle_benchmark": rusle_benchmark(
            str(_INTERIM / "A_ours_catchment.tif"), mk_rusle,
            str(_INTERIM / "stand_coverage_catchment.tif"),
            also_compare={"LS": str(_INTERIM / "ls_factor_catchment.tif")}),
        "rusle_buffer_crossref": {
            th: rusle_buffer_crossref(str(_INTERIM / "A_ours_aoi16m.tif"),
                                      str(_INTERIM / f"streams_{th}ha.tif"),
                                      cfg_e["buffer_widths_m"])
            for th in (0.5, 2.0, 10.0)},
        "deadwood_aggregate": deadwood_aggregate(stands, cfg_e),
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    site_plan = build_site_plan(stands, habitats, str(_INTERIM / "streams_0.5ha.tif"),
                                cfg_e, cfg_d3)
    site_plan.to_file(out_dir / "site_plan.gpkg", driver="GPKG")

    figures.module_e_buffer_capture(buffers, out_dir / "figures" / "e_buffer_capture.png")
    figures.module_e_rusle_map(str(_INTERIM / "A_ours_aoi16m.tif"),
                               str(_INTERIM / "streams_0.5ha.tif"),
                               out_dir / "figures" / "e_rusle_map.png")
    figures.module_e_site_plan_bars(out_dir / "site_plan.gpkg",
                                    out_dir / "figures" / "e_site_plan_bars.png")

    (out_dir / "run_metadata.json").write_text(json.dumps({
        "run_id": run_id, "git_sha": _git_sha(),
        "created": datetime.now().isoformat(timespec="seconds"),
        "config": "config/pipeline.yaml", "module": "E",
        "n_stands": int(len(stands)), "n_site_plan_rows": int(len(site_plan)),
    }, indent=2), encoding="utf-8")
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
