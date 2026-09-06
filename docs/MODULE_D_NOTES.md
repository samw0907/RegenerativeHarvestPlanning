# Module D - notes, decisions and rationale

Running record of *why* Module D is built the way it is and *what the results
mean*. Source material for the final README. Companion plan:
`PROJECT_2_REGENERATIVE_HARVEST_PLANNING.md`, Module D section.

---

## 1. What Module D is

For every stand in the AOI: when can it be harvested, and what stump treatment
does it trigger. Three parts on one hydrology/terrain backbone:

- **D1 - reimplement depth-to-water (DTW)** on a validation catchment and
  benchmark it against Luke's own 2023 CMv2 product.
- **D2 - extend it** with a weather term (dynamic threshold selection from FMI
  data) and a soil term (peat vs mineral bearing capacity), turning five static
  wetness maps into a dated surface.
- **D3 - root rot obligation** as a deterministic rule engine from the Forest
  Damages Prevention Act.

---

## 2. Design decisions

Carried in from TASK 00 (`docs/TASK_00_FINDINGS.md`), not re-litigated here:
DTW product = 2023 CMv2 (decision D3), thresholds `[0.5, 1, 2, 4, 10]` ha,
values in centimetres; D1 validation catchment = SYKE `FI1-14.06.161`
(148 km², bbox `[414920, 6945300, 429010, 6964880]`); FMI station = 101537
(Viitasaari Haapaniemi, daily since 1970).

### 2.1 Two blocking data-access gaps, closed before any D1 analysis (2026-09-05)

Both `fi_forest_data` functions needed for D1 were stubs or under-scoped when
copied from Project 1 (which had no use for either):

- **`nls.fetch_dem` caps at 100 km2 per request** (the NLS OGC API Processes
  bbox limit). The validation catchment (148 km2) and the full AOI (3,400 km2)
  both exceed it. Added **`nls.fetch_dem_tiled`**: splits the AOI into a grid of
  <= 100 km2 tiles (default 9x9 km = 81 km2), fetches each through the existing
  `fetch_dem` (so each tile is independently cached), mosaics with
  `rasterio.merge`. Verified on the catchment: 6 tiles, 119 s.
- **`luke.fetch_dtw` was a NotImplementedError stub.** Checked the live Funet
  mirror directly rather than assuming a layout: DTW 2023 CMv2 is delivered as
  flat per-threshold directories of 6x6 km tiles named by the NLS UTM10
  mapsheet code (`DTW_INT_CMv2_{050,1,2,4,10}/{sheet}.tif`, e.g. `K3222B.tif`;
  confirmed Int16, EPSG:3067, nodata 32767 against a live tile). This is the
  same mapsheet grid Module A's ALS fetch already resolves, so `fetch_dtw`
  reuses that resolver (promoted from private `_mapsheets_for_bbox` to public
  `nls.mapsheets_for_bbox`, since it is now shared across modules) rather than
  parsing Luke's own tile-index shapefile. Verified on the catchment: all 5
  thresholds, 23-44 s each.

Both are gated on `NLS_API_KEY` (the same free key from Project 1 - one
account, not project-scoped; Sam copied `config/.env` across).

### 2.2 First live data check: DTW threshold ordering (2026-09-05)

Sanity check from the DTW product description: wet-fraction (share of pixels
with DTW <= 1 m) should fall monotonically as the channel-initiation threshold
rises, since a larger threshold means fewer, larger channels and so a smaller
area is close to one. On the validation catchment:

| threshold | wet fraction (DTW <= 1 m) | max DTW value |
|-----------|---------------------------|----------------|
| 0.5 ha | 0.412 | 37.3 m |
| 1 ha | 0.322 | 44.8 m |
| 2 ha | 0.242 | 52.6 m |
| 4 ha | 0.177 | 56.7 m |
| 10 ha | 0.113 | 68.3 m |

Monotonic as expected, and in the same range DATA_SOURCES.md records from an
independent spot-check (44% -> 13% on a different P2 tile). All five rasters
share the same valid-pixel count (48,858,046), confirming a consistent extent
and nodata mask across thresholds. This is a data-integrity check, not yet the
D1 analysis (our own DTW reimplementation and its benchmark against this
product) - it confirms the fetched reference product is sound before building
anything against it.

