# regenerative-harvest-planning/fi_forest_data/validate.py
"""Configuration validation.

Checks config/pipeline.yaml (and the AOI file it points at) for missing or
out-of-range parameters, so a typo fails fast rather than defaulting silently.
Importable, and runnable as `python -m fi_forest_data.validate config/pipeline.yaml`
(which is what CI does). Returns / prints a list of problems; empty means valid.
Schema per docs/REPO_SCAFFOLD.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from fi_forest_data.aoi import AOI

_REFERENCE_PRODUCTS = {"dtw_2019", "dtw_2023_cmv2"}
_PIT_REMOVAL = {"carve", "breach"}
_FLOW_ALGORITHMS = {"dinf", "d8", "mfd"}
_NODE_SOURCES = {"protected_areas", "habitat_s10", "ymparistotuki", "old_stands"}


def _num(problems: list[str], d: dict, key: str, lo=None, hi=None, ctx: str = "") -> None:
    if key not in d:
        problems.append(f"{ctx}: missing '{key}'")
        return
    v = d[key]
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        problems.append(f"{ctx}.{key}: expected a number, got {v!r}")
        return
    if lo is not None and v < lo:
        problems.append(f"{ctx}.{key}: {v} below minimum {lo}")
    if hi is not None and v > hi:
        problems.append(f"{ctx}.{key}: {v} above maximum {hi}")


def _in(problems: list[str], d: dict, key: str, allowed: set, ctx: str = "") -> None:
    if key not in d:
        problems.append(f"{ctx}: missing '{key}'")
    elif d[key] not in allowed:
        problems.append(f"{ctx}.{key}: {d[key]!r} not in {sorted(allowed)}")


def _bbox4(problems: list[str], d: dict, key: str, ctx: str = "") -> None:
    v = d.get(key)
    if not isinstance(v, list) or len(v) != 4 or not all(isinstance(x, (int, float)) for x in v):
        problems.append(f"{ctx}.{key}: expected a 4-number bbox")
        return
    minx, miny, maxx, maxy = v
    if not (minx < maxx and miny < maxy):
        problems.append(f"{ctx}.{key}: not min < max, got {v}")


def _dmy(problems: list[str], d: dict, key: str, ctx: str = "") -> None:
    v = d.get(key)
    if not isinstance(v, dict) or "start" not in v or "end" not in v:
        problems.append(f"{ctx}.{key}: expected keys 'start' and 'end' (MM-DD)")


def validate_pipeline_config(cfg: dict, base_dir: Path | None = None) -> list[str]:
    """Return a list of problem strings for a loaded pipeline config. Empty = valid."""
    problems: list[str] = []
    base_dir = base_dir or Path(".")

    # --- AOI ---
    aoi_ref = cfg.get("aoi")
    if not aoi_ref:
        problems.append("top level: missing 'aoi'")
    else:
        aoi_path = (base_dir / aoi_ref).resolve()
        if not aoi_path.exists():
            problems.append(f"aoi: file not found: {aoi_path}")
        else:
            try:
                AOI.from_yaml(aoi_path)
            except ValueError as exc:
                problems.append(f"aoi: {exc}")

    # --- module D1: DTW reimplementation ---
    d1 = cfg.get("module_d1_dtw_derive")
    if not isinstance(d1, dict):
        problems.append("top level: missing 'module_d1_dtw_derive' block")
    else:
        _bbox4(problems, d1, "validation_catchment_bbox_3067", "module_d1_dtw_derive")
        _in(problems, d1, "reference_product", _REFERENCE_PRODUCTS, "module_d1_dtw_derive")
        _in(problems, d1, "reference_unit", {"mm", "cm", "m"}, "module_d1_dtw_derive")
        _num(problems, d1, "dem_resolution_m", 0, None, "module_d1_dtw_derive")
        if not isinstance(d1.get("culvert_burn"), bool):
            problems.append("module_d1_dtw_derive.culvert_burn: expected true/false")
        _in(problems, d1, "pit_removal", _PIT_REMOVAL, "module_d1_dtw_derive")
        _in(problems, d1, "flow_algorithm", _FLOW_ALGORITHMS, "module_d1_dtw_derive")
        th = d1.get("channel_thresholds_ha")
        if not isinstance(th, list) or not th or not all(isinstance(x, (int, float)) and x > 0 for x in th):
            problems.append("module_d1_dtw_derive.channel_thresholds_ha: expected a non-empty list of positive numbers")

    # --- module D2: weather + soil extension ---
    d2 = cfg.get("module_d2_dtw_extend")
    if not isinstance(d2, dict):
        problems.append("top level: missing 'module_d2_dtw_extend' block")
    else:
        wt = d2.get("weather_term", {})
        if not isinstance(wt, dict):
            problems.append("module_d2_dtw_extend.weather_term: expected a block")
        else:
            if not isinstance(wt.get("enabled"), bool):
                problems.append("module_d2_dtw_extend.weather_term.enabled: expected true/false")
            if "fmi_station_id" not in wt:
                problems.append("module_d2_dtw_extend.weather_term: missing 'fmi_station_id'")
            ap = wt.get("antecedent_precip_days")
            if not isinstance(ap, list) or not ap or not all(isinstance(x, int) and x > 0 for x in ap):
                problems.append(
                    "module_d2_dtw_extend.weather_term.antecedent_precip_days: "
                    "expected a non-empty list of positive integers"
                )
        st = d2.get("soil_term", {})
        if not isinstance(st, dict):
            problems.append("module_d2_dtw_extend.soil_term: expected a block")
        else:
            if not isinstance(st.get("enabled"), bool):
                problems.append("module_d2_dtw_extend.soil_term.enabled: expected true/false")
            _num(problems, st, "peat_bearing_penalty", 0, 1, "module_d2_dtw_extend.soil_term")

    # --- module D3: root rot rule engine ---
    d3 = cfg.get("module_d3_rootrot")
    if not isinstance(d3, dict):
        problems.append("top level: missing 'module_d3_rootrot' block")
    else:
        _dmy(problems, d3, "mandatory_period", "module_d3_rootrot")
        _num(problems, d3, "mineral_soil_conifer_volume_share_min", 0, 1, "module_d3_rootrot")
        _num(problems, d3, "peat_soil_spruce_volume_share_min", 0, 1, "module_d3_rootrot")
        if "exemption_min_temp_c" not in d3:
            problems.append("module_d3_rootrot: missing 'exemption_min_temp_c'")
        _num(problems, d3, "exemption_lookback_days", 0, None, "module_d3_rootrot")
        if "spore_dispersal_mean_temp_c" not in d3:
            problems.append("module_d3_rootrot: missing 'spore_dispersal_mean_temp_c'")
        _num(problems, d3, "urea_watercourse_setback_m", 0, None, "module_d3_rootrot")

    # --- module E: Plus site planning ---
    e = cfg.get("module_e_plus")
    if not isinstance(e, dict):
        problems.append("top level: missing 'module_e_plus' block")
    else:
        for key in ("buffer_widths_m", "habitat_setback_widths_m"):
            v = e.get(key)
            if not isinstance(v, list) or not v or not all(isinstance(x, (int, float)) and x > 0 for x in v):
                problems.append(f"module_e_plus.{key}: expected a non-empty list of positive numbers")
        _num(problems, e, "dtw_wet_threshold_m", 0, None, "module_e_plus")
        _num(problems, e, "retention_trees_per_ha", 0, None, "module_e_plus")
        _num(problems, e, "retention_min_dbh_cm", 0, None, "module_e_plus")
        _num(problems, e, "deadwood_trees_per_ha", 0, None, "module_e_plus")
        if not isinstance(e.get("deadwood_vmi_zone"), str) or not e.get("deadwood_vmi_zone"):
            problems.append("module_e_plus.deadwood_vmi_zone: expected a non-empty string")
        _num(problems, e, "deadwood_vmi_m3_per_ha", 0, None, "module_e_plus")
        _num(problems, e, "deadwood_vmi_standing_share", 0, 1, "module_e_plus")
        _num(problems, e, "biodiversity_stumps_per_ha", 0, None, "module_e_plus")
        ccf = e.get("ccf_peatland")
        if not isinstance(ccf, dict):
            problems.append("module_e_plus.ccf_peatland: expected a block")
        else:
            _num(problems, ccf, "peat_soiltype_min", 0, None, "module_e_plus.ccf_peatland")
            _num(problems, ccf, "fertility_class_max", 1, 8, "module_e_plus.ccf_peatland")
            _num(problems, ccf, "spruce_share_min", 0, 1, "module_e_plus.ccf_peatland")
            ds = ccf.get("drained_states")
            if not isinstance(ds, list) or not ds or not all(isinstance(x, int) for x in ds):
                problems.append("module_e_plus.ccf_peatland.drained_states: expected a non-empty list of integers")
        _num(problems, e, "channel_network_resolution_m", 0, None, "module_e_plus")
        rusle = e.get("rusle")
        if not isinstance(rusle, dict):
            problems.append("module_e_plus.rusle: expected a block")
        else:
            if not isinstance(rusle.get("benchmark_layer"), str) or not rusle.get("benchmark_layer"):
                problems.append("module_e_plus.rusle.benchmark_layer: expected a non-empty string")
            _num(problems, rusle, "ls_exponent_m", 0, None, "module_e_plus.rusle")
            _num(problems, rusle, "ls_exponent_n", 0, None, "module_e_plus.rusle")
            _num(problems, rusle, "ls_specific_area_cap_m", 0, None, "module_e_plus.rusle")
            _num(problems, rusle, "k_default", 0, 1, "module_e_plus.rusle")
            kbs = rusle.get("k_by_soiltype")
            if not isinstance(kbs, dict) or not kbs or not all(
                    isinstance(v, (int, float)) and 0 <= v <= 1 for v in kbs.values()):
                problems.append("module_e_plus.rusle.k_by_soiltype: expected a non-empty {code: K in 0..1} map")

    # --- module F: connectivity ---
    f = cfg.get("module_f_connectivity")
    if not isinstance(f, dict):
        problems.append("top level: missing 'module_f_connectivity' block")
    else:
        ns = f.get("node_sources")
        if not isinstance(ns, list) or not ns or not set(ns) <= _NODE_SOURCES:
            problems.append(f"module_f_connectivity.node_sources: expected a subset of {sorted(_NODE_SOURCES)}")
        _num(problems, f, "old_stand_age_min_years", 0, None, "module_f_connectivity")
        _num(problems, f, "resistance_sensitivity_runs", 1, None, "module_f_connectivity")

    return problems


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python -m fi_forest_data.validate <pipeline.yaml>")
        return 2
    path = Path(argv[0])
    if not path.exists():
        print(f"config not found: {path}")
        return 2
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    problems = validate_pipeline_config(cfg, base_dir=path.parent)
    if problems:
        print(f"{path}: {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"{path}: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
