# Project 2 — Regenerative Harvest Planning
Modules D + E + F. Created 2026-08-26, revised same day; lessons from Project 1
added 2026-08-30 (see below) once Project 1 (Modules A/B/C) completed.
Depends on: METSA_GIS_RESEARCH_FINDINGS.md (see Part G for the DTW method)
Shares `fi_forest_data` with Project 1.
Working repo name: `/RegenerativeHarvestPlanning`

---

## One-line framing

Operationalises Metsä Group Plus and the Finnish harvest-window problem: for every
stand in a mill's procurement area, when can it be harvested, what must be left
behind, and where do biodiversity measures deliver most benefit.

The centrepiece is a **date-specific wetness and trafficability surface**, built by
extending the national DTW method with the two terms its own authors say are
missing.

## Design principle: follow the analyst's workflow

Same three-tier rule as Project 1, stated explicitly in the README:

- **FETCH** — registers and designations. Protected areas, §10 habitats,
  environmental support sites, forest use declarations, stand boundaries.
- **DERIVE AND BENCHMARK** — official product exists and the method is published.
  Derive on a validation subset, quantify agreement, then consume the official
  product at AOI scale.
- **DERIVE ONLY** — no official product exists. Where the analysis lives.

## On machine learning — not the default approach

Every module here is either a documented operational method (DTW, RUSLE, D-infinity
flow routing), a deterministic legal rule engine (root rot obligation, Metsä Group
Plus measures), or transparent graph analysis (connectivity). None of it needs ML
by default, and introducing it would obscure results the audience will want to
interrogate directly. This is a default, not a prohibition: a module that would
clearly benefit from ML can be discussed as a design decision, agreed before
implementing rather than substituted silently.

## Why these three belong together

One hydrology and terrain backbone, answering three sequential questions about the
same stand: **when** can a harvester work here (D), **what** must be left (E),
**where** does a measure matter most (F).

They also share a specific dependency. Urea must not be applied within 10 m of
watercourses, and Plus buffer zones are 10–30 m from waterways. Both need a
small-stream network that mapped hydrography does not contain, and both get it from
the same DTW-derived channel network.

---

## Lessons carried from Project 1 (added 2026-08-30, before Module D starts)

Project 1 (Modules A, B, C) is complete. A self-critical external review
(`docs/EXTERNAL_REVIEW.md`) found no fundamental problems, but several claims
needed tightening and one real analytical error surfaced (a small-sample
lead-time claim in Module C2, withdrawn once tested). The following are
pre-committed for Project 2 so they do not have to be retrofitted at the end.

**Framing, decided up front, not after the fact:**
- **State independence honestly from the first draft.** D1's "our DTW vs
  official DTW" and E's "our RUSLE vs Metsäkeskus RUSLE" both benchmark against
  products built from the same NLS DEM. Call this *agreement*, not independent
  validation - Project 1 had to walk this back for Module A's MS-NFI comparison
  after the fact.
- **Separate a method limit from a physical limit.** If D1's D-infinity + carve
  choice diverges from Luke's D8 + breaching, or the korjuukelpoisuus confusion
  matrix disagrees badly in one class, name the specific processing choice
  before concluding "the phenomenon isn't visible from open data." Project 1
  called two-date dNBR thinning detection "undetectable" when "not separable by
  this method" was the accurate statement - a time-series or SAR approach was
  never tried.
- **A declaration is a permit, not a felling record.** Already learned in
  Module B and correctly reused for D1's validation ("do harvests cluster in the
  predicted workable windows"). Keep stating this every time a declared date
  stands in for an actual event date.

**Statistical rigor, pre-committed rather than added later:**
- **Sample-size gate before reporting a distribution.** Do not quote a
  median/quantiles below roughly n = 12; state "too few, qualitative only"
  instead. Applies to any per-felling-type, per-stand-class, or per-year
  subset in D/E/F validation (Module C2's lead-time claim was withdrawn for
  exactly this reason).
- **Collinearity check on any fitted weighting or regression.** If Module E's
  RUSLE, or Module F's resistance surface, ever fits or tunes weights, report
  VIFs or an equivalent alongside them - cheap, and it was the difference
  between a shaky-looking and a demonstrably robust Module C1 driver ranking.
- **Skill-over-baseline, not significance alone.** Compare any ranking or
  classifier to a naive baseline (equal weighting, or the official product
  itself) and report whether it actually beats it, the way C1's average
  precision was checked against a naive additive index.
- **Residual spatial-structure check for any blocked CV or accuracy claim.**
  Module A's semivariogram check confirmed its CV blocks were adequate (no
  autocorrelation beyond ~250 m against a 2 km block). Run the equivalent for
  any fitted, cross-validated piece of D/E/F, or state explicitly why it does
  not apply (D1's DTW reimplementation is deterministic, not fitted, so this
  check is not needed there).