---

## 3. Method and results

### D1a - blocking data-access pieces + DTW reference fetch (done)

See 2.1-2.2 above. Cached: DEM mosaic for the validation catchment
(`data/raw/nls/dem2m_mosaic_fi1_14_06_161.tif`), all 5 DTW thresholds
(`data/raw/luke/dtw2023_{050,1,2,4,10}ha__fi1_14_06_161.tif`).

### D1b - the exact catchment polygon (done)

The DEM/DTW fetch in D1a used the catchment's **bounding box**; the actual
comparison needs the true non-rectangular SYKE polygon (a rectangle would
compare pixels outside the real watershed). Implemented
`syke.fetch_catchment`: no route existed for this yet (Project 1 never touched
SYKE), so checked the live `valumaalueet.zip` (259 MB) directly rather than
assuming a layout - opened via GDAL's `/vsizip//vsicurl/` (the server sends
`Accept-Ranges: bytes`, so this reads only what a `WHERE` query needs, not the
whole archive). Found layers `Valumaaluejako_taso{1..5}` + `_purkupiste`
(outlets); the id field is `taso4_osat`. Queried `FI1-14.06.161` directly:
**148.22 km2**, bounds exactly matching the bbox already in
`config/pipeline.yaml` - confirms the two were derived from the same source.
The source CRS has no top-level EPSG authority tag (a raw PROJCS matching
ETRS-TM35FIN's parameters exactly), so `fetch_catchment` sets EPSG:3067
explicitly rather than trusting an inferred CRS.

### D1c - reimplement DTW: wrong tool first, root-caused, corrected (2026-09-05)

Implemented `src/d1_dtw_derive.py`: clip DEM to the true catchment polygon,
`BreachDepressionsLeastCost` (Lindsay 2016, via WhiteboxTools - confirmed
15,056,943 of 37 M cells were single/multi-cell pits, normal for a 2 m LiDAR
DEM), `DInfFlowAccumulation` for channel delineation, a per-threshold streams
raster from the cell-count equivalent of each ha threshold. One bug fixed along
the way: `WhiteboxTools.set_working_dir` needs an **absolute** path - a
relative one resolves against the external `whitebox_tools.exe` process's own
cwd, silently producing no output. Added an explicit output-exists check after
every WhiteboxTools call so this fails loudly next time.

**First attempt was wrong, not just divergent, and Sam was right to push back
on accepting it.** The first version used `DownslopeDistanceToStream(dinf=True)`
- horizontal flow-path distance to the nearest channel cell. Result: **30-40x**
higher than Luke's product at every threshold (median 50.8 m vs Luke's 1.55 m
at 0.5 ha), correlation only 0.39-0.47. Investigated rather than either
accepting it or dropping it:

1. Ruled out D-infinity as the cause: re-ran the same tool in D8 mode - same
   ~40x inflation (median 59 m). Not a D-infinity quirk.
2. Tested the "missing slope floor" hypothesis directly, using WhiteboxTools'
   `CostDistance` with an explicit floor (0.5-5 degrees swept) on a
   slope-based friction surface. **Made it worse** (median 285-510 m) - this
   ruled out "horizontal distance, just missing a floor" as the fix.
3. Reconsidered what DTW actually represents: a modelled **water-table
   height**, not a horizontal distance. WhiteboxTools has a purpose-built tool
   for exactly that concept - `ElevationAboveStream` (vertical elevation drop
   to the nearest downslope channel cell). Re-ran with that instead.

**`ElevationAboveStream` agrees well, on the corrected, correctly nodata-masked
comparison** (both a Pearson and a Spearman rank correlation - rank matters
here because it tests "does this identify the same relatively wet/dry cells",
which is closer to what D2 actually needs than exact metre-for-metre agreement):

