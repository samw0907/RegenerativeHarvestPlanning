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

### E1b - full-AOI channel network derivation (done, 2026-09-05)

`src/e_plus_site_planning.py`: `prepare_flow_accumulation` (BreachDepressionsLeastCost
-> D8Pointer -> D8FlowAccumulation, computed once) and `extract_channel_network`
(ExtractStreams at a given threshold -> RasterStreamsToVector), per the D8
decision in section 2.2. `cells_for_distance` (physical distance -> whole cell
count at a given resolution, unit tested) keeps the breach search radius
comparable in real terms to D1's, rather than reusing D1's raw cell count,
which meant something different at 2 m.

**Engineering note caught during this step, not before it:** the first version
ran breach+pointer+accumulation inside the same function as the per-threshold
extract+vectorise step, so deriving multiple waterway-class thresholds meant
redoing the ~450 s accumulation step every time (measured directly: three
separate calls at 0.5/2/10 ha took 450, 445 and 454 s each - the extraction
step is not what dominates the runtime). Refactored to compute the
accumulation raster once and reuse it: the remaining three thresholds (1, 2,
4 ha - only 2 ha was already done) then took **1-5 s each**, not 450 s.

**Full-AOI results, all 5 of D1's thresholds (16 m, D8):**

| threshold (ha) | n segments | length (km) | density (km/km²) |
|---|---|---|---|
| 0.5 | 377,903 | 37,539 | 11.04 |
| 1.0 | 184,407 | 25,471 | 7.49 |
| 2.0 | 92,805 | 17,831 | 5.24 |
| 4.0 | 46,656 | 12,632 | 3.72 |
| 10.0 | 18,509 | 8,105 | 2.38 |

**A genuine validation check, run because the 0.5 ha density looked high
enough to be worth distrusting, not because it was asked for.** At 16 m, a
0.5 ha channel-initiation threshold needs only ~20 contributing cells
(0.5 ha / 0.0256 ha per 16 m cell) - a far less discriminating bar than the
same 0.5 ha threshold's 1,250 cells at D1's 2 m, so a dense, noise-inflated
network was a real possibility worth checking, not assuming away. The check:
does channel length scale across thresholds the way a real drainage network
does? Real channel networks follow an approximately power-law relationship
between total length and the contributing-area threshold (Horton's laws /
Rodriguez-Iturbe & Rinaldo's river network scaling, commonly close to
length ~ threshold^-0.5 empirically) - noise-dominated artefacts would not be
expected to follow this cleanly. The four consecutive threshold steps here
give implied exponents of **-0.56, -0.51, -0.50, -0.48** - tightly clustered
around the expected -0.5 across the *entire* range, including the 0.5 ha step
that prompted the check. The 10 ha ("major streams only") density of
2.38 km/km² also sits inside commonly cited real-world drainage-density ranges
for well-developed channel networks, an independent cross-check in the same
direction. Read together, this is reasonable evidence the derived network is a
credible channel hierarchy at all 5 thresholds, not a 16 m-resolution noise
artefact - though see the caveat below on what a Finnish managed-forest
network actually contains at the wet end.

### E1c - mapped hydrography fetch and the buffer comparison (done, 2026-09-05)

**`nls.fetch_topographic` implemented, deviating from `DATA_SOURCES.md`'s
per-block-directory route.** The plan called for resolving the AOI to NLS
1:100k block codes (`shp/{block}/...`) to avoid downloading a multi-GB national
file. Instead this reads the single national `MTK-virtavesi` GeoPackage (6.6 GB)
directly via GDAL `/vsicurl/` with a bbox filter, the same pattern already used
for the SYKE catchment fetch (`syke.fetch_catchment`) - the Funet mirror sends
`Accept-Ranges: bytes`, so GDAL's spatially-indexed read only pulls the AOI's
features. Confirmed live: 182,525 stream features for the full AOI in 297 s,
cached afterwards (1.9 s on a repeat call). Slower than the block-tiled route
would have been, but simpler for a one-off AOI-scale fetch, and avoids building
a second block/tile-resolution scheme just for this one dataset - a documented
trade-off, not an oversight.

