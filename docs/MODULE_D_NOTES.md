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

### D1b - next
Reimplement DTW on the validation catchment: burn culverts at road/channel
crossings, carve remaining pits (Lindsay 2016), route flow with D-infinity
(Tarboton 1997) from the fetched DEM, take slope from the unmodified surface,
initiate channels at the same 5 thresholds, compute slope-weighted cumulative
distance to channel. Compare against the now-cached Luke DTW 2023 CMv2 at each
threshold: agreement statistics plus a written account of where the two
diverge (expected divergence: our D-infinity + carve vs Luke's D8 + breaching).

---

## 4. Results and what they mean

(filled in as D1b completes)

---

## 5. Caveats and open items

- The validation catchment fetch used the **bounding box**, not the exact SYKE
  polygon; the plan calls for re-fetching the precise non-rectangular catchment
  polygon from `valumaalueet.zip` for the actual D1 clip - not yet done, needed
  before computing agreement statistics (a bbox is fine for a raw-data fetch,
  not for a clean comparison against a non-rectangular catchment).
- `nls.mapsheets_for_bbox` resolves the same grid via the NLS OGC API
  (`karttalehtijako_koko_suomi`), so `fetch_dtw` still needs `NLS_API_KEY` even
  though the DTW tiles themselves come from the key-free Funet mirror.
- DEM fetch is the slow step (119 s for 6 tiles on the catchment); the full AOI
  (3,400 km2) would need roughly 40+ tiles - budget several minutes when that
  fetch is eventually run for D2/D3's AOI-wide surfaces.