**Process, already working, keep doing it:**
- **One "TASK 00"-style discovery pass up front, for the whole project** -
  already done here (D2/D3/D4 below were resolved before Module D starts) and
  it is why Project 2's plan needs less mid-build correction than Project 1's
  did. Re-run the small D4 opens (surface-water-flow route, ympäristötuki field,
  CLC2024 release, a spot-check that a 32766 MS-NFI pixel appears in-AOI) at
  Module D kickoff rather than discovering them mid-module.
- **Keep `MODULE_D_NOTES.md` / `MODULE_E_NOTES.md` / `MODULE_F_NOTES.md` running
  from day one**, same shape as Project 1's - decision + reasoning, results,
  plain-language explanation - so the README write-up is assembly, not a
  rewrite, at the end.
- **Module F's sensitivity-sweep / "robust set, not one map" discipline was
  already written into this plan before Project 1 started.** No change needed;
  it is the standard the other modules should match, not a lesson still to
  learn.
- **Decision D2 (Module E deadwood deficit) is still open** and should be
  resolved before Module E starts, not before Module D.

---

## Area of interest

**Äänekoski bioproduct mill procurement area, Central Finland.**
Äänekoski – Saarijärvi – Laukaa. FIXED EXTENT:
- EPSG:3067 bbox: `[404000, 6910000, 454000, 6978000]`
- WGS84 bbox: `[25.15, 62.32, 26.10, 62.92]`
- 50 x 68 km, ~3,400 km²

Rationale: literal Metsä operational geography — the mill consumes ~6.5 Mm³/yr
(~4.5 Mm³ softwood, ~2 Mm³ birch), mostly Finnish-sourced, and most of the jobs it
created are in wood procurement. Drained peatland where the continuous-cover target
and the trafficability problem bite hardest — **TASK 00: ~13% of the AOI is
peatland by MS-NFI site main type (~440 km²), a meaningful minority rather than a
peat-dominated landscape**; the wording is calibrated but the extent is kept. Very
dense lake and stream network, so buffer derivation is non-trivial. Mixed pine and
spruce (pine 48% / spruce 34% by volume), so root rot rules apply across both the
mineral and peat cases rather than trivially.

DEM and DTW coverage confirmed at AOI level in TASK 00 — both cover the AOI in
full.

Deliberately a different landscape from Project 1, so the two read as two case
studies rather than one dataset stretched across six analyses.

---

## Module D — Harvest windows: dynamic wetness × trafficability × root rot

### Data

| Tier | Item | Source |
|---|---|---|
| DERIVE AND BENCHMARK | DTW at five thresholds (0.5/1/2/4/10 ha) | NLS 2 m DEM; benchmark vs Luke DTW 2023 CMv2 |
| DERIVE AND BENCHMARK | Trafficability classification | Our DTW + slope + soil; benchmark vs Metsäkeskus korjuukelpoisuus (6 classes = `HarvestAccessibilityType`) |
| FETCH | Official DTW at AOI scale | Luke DTW 2023 CMv2, Funet mirror `nic.funet.fi/index/geodata/luke/dtw/2023/` (mapsheet GeoTIFF tiles + tile-index shapefile) |
| FETCH | Peat vs mineral main type, species volumes | Luke MS-NFI 2023 (`paatyyppi_`, `kuusi_`, `manty_`, …), Metsäkeskus stands (`soiltype`, proportions) |
| FETCH | Daily temperature and precipitation, snow depth | FMI open data |
| FETCH | Harvest timing (validation) | Metsäkeskus forest use declarations |

### D1 — Reimplement DTW, and benchmark it

Follow the published method on a validation catchment: burn culverts at
road/channel crossings, carve remaining pits (Lindsay 2016), route flow with
D-infinity (Tarboton 1997), take slope from the unmodified surface, initiate
channels at 0.5, 1, 2, 4 and 10 ha, compute slope-weighted cumulative distance to
channel in metres.

**Validation catchment (TASK 00):** SYKE Valuma-aluejako sub-catchment
**`FI1-14.06.161`** (Kymijoki system, near Äänekoski), **148 km²**, bbox EPSG:3067
`[414920, 6945300, 429010, 6964880]`, fully inside the AOI, near-headwater — small
enough to reprocess at 2 m (~37 M cells), large enough to be meaningful. Re-fetch
the exact polygon from `valumaalueet.zip` for the non-rectangular clip.

Note the reference product (Luke DTW 2023 CMv2) uses **D8** flow routing and a
breaching pit-removal; our D-infinity + carve choice is one expected source of
divergence to account for in the written comparison. Luke's DTW values are in
**centimetres** (2023); ours are in metres — align units before comparing.

