"""Build the bundled EXAMPLE run in dashboard/sample_run/ from a real finished pipeline run (D-X-17).

The example lets anyone open real results without accounts or model weights. A full run folder is far too big for git
(rasters, raw downloads, every road within the 15 km routing buffer), so this keeps only what the dashboard shows and
slims it to < ~5 MB:
  * run.json / stats.json: copied, absolute paths made relative, ``example: true`` + an info notice added;
  * overlays/*.png: satellite images reduced to a 256-colour palette;
  * vector layers: coordinates rounded to ~1 m; buildings/roads/bridges/places kept only where something happened
    or (for the main roads, settlements and important places) inside the analysed area;
  * floodpath/: the precomputed result (trace one first: ``python -m povodne.floodpath <run> --lon X --lat Y``);
  * report/: copied as is. Rasters, raw data and logs are dropped.

Run:  python dashboard/tools/make_example_run.py runs/<finished run> [--run-id example_<name>] [--out dashboard/sample_run]
The synthetic generator (make_sample_run.py) stays for development without a real run.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

import geopandas as gpd
import shapely
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
OUT = HERE.parent / "sample_run"
EXAMPLE_ID_PREFIX = "example_"
MAIN_ROADS = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link"}
NOTE = ("This is a bundled example of a finished analysis, slimmed to fit the download: the satellite images use fewer "
        "colours, and roads, buildings and places outside the area are kept only where the flood affected them. "
        "The flood path shows one precomputed trace.")


def _relative_paths(text: str) -> str:
    """Drop machine-specific absolute paths (e.g. the model file) so the example does not leak the build machine."""
    root = re.escape(str(REPO_ROOT).rstrip("/") + "/")
    return re.sub(r'"/[^"]*?/(models/[^"]+)"', r'"\1"', re.sub(root, "", text))


def _write_gdf(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf = gdf.copy()
    gdf["geometry"] = shapely.set_precision(gdf.geometry.values, 1e-5)  # ~1 m: invisible on the map, ~half the size
    gdf = gdf[~gdf.geometry.is_empty]
    gdf.to_file(path, driver="GeoJSON", COORDINATE_PRECISION=5)


def _slim_vectors(src: Path, out: Path, area) -> dict[str, int]:
    def read(rel: str) -> gpd.GeoDataFrame | None:
        f = src / rel
        return gpd.read_file(f) if f.is_file() else None

    def inside(g: gpd.GeoDataFrame):
        return g.geometry.intersects(area)

    keep: dict[str, object] = {
        "flood/flood_polygons.geojson": lambda g: slice(None),
        "flood/debris_polygons.geojson": lambda g: slice(None),
        "damage/buildings_damage.geojson": lambda g: g["grade"] != "none",
        "damage/roads_damage.geojson": lambda g: (g["status"] != "passable") | (g["highway"].isin(MAIN_ROADS) & inside(g)),
        "damage/bridges_damage.geojson": lambda g: (g["status"] != "passable") | g["hit"].astype(bool),
        "damage/facilities_damage.geojson": lambda g: inside(g) | g["hit"].astype(bool),
        "damage/settlement_areas.geojson": lambda g: inside(g) | (g["buildings_affected"] > 0),
        "network/settlements_access.geojson": lambda g: inside(g) | (g["status"] != "connected"),
        "network/facilities_access.geojson": lambda g: inside(g) | g["hit"].astype(bool) | ~g["access"].isin(["reachable", "connected"]),
        "network/road_cuts.geojson": lambda g: slice(None),
        "network/landing_zones.geojson": lambda g: slice(None),
        "floodpath/path.geojson": lambda g: slice(None),
        "floodpath/settlements_on_path.geojson": lambda g: slice(None),
    }
    counts = {}
    for rel, rule in keep.items():
        g = read(rel)
        if g is None:
            continue
        g = g[rule(g)] if len(g) else g
        _write_gdf(g, out / rel)
        counts[rel] = len(g)
    return counts


def build(src: Path, out: Path = OUT, run_id: str | None = None) -> Path:
    src, out = Path(src), Path(out)
    meta = json.loads(_relative_paths((src / "run.json").read_text(encoding="utf-8")))
    stats = json.loads(_relative_paths((src / "stats.json").read_text(encoding="utf-8")))
    if (meta.get("progress") or {}).get("state") != "done":
        raise SystemExit(f"{src} is not a finished run")
    area = shapely.geometry.shape(meta["aoi"])
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    run_id = run_id or meta["run_id"]
    run_id = run_id if run_id.startswith(EXAMPLE_ID_PREFIX) else EXAMPLE_ID_PREFIX + run_id  # never collides with run_* ids
    meta.update(run_id=run_id, example=True, mock=False)
    meta.pop("timings_s", None)
    meta["notices"] = [{"step": "dashboard", "code": "bundled_example", "severity": "info", "message": NOTE, "details": {}}] + \
        [n for n in meta.get("notices", []) if n.get("code") != "bundled_example"]
    stats["run_id"] = run_id
    (out / "run.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    (out / "stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    if (src / "aoi.geojson").is_file():
        shutil.copy2(src / "aoi.geojson", out / "aoi.geojson")

    for rel in ("damage/damage_summary.json", "network/graph_stats.json", "network/repair_priority.json",
                "floodpath/along_path.json", "flood/confidence.json", "overlays/index.json"):
        if (src / rel).is_file():
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_text(_relative_paths((src / rel).read_text(encoding="utf-8")), encoding="utf-8")
    if (src / "report").is_dir():
        shutil.copytree(src / "report", out / "report")
    for png in sorted((src / "overlays").glob("*.png")):
        im = Image.open(png)
        if png.stem.startswith("s2_"):  # photo-like satellite images: a palette keeps them sharp at ~1/4 of the size
            im = im.convert("RGBA").quantize(256, method=Image.Quantize.FASTOCTREE)
        im.save(out / "overlays" / png.name, optimize=True)

    counts = _slim_vectors(src, out, area)
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"example {run_id} -> {out} ({size / 1e6:.1f} MB)")
    for rel, n in counts.items():
        print(f"  {rel}: {n}")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("run_dir", type=Path)
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--run-id", help="id shown in History (default: example_<source run id>)")
    a = p.parse_args()
    build(a.run_dir, a.out, a.run_id)


if __name__ == "__main__":
    main()
