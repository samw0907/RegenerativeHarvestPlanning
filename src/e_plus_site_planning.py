# regenerative-harvest-planning/src/e_plus_site_planning.py
"""Module E - Metsa Group Plus site planning.

Turns the quantified Plus measures into a per-stand site plan:
- Waterway buffers (10/20/30 m) on the D1 derived channel network, compared
  against buffers from mapped hydrography alone (NLS topographic database) to
  quantify the additional area captured by streams mapped hydrography omits.
- Peatland continuous-cover prescription: lush, drained, spruce-dominated peat
  stands (site fertility, drainage status, spruce share - all in MS-NFI /
  Metsakeskus stand data), quantified against the +30% continuous-cover-share
  target.
- Retention and deadwood deficit against the gap to 30 retention trees/ha
  (>15 cm dbh), 20 dead trees/ha, 10 high-biodiversity stumps/ha. **Decision D2
  (docs/TASK_00_FINDINGS.md) is still open**: MS-NFI 2023 has no standing-
  deadwood theme, so there is no per-stand m3/ha source for the deadwood half of
  this. Resolve before building this component - candidates: drop it; use the
  Metsakeskus habitat `deadwoodpotential` field (qualitative); Luke VMI
  field-plot deadwood statistics at region level. Do not substitute a proxy
  silently.
- Valuable §10 habitat proximity and required setbacks.
- The conflict overlay: D3's root-rot risk vs the peatland continuous-cover
  prescription (CCF is best done in winter and discouraged under high root-rot
  risk) - surface the stands where the two disagree, do not average over it.

Data tiers: §10 habitats and mapped hydrography FETCH; RUSLE erosion risk DERIVE
AND BENCHMARK against Metsakeskus's own RUSLE (state this as agreement, not
independent validation, from the first draft - both derive from the same NLS
DEM; see the Project 1 lesson in the plan doc). Buffers and the deficit gap
DERIVE ONLY.

No implementation yet - scaffold only.
"""
