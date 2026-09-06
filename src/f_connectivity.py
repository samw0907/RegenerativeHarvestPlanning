# regenerative-harvest-planning/src/f_connectivity.py
"""Module F - biodiversity network connectivity.

Nodes: protected areas (SYKE/Metsahallitus), Forest Act §10 habitats,
environmental support (ymparistotuki) sites, old or structurally rich stands.
Resistance surface from stand age, canopy structure, species composition and
land cover. Connectivity via least-cost paths and graph-theoretic importance
measures. Rank candidate stands by marginal connectivity gain if a Plus
retention measure were applied there.

Data tier: FETCH throughout (registers and designations); the connectivity
analysis itself is transparent graph analysis, not a fitted model.

The honesty requirement (already the standard the other modules should match,
not a new lesson): resistance surfaces are assumption-laden. Run a sensitivity
sweep across plausible parameterisations (`resistance_sensitivity_runs` in
config) and report which stands are robustly high-value across all of them
versus which are artefacts of one parameter choice. The robust set is the
deliverable. Presented as an exploratory prioritisation method, not a
recommendation - the least certain of the three modules, and the README says so.

F1 (node assembly) implemented below.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd


def assemble_nodes(
    protected_areas: gpd.GeoDataFrame,
    habitats_s10: gpd.GeoDataFrame,
    ymparistotuki: gpd.GeoDataFrame,
    stands: gpd.GeoDataFrame,
    *,
    old_stand_age_min_years: int = 120,
) -> gpd.GeoDataFrame:
    """Merge the four Module F node sources into one polygon GeoDataFrame with a
    `node_type` column ("pa_state" / "pa_private" / "pa_natura_sac" /
    "pa_natura_spa" / "habitat_s10" / "ymparistotuki" / "old_stand").

    Old stands are Metsakeskus stands with `meanage >= old_stand_age_min_years`
    (config default 120). All inputs must be EPSG:3067; only geometry and
    node_type are kept."""
    parts = []

    if len(protected_areas):
        pa = protected_areas.copy()
        pa["node_type"] = "pa_" + pa["pa_source"].astype(str)
        parts.append(pa[["node_type", "geometry"]])

    if len(habitats_s10):
        parts.append(gpd.GeoDataFrame(
            {"node_type": "habitat_s10", "geometry": habitats_s10.geometry.values},
            crs="EPSG:3067"))

    if len(ymparistotuki):
        parts.append(gpd.GeoDataFrame(
            {"node_type": "ymparistotuki", "geometry": ymparistotuki.geometry.values},
            crs="EPSG:3067"))

    age = pd.to_numeric(stands.get("meanage"), errors="coerce")
    old = stands[age >= old_stand_age_min_years]
    if len(old):
        parts.append(gpd.GeoDataFrame(
            {"node_type": "old_stand", "geometry": old.geometry.values},
            crs="EPSG:3067"))

    if not parts:
        return gpd.GeoDataFrame({"node_type": [], "geometry": []}, crs="EPSG:3067")
    return gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:3067")
