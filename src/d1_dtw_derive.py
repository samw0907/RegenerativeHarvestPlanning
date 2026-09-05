# regenerative-harvest-planning/src/d1_dtw_derive.py
"""Module D1 - reimplement depth-to-water, and benchmark it.

On the validation catchment (SYKE FI1-14.06.161, 148 km2): burn culverts at
road/channel crossings, carve remaining pits (Lindsay 2016), route flow with
D-infinity (Tarboton 1997) from the NLS 2 m DEM, take slope from the unmodified
surface, initiate channels at 0.5/1/2/4/10 ha, compute slope-weighted cumulative
distance to channel in metres. Compare against Luke DTW 2023 CMv2 (D8 flow
routing, breaching pit-removal - an expected source of divergence to account for
in the write-up; units: theirs is centimetres, ours is metres).

Data tiers: 2 m DEM DERIVE input; Luke DTW 2023 CMv2 DERIVE AND BENCHMARK
reference, fetched at AOI scale after the validation-catchment comparison earns
it (three-tier rule - do not reprocess the full AOI at 2 m for no reason;
Project 1's Module A stopped short of this AOI-scale step, learn from that).

Blocking dependency: `fi_forest_data.nls.fetch_dem` caps at 100 km2 per request;
the validation catchment (148 km2) already exceeds it, so a tiling wrapper is
needed before this module can fetch its own DEM. `fi_forest_data.luke.fetch_dtw`
is not yet implemented (mapsheet-tiled Funet mirror, unlike MS-NFI's single
whole-Finland file) - build that first too.

No implementation yet - scaffold only.
"""
