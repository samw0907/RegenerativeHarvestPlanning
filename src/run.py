# regenerative-harvest-planning/src/run.py
"""Pipeline entry point.

Loads and validates config/pipeline.yaml, resolves the AOI, and runs the
requested modules (D1, D2, D3, E, F) in order, writing outputs under
outputs/{project}/{module}/{run_id}/ where run_id is
{YYYYMMDD}_{HHMMSS}_{git_short_sha}. Each module writes rasters, vectors,
tables, figures, report.json and run_metadata.json.

No implementation yet - scaffold only.
"""