**`rasterize_lines`, `distance_to_features_m` and `buffer_comparison` added -
raster-based, not vector polygon buffering.** At 378k derived-network segments,
buffering each as a vector polygon and unioning them (the "obvious" GeoPandas
approach) is a well-known GEOS performance cliff, and the analytical need here
is an area figure, not buffer polygon geometry. Instead: rasterize both
networks onto the 16 m grid, run a Euclidean distance transform from each
(`scipy.ndimage.distance_transform_edt`, a deterministic algorithm, not a
model), threshold at each buffer width, and count cells - the same raster-first
idiom already used for DTW and the wetness surfaces. Unit tested against a
synthetic 10x10 grid with two known parallel lines, including a buffer width
chosen specifically to produce a real overlap (not just the disjoint case) to
exercise the set-difference ("additional area") logic.

**Full-AOI results** (AOI = 340,000 ha; mapped hydrography's own buffer is
fixed across rows since it does not depend on the derived-network threshold):

| threshold (ha) | 10 m: derived / mapped / additional (ha) | 20 m | 30 m |
|---|---|---|---|
| 0.5 | 60,269 / 31,572 / 47,171 | 139,911 / 64,330 / 96,286 | 169,756 / 74,374 / 113,544 |
| 1.0 | 40,944 / 31,572 / 30,371 | 100,940 / 64,330 / 64,763 | 124,464 / 74,374 / 77,147 |
| 2.0 | 28,632 / 31,572 / 20,143 | 73,015 / 64,330 / 43,653 | 90,873 / 74,374 / 52,141 |
| 4.0 | 20,243 / 31,572 / 13,548 | 52,674 / 64,330 / 29,475 | 65,941 / 74,374 / 35,166 |
| 10.0 | 12,949 / 31,572 / 8,217 | 34,238 / 64,330 / 17,979 | 43,058 / 74,374 / 21,437 |

**A striking number was checked before being treated as a result, not reported
on its own.** The 0.5 ha / 30 m cell reads as "additional" buffer area of
113,544 ha - roughly a third of the entire AOI, and the derived network's own
30 m buffer at that threshold (169,756 ha) is very close to half the AOI,
about double mapped hydrography's own 30 m buffer share (74,374 ha, 21.9% of
the AOI - an independent, sane-looking figure in its own right). A number this
large deserves the same scrutiny the D1 tool-choice error should have gotten
from the start, not acceptance because it is analytically convenient. Two
things support treating it as real rather than a bug: (1) the E1b scaling-law
check already showed the 0.5 ha network is not resolution noise, and (2) the
pattern across thresholds is monotonic and physically sensible - derived
buffer area shrinks steadily as the threshold rises, mapped hydrography's own
figure is threshold-invariant (correct, since it is one fixed dataset every
row), and at 10 ha the derived network is *sparser* than mapped hydrography
(12,949 ha vs 31,572 ha at 10 m) - expected, since MTK-virtavesi is a
comprehensive cartographic product while a 10 ha D8 threshold only captures
the largest channels.

**What the number does not mean, stated plainly:** it is not "hectares of
natural stream buffer mapped hydrography failed to capture." Per the E1b
caveat, the wet end of this range almost certainly includes a large share of
Finnish managed-forest drainage ditches, which a low flow-accumulation
threshold cannot distinguish from natural headwater streams - this repository
has no independent ditch-network layer to separate the two. The honest framing
for the README is a **range across waterway-class thresholds**, not a single
headline figure: 0.5-1 ha as an inclusive upper bound (streams and drainage
features combined), 10 ha as a conservative lower bound (major channels only,
where the "additional" figure - 21,437 ha at 30 m, 6.3% of the AOI - is a much
more defensible "mapped hydrography misses this" claim), with 2-4 ha as the
middle ground most likely to represent genuine small natural streams without
being ditch-dominated. Reporting the full table, not a cherry-picked row, is
the point - the same sensitivity-sweep discipline Module F's connectivity work
is already committed to.

### E2 - peatland continuous-cover prescription (done, 2026-09-06)

`select_ccf_peatland` and `ccf_area_summary` in `src/e_plus_site_planning.py`:
the Plus "lush drained spruce-dominated peatland" category as a four-way filter
on the Metsakeskus stand layer, all fields read directly (same conventions as
D3): `soiltype >= 60` (peat/organic), `fertilityclass <= 3`
(lehto..mustikkaturvekangas), `drainagestate in {7, 8, 9}`
(ojikko/muuttuma/turvekangas - the drained-mire transformation stages), and
`proportionspruce >= 0.5`. The fertility cut is the one genuine judgement call
- strict "reheva" is `<= 2`, but the practical CCF-on-spruce-peat guidance
(Tapio) covers down to mustikkaturvekangas (`<= 3`), so `<= 3` is the config
default and `<= 2` is reported alongside it, not buried. All parameters are in
`config/pipeline.yaml` `module_e_plus.ccf_peatland`; unit tested on synthetic
stands including the boundary case and string/NaN coercion.