| threshold | n | Pearson r | Spearman r | bias (ours - Luke) | RMSE | median ours | median Luke |
|-----------|---|-----------|------------|---------------------|------|--------------|-------------|
| 0.5 ha | 22.0 M | 0.62 | 0.78 | +2.5 m | 6.5 m | 2.48 m | 1.55 m |
| 1 ha | 21.9 M | 0.68 | 0.81 | +2.7 m | 7.0 m | 3.26 m | 2.18 m |
| 2 ha | 21.8 M | 0.76 | 0.83 | +2.7 m | 7.0 m | 4.15 m | 2.99 m |
| 4 ha | 21.8 M | 0.82 | 0.86 | +2.4 m | 6.7 m | 5.25 m | 4.17 m |
| 10 ha | 21.6 M | 0.87 | 0.88 | +2.2 m | 6.5 m | 7.05 m | 6.14 m |

Correlation rises with threshold (sparser, better-defined channel networks at
higher thresholds agree more); the bias is small, consistent (+2.2 to +2.8 m,
not 30-40x), and has a plausible cause (no culvert-burning, D-infinity vs D8
channel definition, no peatland-specific cost-model-v2 adjustment - Luke's
improvement specifically for drained peat, which this catchment likely has
some of). This is a genuinely usable D1 comparison, not a rationalised bad one.

**Simplifications in this version, flagged not hidden:**
- **No culvert-burning** (lowering the DEM at road/stream crossings). Needs the
  NLS topographic database (`MTK-tie` roads, `MTK-virtavesi` streams), no fetch
  route built yet in this repo - a similar live-probe to the SYKE one above
  would be needed first.
- **`ElevationAboveStream` has no D-infinity/D8 option** - it uses
  WhiteboxTools' own internal downslope-tracing rule for the within-cell trace,
  so D-infinity governs where the channel network is (via
  `DInfFlowAccumulation`) but not the exact path traced down to it.
- **One DEM throughout**, not two. The plan's wording says take elevation from
  the *unmodified* surface while routing flow on the *breached* one;
  `ElevationAboveStream` takes a single DEM for both, so this pass used the
  breached DEM for both. A shallow least-cost breach changes few cells.

### D2a - weather and soil terms (done, 2026-09-05)

