"""Download the Copernicus EMS Rapid Mapping products of one activation (default EMSR927).

VALIDATION ONLY. EMS maps are reference data for checking finished results; they must never be
used as input, for training or for tuning thresholds (hackathon data rules). Nothing in
`src/povodne/` may read the files this script writes.

Usage:  python validation/fetch_ems.py [--code EMSR927] [--out validation/data]

Writes  <out>/<code>/<AOIxx>_<PRODUCT>_v<N>/  (extracted vector package, EPSG:4326)
        <out>/<code>/activation.json          (raw activation metadata from the EMS API)
        <out>/<code>/inventory.json           (which products exist, image dates, delivery time)
Source: European Union, Copernicus Emergency Management Service data.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

import requests

API = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/"


def fetch_activation(code: str) -> dict:
    r = requests.get(API, params={"code": code}, timeout=60)
    r.raise_for_status()
    res = r.json().get("results") or []
    if not res:
        raise SystemExit(f"activation {code} not found")
    return res[0]


def product_dirname(p: dict) -> str:
    # e.g. AOI03_GRA_MONIT01_v1 — taken from the download file name
    name = p["downloadPath"].rsplit("/", 1)[-1].removesuffix(".zip")
    return name.split("_", 1)[1]  # strip "EMSR927_"


def inventory(act: dict) -> list[dict]:
    rows = []
    for aoi in act.get("aois", []):
        for p in aoi.get("products", []):
            v = p.get("version") or {}
            rows.append({
                "aoi": aoi["number"], "aoi_name": aoi["name"], "type": p.get("type"),
                "monitoring": p.get("monitoringNumber", 0), "version": v.get("number"),
                "delivered": v.get("statusCode") == "F", "delivery_time": v.get("deliveryTime"),
                "note": v.get("reason") or "",
                "images": [{"sensor": i.get("sensorName"), "time": i.get("acquisitionTime")}
                           for i in p.get("images", [])],
                "download": p.get("downloadPath") or None,
                "dir": product_dirname(p) if p.get("downloadPath") else None,
            })
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--code", default="EMSR927")
    ap.add_argument("--out", default=str(Path(__file__).parent / "data"))
    a = ap.parse_args(argv)
    root = Path(a.out) / a.code
    root.mkdir(parents=True, exist_ok=True)
    act = fetch_activation(a.code)
    (root / "activation.json").write_text(json.dumps(act, indent=1))
    inv = inventory(act)
    for row in inv:
        if not row["delivered"] or not row["download"]:
            print(f"AOI{row['aoi']:02d} {row['aoi_name']}: not delivered ({row['note']})")
            continue
        d = root / row["dir"]
        if d.exists() and any(d.glob("*.shp")):
            print(f"{row['dir']}: already downloaded")
            continue
        print(f"{row['dir']}: downloading …", flush=True)
        r = requests.get(row["download"], timeout=600)  # redirects to S3
        r.raise_for_status()
        d.mkdir(exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for m in z.infolist():
                # only vector layers + metadata; skip big rasters, never write outside d
                fn = Path(m.filename).name
                if fn and Path(fn).suffix.lower() in {".shp", ".shx", ".dbf", ".prj", ".cpg", ".json", ".xml"}:
                    (d / fn).write_bytes(z.read(m))
    (root / "inventory.json").write_text(json.dumps(inv, indent=1))
    print(f"inventory: {root / 'inventory.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