**Full-AOI stand fetch:** 168,026 stands, 235,077 ha, in 351 s (WFS paging,
cached afterwards). Note this is ~69% of the 340,000 ha AOI - the Metsakeskus
stand layer is private forest land with a management plan, so state
(Metsahallitus) forest and non-forest land are simply absent. Every figure
below is "of the private-forest supply area", not the whole AOI.

| quantity | area (ha) | share |
|---|---|---|
| total private-forest stand area | 235,077 | - |
| peatland forest (`soiltype >= 60`) | 26,373 | 11.2% of stand area |
| drained peatland forest | 21,124 | 80% of peatland |
| ... spruce-dominated | 2,359 | 11% of drained peatland |
| ... fertility `<= 3` | 5,568 | 26% of drained peatland |
| **CCF-eligible (all four filters)** | **1,674** | **7.9% of drained peatland, 0.7% of stand area** |
| CCF-eligible at strict fertility `<= 2` | 141 | 0.7% of drained peatland |

**What binds, and why the number is small.** The result held up to a
which-filter-dominates check: drained peatland here averages 60% pine / 23%
spruce by volume share - it is overwhelmingly pine mire (rame), and the
spruce-dominated subset is only 2,359 ha. Species is the hard constraint, then
fertility (of those 2,359 ha, 1,674 ha - 71% - are also rich enough). So
~1,700 ha of lush drained spruce peatland across the supply area is not a
disappointing result to explain away; it reflects that spruce mires (korvet)
are the uncommon fertile minority of Finnish peatland forest, which is exactly
why Plus singles them out. The strict-fertility figure (141 ha) is an order of
magnitude smaller - the `<= 3` vs `<= 2` choice genuinely moves the headline,
hence reporting both.

**On the "+30%" target.** Plus's 2030 target is "+30% share of continuous
cover forestry in peatland forest regeneration" - a *relative* increase against
an unpublished baseline CCF share, so "% of target met" is not computable and
is not claimed. What E2 delivers instead is the addressable area: ~1,700 ha of
regeneration felling that the prescription would move from clearcut to
group/selection cutting if Plus were applied supply-area-wide, plus the
sensitivity to the fertility-band choice.

**Independent cross-reference.** Metsakeskus's own `cuttingtype_ccs` field (a
continuous-cover silviculture proposal) is set on 264 of 168,026 stands
(0.16%) - far sparser than our 1,674 ha eligible set and not peatland-specific,
so not a validation, but it confirms CCS is currently a rare proposal in this
data, consistent with Plus targeting an increase from a low base.

Not yet built: RUSLE erosion risk; the per-stand site-plan record assembly and
`figures.py` / `run.py`.

### E3 - the Plus CCF vs root-rot conflict overlay (done, 2026-09-06)

Two functions in `src/e_plus_site_planning.py`, both reusing existing D2/D3
logic unchanged, run on the full-AOI stand data and the 55-year FMI record.

**1. Stand overlap (`ccf_rootrot_conflict`).** Applies D3's `species_soil_rule`
to the E2 CCF-eligible set. 100% of it - 1,673.7 ha / 1,581 stands - also
triggers the root-rot species/soil rule. This is forced by the filter
definitions: the CCF filter requires spruce share >= 0.5 on peat, and the
peat-soil root-rot trigger is spruce share >= 0.5, so the two select the same
stands. Kept as a one-line fact, not a result in its own right.

**2. Conflict-free felling window (`conflict_free_felling_window`).** The
substantive calculation. Counts days per winter that are both frozen ground
(D2's `frozen_ground_days` proxy - the trafficability route the plan assumes
for CCF felling on wet peat) and outside the root-rot mandatory stump-treatment
period (1 May - 30 Nov). One figure for the whole CCF-eligible set: those
stands are all peat/drained/spruce/lush in one AOI with one FMI station and the
mandatory period is a fixed national calendar, so there is no per-stand
variation to compute.

Result, by decade (station 101537, 53 complete winters):

| decade | mean conflict-free days/winter |
|---|---|
| 1970s | 109.6 |
| 1980s | 111.8 |
| 1990s | 109.7 |
| 2000s | 103.7 |
| 2010s | 93.4 |
| 2020s (4 winters) | 106.8 |

