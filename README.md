# Regenerative Harvest Planning

A batch geospatial pipeline that turns Finnish open data into planning numbers
for one wood-procurement area: **when can a stand be harvested**, **what does
Metsä Group Plus require there**, and **where do biodiversity measures deliver
most benefit**. Every method is a published operational method, a deterministic
legal rule, or transparent statistics — no machine learning, no black boxes.
Project 2 of two; companion repo `boreal-stand-intelligence`.

**Area of interest:** Central Finland, the Äänekoski mill procurement area
(Äänekoski–Saarijärvi–Laukaa), EPSG:3067 `[404000, 6910000, 454000, 6978000]`,
50 × 68 km, ~3,400 km². The Metsäkeskus stand data covers the ~235,000 ha of
**private managed forest** inside that box (the rest is lakes, state forest and
non-forest land), so per-stand figures are "of the private-forest supply area".

---

## Summary

Three modules, built and validated against official products where they exist:

| Module | What it does | Headline result |
|---|---|---|
| **D — Harvest windows** | Rebuild the national depth-to-water (wetness) map, add weather and soil terms, and encode the root-rot stump-treatment law as a rule engine | Reproduced depth-to-water at rank correlation 0.78–0.88 vs Luke's official product; the frost/growing season has lengthened **~30 days (20%) over 55 years** |
| **E — Metsä Group Plus** | Waterway buffers, the peatland continuous-cover prescription, §10 habitat setbacks, RUSLE erosion risk, deadwood, and a per-stand site plan | Our derived stream network finds **21,000–114,000 ha of buffer zone that official mapped hydrography misses**; the continuous-cover-on-peatland target is only **~1,700 ha** |
| **F — Connectivity** | Rank stands by how much a retention measure there would improve the biodiversity-network's connectivity, with a sensitivity sweep | Two large Natura sites carry **~70% of network connectivity**; a **robust set of 3,783 stands (8,546 ha)** stays top-priority across 20 different assumption sets |

**What the data actually showed:**

- **The season is getting longer.** Measuring the warm season from 55 years of
  daily temperature (not a fixed calendar) shows it grew ~30 days since the
  1970s. That lengthens root-rot infection risk and shortens the frozen-ground
  window that wet-site harvesting depends on.
- **Official mapped hydrography misses small streams.** Buffering our
  DEM-derived stream network and comparing against the National Land Survey's
  mapped watercourses, tens of thousands of hectares of protective buffer zone
  sit around channels that are not on the official map (partly real headwater
  streams, partly forestry drainage ditches).
- **Metsäkeskus's published "RUSLE erosion" layer is really a slope index.** It
  correlates strongly with our slope-length factor (rank r 0.82) but has
  essentially no land-cover signal — it flags steep terrain, not actual soil
  loss under real forest cover.
- **The Plus continuous-cover-on-peatland target is small and doubly
  regulated.** Only ~1,700 ha of the supply area is lush, drained,
  spruce-dominated peatland (rich spruce mires are rare), and 100% of it also
  triggers the root-rot stump-treatment obligation.
- **Harvest declarations can't be used to check timing.** The declaration
  arrival date is an administrative filing date, not a felling date, so a
  planned check of "do harvests cluster in workable windows" came back
  inconclusive — reported as such rather than forced.

---

## Data

| Source | Data used | Tier |
|---|---|---|
| Metsäkeskus (Finnish Forest Centre) | stands, §10 habitats, forest-use declarations, Kemera environmental-support sites, RUSLE erosion raster | FETCH / BENCHMARK |
| NLS (National Land Survey) | 2 m DEM, topographic-database watercourses | DERIVE input / FETCH |
| Luke | depth-to-water (DTW) 2023, MS-NFI soil theme, regional deadwood statistics | BENCHMARK / FETCH |
| FMI | daily weather 1970–2024, station 101537 | FETCH |
| SYKE | catchment boundaries, CORINE Land Cover 2018, protected areas, Natura 2000 | FETCH |

**Three-tier rule.** *FETCH* — registers and legal records. *DERIVE AND
BENCHMARK* — an official product exists; derive our own on a validation
catchment, quantify agreement, then consume the official product at full scale.
*DERIVE ONLY* — no official product; this is where the analysis lives. The tier
is stated in every module docstring. All processing in EPSG:3067.

---

## Module D — Harvest windows and root rot

**D1 — depth to water.** Depth-to-water is a modelled water-table height used to
judge trafficability. We reimplemented it on a 148 km² validation catchment
(breach depressions → D-infinity flow routing → elevation above the nearest
stream) and compared against Luke's official 2023 product: rank correlation
0.78–0.88, small +2–3 m bias. A first tool choice was 30–40× wrong; it was
root-caused and replaced rather than documented as-is.

**D2 — weather and soil.** The five official DTW maps are wetness-condition
variants (0.5 ha = very wet, 10 ha = dry). We pick between them per date from a
weather signal (antecedent rainfall + snowmelt) ranked against the station's own
55-year record, and further wet peat soils by a bearing-capacity penalty. A site
is "workable" if it is dry enough **or** the ground is frozen.

