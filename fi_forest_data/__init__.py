# regenerative-harvest-planning/fi_forest_data/__init__.py
"""Data access layer for the Finnish forest portfolio.

Fetches, caches and reprojects data from Metsakeskus, Luke, NLS, FMI and SYKE.
Reprojection to EPSG:3067 happens here at ingest, once, and nowhere else. This
layer contains no analysis logic: it only gets data and hands it over. Copied
from boreal-stand-intelligence (Project 1); this repo does not use Sentinel
(no sentinel.py) and adds syke.py for protected areas, CORINE and watersheds.
"""

from fi_forest_data.aoi import AOI

__all__ = ["AOI"]
