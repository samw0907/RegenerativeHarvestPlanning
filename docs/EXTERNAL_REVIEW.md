# External review - critical appraisal of Project 2

Written as if by a reviewer on the Metsä Group GIS / forest-data side, looking
at this repository as a portfolio piece attached to a candidate's CV for a
junior-to-mid GIS analyst position. Two lenses:

1. **Positioning** - is this pitched at the right level, and does it help or
   hurt the candidate?
2. **Method** - where a technique is misapplied or over-claimed, where an
   official product that should have been the benchmark was not used, and where
   an assumption is larger than it needed to be.

**This document changes nothing.** It is a register of criticisms. A separate
pass decides which, if any, warrant a change to method, code, scope or framing.

---

## Status after the first fix pass (2026-09-06)

**Actioned:**

- **B1 (High)** - *done.* `korjuukelpoisuus_benchmark` (`src/d_validation.py`)
  compares the D2 soil-adjusted DTW against Metsäkeskus's operational
  Korjuukelpoisuus raster on the D1 catchment. Result: Spearman **-0.58**, a
  clean monotonic gradient across classes 1-5 (class-1 median soil-adjusted DTW
  8.1 m -> class-5 0.47 m), with one honest weakness - D2 under-flags class 6
  (peatland "winter-only" stands). D2 now has a DERIVE-AND-BENCHMARK result
  against an operational product. Unit tested; wired into `run.py`.
- **B2 (Medium)** - *done.* `trend_test` (Mann-Kendall) added. The D3
  season-lengthening is **tau 0.32, p = 0.0005** (significant); the E3
  conflict-free-window decline is **tau -0.20, p = 0.040** (weak but
  significant). Both notes and the README now carry the statistics.
- **D3 (F, Medium)** - *done.* `patch_dpc` now uses the maximum-product
  probability path (`_max_product_probability`, Dijkstra via `networkx`), the
  proper PC definition. PC 0.305 -> 0.322, top dPC values shift < 1 point, the
  ranking is unchanged - the simplification had been harmless here, but the
  method is now standard.
- **C1 (High)** - *reframed.* README and MODULE_E_NOTES now headline the
  waterway-buffer result on the 2-4 ha threshold band (~30,000-50,000 ha
  additional), with the ditch-inclusive 0.5-1 ha figure explicitly not the
  headline.
- **C2 (High)** - *reframed.* E5/E6 are now reported as a **relative**
  erosion-risk pattern, not absolute t/ha/yr; the README and notes say the
  absolute scale could not be reconciled with the Metsäkeskus product.
- **C3 (Medium)** - *done.* The E2 fertility cut is now cited to Tapio's
  *Metsänhoidon suositukset 2019* (continuous cover on drained spruce mires,
  mustikkaturvekangas and richer); both `<= 3` and `<= 2` results reported.
- **C5 (Medium)** - *done.* The deadwood figure is now cited to Luke's
  Tilastotietokanta table "Kuolleen puuston keskitilavuus metsämaalla",
  VMI2022, not a news article.
- **A1 / A3 / A4 (positioning)** - *reframed.* The README opens with a scope
  note: the reimplementations were to understand and check the official
  products; in a role you would consume them. Module F is labelled exploratory
  throughout. The "no ML" framing is softened to "chosen for interpretability".
- **D5 (F, Medium)** - *reframed.* "Robust" is now defined precisely in the
  notes and README as stable across the *resistance-model parameters*, not the
  structural choices.
- **D6 (F, Low)** - *reframed.* The README states the node network is
  effectively designations + old stands (ympäristötuki is 10 tiny polygons).
- **E1 (Medium)** - *documented, not closed.* The README now has an explicit
  "reproducibility gap" note pointing at a `--rebuild` flag as the fix.

**Considered and deferred (documented as caveats, not actioned):**

