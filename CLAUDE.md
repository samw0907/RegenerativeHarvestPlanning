# CLAUDE.md — regenerative-harvest-planning

Project 2 of a two-project portfolio piece. This repo operationalises the
Finnish harvest-window problem and the published "Metsä Group Plus"
regenerative-forestry targets (a real, specific programme this module's numbers
are drawn from — 10–30 m buffers, 30 retention trees/ha, etc.) for one mill
procurement area: for every stand, when can it be harvested, what must be left
behind, and where do biodiversity measures deliver most benefit. Centrepiece is
a date-specific wetness and trafficability surface, extending the national DTW
method with the two terms its own authors say are missing. Batch analytical
pipeline, validated against official products where they exist, static figures
and JSON reports.

Companion repo: `boreal-stand-intelligence` (Project 1, complete). Shares
`fi_forest_data`, copied across rather than packaged (see "Where things are").

## Hard constraints
- Machine learning is not the default approach. Every module here is a
  documented operational method (DTW, D-infinity flow routing), a deterministic
  legal rule engine (root rot obligation, Metsä Group Plus measures), or
  transparent graph analysis (connectivity). ML is not forbidden, but
  introducing it is a design decision to raise and agree first, not a silent
  substitution.
- Do not attempt NLS 5 p laser scanning data — this repo has no ALS use at all
  (unlike Project 1); only the 2 m DEM matters here, from the key-free Funet
  mirror.
- EPSG:3067 (ETRS-TM35FIN) throughout. Reproject once at ingest, never
  mid-pipeline.
- MS-NFI nodata 32766 (forestry land without satellite cover) and 32767 (not
  forestry land or outside country) have different meanings. Do not collapse
  them.
- Luke DTW unit care: 2019 vintage is millimetres (x1000), 2023 CMv2 is
  centimetres (x100). This repo uses 2023 CMv2 throughout (TASK 00 decision D3)
  — never mix vintages in one comparison.
- CC BY 4.0 attribution required on all outputs derived from Metsäkeskus, Luke,
  NLS, FMI or SYKE data. Include the attribution string in figure captions and
  JSON reports.
- Pin Metsäkeskus and Luke endpoint/product versions. Record the fetch date in
  run metadata.
- No emojis anywhere. Comments sparingly, plus a file path comment at the top of
  each file.
- Never delete data, drop a database, force-push or rewrite history without
  stopping first and explaining the risk in detail.
- Never read, write or create .env or credentials files. Local git only.

## Method constraint, stated positively
Every method here is a documented operational method (DTW, RUSLE, D-infinity
flow routing), a deterministic rule engine (root rot, Metsä Group Plus), or
transparent graph analysis (connectivity, with a sensitivity sweep). If a task
seems to need something else, raise it.

