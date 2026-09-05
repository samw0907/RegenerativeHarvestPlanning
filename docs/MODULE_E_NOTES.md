# Module E - notes, decisions and rationale

Running record of *why* Module E is built the way it is and *what the results
mean*. Source material for the final README. Companion plan:
`PROJECT_2_REGENERATIVE_HARVEST_PLANNING.md`, Module E section.

---

## 1. What Module E is

Turns the Metsä Group Plus regenerative-forestry targets into a per-stand site
plan across the full AOI (the Äänekoski mill procurement area): waterway
buffers from our own derived stream network, a peatland continuous-cover
prescription, retention/deadwood targets, valuable-habitat proximity, and a
conflict overlay against Module D's root-rot risk.

---

## 2. Design decisions

### 2.1 Deadwood deficit (TASK 00 Decision D2) - resolved 2026-09-05

Carried in unresolved from TASK 00: MS-NFI 2023 has no standing-deadwood theme
(confirmed - the 45 themes are stand/volume and living-tree biomass only), so
the Plus deadwood target (>=20 dead trees/ha, plus 10 high-biodiversity stumps/ha
against a 4/ha baseline) had no obvious per-stand data source. Left deferred
until Module D was built and the picture was fuller, per Sam's own call in
`TASK_00_FINDINGS.md`.

**The remaining candidate was checked live, not assumed.** Metsakeskus's
`v2/habitat` layer does carry a `deadwoodpotential` field - fetched for the D1
catchment (167 habitat polygons) to check it. It is **null on every single
polygon**, and habitat polygons cover only 76.6 ha of the 148 km² catchment
(under 0.1%) even where populated - it could never stand in for a per-stand
measure across general production forest, only the small fraction of stands
that overlap a mapped §10 habitat. No per-stand or per-pixel deadwood source
exists anywhere in the open data checked for this project.

**Decision: aggregate regional statistic only, no per-stand deficit map.**
Three options were on the table (drop entirely; per-stand qualitative proxy
via `deadwoodpotential`; model from mortality/biomass) plus this one; Sam chose
the aggregate-statistic route. Cite a published Luke VMI figure - the most
recent available, the VMI2022 rolling update, gives **5.5 m³/ha total dead wood
in Etelä-Suomi** (the AOI's VMI reporting zone), of which Luke's own reporting
states over 70% is lying deadwood (maapuu) and the remainder standing
(pystypuu) - recorded in config as `deadwood_vmi_m3_per_ha: 5.5` and
`deadwood_vmi_standing_share: 0.3`. Applied to the AOI's total forest area,
this gives one supply-area-scale current-stock figure, reported **alongside**
the Plus stems/ha target rather than combined into a single deficit
percentage: volume (m³/ha) and stem count (trees/ha) are different units, and
converting between them needs an average-snag-volume constant that has no
sourced regional value - manufacturing one would be exactly the "substitute a
proxy silently" the plan's own text warns against. Retention-tree and stump
targets remain flat legal constants (Plus's own published numbers), not
per-stand gap-to-target maps, for the same reason: no per-stand current-state
source exists for those either beyond what Metsäkeskus stand stem-count/basal-
area fields can approximately support.

This does not become a per-stand column in Module E's site-plan output. It is
one number (or a small table by forest type) reported once, in the results
writeup and the "what the 2030 targets mean physically" talking point the plan
itself names.

### 2.2 Channel-network derivation scale for waterway buffers

D1's DTW reimplementation deliberately stayed at the 148 km² validation
catchment: Luke's official DTW *raster* is a full-AOI benchmark product to
consume once agreement is demonstrated, per the three-tier rule ("do not
reprocess a full AOI where the benchmark pattern applies").

Waterway buffers need something different: an actual **stream *vector*
network** to buffer at 10/20/30 m and compare against mapped NLS hydrography.
Luke does not publish one - DTW is a continuous wetness raster, not a
discretised channel network - so this specific piece is **DERIVE ONLY**, not
DERIVE AND BENCHMARK (matches the plan's own data table). The three-tier
rule's "don't reprocess a full AOI" guidance is about *not* redoing work an
official product already covers; it does not apply here, because there is no
official product to fall back on for the rest of the 3,400 km² AOI. Restricting
this to the validation catchment would leave Module E's headline "hectares
mapped hydrography misses" finding covering under 4% of the actual mill supply
area the plan frames it around.

At the same time, running D-infinity flow accumulation across the full AOI at
the config's native 2 m DEM resolution is roughly 850 million cells - the exact
scale CLAUDE.md's three-tier rule flags as the wrong engineering call, and here
for what is fundamentally an illustrative buffer-area comparison, not a core
wetness index like DTW itself.

**Decision (Sam, 2026-09-05): full AOI, at a coarser resolution.** Resample the
DEM to **16 m** (config `channel_network_resolution_m`) for the AOI-wide
channel-network derivation - chosen to match MS-NFI's native 16 m grid exactly,
so the derived channel/buffer layer joins MS-NFI's fertility/drainage/spruce-
share themes (needed for the peatland CCF prescription and the conflict
overlay) without a second resampling step, rather than picking an arbitrary
coarser value. At 16 m the full AOI is ~13.3 million cells - the same order of
magnitude as rasters already handled comfortably in Project 1, not a new class
of problem. D1's validated 2 m catchment work is unaffected and remains the
high-fidelity demonstration that the underlying method (D-infinity +
elevation-above-stream) is sound; this is a resolution trade-off for the
AOI-wide *application* of that already-proven method, and is stated as such
rather than left implicit.

---

## 3. Method and results

### E1a - full-AOI DEM: fetch and resample (done, 2026-09-05)

`fi_forest_data.nls.resample_dem` added: block-averages a DEM GeoTIFF to a
coarser resolution (`Resampling.average`, the physically appropriate reduction
for elevation), used to implement the 16 m full-AOI decision from 2.2. Unit
tested against a synthetic gradient raster (checks a known block average and
that a finer target resolution is rejected).

Fetched the full 3,400 km² AOI at 2 m via `fetch_dem_tiled` (48 tiles, 9 km
grid) - **966 s** (~16 min), matching the D1 catchment's per-tile timing
(~20 s/tile) scaled up to 48 tiles. Resampled to 16 m in 4 s. Result: shape
(4250, 3125), exactly `50000/16 x 68000/16`, bounds match the AOI bbox exactly,
**zero nodata cells** (no tile gaps), elevations 81-269 m (plausible for Central
Finland), and the 16 m resample's sampled min/max/mean match the 2 m mosaic's
to within rounding - confirms the averaging did not introduce artefacts.

---

## 4. Results and what they mean

(not yet built)

---

## 5. Caveats and open items

- The 16 m channel-network resolution is coarser than D1's validated 2 m
  catchment work; small headwater streams resolvable at 2 m will not all
  survive to 16 m. The buffer-area comparison at AOI scale should be read as
  "at least this much extra area, at 16 m fidelity" rather than a precise
  fine-scale figure - the 2 m catchment result is the fidelity benchmark.
- `deadwood_vmi_m3_per_ha` (5.5) and `deadwood_vmi_standing_share` (0.3) are
  read from a web search of Luke's own published news reporting on the
  VMI2022 update, not yet cross-checked against the primary PxWeb table or a
  formal Luke publication PDF - worth pinning to a citable primary source
  before the figure appears in the README, not just a paraphrased news figure.
