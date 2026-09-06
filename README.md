# Regenerative Harvest Planning

A batch geospatial pipeline that turns Finnish open data into planning numbers
for one wood-procurement area: **when can a stand be harvested**, **what does
Metsä Group Plus require there**, and **where do biodiversity measures deliver
most benefit**. Methods are published operational methods, deterministic legal
rules, or transparent statistics — chosen for interpretability on this problem
set, not as a stance against machine learning. Project 2 of two; companion repo
`boreal-stand-intelligence`.

**Area of interest:** Central Finland, the Äänekoski mill procurement area
(Äänekoski–Saarijärvi–Laukaa), EPSG:3067 `[404000, 6910000, 454000, 6978000]`,
50 × 68 km, ~3,400 km². The Metsäkeskus stand data covers the ~235,000 ha of
**private managed forest** inside that box (the rest is lakes, state forest and
non-forest land), so per-stand figures are "of the private-forest supply area".

**Scope note.** Two steps here reimplement national models from scratch —
depth-to-water (Module D) and RUSLE erosion (Module E). That was done to
*understand* those models and to sanity-check the official products against an
independent derivation; in an operational role you would consume Luke's DTW
raster, Metsäkeskus's RUSLE and its Korjuukelpoisuus (harvest-trafficability)
layer directly. Module F (connectivity) is exploratory work beyond the core
brief. The parts closest to a day-to-day GIS role are the data engineering, the
rule engine, and the overlay/buffer analyses in Module E.

---

## Summary

Three modules, built and validated against official products where they exist:

| Module | What it does | Headline result |
|---|---|---|
| **D — Harvest windows** | Rebuild the national depth-to-water (wetness) map, add weather and soil terms, and encode the root-rot stump-treatment law as a rule engine | Depth-to-water reproduced at rank correlation 0.78–0.88 vs Luke's product; the extended workability model tracks Metsäkeskus's operational Korjuukelpoisuus classes (Spearman −0.58); the warm season has lengthened significantly (**Mann-Kendall p = 0.0005, ~30 days / 55 years**) |
| **E — Metsä Group Plus** | Waterway buffers, the peatland continuous-cover prescription, §10 habitat setbacks, RUSLE erosion risk, deadwood, and a per-stand site plan | The derived stream network finds **~30,000–50,000 ha of buffer zone that official mapped hydrography misses** (at the natural-stream threshold band); the continuous-cover-on-peatland target is only **~1,700 ha** |
| **F — Connectivity** *(exploratory)* | Rank stands by how much a retention measure there would improve the biodiversity-network's connectivity, with a sensitivity sweep | Two large Natura sites carry **~70% of network connectivity**; a **robust set of 3,783 stands (8,546 ha)** stays top-priority across 20 resistance-model parameterisations |

**What the data actually showed:**

- **The warm season is lengthening, on a firm trend.** Measured from 55 years of
  daily temperature (not a fixed calendar), it grew ~30 days since the 1970s —
  a statistically significant increase (Mann-Kendall tau 0.32, p = 0.0005).
  That lengthens root-rot infection risk; the frozen-ground felling window on
  the wettest stands shows a weaker but still significant decline (p = 0.04).
- **Official mapped hydrography misses small streams.** Buffering the
  DEM-derived stream network against the National Land Survey's mapped
  watercourses, ~30,000–50,000 ha of protective buffer zone sits around small
  natural channels that are not on the official map (the figure rises to
  ~100,000 ha if forestry drainage ditches are included, which is why the
  natural-stream threshold band is the one reported).
- **Metsäkeskus's published "RUSLE erosion" layer is really a slope index.** It
  correlates strongly with the slope-length factor (rank r 0.82) but has
  essentially no land-cover signal — it flags steep terrain, not actual soil
  loss under real forest cover. Our own RUSLE is reported as a *relative* risk
  pattern only; the absolute t/ha/yr scale could not be reconciled with the
  Metsäkeskus product.
- **The Plus continuous-cover-on-peatland target is small and doubly
  regulated.** Only ~1,700 ha of the supply area is drained, spruce-dominated
  peatland at the continuous-cover site band (rich spruce mires are rare), and
  100% of it also triggers the root-rot stump-treatment obligation.
- **Harvest declarations can't be used to check timing.** The declaration
  arrival date is an administrative filing date, not a felling date, so a
  planned check of "do harvests cluster in workable windows" came back
  inconclusive — reported as such rather than forced. (The Korjuukelpoisuus
  benchmark above is what replaced it.)

---

## Data

| Source | Data used | Tier |
|---|---|---|
| Metsäkeskus (Finnish Forest Centre) | stands, §10 habitats, forest-use declarations, Kemera environmental-support sites, RUSLE erosion raster, Korjuukelpoisuus (harvest trafficability) | FETCH / BENCHMARK |
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

**D2 benchmark — Korjuukelpoisuus.** The bearing-capacity part of the workability
model was checked against Metsäkeskus's operational harvest-trafficability
raster (`Korjuukelpoisuus`, class 1 = year-round … 6 = winter-only). It tracks
the operational classes well: Spearman −0.58, and a clean monotonic gradient
(class-1 median soil-adjusted DTW 8.1 m down to class-5 at 0.47 m). One known
weakness: it under-flags class 6, the peatland stands the operational product
marks winter-only from soil type — D2's flat peat penalty does not fully
capture that.

