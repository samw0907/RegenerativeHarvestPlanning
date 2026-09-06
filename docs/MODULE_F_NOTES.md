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

---

## 4. Results and what they mean

(F1 nodes + F2 baseline resistance so far - see the tables above)

---

## 5. Caveats and open items

- ymparistotuki contributes only 10 tiny polygons in this AOI; the open Kemera
  data has no passive habitat-conservation ymparistotuki contracts, only the
  workcode-641 nature-management project polygons. The node network is
  effectively protected areas + §10 habitats + old stands.
- "old stand" is a single `meanage >= 120 yr` cut with no structural-richness
  refinement yet (basal area, deadwood, multi-storey) - the plan's "old **or
  structurally rich**" is only half-implemented at F1.
