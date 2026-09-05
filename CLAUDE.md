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
  **Decision D2 (Module E deadwood deficit) is still open** — resolve before
  Module E, not before Module D. **Decision D4** (small opens: surface-water-
  flow route, ympäristötuki field, CLC2024 release, a 32766-pixel spot-check) —
  close at kickoff.
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
**Scaffolded (2026-08-30), not yet started.** Structure, config (with all TASK 00
values already filled in — nothing here needs re-deciding), and stub modules are
in place; `config/pipeline.yaml` validates against `fi_forest_data/validate.py`.
Next: Module D1 (reimplement DTW and benchmark it), after building the two
blocking pieces its scaffold docstring names (`nls.fetch_dem` tiling wrapper,
`luke.fetch_dtw` implementation). Then D2, D3, E, F.