**D3 — root-rot rule engine.** The Forest Damages Prevention Act requires stump
treatment when conifer-dominated stands are felled 1 May–30 Nov, with a
cold-spell exemption. Coded as a deterministic rule. On real stand data it
triggers on ~70% of stands. Measuring the spore season from temperature shows
the ~30-day lengthening noted above.

**Validation caveat.** A declaration is a permit, not a felling record; the
declaration dataset's dates are administrative, so they cannot confirm the
timing model.

Full detail: `docs/MODULE_D_NOTES.md`.

---

## Module E — Metsä Group Plus site planning

**Waterway buffers.** We derived a stream network for the whole AOI from the
16 m DEM at five channel-size thresholds and buffered it at 10/20/30 m. Compared
against the official mapped watercourses, the derived network's 30 m buffer adds
**~21,000 ha** (major channels only, the defensible lower bound) to **~114,000
ha** (all small streams and ditches, the inclusive upper bound). Reported as a
range, not one number.

**Peatland continuous cover.** Plus prescribes group/selection cutting instead
of clearcutting on lush, drained, spruce-dominated peatland. That is **1,674 ha**
— 7.9% of drained peatland, 0.7% of the supply area — because spruce mires are
the uncommon fertile minority of Finnish peatland. All of it also triggers the
D3 root-rot rule; the felling season that satisfies both (frozen ground, outside
the treatment period) is about 106 days a year.

**§10 habitat setbacks.** ~5–6% of stand area lies within a Plus-scale setback
of a Forest Act §10 valuable habitat; the footprint barely grows from a 10 m to
a 30 m setback.

**RUSLE erosion.** We built the four RUSLE factors (slope-length from the DEM,
soil erodibility from a soil-class lookup, cover from CORINE, a published
regional rainfall constant) on the validation catchment and benchmarked against
Metsäkeskus's own RUSLE raster. Erosion is very low everywhere (90th-percentile
0.4 t/ha/yr — flat boreal forest). The benchmark showed Metsäkeskus's product is
a slope-driven terrain index with no cover signal, so our fuller version diverges
from it exactly where we add soil and land cover.

**Deadwood.** No per-stand deadwood data exists in the open data, so this is one
aggregate figure: the supply area holds an estimated **~1.29 million m³** of dead
wood (~0.39 million m³ standing) from the regional forest-inventory average. The
Plus stems-per-hectare target is reported alongside, not converted.

**Site plan.** One record per stand (168,026 stands) joining every constraint:
root-rot obligation, continuous-cover prescription, nearest §10 habitat and
setback flag, nearest stream and buffer flag, and a harvest-timing note.

Full detail: `docs/MODULE_E_NOTES.md`.

---

## Module F — Biodiversity network connectivity

**Nodes.** 2,769 patches from protected areas, §10 habitats, environmental-
support sites and old stands (≥120 years).

**Resistance surface.** A movement-cost grid from stand age, structure
(basal area), deciduous share and CORINE land cover — old, mixed, closed forest
is cheap to cross, clearcuts and fields are expensive, lakes are barriers.

**Connectivity.** Least-cost distances between all patch pairs, a Probability of
Connectivity index, each patch's importance (dPC), and least-cost corridors
along the network backbone. Two large Natura sites carry ~70% of connectivity by
dPC.

**Sensitivity sweep.** Resistance surfaces are assumption-laden, so we re-ran
the whole thing 20 times with the weights, land-cover values and dispersal
distance randomly perturbed. The connectivity index itself swings 2× (0.20–0.41);
the per-stand ranking does not. The deliverable is the **robust set — 3,783
stands (8,546 ha)** that stay in the top priority decile across the sweep,
presented as an exploratory prioritisation, not a recommendation.

Full detail: `docs/MODULE_F_NOTES.md`.

---

## Running it

```
pip install -r requirements.txt
python -m fi_forest_data.validate config/pipeline.yaml
python -m src.run                 # Modules E and F baseline
python -m src.run --sweep         # also the ~30-minute F3b sensitivity sweep
```

Outputs (report JSON, vector layers, figures) go to
`outputs/regenerative-harvest-planning/{e,f}/{run_id}/`. `data/` and `outputs/`
are gitignored and regenerated. The expensive derivations (full-AOI DEM, 16 m
channel network, RUSLE factor rasters) are produced by the per-step scripts
documented in the module notes and cached in `data/interim/`; Module D is run
from its own documented steps.

## What this is and is not

- A reproduction and extension study on **open data only**, not an operational
  product. Where an official product exists we quantify agreement with it, which
  is agreement — not independent ground-truth validation, since both sides often
  come off the same DEM.
- Figures are indicative, not cartographic deliverables.
- Module F is the least certain module and its output is a prioritisation to
  explore, not a plan.

## Attribution

Contains data from Metsäkeskus, NLS, Luke, FMI and SYKE, licensed under CC BY
4.0.
