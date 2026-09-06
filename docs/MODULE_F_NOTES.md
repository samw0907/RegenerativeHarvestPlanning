# Module F - notes, decisions and rationale

Running record of *why* Module F is built the way it is and *what the results
mean*. Source material for the final README. Companion plan:
`PROJECT_2_REGENERATIVE_HARVEST_PLANNING.md`, Module F section.

---

## 1. What Module F is

An exploratory biodiversity-network connectivity prioritisation for the AOI:
which stands, if a Plus retention measure were applied there, would add the
most to the connectivity of the existing protected/valuable-habitat network.
Nodes from designations and old stands; a resistance surface from stand
structure and land cover; least-cost / graph connectivity; and - the point of
the module - a sensitivity sweep so the deliverable is the set of stands that
score high **robustly**, not one assumption-dependent map.

Data tier: FETCH throughout. The connectivity analysis is transparent graph
analysis, not a fitted model.

---

## 2. Design decisions

### 2.1 ymparistotuki node source (TASK 00 D4) - resolved 2026-09-06

TASK 00 left the environmental-support / ymparistotuki layer's exact field and
route OPEN: "a category within the Kemera dataset". Resolved by inspecting the
Metsakeskus Kemera regional GeoPackage
(`aineistot/Kemera/Maakunta/Kemera_Keski-Suomi.zip`, 156 MB zip / 383 MB
GPKG, 32 layers named `{application|completiondeclaration}_{stand|line|point}_
{financingactnumber}_{workcode}`).

**The ymparistotuki / forest-nature-management sites are
`application_stand_11_90`** - `financingactnumber` 11 (Kemera), `workcode`
641, the only layer carrying an `environmentmanagementtype` field and
multi-year `estimatedstartdate`/`projectenddate` (agreement-style records).
There is no Metka-era (act 13) equivalent in the open data - the `_13_*`
layers are fertilisation and forestation. Only **10 polygons fall in the AOI**,
~1 ha total - a small contributor next to the other node sources, but real and
included. `metsakeskus.fetch_kemera_environmental(aoi, region="Keski-Suomi")`
downloads the regional zip once, reads that layer with a bbox filter, caches.

### 2.2 Protected-area fetch route

`syke.fetch_protected_areas` merges three SYKE download-tree zips: state
reserves (`luonnonsuojelualueet_valtio.zip` -> `LsAlueValtio`), private
reserves (`_yksityinen.zip` -> `LsAlueYks`), and Natura 2000
(`natura.zip` -> `natura2000sac_alueet` + `natura2000spa_alueet`). The
`/vsizip//vsicurl/` route works for the smaller files but fails intermittently
on the state-reserve zip ("HTTP response code 0"), so each zip is downloaded to
the cache once and read locally. The reserve shapefiles carry an untagged
EUREF-FIN TM35FIN PROJCS; CRS is forced to EPSG:3067 (coordinate-identical).

---

## 3. Method and results

### F1 - node assembly (done, 2026-09-06)

`src/f_connectivity.py` `assemble_nodes`: merges the four sources into one
polygon layer with a `node_type` column. Old stands = Metsakeskus stands with
`meanage >= 120` (config `old_stand_age_min_years`). Unit tested (each source
tagged, old-stand age filter, empty-source handling).

Full-AOI result: **2,769 nodes**.

| node_type | count | area (ha) |
|---|---|---|
| habitat_s10 | 2,099 | 1,072 |
| old_stand (>= 120 yr) | 413 | 359 |
| pa_private (private reserves) | 212 | 1,558 |
| pa_natura_sac | 26 | 9,512 |
| pa_natura_spa | 7 | 6,172 |
| pa_state | 2 | 1,405 |
| ymparistotuki | 10 | 1 |

**Reading.** The node network is a mix of a few large anchors (26 Natura SAC
sites carry ~9,500 ha, plus SPA and state reserves) and many small stepping
stones (2,099 §10 habitats at ~0.5 ha each, 413 old stands). Total node area
~20,000 ha, ~6% of the 340,000 ha AOI. Old forest is scarce on managed private
land (413 stands over 120 yr, 359 ha) - expected, and part of why the
connectivity question matters. Written to `data/interim/f/nodes_aoi.gpkg`.

Next: F2 - the resistance surface (stand age, canopy structure, species
composition, land cover), then least-cost connectivity and the sensitivity
sweep.

