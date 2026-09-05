# regenerative-harvest-planning/src/d3_rootrot_rules.py
"""Module D3 - root rot obligation, as a deterministic rule engine.

From the Forest Damages Prevention Act. Stump treatment mandatory 1 May-30 Nov
where: mineral soil, pine and/or spruce > 50% of pre-felling stand volume; or
peat soil, spruce > 50%. Exempt where the municipality's minimum temperature
was below -10 C during the three weeks preceding felling (spore dispersal
above roughly +5 C daily mean, so a warm spring starts the season early and a
mild autumn extends it). Layered constraints: conifer stumps > 10 cm diameter,
85% cut-surface coverage, application within 3 hours, no urea within 10 m of
watercourses or small waters - using the D1 derived channel network, not just
mapped hydrography.

Data tiers: stand attributes and FMI daily temperature FETCH; the rule
evaluation itself is a deterministic legal rule, not a statistical model - no
ML question arises here.

Evaluate stand attributes against FMI daily temperature on a date grid across a
full year, per municipality.

No implementation yet - scaffold only.
"""