- **A2** (one crisp operational deliverable) - packaging work for the portfolio.
- **C2 partial** (swap in Lilja's Finnish K factors) - a real parameter study;
  the relative-index reframing removes the pressure.
- **C4** (trim E3 to a paragraph) - the notes already walked the claim back;
  left as-is.
- **C6** (site plan uses per-stand workability) - the Korjuukelpoisuus class is
  the natural thing to carry into E8; a real build, deferred.
- **D1 full** (decide Module F scope - keep vs trim) - kept in full, labelled
  exploratory; trimming is a call for the next review.
- **D2 (F)** (name a focal species for the resistance surface) - a substantive
  re-parameterisation, deferred; the limitation is now stated.
- **D4 (F)** (64 m subset check) - deferred.
- **E1 full** (fold derivations into `run.py`) - deferred; documented.

The net effect: the review's single biggest gap (no operational benchmark for
D2) is closed with a genuine result; two soft headline numbers (buffer range,
RUSLE absolutes) are re-based; the positioning is now explicit about scope and
level; and the smaller framing points are fixed. The deferred items are all
either larger builds or portfolio packaging.

---

## How to read this

Each item: **Finding** / **Why it matters** / **Better alternative** /
**Already acknowledged?** (does the repo's own documentation flag it) /
**Reviewer's lean** (deliberately provisional).

Severity:

- **High** - a headline claim is not adequately supported, a reported number
  could be materially wrong, or the framing would mislead a Metsä reader.
- **Medium** - a defensible shortcut, but a clearly better standard alternative
  (often an official Finnish product) exists that would change the numbers or
  the confidence in them.
- **Low** - worth recording; small effect or presentational.

---

## 0. Overall assessment

Technically this is well above the bar for the role it is attached to. The data
engineering (five agencies, WFS/WCS/OGC-API/zip, caching, a stated three-tier
rule) is exactly the day job and is done cleanly. The honesty is consistent and
load-bearing: the DTW tool error was root-caused rather than shipped, the
declaration-timing check is reported as inconclusive, the RUSLE benchmark is
framed as "agreement, not validation", and the connectivity index is explicitly
not reported as a headline number. The derived-stream-network Horton-law check
is a genuinely good piece of unprompted validation.

The concerns cluster in four places:

1. **Level and positioning.** Two modules reimplement national models from
   first principles (depth-to-water, RUSLE) and one is a specialist
   landscape-ecology analysis (graph connectivity + Monte Carlo). A hiring
   manager for a GIS-analyst seat will read this as "wants an R&D or specialist
   role" or "how much of this is the candidate's own work". Not a flaw in the
   analysis; a flaw in how the project sells the person.
2. **Official products that should have been the benchmark were not used.**
   Metsäkeskus publishes an operational harvest-trafficability raster
   (Korjuukelpoisuus) - the direct comparison for Module D2's workability
   output - and it is never used. Module E's RUSLE is benchmarked, but against
   a product the review itself shows is a slope index, and the absolute values
   are left unresolved.
3. **A couple of headline numbers are too soft to headline.** The
   waterway-buffer result is a 5x range (21,000-114,000 ha) whose wet end the
   repo admits is drainage ditches. The 30-day season-lengthening claim has no
   trend-significance test.
4. **Module F is under-grounded and hard for a non-specialist reviewer to
   assess.** The resistance surface is entirely assumption-based, models no
   named species, and the "robust set" is robust only to the parameters the
   sweep varies, not the structural choices.

None of this collapses the project. Most of it is framing, one missing
benchmark, and a decision about Module F's scope.

---

## A. Positioning and candidate fit

### A1. The project demonstrates capability well above the advertised role - High (framing)
**Finding.** A junior-to-mid GIS analyst in Finnish forestry consumes Luke's
DTW raster and Metsäkeskus's RUSLE and Korjuukelpoisuus layers; runs
buffers, overlays, zonal stats; produces maps and standard reports. This
project *reimplements* DTW (breach depressions, D-infinity routing,
elevation-above-stream) and RUSLE (all five factors) and benchmarks them
statistically, and builds a graph-theoretic connectivity pipeline with a 20-run
Monte-Carlo sensitivity analysis.
**Why it matters.** To a Metsä hiring reviewer this reads two ways: (a) strong,
rigorous, understands the domain deeply; (b) over-qualified / over-engineered /
"is this really a GIS-analyst candidate, and is this all their own work". The
second reading is a real risk and the repo does nothing to manage it.
**Better alternative.** State plainly, in the README and in conversation, that
the reimplementations were to *understand and sanity-check* the official
products, and that in a role the candidate would consume Luke's DTW,
Metsäkeskus's RUSLE and Korjuukelpoisuus. Lead the portfolio with the data
engineering and the findings (both role-appropriate), not the model rebuilds.
**Already acknowledged?** No - the README presents the rebuilds neutrally as
method.
**Reviewer's lean.** Reframe. Do not remove the work, but change what the
project foregrounds.

### A2. Breadth without a single crisp operational deliverable - Medium
**Finding.** ~15 analyses across three modules. There is no one polished output
a Metsä planner would pick up and use - e.g. a district-level "stand harvest-
window calendar", or a "buffer-gap map for one supply block", or a "CCF-
eligible stand list with the root-rot conflict flagged".
**Why it matters.** A reviewer assessing "can this person deliver a thing my
team needs next month" sees range but has to assemble the deliverable
themselves from `report.json` and seven GeoPackages.
**Better alternative.** Pick one module (E is the natural choice) and produce
one finished artefact end to end - a map series plus a short PDF-style
write-up for one sub-area - as the headline, with the rest as supporting depth.
**Already acknowledged?** No.
**Reviewer's lean.** Worth doing for the portfolio; it is packaging, not rework.

### A3. Domain framing is textbook-correct but reads as "read the documentation" - Medium
**Finding.** Metsä Group Plus measures, kelirikko, ojitus, root-rot obligation,
CCF-on-peat - all handled correctly, but framed the way the published guidance
frames them. A working practitioner would more often reach for the operational
product: Korjuukelpoisuus for trafficability, the Metsäkeskus RUSLE for erosion
zoning, the ojitus / drainagestate data for ditches.
**Why it matters.** A Metsä forester on the interview panel may notice that the
project derives proxies where an operational layer already exists, which reads
as "hasn't worked with the operational stack".
**Better alternative.** Benchmark against the operational products explicitly
(see B1, C2); when a proxy is used, say why the operational layer was not
sufficient.
**Already acknowledged?** Partially - the three-tier rule names benchmarking,
but D2 and E's workability/erosion outputs skip it.
**Reviewer's lean.** Add the operational-product comparisons; they are the
single thing that would most change how a Metsä reviewer reads the project.

### A4. The "no machine learning" rule is presented as a virtue; Metsä / Luke use ML - Low
**Finding.** "No black boxes" is stated as a design principle. MS-NFI's improved
k-NN, and newer Luke work with gradient boosting, are ML; Metsä's data team is
not ML-averse.
**Why it matters.** Neutral-to-slightly-negative: could read as principled, or
as "has not done ML".
**Better alternative.** Frame it as "chosen for interpretability on this
problem set", not as a general stance, and note where ML would be the right
tool (e.g. a gradient-boosted volume comparison, already a documented deferred
extension in Project 1).
**Reviewer's lean.** Soften the framing; it is a one-line change.

---

## B. Module D - harvest windows and root rot

### B1. Metsäkeskus Korjuukelpoisuus is the missing benchmark for D2 - High
**Finding.** D1's DTW is benchmarked against Luke's official DTW (good). But
D2's actual output - a per-date *workability* classification from soil-adjusted
DTW plus frozen ground - is never compared against Metsäkeskus's operational
**Korjuukelpoisuus** raster (a 6-class harvest-trafficability product,
kelirikko ... talvi, 16 m, on the same WCS the project already uses for RUSLE).
This is the direct DERIVE-AND-BENCHMARK comparison for D2 and the three-tier
rule calls for it.
**Why it matters.** D2 is the module's core novelty (adding weather and soil to
DTW), and its one validation route - declared harvest timing - came back
inconclusive. So the headline extension is currently unvalidated. Korjuukelpoisuus
is the obvious, available check.
**Better alternative.** Fetch `Korjuukelpoisuus` for the D1 catchment (or the
AOI), map D2's workable/not classification onto its classes, and report
agreement - even a confusion matrix against "class 6 = winter-only" would be
worth more than the declaration check.
**Already acknowledged?** No. Korjuukelpoisuus is in `DATA_SOURCES.md` but is
not used anywhere in Project 2.
**Reviewer's lean.** Do this. It is the biggest single gap in Module D.