The plan states the *goal* ("select the appropriate threshold surface per date
from FMI precipitation, snowmelt and antecedent conditions... interpolate
between threshold surfaces rather than switching abruptly") but not an exact
formula - this is genuinely our extension, not a reproduction. Design, recorded
so the reasoning is traceable:

- **Wetness signal**: a weighted blend of rolling antecedent-precipitation
  sums (7/14/30 day, shorter windows weighted more since they reflect "right
  now" conditions) and an active-snowmelt term (day-over-day snow-depth loss,
  weighted comparably to rainfall). `rrday`/`snow` both use FMI's `-1` "none"
  sentinel, which is clipped to 0 before use, not treated as a negative value.
- **Self-calibration, not an arbitrary cutoff**: the raw wetness signal is
  ranked (percentile) against the station's own **full 55-year record**
  (1970-2024, fetched once and cached - `fi_forest_data.fmi.fetch_daily` now
  caches to CSV, since this record is reused for the later frozen-season-length
  deliverable). Percentile 1.0 (wettest day on record) maps to the 0.5 ha
  threshold, 0.0 (driest) to 10 ha, log-spaced in between (the 5 official
  thresholds are themselves roughly log-spaced).
- **Surface interpolation**: log-*weighted* blend position, but a **linear**
  blend of the raster values themselves - DTW = 0 (a channel cell) is common
  and valid, and interpolating the log of the values would be undefined there.
- **Soil term**: MS-NFI `paatyyppi` (site main type) - confirmed live against
  the D1 catchment: class 1 = kangas/mineral (90.9 %), classes 2-4 = peatland
  subtypes (korpi/rame/letto, 9.1 % combined), consistent with the AOI-wide
  ~13 % from TASK 00. A peat cell's effective DTW is scaled by
  `1 - peat_bearing_penalty` (config: 0.5), reading it as wetter than its raw
  topographic value.

**Validated on real dates from the 55-year FMI record, not synthetic ones:**

| date | event | wetness percentile | selected threshold |
|------|-------|---------------------|---------------------|
| 1980-07-22 | wettest day on record | 1.000 | 0.50 ha (wettest map) |
| 1992-04-26 | peak single-day snowmelt | 0.987 | 0.52 ha |
| 2018-06-02 | 2018 European drought, driest catchment-relevant summer day | 0.000 | 9.99 ha (driest map) |

The threshold selection behaves exactly as intended - genuine wet extremes
(storm and snowmelt) correctly select the wettest map, the well-documented 2018
drought correctly selects the driest. Threshold distribution across the full
record: median 2.0 ha, IQR 1.0-4.0 ha - centred on Luke's own "2 ha = average"
framing, which is a good internal-consistency sign for the calibration.

On the 2018-06-02 demo surface (interpolated at threshold_ha = 9.99, i.e.
almost exactly the 10 ha map): mineral-soil median DTW 6.22 m; peatland raw
median DTW 1.78 m (peat sits in topographic lows, so it already reads wetter
before any adjustment) -> peat-adjusted median 0.89 m. The soil term visibly
does its job: even on the driest day on record, peat is flagged far wetter than
its topography alone would suggest.

Implementation: `src/d2_dtw_extend.py` (pure numpy/pandas, no WhiteboxTools -
fully unit tested, `tests/test_d2_dtw_extend.py`). `fi_forest_data/fmi.py`
gained disk caching for `fetch_daily` and a real fix for `stations_near` (the
WFS bbox filter does not constrain results at all - confirmed empirically;
replaced with a client-side geodesic-distance filter, tested against a live
call: correctly returns 10 stations within 30 km of the P2 AOI, station 101537
at 17.1 km, matching the TASK 00 pick). `fi_forest_data/luke.py` gained the
`soil_main_type` (`paatyyppi`) theme.

### D3a - root rot rule engine (done, 2026-09-05)

`src/d3_rootrot_rules.py`: species/soil trigger (mineral: pine+spruce share >=
50%; peat: spruce share alone >= 50%), the fixed calendar period (1 May-30 Nov),
a cold-spell exemption (any tmin < -10 C in the trailing 21 days before
felling), and `evaluate_obligation` combining all three. Purely deterministic
- no fitted model, no ML question. Fully unit tested
(`tests/test_d3_rootrot_rules.py`), including a real early-May cold-snap case
confirmed against the live FMI record (see below).

**Tested against real stand data.** Fetched Metsakeskus `stand` for the D1
catchment (11,557 stands, first Metsakeskus fetch in this repo): **10.4 % peat
by `soiltype`**, matching MS-NFI's `paatyyppi`-based 9.1 % for the same area
almost exactly - two independent Metsakeskus/Luke data sources agreeing on
the same catchment's soil composition is a good cross-check. The species/soil
rule triggers on **70.4 %** of stands (7,990 mineral + 143 peat) - this
catchment is heavily conifer, so the obligation is the common case, not the
exception, here.

**Cold-spell exemption confirmed against the real 55-year record**, not just
synthetic tests: of 825 early-May dates (1970-2024, day <= 15), **107 (13 %)**
get the exemption; the first hit (1 May 1970) has a real trailing-21-day
minimum of -10.5 C, just past the -10 C threshold.

**`spore_season_bounds` - the measured biological season vs the regulatory
calendar window.** Using FMI's own "thermal growing season" definition (first/
last day of a >=5-day run with mean temperature >= +5 C - the same threshold
config already used for spore dispersal), the *actual* warm season in
representative years ran 153-189 days (e.g. 2000: 19 Apr - 25 Oct; 2020: 2 May
- 7 Nov) - shorter than but well inside the fixed 1 May-30 Nov (214-day)
calendar window, which is consistent with that window being a deliberately
generous regulatory approximation. **The measured season has lengthened over
the record**: mean 147.2 days in 1970-1979 vs 176.9 days in 2015-2024, about
30 days longer. A Mann-Kendall trend test on the 55 annual values (added in
the first fix pass) puts this on firm ground: **tau = 0.32, p = 0.0005**,
OLS slope +0.52 days/year (~29 days over 55 years). It is a statistically
significant increasing trend, not just a warm last decade - the flip side of
the plan's own flagged talking point (a shortening *frozen* harvest window),
and the same warming trend that raises root-rot risk duration also compresses
the frozen season Module D's trafficability logic depends on.
- **The declared-vs-random concordance check is a genuine negative result,
  reported without softening.** Declared harvest dates show no concordance
  advantage over random dates against the D1-D3 workability model (lift 0.976
  overall, 0.881 - worse, not better - on peat stands specifically), and the
  root cause is traceable to the ground-truth field: `DECLARATIONARRIVALDATE`
  is an administrative filing/record timestamp (confirmed inconsistent against
  the same record's `STANDARRIVALDATE` by years, in one case 15), not a felling
  date. This does not validate or invalidate the D1-D3 model itself - it means
  this particular check cannot answer the question it was designed to answer
  with the data available, and must be reported that way rather than as either
  a pass or a fail of the underlying model.

Urea watercourse setback (`urea_setback_violation`) is implemented and unit
tested against synthetic geometry; not yet run against D1's actual derived
channel network for the catchment (that channel network exists as the D-infinity
flow-accumulation raster from D1, not yet vectorised into a line network usable
for a distance query - a small remaining step).

### D validation - declared harvest timing vs predicted workability (done, 2026-09-05, negative result - see below)

`src/d_validation.py`: for each of the D1 catchment's 8,314 forest-use
declarations, sample all 5 Luke DTW threshold rasters at the declaration's
centroid, blend them at D2's per-date threshold (real FMI weather on the
declaration's own arrival date), apply the D2 soil term from the declaration's
own `SOILTYPE`, and classify workable/not with the D2 frozen-ground override.
Compare the workable rate on real declared dates against a negative control -
the same 8,071 usable locations (243 fall outside the DTW raster extent) given
a random date instead - the same design Module B used in Project 1.

**A real bug was caught and fixed first.** `DECLARATIONARRIVALDATE` strings
carry a mixed +02:00/+03:00 (EET/EEST) local offset with midnight wall-clock
time. Parsing with `utc=True` (pandas requires it for mixed offsets) converts
to UTC first, shifting the calendar date back a day, which then silently failed
to match `daily_weather`'s midnight-normalised index on `.reindex()` and
produced 100 % NaN downstream with no error. Fixed by taking the date substring
directly (`.astype(str).str.slice(0, 10)`) rather than doing timezone
arithmetic at all, since the wall-clock date is already unambiguous in the
string.

**The result is a null-to-slightly-negative one, and it is reported as such.**

| population | n | workable rate, declared | workable rate, random control | lift | frozen share, declared | frozen share, control |
|---|---|---|---|---|---|---|
| all declarations | 8,071 | 0.825 | 0.846 | **0.976** | 0.255 | 0.347 |
| mineral soil only | 7,340 | 0.865 | 0.885 | 0.977 | 0.247 | 0.347 |
| peat only (poor bearing capacity) | 735 | 0.430 | 0.488 | **0.881** | 0.325 | 0.382 |

Declared dates are not more workable than random dates by this model - if
anything slightly less so - and the gap is *widest*, not narrowest, on peat
stands, which is exactly backwards from what a real trafficability-driven
concordance would predict (peat is where timing should matter most). Declared
dates are also *less* often frozen than random dates (25-33 % vs 35-38 %),
which is the opposite of the "Finns log wet ground in winter" prior.

**Root cause: `DECLARATIONARRIVALDATE` is not a felling date.** The same
declaration record carries `STANDARRIVALDATE` and `REGENERATIONARRIVALDATE` as
separate timestamps, and spot-checking rows shows gaps of years between
`DECLARATIONARRIVALDATE` and `STANDARRIVALDATE` for the same record (e.g. one
row: declaration 1997-03-17, stand record 2012-08-07 - a 15-year gap). These
are administrative record timestamps in the Metsakeskus data model, not a
chronology of one physical felling event. Monthly aggregation supports the same
conclusion from a different angle: the *workability model itself* behaves
physically and consistently (workable rate 0.95-0.97 in Jan/Feb, driven by the
frozen-ground override; 0.72-0.75 in Jul-Oct, when spring's post-snowmelt dry
spell has given way to summer/autumn rain - a plausible, internally consistent
seasonal pattern), but declarations are filed roughly in proportion to the
calendar year rather than concentrated in the model's workable months, which is
what produces a lift near 1.0 regardless of whether the underlying physical
relationship is real.

**This is treated as an honest negative/inconclusive finding, not softened.**
Per the standing rule this session set with D1 (reject a result rather than
document-and-move-on if it reads as flat-out wrong) - the distinction here is
that D1's error was a bug in *our own pipeline* with a fixable root cause,
where this one is a genuine limitation of the *ground-truth data field*
available: no Metsakeskus declaration field records when felling actually
happened, only when records were filed/updated. That is not fixable by
changing the model, and rerunning at full AOI scale would not change the
conclusion. D1/D2/D3 stand on their own validation (DTW benchmark correlation,
real-date weather checks, real-stand rule-engine agreement); this check
specifically cannot confirm or refute whether the D1-D3 workability model
tracks real felling timing, and the README and any figure using this result
must say so plainly rather than reporting the lift number without the caveat.

### D validation - D2 workability vs Metsakeskus Korjuukelpoisuus (done, first fix pass 2026-09-06)

The external review's headline criticism: D2's actual output - a
bearing-capacity workability classification - was never benchmarked against
Metsakeskus's **operational Korjuukelpoisuus** raster (HarvestAccessibilityType
1 = year-round even in thaw ... 6 = winter-harvest only, 16 m, on the same WCS
the project already uses for RUSLE). `korjuukelpoisuus_benchmark` in
`src/d_validation.py` does that comparison on the D1 catchment: the D2
soil-adjusted DTW at Luke's 2 ha ("average conditions") threshold, the peat
term from the MS-NFI soil raster, aligned onto the Luke DTW grid, against the
Korjuukelpoisuus class.

