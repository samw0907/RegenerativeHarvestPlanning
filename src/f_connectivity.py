# regenerative-harvest-planning/src/f_connectivity.py
"""Module F - biodiversity network connectivity.

Nodes: protected areas (SYKE/Metsahallitus), Forest Act §10 habitats,
environmental support (ymparistotuki) sites, old or structurally rich stands.
Resistance surface from stand age, canopy structure, species composition and
land cover. Connectivity via least-cost paths and graph-theoretic importance
measures. Rank candidate stands by marginal connectivity gain if a Plus
retention measure were applied there.

Data tier: FETCH throughout (registers and designations); the connectivity
analysis itself is transparent graph analysis, not a fitted model.

The honesty requirement (already the standard the other modules should match,
not a new lesson): resistance surfaces are assumption-laden. Run a sensitivity
sweep across plausible parameterisations (`resistance_sensitivity_runs` in
config) and report which stands are robustly high-value across all of them
versus which are artefacts of one parameter choice. The robust set is the
deliverable. Presented as an exploratory prioritisation method, not a
recommendation - the least certain of the three modules, and the README says so.

No implementation yet - scaffold only.
"""