Overall mean ~106 days/winter, range 61-131.

**Reading of the result.** The window is ~106 days a year and the long-run
decline is modest - about 3 days between the first and last decade means, well
inside the winter-to-winter spread (61-131). The one clear feature is a 2010s
dip to ~93, with a partial recovery in the (short, noisy) 2020s sample. This is
a smaller effect than the raw frozen-ground-day trend elsewhere in this
project (D3's +30-day warm-season lengthening, and total frozen-ground days
falling ~134 -> ~110 over the record), and the reason is specific: the
frozen-ground days lost to warming are mostly at the November and April
shoulders, and the November ones sit inside the mandatory period already, so
removing them does not change this count. The Dec-Apr core that this window
depends on has been comparatively stable.

So the honest statement for the README is: the CCF prescription applies to
~1,700 ha that the root-rot rule also covers, and those stands have roughly a
three-and-a-half month annual window in which felling avoids both the
bearing-capacity limit and the treatment obligation - a window that dipped in
the 2010s but has not shown a strong sustained decline over the record. Not
"the window is closing".

Unit tested: the stand overlap (synthetic stands, boundary spruce share) and
the window count (synthetic weather with frost runs placed inside and outside
the mandatory period).

### E4 - §10 valuable-habitat proximity (done, 2026-09-06)

`habitat_proximity` in `src/e_plus_site_planning.py`. `fetch_layer("habitat")`
returns 2,099 Forest Act §10 valuable-habitat polygons for the full AOI
(1,072 ha total, median 0.32 ha, all polygons; fetched in 3 s, cached). Two
`habitattype` values: type 1 (1,768 polygons) and type 3 (331). A single
`gpd.sjoin_nearest` gives every stand its distance to the nearest habitat
(21 s for 168,026 stands); each setback width then counts the stands and stand
area within it, split by the nearest habitat's type.

| setback | stands within | stand area within (ha) | % of stand area | nearest type 1 / type 3 (ha) |
|---|---|---|---|---|
| 10 m | 8,695 | 11,709 | 5.0% | 9,981 / 1,728 |
| 20 m | 9,760 | 13,488 | 5.7% | 11,536 / 1,952 |
| 30 m | 10,712 | 15,013 | 6.4% | 12,858 / 2,154 |

**Reading.** About 5-6% of private-forest stand area is within a Plus-scale
setback of a §10 habitat - a real operational constraint, not a dominant one.
The affected area barely grows from 10 m to 30 m (11,709 -> 15,013 ha): the
habitats are small scattered polygons (~1 per 1.6 km²), so once the stands that
touch them are counted, widening the setback only picks up a thin fringe more.
The type split tracks the polygon counts - ~85% of the affected area is nearest
a type-1 habitat.

**What the number is and is not.** "Stand area within" is the area of every
stand that has any part inside the setback - a large stand touching one small
habitat contributes its whole area. It is "stand area subject to a §10 setback
constraint when harvested", not the area that must be left uncut (the actual
retained strip is a thin buffer, far smaller). There is no single legal setback
distance for §10 habitats - the Forest Act requires preserving their special
characteristics without naming a width - so this is swept at the Plus
waterway-buffer widths (config `habitat_setback_widths_m`) rather than asserting
one number.

Unit tested with three stands at known 5 / 15 / 25 m gaps from one habitat
polygon.

### E5 - RUSLE erosion risk (in progress)

DERIVE AND BENCHMARK: build `A = R * K * LS * C * P` on the D1 validation
catchment (148 km², 2 m), compare against Metsakeskus's own WCS
`RUSLE-eroosiomalli` product (2 m, t/ha/yr), quantify agreement, then consume
the Metsakeskus product at AOI scale for the "where do buffers matter most"
cross-reference. Same shape as D1's DTW. P = 1 (no support practices in
forestry).

**Honesty note, pre-committed from Project 1:** our LS and Metsakeskus's RUSLE
both come off the same NLS 2 m DEM, so agreement on the terrain-driven part is
expected, not independent validation - stated plainly in the benchmark writeup.

**Factor method decisions (discussed one at a time, 2026-09-06):**
- **R** (rainfall erosivity): a single published constant for central Finland
  from Panagos et al. 2015 (*Rainfall erosivity in Europe*), not derived from
  FMI data - proper R needs sub-hourly intensity we do not have, R is a scalar
  that does not affect the spatial benchmark, and this is the source the
  European RUSLE product uses.