## Three-tier data rule
Every input is FETCH (registers and designations), DERIVE AND BENCHMARK (an
official product exists with a published method — derive on a validation
subset, quantify agreement, then consume the official product at full AOI
scale), or DERIVE ONLY (no official product; this is where the analysis lives).
State the tier in the module docstring. Do not reprocess a full AOI where the
benchmark pattern applies. **State benchmark agreement honestly**: D1's DTW and
E's RUSLE both compare against products built from the same NLS DEM this repo
uses — that is agreement, not independent validation (a lesson carried from
Project 1's Module A, which had to walk back an overstated independence claim).

## AOI
Project 2, Central Finland (Äänekoski bioproduct mill procurement area:
Äänekoski – Saarijärvi – Laukaa). EPSG:3067 bbox:
[404000, 6910000, 454000, 6978000] — 50 x 68 km, ~3,400 km². Fixed. See
config/aoi_central.yaml. D1 validation catchment (SYKE FI1-14.06.161, 148 km²)
is fixed separately, config/pipeline.yaml.

## Where things are
- `docs/PROJECT_2_REGENERATIVE_HARVEST_PLANNING.md` — the plan, including the
  "Lessons carried from Project 1" section (read this before starting Module D)
- `docs/METSA_GIS_RESEARCH_FINDINGS.md` — background and published methods
- `docs/DATA_SOURCES.md` — endpoints, schemas, field mappings
- `docs/REPO_SCAFFOLD.md` — module contracts, config schema, acceptance criteria
- `docs/TASK_00_DISCOVERY.md` — the discovery task that verifies DATA_SOURCES.md
- `docs/TASK_00_FINDINGS.md` — discovery findings, deviations, decisions.
  **Decision D2 (Module E deadwood deficit) resolved 2026-09-05**: aggregate
  regional VMI statistic only, no per-stand deficit map (no per-stand or
  per-pixel deadwood source exists anywhere in the open data — confirmed live,
  not just in theory). **Decision D4** (small opens: surface-water-flow route,
  ympäristötuki field, CLC2024 release, a 32766-pixel spot-check) — close at
  kickoff.
- `docs/MODULE_D_NOTES.md`, `MODULE_E_NOTES.md`, `MODULE_F_NOTES.md` — running
  rationale + results per module, source material for the README. Create at
  each module's start, keep current as it is built (not yet created).
- `fi_forest_data/` — data access layer, copied from `boreal-stand-intelligence`
  (see each module's docstring for what still needs building: `luke.fetch_dtw`,
  a tiling wrapper for `nls.fetch_dem`, `syke.py` is new here)
- `src/` — analysis modules, letter/number-prefixed to match the project plan

## Local setup
Shared `.venv` at the working directory root (same one Project 1 uses).
From this repo: `pip install -r requirements.txt`. Both repos use the same
top-level package names (`fi_forest_data`, `src`), so **do not `pip install -e .`
for both repos into the shared venv at once** — the second editable install
silently redirects `import fi_forest_data` to the second repo's directory,
breaking the first. In practice this session never needed the editable install:
run scripts with the working directory set to the repo root (Python's default
`sys.path` then resolves `fi_forest_data`/`src` locally) rather than relying on
a global install. `Dockerfile` and `docker-compose.yml` are unaffected (each
container has only one repo's code) and give a reproducible run; CI runs flake8,
config validation and pytest per-repo, also unaffected.

## Status
**Module D complete (2026-09-05).** D1 (DTW reimplementation, benchmarked
against Luke's official product after rejecting and root-causing a first,
30-40x-wrong tool choice), D2 (weather/soil terms extending DTW into a dated
surface), D3 (root-rot rule engine, validated against real stand data) and the
D-validation step (declared harvest timing vs predicted workability — an
honest negative/inconclusive result, traced to `DECLARATIONARRIVALDATE` being
an administrative timestamp rather than a felling date, not a model failure)
are all built, tested and written up in `docs/MODULE_D_NOTES.md`.

**Module E complete (2026-09-06).** E1 (full-AOI derived stream network at
16 m + buffer comparison vs mapped hydrography), E2 (peatland CCF prescription,
~1,674 ha), E3 (CCF-vs-root-rot conflict overlay — 100% structural overlap +
the ~106-day/yr conflict-free felling window), E4 (§10 habitat proximity, ~6%
of stand area), E5 (RUSLE — LS/K/C/R built, benchmarked against Metsäkeskus's
product which turned out to be an LS-dominated terrain index), E6 (full-AOI
16 m RUSLE × buffer cross-reference), E7 (deadwood aggregate, ~0.39 Mm³
standing), E8 (per-stand site-plan record, 168,026 stands), E9 (`figures.py`
and a Module-E `run.py`). All in `docs/MODULE_E_NOTES.md`.

**Module F complete (2026-09-06).** F1 (node assembly — 2,769 nodes from
protected areas / §10 habitats / ympäristötuki / old stands; resolves TASK 00
D4), F2 (resistance surface from stand age/structure/species + CLC land cover),
F3a (least-cost connectivity — 786 patches, dPC patch importance, backbone
corridors, per-stand priority score), F3b (20-run sensitivity sweep → robust
set of 3,783 stands / 8,546 ha; PC itself swings 0.20–0.41 but the ranking is
stable), F4 (figures + `run.py` wiring). All in `docs/MODULE_F_NOTES.md`.
`python -m src.run` writes `outputs/.../{e,f}/{run_id}/`; add `--sweep` for
F3b. Next: the README.