### B2. The 30-day season-lengthening finding has no significance test - Medium
**Finding.** MODULE_D_NOTES reports the thermal season grew from a 1970s mean
of 147 days to 177 in 2015-2024, "a quantified, climate-consistent finding".
There is no trend test against interannual variance.
**Why it matters.** Project 1's review flagged exactly this pattern (a
decade-mean difference stated as a finding without a test). Interannual
variability in Finnish season length is large; a Mann-Kendall or OLS-trend
p-value is needed before this is a "finding" rather than "the last decade ran
warm".
**Better alternative.** Mann-Kendall on the annual series; report tau and p.
Same for the E3 frozen-window series.
**Already acknowledged?** No.
**Reviewer's lean.** Add the test; it is a few lines and it either firms up the
claim or downgrades it to "consistent with warming, not independently
significant here".

### B3. The frozen-ground proxy is a crude stand-in for soil frost - Medium
**Finding.** "Frozen ground" = a run of >= 3 days with tmin <= -2 C. Real soil
frost lags air temperature, depends heavily on snow cover (insulation), soil
moisture and the organic layer, and is what actually governs machine bearing
capacity.
**Why it matters.** Every D2/D3/E3 "workable in winter" number flows from this
proxy. FMI publishes a soil-frost / snow model and soil-temperature
observations; the proxy has not been checked against either for even one
winter.
**Better alternative.** Validate the proxy against FMI soil-temperature data or
the frost model for a few winters at station 101537; or state it as an
uncalibrated indicator.
**Already acknowledged?** Partially - called "a simple, transparent proxy".
**Reviewer's lean.** One winter of FMI soil-temp comparison would settle it.