- **K** (soil erodibility): a config lookup from Metsakeskus `soiltype` code
  groups (till / sorted fines / coarse sand / peat / organic) to K values from
  Nordic RUSLE literature. Class-mean approximation, but it is the distinction
  that dominates Finnish erodibility and it lets K shape the risk pattern.
- **C** (cover-management): CORINE Land Cover, C per class from the Panagos 2015
  land-cover method. Needs `syke.fetch_clc` built. Full-AOI surface; check for a
  CLC2024 release (TASK 00 D4), else CLC2018.

#### E5a - LS factor (done, 2026-09-06)

`ls_factor` in `src/e_plus_site_planning.py`: Moore & Burch (1986)
unit-stream-power form, `LS = (A_s / 22.13)**m * (sin theta / 0.0896)**n`, with
`m = 0.4`, `n = 1.3` (config `module_e_plus.rusle`). A_s (specific catchment
area, m) = flow-accumulation cells x cell size, capped at 100 m so near-channel
cells do not diverge - LS is hillslope wash, not channel routing. Reuses the
two rasters D1 already produced for the catchment (`slope_deg.tif`,
`dinf_accum_cells.tif`); no new terrain processing. Unit tested against a
hand-computed value and the flat-cell / nodata zero cases.

Catchment result: LS median 0.13, mean 0.66, p95 3.1, p99 6.1, max 42, with
54% of cells non-zero (the rest dead-flat or outside the polygon). Low values
are expected - D1 already established this catchment is very flat (slope
median 1.55 deg). Written to `data/interim/e/ls_factor_catchment.tif` for the
assembly step.

Next: K (soil-class lookup, rasterised from the catchment stand polygons), then
C (`fetch_clc` + CLC reclass), then R (Panagos constant), then assemble A and
benchmark against the Metsakeskus WCS product.

#### E5b - K factor (done, 2026-09-06)

`k_factor` in `src/e_plus_site_planning.py`: maps each stand polygon's
Metsakeskus `soiltype` code to a RUSLE K value via a flat config table
(`module_e_plus.rusle.k_by_soiltype`, 23 codes), then rasterises onto the LS
grid. The SoilTypeType code list came from Project 1's cached KOOD V35 workbook
notes. K values are from Panagos et al. 2014 (*Soil erodibility in Europe*)
ranges plus Finnish context, grouped as: coarse till / coarse mineral 0.025;
coarse sorted (glaciofluvial) 0.013; fine-textured mineral 0.043 (the
erosion-prone class); stony 0.020; bedrock 0.005; peat 0.015; Metsakeskus's own
"eroosioherkka" (erosion-sensitive) peat codes 64-67 0.030; mould/gyttja 0.025.
Unit tested (code mapped, unknown code and off-polygon gap both fall to the
default).

`stand_coverage_mask` added alongside: the Metsakeskus stand layer is
private-forest only and covers **60% of the catchment bbox grid**, so off-stand
cells get a flat `k_default` (0.025) and their `A` is not a real derivation.
The benchmark against Metsakeskus's RUSLE will be computed on stand-covered
cells only, and this mask is what restricts it.

Catchment K on stand-covered cells: 67% at 0.025 (coarse till - the dominant
Finnish soil), 12% fine mineral (0.043), 12% stony, 8% peat, <1% each sorted
coarse and rock. Mean K 0.026, which matches Panagos 2014's Finland mean
(~0.028-0.032) - a reassuring cross-check that the class values are in the
right range. Written to `data/interim/e/k_factor_catchment.tif` (and
`stand_coverage_catchment.tif`).

Next: C (`fetch_clc` + CLC reclass), then R (Panagos constant), then assemble A
and benchmark.

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
- The 0.5 ha network's scaling behaviour is credible, but that does not mean
  every segment in it is a natural stream. Finnish managed forest on peatland
  is heavily ditched (ojitus) for drainage, and a dense artificial ditch
  network is exactly the kind of converging-flow feature a low threshold would
  also pick up - the D8 accumulation surface cannot distinguish "small natural
  headwater stream" from "forestry drainage ditch" by construction. Both
  arguably matter for the water-protection buffer question the module is
  built to answer, but the results writeup should name the network as "small
  streams and drainage features" at the wet end, not claim it is purely
  natural channels mapped hydrography failed to capture.