**Result - D2 tracks the operational classification.**

| Korjuu class | median D2 soil-adj DTW (m) | share D2 calls workable (> 1 m) |
|---|---|---|
| 1 (year-round) | 8.13 | 0.98 |
| 2 | 3.37 | 0.86 |
| 3 | 1.64 | 0.67 |
| 4 | 0.48 | 0.20 |
| 5 | 0.47 | 0.18 |
| 6 (winter only) | 0.91 | 0.47 |

Spearman rank correlation between soil-adjusted DTW and the Korjuu class is
**-0.58** (drier D2 prediction -> better operational class, as it should be).
Classes 1-5 are a clean monotonic gradient. **The one weakness, stated
plainly:** class 6 (which Metsakeskus assigns to peatland stands that are
trafficable in winter only) has a median D2 DTW of 0.91 m and D2 still calls
47% of it workable-when-not-frozen. D2's topography-plus-a-flat-peat-penalty
term under-captures the peat-specific constraint that the operational product
encodes from soil type directly. This is the concrete thing to improve in D2's
soil term, and it is why the E8 site plan should carry the Korjuukelpoisuus
class rather than only a peat flag.

So D2 now has a real DERIVE-AND-BENCHMARK result against an operational Finnish
product, which the declaration-timing check could not provide.