### B4. One FMI station for a 3,400 km2 AOI; the root-rot test is municipality-specific - Low
**Finding.** The Act's cold-spell exemption is defined per municipality; D3 uses
station 101537 for the whole AOI. Frost timing varies across the AOI.
**Why it matters.** Small - the AOI is climatically fairly uniform - but the
rule engine claims to encode a municipality-level test it does not apply
spatially.
**Better alternative.** Add a second/third station and interpolate, or state the
single-station assumption in the rule-engine output.
**Already acknowledged?** Yes, in the caveats.
**Reviewer's lean.** Note it; add stations only if D is revisited.

### B5. DTW reimplementation: single breached DEM, no culvert-burning, bias not decomposed - Low
**Finding.** One conditioned DEM is used for both routing and elevation; road/
stream crossings are not burned; the +2-3 m bias vs Luke is explained
(D-infinity vs D8, no culverts, no peat cost-model) but not attributed.
**Already acknowledged?** Yes, explicitly, in MODULE_D_NOTES.
**Reviewer's lean.** Leave; the honest flagging is sufficient for a portfolio.

---

## C. Module E - Metsä Group Plus site planning

### C1. The waterway-buffer headline is a 5x range whose wet end is ditches - High
**Finding.** "Our derived stream network finds 21,000-114,000 ha of buffer zone
that mapped hydrography misses." The 0.5 ha network is ~15% of the AOI as stream
cells; the repo's own caveat says a large share is forestry drainage ditches,
not natural streams.
**Why it matters.** A range this wide, with the wet end acknowledged to be
partly an artefact, is not a usable headline - a Metsä water-protection planner
would ask "so which is it". The credible figure is the 2-4 ha threshold
(~30,000-50,000 ha additional), not the range.
**Better alternative.** Subtract a ditch layer. Metsäkeskus stand data carries
`drainagestate` (ojikko/muuttuma/turvekangas) and there are national ditch
datasets; masking derived channels that coincide with mapped/derived ditches
would separate "missed natural streams" from "known ditches". Failing that,
report only the 2-4 ha figure and drop the range framing.
**Already acknowledged?** Yes - the caveat is clear. But the README still leads
with the full range.
**Reviewer's lean.** Either subtract ditches or re-headline on 2-4 ha.