### F2 - resistance (movement-cost) surface (done, 2026-09-06)

`f_connectivity.resistance_surface`: a 16 m surface (matching the Module E
channel-network / RUSLE grid) built from four terms, each normalised to [0,1]
(0 = best habitat, 1 = worst), combined by config weights:

| term | source | formula | weight |
|---|---|---|---|
| age | Metsakeskus stand `meanage` | 1 - min(age / 120, 1) | 0.30 |
| structure | Metsakeskus stand `basalarea` | 1 - min(BA / 25, 1) | 0.25 |
| species | Metsakeskus stand `proportionother` (deciduous share) | 1 - min(share / 0.5, 1) | 0.20 |
| land cover | SYKE CLC2018 category (config) | lookup: forest 0.10 ... water 1.00 | 0.25 |

No canopy-cover field in the stand data, so basal area stands in as the
structure proxy (flagged). Where a stand attribute is missing (off stand land,
or a null value) that term falls back to the land-cover term, so non-forest
land is scored on land cover alone. The blended [0,1] surface is rescaled to
[1, 100]; water cells are then set to 1000 (a near-absolute barrier). Every
constant is in `config/pipeline.yaml` `module_f_connectivity.resistance` - this
is exactly the surface F3 will sweep. The CLC-value -> category map
(`_CLC_GROUPS`) is a fixed property of the SYKE scheme and lives in code, not
config. Unit tested (term blending, water barrier, off-stand land-cover
fallback).

Baseline surface for the AOI (`data/interim/f/resistance_baseline.tif`):
non-water resistance p10 27, median 43, mean 47, p90 80, max 98; water 16.5% of
cells. The median ~43 is the typical managed middle-aged conifer stand
(meanage ~47, BA ~19, deciduous ~0.14); low-resistance cells are older / more
deciduous forest, high-resistance cells are clearcuts, young stands and fields.

Next: F3 - least-cost connectivity between the F1 nodes across this surface,
graph importance measures, and the sensitivity sweep that produces the robust
set.

### F3a - least-cost connectivity, patch importance, per-stand score (baseline, done 2026-09-06)

All in `src/f_connectivity.py`, `scikit-image` `MCP_Geometric` for least-cost
accumulation, config `module_f_connectivity.connectivity`:

- `_coarsen` - the 16 m resistance surface averaged to **128 m** for the
  least-cost work (a landscape-connectivity computation does not need 16 m, and
  it makes the sensitivity sweep tractable); cells whose coarse average clears
  half the water value are snapped back to the barrier so lakes stay
  impassable.
- `build_patches` - the F1 nodes buffered out 200 m, unioned, buffered back and
  exploded, keeping patches >= 0.5 ha: **786 patches** (median 1.9 ha, max
  2,138 ha - the big Natura sites). The 200 m merge does not consolidate the
  §10 habitats much; they really are scattered further apart than that.
- `patch_least_cost` - one MCP accumulation per patch (**41 s** for 786
  patches at 128 m), giving an 786x786 cost-distance matrix. 179,101 of
  308,505 patch pairs are mutually reachable - the rest are separated by lakes,
  realistic for this landscape.
- `patch_dpc` - Probability of Connectivity (Saura & Pascual-Hortal 2007) and
  each patch's **dPC** (% drop in PC if that patch were removed),
  `p_ij = exp(-cost_ij / 8000)`.
- `backbone_edges` + `corridor_density` - corridors accumulated only for the
  connectivity **backbone** (each patch to its 3 lowest-cost neighbours, 1,174
  undirected edges), not every patch pair. Each corridor is the cells within
  15% cost slack of the least-cost line, weighted by pair connectivity. (A
  first attempt accumulated the top 25% of *all* pairs and blanketed 93% of the
  landscape - useless as a discriminator; the backbone version covers 35%.)
- `per_stand_corridor_score` - zonal mean of the corridor-density raster per
  stand (one rasterisation + `scipy.ndimage.mean`), the per-stand
  connectivity-priority score.

**Baseline results:**

- **PC = 0.305.** dPC is dominated by the two largest Natura patches: **36.3%
  and 34.2%**, then 21.8%, 7.5%, 6.3%, tailing off. Removing either big anchor
  roughly halves network connectivity. The ranking is stable to the coarsening
  choice (a 64 m run gave 38.4 / 35.2 / 18.5 / 7.4) - the patch-importance
  result is robust, the big protected sites carry the network and the many
  small §10 habitats add little individually.