---

## 4. Results and what they mean

- **The DTW reimplementation is a genuine, usable reproduction, not a
  documented failure.** Elevation-above-stream (a water-table-height proxy,
  D-infinity-delineated channel network at each of the 5 official thresholds)
  correlates 0.62-0.87 (Pearson) / 0.78-0.88 (Spearman) with Luke's official
  DTW 2023 CMv2 product, with a small, consistent +2.2 to +2.8 m bias and a
  plausible explanation for it (no culvert-burning, D-infinity vs D8, no
  peatland cost-model adjustment).
- **Getting there required rejecting the first result, not rationalising it.**
  A first, plausible-sounding tool choice (horizontal downslope distance to
  channel) was 30-40x off with only weak correlation. Two follow-up hypotheses
  (D-infinity artefact; missing slope floor) were tested and ruled out before
  landing on the actual issue - DTW models a water-table height, not a
  distance, and the tool needs to match that concept, not just be
  "hydrologically flow-direction-aware".
- **The catchment is confirmed genuinely flat** (38 % of cells below 0.1 deg
  slope), which is exactly the terrain where a wrong cost formula diverges
  hardest - a useful fact for interpreting D2's soil/weather terms too.
- **D2 turns five static maps into a dated, self-calibrated surface that
  behaves physically.** Tested on three real dates spanning 55 years, not
  synthetic ones: the wettest day on record and a peak snowmelt day both
  correctly select the wettest (0.5 ha) map; the 2018 European drought
  correctly selects the driest (10 ha) map. The soil term then further wets
  peat cells specifically - on the driest day on record, peat still reads as
  ~7x closer to saturation (0.89 m) than the mineral median (6.22 m). Both
  terms are transparent, unit-tested, deterministic transformations - no
  fitted model, matching the method constraint.