### C2. RUSLE absolute values are reported without a resolved scale or a Finnish K factor - High
**Finding.** (a) The R factor (300) is taken from a south-west Finland
watershed study, applied to Central Finland. (b) The K values are Panagos 2014
(Europe-wide) "plus Finnish context", when Lilja et al. published Finnish RUSLE
K factors specifically. (c) The benchmark left the absolute scale vs Metsäkeskus
unresolved (~100x, "probably units") and the module still reports absolute A
(median 0.10, max 62 t/ha/yr).
**Why it matters.** Reporting t/ha/yr numbers built on an out-of-region R, a
non-Finnish K, and an unreconciled scale invites a reviewer to distrust all of
E5. The *relative* risk map is fine; the absolute numbers are not defensible as
stated.
**Better alternative.** Swap in Lilja's Finnish K; resolve the Metsäkeskus
units (product spec or a direct query); and if the units cannot be resolved,
report E5 as a relative erosion-risk index only, with no t/ha/yr.
**Already acknowledged?** The scale gap and the R provenance are flagged; the
Finnish-K alternative is not mentioned.
**Reviewer's lean.** Finnish K + drop or caveat absolute A.

### C3. E2's fertility cut swings the result 12x and the chosen value is asserted - Medium
**Finding.** CCF-eligible area is 1,674 ha at fertility <= 3 and 141 ha at
<= 2. The notes report both (good) but justify <= 3 as "the practical CCF-on-
spruce-peat band (Tapio)" without a specific citation.
**Why it matters.** The headline number depends entirely on this choice, and a
12x swing between two defensible cuts is large.
**Better alternative.** Cite the exact Tapio / Luke guidance for CCF on drained
spruce mires (it specifies site types), and pin the cut to it. If the guidance
is a range, report the range as the result.
**Already acknowledged?** Yes - both values are reported.
**Reviewer's lean.** Get the citation; it is a document lookup.

### C4. E3's conflict overlay is largely a tautology - Medium
**Finding.** "100% of CCF-eligible stands also trigger the root-rot rule" is
forced by both filters keying on spruce share >= 0.5. The substantive part (the
~106-day conflict-free window) was over-stated once and corrected in the notes.
**Why it matters.** As a standalone "finding" the overlap says little. The
module's real content is the window calculation, which is an AOI-level statistic
with no per-stand variation.
**Better alternative.** Demote the overlap to one sentence; lead E3 with the
window and its (tested - see B2) trend. Or fold E3 into E2 as a note.
**Already acknowledged?** Yes - the notes already walked back the first version.
**Reviewer's lean.** Trim E3 to a paragraph.

### C5. Deadwood: the regional figure comes from a news article - Medium
**Finding.** `deadwood_vmi_m3_per_ha: 5.5` is from a Luke news item on the
VMI2022 update, not the PxWeb statistics table or a VMI report.
**Why it matters.** A deliverable should not rest a headline number
(~1.29 Mm3 / ~0.39 Mm3 standing) on a paraphrased news figure.
**Better alternative.** Pull the number from Luke's statistics database (the
`kuolleen puuston tilavuus` table by region) or the primary VMI report and cite
it.
**Already acknowledged?** Yes, explicitly flagged in the caveats.
**Reviewer's lean.** Fix before the number appears anywhere client-facing.