**D3 — root-rot rule engine.** The Forest Damages Prevention Act requires stump
treatment when conifer-dominated stands are felled 1 May–30 Nov, with a
cold-spell exemption. Coded as a deterministic rule. On real stand data it
triggers on ~70% of stands. The measured warm season lengthened ~30 days over
the record — a significant trend (Mann-Kendall tau 0.32, p = 0.0005).

**Validation caveat.** A declaration is a permit, not a felling record; the
declaration dataset's dates are administrative, so they cannot confirm the
timing model. The Korjuukelpoisuus benchmark above is the check that replaced
it.

Full detail: `docs/MODULE_D_NOTES.md`.

---

## Module E — Metsä Group Plus site planning

**Waterway buffers.** We derived a stream network for the whole AOI from the
16 m DEM at five channel-size thresholds and buffered it at 10/20/30 m. At the
2–4 ha threshold band — the one most likely to be genuine small natural streams
rather than drainage ditches — the derived network's 30 m buffer adds
**~30,000–50,000 ha** over the National Land Survey's own mapped watercourses
(30 m buffer, 74,000 ha). Including all headwater channels and ditches (0.5 ha
threshold) pushes it to ~100,000 ha, but that end is ditch-inclusive and is not
the reported figure. The full threshold table is in the notes.

**Peatland continuous cover.** Plus prescribes group/selection cutting instead
of clearcutting on drained, spruce-dominated peatland at the more fertile site
types. At the site band Tapio's 2019 recommendations flag for continuous cover
(mustikkaturvekangas and richer) that is **1,674 ha** — 7.9% of drained
peatland, 0.7% of the supply area (141 ha at the strictest cut). Small because
spruce mires are the uncommon fertile minority of Finnish peatland. All of it
also triggers the D3 root-rot rule; the felling season that satisfies both is
about 106 days a year, on a weak downward trend (p = 0.04).

**§10 habitat setbacks.** ~5–6% of stand area lies within a Plus-scale setback
of a Forest Act §10 valuable habitat; the footprint barely grows from a 10 m to
a 30 m setback.

**RUSLE erosion.** We built the four RUSLE factors (slope-length from the DEM,
soil erodibility from a soil-class lookup, cover from CORINE, a published
regional rainfall constant) on the validation catchment and benchmarked against
Metsäkeskus's own RUSLE raster. The benchmark showed Metsäkeskus's product is a
slope-driven terrain index with no cover signal, and the absolute scales could
not be reconciled (~100×, likely a units difference). **E5/E6 are therefore
reported as a *relative* erosion-risk pattern, not absolute t/ha/yr** — erosion
is low throughout (indicative p90 ≈ 0.4 t/ha/yr), and the usable output is which
cells rank as erosion-prone.

**Deadwood.** No per-stand deadwood data exists in the open data, so this is one
aggregate figure: the supply area holds an estimated **~1.29 million m³** of dead
wood (~0.39 million m³ standing), from Luke's regional forest-inventory
statistics-database value (Etelä-Suomi, VMI2022). The Plus stems-per-hectare
target is reported alongside, not converted.

**Site plan.** One record per stand (168,026 stands) joining every constraint:
root-rot obligation, continuous-cover prescription, nearest §10 habitat and
setback flag, nearest stream and buffer flag, and a harvest-timing note.

Full detail: `docs/MODULE_E_NOTES.md`.

---

## Module F — Biodiversity network connectivity *(exploratory)*

This module goes beyond the core brief. It is landscape-ecology / conservation-
planning work — useful as a prioritisation to explore, not an operational
output, and there is no official product to benchmark it against.

**Nodes.** 2,769 patches from protected areas (mostly Natura sites), §10
habitats and old stands (≥120 years). Environmental-support sites contribute
only 10 tiny polygons here, so the network is effectively designations + old
stands.

**Resistance surface.** A movement-cost grid from stand age, structure
(basal area), deciduous share and CORINE land cover — old, mixed, closed forest
is cheap to cross, clearcuts and fields are expensive, lakes are barriers. The
values are chosen, not calibrated to a named species; this is the module's main
limitation.

**Connectivity.** Least-cost distances between all patch pairs, Probability of
Connectivity (maximum-product paths), each patch's importance (dPC), and
least-cost corridors along the network backbone. Two large Natura sites carry
~70% of connectivity by dPC.

**Sensitivity sweep.** Because the resistance values are assumption-based, we
re-ran the whole thing 20 times with the weights, land-cover costs and dispersal
distance randomly perturbed. The connectivity index itself swings 2×
(0.20–0.41); the per-stand ranking does not. The deliverable is the **robust set
— 3,783 stands (8,546 ha)** that stay in the top priority decile across the
sweep. "Robust" here means stable across the *resistance-model parameters* — the
structural choices (node sources, patch merge, grid resolution) are held fixed.

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
are gitignored and regenerated.

**Reproducibility gap (known).** `run.py` covers the fast analysis and
reporting, but it depends on expensive intermediate rasters (full-AOI DEM, the
16 m channel network, the RUSLE factor rasters, the F2 resistance surface) that
are currently produced by per-step scripts described in the module notes and
cached in `data/interim/`. Folding those derivations into `run.py` behind a
`--rebuild` flag, and doing one clean cold run, is an open item. Module D is run
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