- **Per-stand corridor score:** 42,005 of 168,026 stands score above zero
  (25%); the top decile of those is the baseline connectivity-priority set.
  Written to `data/interim/f/stand_connectivity_scores.gpkg` (plus
  `patches.gpkg` with dPC, `corridor_density.tif`).

### F3b - sensitivity sweep and the robust set (done, 2026-09-06)

`perturb_resistance_cfg` + `sensitivity_sweep` in `src/f_connectivity.py`.
`_coarsen` was split so the sweep can coarsen an in-memory resistance array
(`_coarsen_array`) without a raster round-trip per run.

Each of the **20 runs** (`resistance_sensitivity_runs`, seeded) perturbs the
*ecological* assumptions and leaves the numerical settings fixed: every
resistance weight `*= 1 + U(-0.4, 0.4)` then renormalised (draws spanned age
0.20-0.43, structure 0.13-0.37, species 0.15-0.30, land cover 0.16-0.39); every
land-cover category resistance `*= 1 + U(-0.3, 0.3)` clipped to [0.02, 1];
`dispersal_cost *= 1 + U(-0.5, 0.5)` (4,600-12,000). The patch set is fixed -
the F1 nodes do not depend on the resistance model. Each run recomputes the
cost surface, the 786x786 least-cost matrix, the backbone corridors and the
per-stand corridor score, and records which stands land in that run's top
decile (~4,400 stands per run).

**The connectivity index is assumption-sensitive; the ranking is not.**
Probability of Connectivity ranged **0.196 to 0.414** across the 20 runs
(median 0.363) - a ~2x swing, exactly the reason the plan requires this sweep.
But the per-stand `top_decile_runs` histogram is sharply bimodal: **162,212
stands never top-decile, ~65-250 stands each appearing in 1-19 runs, then 466
in 19 runs and 3,029 in all 20.** A stand is almost always high-priority or
almost never - the ordering barely moves when the resistance model does.

**Robust set: 3,783 stands, 8,546 ha** (top-decile in >= 80% of runs -
`robust_top_decile_frac`). That is ~85% of any single run's top decile, so the
baseline F3a ranking was already close to the robust one. Written to
`data/interim/f/stand_connectivity_robust.gpkg` (`mean_score`,
`top_decile_runs`, `robust`); per-run parameters and PC in
`sensitivity_runs.json`.

---

## 4. Results and what they mean

- **The protected-area network here is anchored by a few large Natura sites**
  (two patches carry ~70% of the connectivity by dPC); the ~2,100 small §10
  habitats are stepping stones that matter collectively, not individually.
- **The robust connectivity-priority set is 3,783 stands (8,546 ha)** - the
  stands that rank in the top decile for "where a Plus retention measure would
  most help link the network" across 20 perturbations of the resistance model.
  They sit along the least-cost backbone between the anchor patches.
- **The Probability of Connectivity index itself moves ~2x with the
  assumptions (0.20-0.41)** and is not reported as a headline number; the
  robust *ranking* is what survives the sweep, and that is what the deliverable
  is - presented as exploratory prioritisation, not a recommendation. This is
  the least certain of the six modules and the README will say so.

---

## 5. Caveats and open items

- ymparistotuki contributes only 10 tiny polygons in this AOI; the open Kemera
  data has no passive habitat-conservation ymparistotuki contracts, only the
  workcode-641 nature-management project polygons. The node network is
  effectively protected areas + §10 habitats + old stands.
- "old stand" is a single `meanage >= 120 yr` cut with no structural-richness
  refinement yet (basal area, deadwood, multi-storey) - the plan's "old **or
  structurally rich**" is only half-implemented at F1.
- The sweep perturbs the resistance weights, land-cover values and dispersal
  cost but not the structural choices - node sources, the 200 m patch merge,
  the 128 m grid, the backbone-k and corridor-slack. Those are fixed; a fuller
  treatment would vary them too.
- The 20-run sweep took ~30-40 min of compute (a laptop-sleep stretched the
  wall clock to ~3 h). `patch_least_cost` (786 MCP accumulations) dominates;
  raising `patch_min_area_ha` or `coarsen_factor` is the lever if the sweep
  needs to be cheaper.
