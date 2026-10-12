"""povodne — flood damage mapping from space (Sentinel-1/2, Copernicus DEM, pre-event OpenStreetMap).

Entry point: ``python -m povodne run ...`` (whole pipeline) and ``python -m povodne serve`` (dashboard).
Modules talk to each other only through files in a run directory (docs/ARCHITECTURE.md).
"""
__version__ = "0.1.0"
