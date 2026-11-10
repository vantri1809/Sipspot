#!/usr/bin/env python3
"""Extract SipSpot drinking-water points from an OSM PBF (e.g. a Geofabrik extract).

Output is purely OSM-derived and uses the same feature schema as fetch_points.py.
Do not merge the result with data/partners.geojson.

Read a Geofabrik OSM PBF and write data/overpass-cache/pbf-<name>.json.
Then run build_points.py (or fetch_points.py --cache-only) to publish.
Needs the project .venv (pyosmium): .venv/bin/python scripts/extract_from_pbf.py <file.pbf>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import osmium

from fetch_points import in_uk, to_feature  # noqa: E402
from water_attributes import is_excluded_osm  # noqa: E402


def matches(tags: dict) -> bool:
    if tags.get("amenity") == "drinking_water":
        return True
    if tags.get("drinking_water:refill") == "yes":
        return True
    if tags.get("amenity") == "water_point":
        return True
    if tags.get("man_made") == "water_tap" and tags.get("drinking_water") == "yes":
        return True
    return False


def tags_dict(obj) -> dict:
    return {t.k: t.v for t in obj.tags}


def meta(obj, typ: str) -> dict:
    ts = obj.timestamp
    timestamp = ts.strftime("%Y-%m-%dT%H:%M:%SZ") if ts is not None else None
    return {
        "type": typ,
        "id": int(obj.id),
        "tags": tags_dict(obj),
        "timestamp": timestamp,
        "version": int(obj.version) if obj.version else None,
        "changeset": int(obj.changeset) if obj.changeset else None,
    }


def way_center(w) -> tuple[float, float] | None:
    lats, lons = [], []
    for n in w.nodes:
        if not n.location.valid():
            continue
        lats.append(n.location.lat)
        lons.append(n.location.lon)
    if not lats:
        return None
    return sum(lats) / len(lats), sum(lons) / len(lons)


class Extractor(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.elements = []
        self.seen = 0

    def node(self, n):
        tags = tags_dict(n)
        if not matches(tags):
            return
        if not n.location.valid():
            return
        el = meta(n, "node")
        el["lat"] = n.location.lat
        el["lon"] = n.location.lon
        self.elements.append(el)
        self.seen += 1

    def way(self, w):
        tags = tags_dict(w)
        if not matches(tags):
            return
        center = way_center(w)
        if not center:
            return
        el = meta(w, "way")
        el["center"] = {"lat": center[0], "lon": center[1]}
        self.elements.append(el)
        self.seen += 1


def extract(pbf_path: Path) -> list[dict]:
    handler = Extractor()
    handler.apply_file(str(pbf_path), locations=True, idx="flex_mem")
    print(f"{pbf_path.name}: {handler.seen} matching elements", flush=True)
    return handler.elements


def main(paths: list[str]) -> int:
    elements = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            print(f"Missing {path}", file=sys.stderr)
            return 1
        elements.extend(extract(path))
    stems = "-".join(Path(raw).stem.replace("-latest", "").replace(".osm", "") for raw in paths)
    out = Path(__file__).resolve().parents[1] / "data" / "overpass-cache" / f"pbf-{stems}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"elements": elements, "source": "geofabrik-pbf"}), encoding="utf-8")
    print(f"Wrote {len(elements)} raw elements to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
