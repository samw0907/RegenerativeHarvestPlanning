# regenerative-harvest-planning/src/d2_dtw_extend.py
"""Module D2 - the DTW extension: adding soil and weather.

Weather term: select the wetness-condition threshold surface (of the five D1
channel-initiation thresholds) per date from FMI precipitation, snowmelt and
antecedent conditions (fmisid 101537, Viitasaari Haapaniemi, daily since 1970),
interpolating between threshold surfaces rather than switching abruptly - turns
five static maps into a dated time series.

Soil term: modulate the wetness-to-trafficability translation by peat vs
mineral main type (MS-NFI `paatyyppi`), since peat holds water and has low
bearing capacity even at DTW values that read dry on mineral soil.

Data tiers: FMI daily observations FETCH; MS-NFI soil main type FETCH; the
combined surface DERIVE ONLY (no official date-specific product exists).

Validation: does declared harvest activity on poor-bearing-capacity stands
actually concentrate in the predicted frozen/dry windows (forest use
declarations, reused from Project 1's data access pattern)? Apply the Project 1
lesson: a declaration is a permit, not a felling record, and any per-felling-
type or per-year subset needs a stated minimum n before quoting a distribution
(see docs/PROJECT_2_REGENERATIVE_HARVEST_PLANNING.md, "Lessons carried from
Project 1").

Blocking dependency: `fi_forest_data.fmi.stations_near` returns the whole
network (needs a client-side distance filter) - low priority since the station
to use is already pinned; fix only if a second station is needed.

No implementation yet - scaffold only.
"""