### C6. The site plan does not use Module D's per-date workability - Medium
**Finding.** E8's `harvest_timing` column is a two-value flag (peat or
CCF -> "frozen-ground preferred"; else "no restriction"). It does not sample
D2's soil-adjusted DTW + weather workability per stand.
**Why it matters.** The project's stated aim is "when can a stand be
harvested"; the site plan answers it with a soil-type flag, not the machinery
built in Module D. The two modules do not connect where they most should.
**Better alternative.** For each stand, sample the D2 workability surface (or
the Korjuukelpoisuus class from B1) and carry a real per-stand harvest-window
descriptor into the site plan.
**Already acknowledged?** No.
**Reviewer's lean.** This is the join that would make E8 a genuine deliverable.

### C7. E5 benchmarked at 2 m on the catchment; the AOI RUSLE (E6) is 16 m and unbenchmarked - Low
**Finding.** The DERIVE-AND-BENCHMARK comparison is catchment-only at 2 m; the
AOI-scale product (E6) is a coarser 16 m RUSLE that is not itself benchmarked.
**Why it matters.** The "benchmarked then scaled" promise is half-kept, same
shape as a Project 1 finding.
**Better alternative.** Note explicitly that E6 is a coarser derivative of the
benchmarked catchment method, not a benchmarked product.
**Reviewer's lean.** Framing note.

---

## D. Module F - biodiversity network connectivity

### D1. A specialist analysis with no benchmark, in a GIS-analyst portfolio - High (positioning)
**Finding.** PC, dPC, least-cost corridors and a Monte-Carlo sensitivity sweep
are conservation-planning / landscape-ecology methods. No official product
exists to check against (acknowledged). A Metsä panel without a connectivity
specialist cannot assess it; one with a specialist will have the detailed
questions below.
**Why it matters.** High-effort, low-verifiability, and furthest from the
advertised role. It is the module most likely to prompt "why is this here".
**Better alternative.** Either (a) keep only F1 (node assembly) + F2 (resistance
surface) + patch dPC as a compact "where are the network's keystone protected
sites" result and drop the corridor/sweep machinery, or (b) keep it in full but
label it clearly as exploratory work beyond the brief.
**Already acknowledged?** The notes and README both call it "the least certain
module" and "exploratory, not a recommendation".
**Reviewer's lean.** Decide scope deliberately. If it stays, it needs D2-D4
below addressed.

### D2. The resistance surface has no empirical basis and models no species - High
**Finding.** Weights (0.30/0.25/0.20/0.25) and land-cover costs (forest 0.1 ...
water 1.0) are chosen, not derived. The analysis is for "forest biodiversity"
in the abstract - no focal species, guild or dispersal ecology.
**Why it matters.** "Connectivity for what?" is the first question any reviewer
asks. Resistance values that are not tied to a named organism's movement (from
telemetry, gene flow, or structured expert elicitation) make the corridors and
the robust set hard to defend. The sensitivity sweep perturbs an arbitrary
centre.
**Better alternative.** Pick one or two focal species with published resistance
parameterisations (e.g. flying squirrel *Pteromys volans* - a legally relevant
Finnish forest connectivity species with a literature - or a deadwood beetle
guild) and parameterise to them; or run a formal multi-expert elicitation and
report the spread.
**Already acknowledged?** No - the abstraction is not flagged as a limitation.
**Reviewer's lean.** Name a focal species or downgrade the module's claims.

### D3. dPC uses the direct pairwise term, not the maximum-product path - Medium
**Finding.** `patch_dpc` sets `p_ij = exp(-cost_ij / dispersal)` directly; the
notes say "adequate at this patch count". Proper PC (Saura & Pascual-Hortal)
uses the maximum-product probability path through the graph.
**Why it matters.** The direct term underestimates connectivity for patches
linked via intermediates, which can change the dPC ranking - and the dPC
ranking (two Natura sites carry ~70%) is a headline.
**Better alternative.** Compute the max-product path (Dijkstra on -log p) before
the dPC removal loop. `networkx` is already a dependency.
**Already acknowledged?** Yes, as a stated simplification.
**Reviewer's lean.** Use the proper path; it is a known algorithm and the
dependency is present.

