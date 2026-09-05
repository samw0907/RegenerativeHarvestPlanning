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