Output: agreement statistics against the official product, and a written account of
where the two diverge and why. This is what earns the right to extend it.

### D2 — The extension: adding soil and weather

Luke's own product description states the limitation plainly: DTW is based entirely
on the elevation model, so **soil type and weather conditions are not taken into
account, and this causes uncertainty** (Ågren et al. 2015, Lidberg et al. 2020).
The extension addresses exactly those two gaps.

**Weather term — dynamic threshold selection.** The five thresholds are already
wetness-condition proxies (per Luke's 2023 product description): 0.5 ha very wet
(snowmelt, prolonged rain), 1 ha wetter than average, 2 ha average, 4 ha drier
late summer, 10 ha drier than average. Currently a user picks one by judgement.
Instead, **select the appropriate threshold surface per date from FMI
precipitation, snowmelt and antecedent conditions** (station `fmisid 101537`,
Viitasaari Haapaniemi, daily record from 1970), producing a continuous time series
rather than five static maps. Interpolate between threshold surfaces rather than
switching abruptly.

This is cheap — it uses the five official products as they are, plus FMI data — and
it converts a static dataset into a dated one.

**Soil term — peat and mineral behave differently.** DTW assumes uniform hydraulic
behaviour. Peat holds water and has low bearing capacity even at DTW values that
would be dry on mineral soil. Modulate the wetness-to-trafficability translation by
peat/mineral main type from MS-NFI, and by superficial deposits where available.

**What the extension actually gives you, in one sentence for the documentation:**
Metsäkeskus tells you a stand is class 4 trafficability in general; this tells you
whether it is workable *this week*.

### D3 — Root rot obligation, as a deterministic rule engine

From the Forest Damages Prevention Act. Treatment mandatory on the risk area where:
- mineral soil: pine and/or spruce together exceed 50% of pre-felling stand volume
- peat soil: spruce exceeds 50% of pre-felling stand volume

Period 1 May – 30 November. Exemption where the municipality's minimum temperature
has been below −10 °C during the three weeks preceding felling. Spore dispersal
above roughly +5 °C daily mean, so a warm spring starts the season early and a mild
autumn extends it. Layered constraints: conifer stumps over 10 cm diameter, 85%
coverage of the cut surface, application within 3 hours, **no urea within 10 m of
watercourses or small waters** — which uses the derived channel network from D1.

Evaluate stand attributes against FMI daily temperature on a date grid across a
full year.

### Validation — using declared harvest timing

The good test: **do harvests actually cluster in the periods the model says are
workable?** Forest use declarations carry geometry and dates. For stands the model
classes as poor-bearing-capacity, check whether declared harvest activity
concentrates in the predicted frozen or dry windows. That closes the loop with open
data and reuses the dataset already central to Project 1.

### Analytical outputs
- Our DTW vs official DTW: agreement and divergence analysis
- Our trafficability vs Metsäkeskus korjuukelpoisuus: confusion matrix across the
  6 classes, with a written account of where a static map and a dated one disagree
- Stand × date obligation matrix, reduced to: harvestable-window length per stand,
  and a stump-treatment-required calendar
- **Frozen-ground season length by year over the historical FMI record, and its
  trend** — from station `fmisid 101537` (Viitasaari Haapaniemi), continuous daily
  tmin/tmean/precip/snow from 1970, ~55 years; a shortening frozen harvesting
  window is a live Finnish wood supply problem and quantifying it over a real
  procurement area is a simple, strong result
- **The awkward set**: stands where the trafficability window and the root rot
  exemption window do not overlap, i.e. workable only when frozen, at a time when
  frozen conditions are becoming less reliable
- Concordance between predicted workable windows and declared harvest timing

### Honest limitations
DTW ignores soil and weather by construction, which is why we extend it — but our
extension is still modelled, not measured, and does not observe actual frost depth
or soil moisture. FMI station density is coarse relative to stand microclimate.
Luke are explicit that DTW should not be read as an exact water table height, only
as an indicator of areas needing careful examination. The output is a
planning-grade screening layer, not an operational go/no-go, and the README says so.

---

## Module E — Metsä Group Plus site planning

Turns the quantified Plus measures into a per-stand site plan derived from open
data.

### Data

| Tier | Item | Source |
|---|---|---|
| DERIVE ONLY | Small-stream network and buffers | Our DTW channel network (module D) |
| DERIVE AND BENCHMARK | Erosion risk | RUSLE from DEM + FMI rainfall + soil + land cover; benchmark vs Metsäkeskus RUSLE |
| FETCH | Forest Act §10 valuable habitats | Metsäkeskus WFS `v2/habitat` |
| FETCH | Site fertility, drainage, spruce share | MS-NFI 2023, Metsäkeskus stands. **No standing-deadwood theme in MS-NFI 2023** — deadwood deficit component is Decision D2 (deferred). |
| FETCH | Mapped hydrography (for comparison) | NLS topographic database |

### Calculations

**Waterway buffer zones (10–30 m).** The analytical value is that mapped
hydrography omits the small streams and seepage lines that actually matter. Buffer
the derived channel network at 10, 20 and 30 m by waterway class, then compare
against buffers from mapped hydrography alone and quantify the additional area
captured. Cross-reference RUSLE to flag where buffers matter most. Hilli & Mykrä
et al. 2022 found the DTW 0.8–1.2 m band characterised by upland forest species,
giving an empirical anchor for where the wet zone ends.

**Peatland continuous cover prescription.** Select lush, drained,
spruce-dominated peatland stands — the exact category where Plus prescribes group
or selection cutting instead of clearcutting, with no ditch repair and no
regeneration obligation. Requires peat main type, site fertility class, drainage
status and spruce share, all present in MS-NFI and Metsäkeskus stand data.
Quantify against the +30% continuous-cover-share target.

**Retention and deadwood deficit.** Plus requires 30 retention trees/ha over 15 cm
dbh, at least 20 dead trees/ha, and 10 high-biodiversity stumps/ha against a 4/ha
baseline. Map the gap between current state and target per stand and in aggregate.
**TASK 00 correction:** standing deadwood volume is **not** an MS-NFI 2023 theme
(the 45 themes are stand/volume + living-tree biomass compartments only). The
deadwood-deficit component has no per-stand m³/ha source. Decision D2 in
`docs/TASK_00_FINDINGS.md` — deferred until the pipeline is further along; candidate
directions are the Metsäkeskus habitat `deadwoodpotential` field (qualitative),
Luke VMI field-plot deadwood statistics at region level, or dropping the component.
Do not substitute a proxy silently.

**Valuable habitat proximity.** §10 habitat polygons adjacent to harvestable
stands, flagged with required setbacks.

**The conflict overlay.** Continuous cover forestry is best done in winter and is
not recommended where root rot risk is high. Overlay module D's root rot risk on
the Plus peatland continuous-cover prescription and surface the stands where the
two pull in opposite directions.

### Analytical outputs
- Per-stand Plus site plan: buffer geometry, prescribed felling method, retention
  requirement, deadwood deficit, adjacent habitat constraints, harvest window from D
- **Hectares of buffer that mapped hydrography misses** — a concrete water
  protection finding
- Continuous-cover-eligible area against the +30% target
- What the 2030 retention and deadwood targets imply physically across one mill's
  supply area
- The Plus-versus-root-rot conflict set, surfaced rather than glossed

---

## Module F — Biodiversity network connectivity

Answers the siting question implied by the 10,000-measures target. "Improving the
biodiversity network" is one of Metsä's ten published regenerative forestry
principles, so this is on-brand rather than invented.

### Data
FETCH throughout: protected areas (SYKE / Metsähallitus), §10 habitats,
environmental support (ympäristötuki) sites from the Metsäkeskus subsidy layers,
stand age and structure from Metsäkeskus and MS-NFI.

### Calculations
Nodes from the above plus old or structurally rich stands. Resistance surface from
stand age, canopy structure, species composition and land cover. Connectivity via
least-cost paths and graph-theoretic importance measures, choosing what runs
sensibly at this scale. Rank candidate stands by marginal connectivity gain if a
Plus retention measure were applied there.

### The honesty requirement
Resistance surfaces are assumption-laden and results move when assumptions move.
Do not present a single map as the answer. Run a sensitivity sweep across plausible
parameterisations and report which stands are **robustly** high-value across all of
them versus which are artefacts of one parameter choice. The robust set is the
deliverable; the sensitivity analysis is what makes it credible in front of people
who will immediately ask about the assumptions.

Presented as an exploratory prioritisation method, not a recommendation. This is
the least certain of the six modules and the README says so.

---

## Deliverables
- Pipeline sharing `fi_forest_data` with Project 1
- Date-specific wetness and trafficability surfaces, stand × date harvest windows,
  Plus site plan records, connectivity prioritisation with sensitivity analysis
- One poster. This project has the stronger map material: derived stream network
  against mapped hydrography, and the seasonal trafficability maps, both read well
  at poster scale.
- README leading with the fetch/derive tiering and the modelled-not-measured caveat

## Talking points generated
- The DTW extension: what adding soil and weather terms actually buys, explained
  as a concrete analytical gain rather than a technical flourish
- The shrinking frozen-ground harvesting window, quantified over a real procurement
  area from the historical record
- Small streams missing from mapped hydrography, and how much buffer area that
  omits
- The conflict between the Plus peatland continuous-cover prescription and root rot
  guidance
- What the 2030 retention and deadwood targets mean physically across one mill's
  supply area