### D4. 128 m grid + ">50% water = barrier" is coarse for a lake-dense landscape - Medium
**Finding.** Least-cost routing runs on a 128 m grid; coarse cells averaging
over land and water are snapped to the barrier value if the mean exceeds half
the water cost.
**Why it matters.** The connectivity pinch points in Central Finland *are* the
narrow land bridges between lakes. At 128 m a real 60-100 m isthmus can be
closed (snapped to barrier) or a non-existent one opened. 179k of 308k pairs
"reachable" is sensitive to this rule.
**Better alternative.** Re-run a subset at 64 m and check the dPC ranking and
the reachable-pair count are stable; or use a max (not mean) rule for the
water snap so land bridges survive.
**Already acknowledged?** No.
**Reviewer's lean.** One 64 m subset check.

### D5. "Robust" is robust to the parameter sweep, not the structural choices - Medium
**Finding.** The sweep varies weights, land-cover costs and dispersal distance.
Fixed across all 20 runs: node sources, the 200 m patch merge, backbone-k = 3,
corridor slack, the 128 m grid.
**Why it matters.** "Robust set of 3,783 stands" sounds stronger than it is -
it is robust to the easy-to-vary continuous parameters only.
**Better alternative.** Add a few structural variants to the sweep (k = 2/4,
merge = 100/300 m, min patch area), or state precisely what "robust" covers.
**Already acknowledged?** Partly - the notes list what is fixed.
**Reviewer's lean.** Tighten the wording; optionally widen the sweep.

### D6. "Old stands" is half the intended definition; ympäristötuki is negligible - Low
**Finding.** Plan said "old **or structurally rich**"; only `meanage >= 120`
is implemented (413 stands, 359 ha). ympäristötuki contributes 10 polygons /
1 ha. The "four node sources" framing oversells a network that is really
protected areas + §10 habitats.
**Better alternative.** Add a structural-richness criterion (basal area +
large-tree / multi-storey proxy), or restate the node set as "designations +
old stands" and note ympäristötuki is immaterial here.
**Already acknowledged?** Yes, both in the caveats.
**Reviewer's lean.** Restate; add structure only if F is kept in full.

---

## E. Cross-cutting / infrastructure / data

### E1. The pipeline is not reproducible end to end from `run.py` - Medium
**Finding.** `run.py` depends on `data/interim/{e,f}/` products created by
ad-hoc scratch scripts that were written, run once, and deleted. A reviewer
cloning the repo cannot regenerate the results without reconstructing those
steps from the module notes.
**Why it matters.** For a portfolio piece whose selling point is "reproducible
batch pipeline", the reproducibility gap is the thing a reviewer will test
first.
**Better alternative.** Fold the derivation steps (DEM fetch/resample, channel
network, RUSLE factor rasters, F2 resistance) into `run.py` behind a
`--rebuild` flag or a prerequisite-builder, and do one clean cold run to prove
it. Project 1 had the same gap (its `run.py` was a stub).
**Already acknowledged?** The notes describe the steps; the README says the
derivations are "produced by the per-step scripts documented in the module
notes" - i.e. the gap is documented, not closed.
**Reviewer's lean.** Close it for at least one module.

### E2. Reprojection is patched inline, against the repo's own hard constraint - Low
**Finding.** CLAUDE.md mandates "reproject once at ingest, never mid-pipeline".
In practice CLC (declared 25835), the reserve shapefiles (untagged TM35FIN) and
others are handled with inline `set_crs`/`allow_override` at point of use.
**Why it matters.** They are coordinate-identical so the numbers are fine, but
it is a deviation from the stated discipline and a reviewer checking the
constraint will notice.
**Better alternative.** A single CRS-normalisation gate in the fetch layer.
**Reviewer's lean.** Note it; low risk.