- **D3's rule engine reproduces the legal test cleanly and finds a genuine
  climate signal along the way.** On the D1 catchment's real stand data
  (11,557 stands), the obligation triggers on 70 % of stands, and two
  independent data sources (Metsakeskus `soiltype`, MS-NFI `paatyyppi`) agree
  the catchment is ~10 % peat. The cold-spell exemption fires on real
  historical cold snaps (13 % of early-May dates over 55 years). Measuring the
  *actual* warm season from temperature rather than assuming the fixed
  calendar window shows it has lengthened **~30 days (20 %)** from the 1970s to
  2015-2024 - a quantified, climate-consistent finding that is also directly
  relevant to the harvest-window problem Module D exists to solve.

---

## 5. Caveats and open items

- `nls.mapsheets_for_bbox` resolves the same grid via the NLS OGC API
  (`karttalehtijako_koko_suomi`), so `fetch_dtw` still needs `NLS_API_KEY` even
  though the DTW tiles themselves come from the key-free Funet mirror.
- The +2.2 to +2.8 m bias's exact cause (culvert-burning vs D-infinity vs peat
  cost-model v2) is plausible but not decomposed - would need each factor
  added back one at a time to attribute the bias, not done here.
- `reimplement_dtw` (the WhiteboxTools pipeline) is not covered by automated
  tests - it needs the real WhiteboxTools binary and multi-minute runs on a
  37 M-cell raster, not something to unit test. `compare_to_reference`'s pure
  numpy comparison logic is tested (`tests/test_d1_dtw_compare.py`).
- DEM fetch is the slow step (119 s for 6 tiles on the catchment); the full AOI
  (3,400 km2) would need roughly 40+ tiles - budget several minutes when that
  fetch is eventually run for D2/D3's AOI-wide surfaces.
- D2's wetness-index formula (window weights, snowmelt-vs-rain weighting) is a
  documented design choice, not a published or literature-calibrated one -
  reasonable and internally consistent (median threshold lands on Luke's own
  "2 ha = average"), but not validated against an independent wetness
  measurement. The plan's later validation step (declared harvest timing vs
  predicted workable windows) was run against real data but turned out to be
  unable to confirm or refute this term specifically - see the D validation
  section above and the caveat below.
- D2 has not yet been run against Luke's official DTW surfaces (only our own
  reimplementation, for the demo); using the official product is what the
  three-tier rule calls for once D1's comparison is done, which it now is.
- Only demonstrated on 3 hand-picked dates (chosen for being clear, well-known
  extremes); a systematic check across the full 55-year record (e.g. does
  known snowmelt onset consistently trigger a threshold shift) is not done.
- D3's urea watercourse setback is unit tested on synthetic geometry only - not
  yet run against D1's real derived channel network, which needs vectorising
  from the D-infinity flow-accumulation raster to a line network first.
- D3 uses one FMI station for the whole 3,400 km2 AOI, same as D2; municipality-
  level variation in frost timing (the legal test is specifically municipality
  minimum temperature) is not resolved - a second or third station may be
  worth adding once D1/D2/D3 run at AOI scale rather than on one catchment.
- `spore_season_bounds`'s 5-day-run threshold is FMI's own published
  convention (reused deliberately, not invented), but the mapping of "thermal
  growing season" onto "root-rot spore dispersal season" - both keyed on the
  same +5 C threshold in the Finnish literature - is a reasonable inference,
  not a cited one-to-one equivalence.
- **The D validation concordance check cannot be treated as evidence about the
  D1-D3 model either way.** No Metsakeskus declaration field records actual
  felling completion; `DECLARATIONARRIVALDATE` is an administrative timestamp
  (demonstrably inconsistent with the same record's `STANDARRIVALDATE` by up
  to 15 years in a spot check). Any future figure, README claim or downstream
  module citing the lift numbers must carry this caveat plainly rather than
  reporting the lift as if it measured real timing behaviour - the same
  discipline as the pre-existing "a declaration is a permit, not a felling
  record" caveat, taken one step further now that the data has confirmed it.