### E3. Config has grown large with per-value citations missing - Low
**Finding.** A 23-entry K table, a 49-entry C table, an 8-entry resistance
land-cover table, resistance weights - many entries are "from literature +
context" without a specific source per value.
**Better alternative.** A one-line citation per block (or per value where they
differ in provenance).
**Reviewer's lean.** Add sources; it is the difference between "tunable" and
"traceable".

### E4. Integration paths are exercised only by deleted scratch runs, not tests/CI - Low
**Finding.** Unit tests cover pure functions; the WhiteboxTools pipeline, the
WCS fetch, the full module runs are verified by live scratch scripts that no
longer exist.
**Better alternative.** A slow integration test (marked, off the default CI
path) that runs one module end to end on a tiny AOI.
**Already acknowledged?** Consistent with Project 1's testing philosophy.
**Reviewer's lean.** Acceptable for a portfolio; note it.

---

## F. Things done well (for balance)

- Honest negative and null results, consistently: the DTW tool error root-caused
  not shipped; the declaration-timing check reported inconclusive; the E3
  window claim walked back; the RUSLE benchmark framed as "agreement, not
  validation, both off the same DEM".
- The Horton-law scaling check on the derived stream network - unprompted,
  quantitative, and exactly the right way to sanity-check a DEM-derived
  network.
- Recognising that Metsäkeskus's published RUSLE is a slope index with no cover
  signal - a sharp, useful observation.
- The F3b sensitivity sweep existing at all; most connectivity work ships a
  single map.
- Three-tier data rule stated in every module docstring.
- Config-driven, no magic numbers in module code.
- Module notes that record *why*, with the reasoning and the dead ends, not
  just the final method.
- The `_stream_mask_from_raster` nodata bug was caught mid-run and
  regression-tested rather than silently producing a wrong buffer figure.

---

## G. Shortlist - most worth a second look

Ranked by (impact on a claim or on how a Metsä reviewer reads the project) x
(low cost):

1. **B1 - benchmark D2 against Korjuukelpoisuus.** The missing official
   comparison; the product is on a WCS the project already uses. Turns D2 from
   "unvalidated extension" into "validated against the operational layer".
2. **A1 / A3 - reposition.** README and CV framing: reimplementations were to
   understand and check the official products; in a role you would consume
   them. Lead with data engineering and findings.
3. **C1 - fix the waterway-buffer headline.** Subtract a ditch layer or report
   only the 2-4 ha figure. The current range reads as "cannot say".
4. **C2 - RUSLE.** Finnish (Lilja) K factor; resolve or drop absolute t/ha/yr.
5. **C5 - deadwood.** Pin the 5.5 m3/ha figure to a primary Luke source.
6. **D1 - decide Module F's scope.** Keep F1+F2+dPC as a compact result and
   drop the corridor/sweep machinery, or keep it in full and label it
   exploratory - and if kept, address D2 (name a focal species) and D3
   (max-product path).
7. **B2 - add a trend-significance test** to the season-lengthening and
   frozen-window claims.
8. **E1 - one clean end-to-end reproducible run** for at least one module.

Everything else is note-and-move-on.

---

## H. Reviewer's one-paragraph verdict

Technically this is a strong project - more rigorous, and more honest about its
limits, than a lot of published forestry GIS work. For the role it is attached
to, the problem is not quality but pitch and packaging: it reimplements two
national models and runs a specialist connectivity analysis, which a Metsä
hiring reviewer will read as over-scope or will want to attribute carefully,
and it never benchmarks its two most operationally relevant outputs
(harvest workability, erosion zoning) against the Metsäkeskus products that
already do those jobs. The fixes are mostly cheap: one benchmark
(Korjuukelpoisuus), two headline numbers tightened (buffer range, RUSLE
absolutes), a primary source for one figure, a trend test, and a deliberate
decision on Module F's scope and framing. Addressing the shortlist would move
this from "impressive but hard to place" to "clearly a strong hire for a
data-capable GIS role".
